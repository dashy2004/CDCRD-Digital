# Tekla MCP
# Capa Python sobre el puente de consola TeklaPuente.exe (Tekla Open API).
# Cada herramienta arma un comando JSON, lo pasa al puente por stdin y
# devuelve la respuesta. Las operaciones que escriben exigen que el modelo
# abierto esté dentro de una carpeta permitida.

import json
import logging
import os
import shutil
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger('tekla_mcp_server')

TIEMPO_MAXIMO_S = 120
ESCRITURAS = frozenset({
    'guardar', 'definir_ejes', 'crear_piezas', 'crear_placa',
    'crear_tornillos', 'crear_soldadura', 'borrar', 'informe',
    'ajustar_extremo', 'cortar_plano', 'cortar_con_pieza', 'despuntar',
    'componente', 'detalle', 'crear_plano', 'numerar',
})
CATALOGOS = ('profdb.bin', 'matdb.bin', 'screwdb.db', 'assdb.db')
Punto = list[float]


class ErrorTekla(RuntimeError):
    """El puente respondió con error o no pudo ejecutarse."""


def _ejecutar_puente(exe: str, comando: dict) -> dict:
    if not os.path.isfile(exe):
        raise ErrorTekla(f"No existe el puente compilado: {exe}. Ejecute puente\\compilar.ps1.")
    try:
        r = subprocess.run([exe], input=json.dumps(comando).encode('utf-8'),
                           capture_output=True, timeout=TIEMPO_MAXIMO_S, check=False)
    except subprocess.TimeoutExpired as e:
        raise ErrorTekla(f"Tekla no respondió en {TIEMPO_MAXIMO_S} s. {_aviso_dialogos()}") from e
    texto = r.stdout.decode('utf-8', errors='replace').strip()
    if not texto:
        raise ErrorTekla("El puente no devolvió nada. " + r.stderr.decode('utf-8', errors='replace')[:400])
    try:
        return json.loads(texto)
    except json.JSONDecodeError as e:
        raise ErrorTekla(f"Respuesta no válida del puente: {texto[:300]}") from e


def _aviso_dialogos() -> str:
    try:
        import captura
        abiertos = captura.dialogos()
    except Exception as e:  # la detección es una ayuda; no debe tapar el error original
        logger.warning("No se pudieron listar los diálogos de Tekla: %s", e)
        return "No se pudo comprobar si hay un diálogo abierto."
    if not abiertos:
        return "No se detectó ningún diálogo abierto."
    return "Diálogo abierto en Tekla: " + " | ".join(
        f"«{d['texto']}» [{', '.join(d['botones'])}]" for d in abiertos) + ". Use tekla_dialogos y tekla_responder_dialogo."


def _dentro_de(ruta: str, raices: list[str]) -> bool:
    # realpath: una unión o enlace dentro de una carpeta permitida no abre la puerta a otra.
    destino = os.path.normcase(os.path.realpath(ruta))
    for raiz in raices:
        if not raiz.strip():
            continue
        base = os.path.normcase(os.path.realpath(os.path.expandvars(raiz)))
        if destino == base or destino.startswith(base.rstrip('\\/') + os.sep):
            return True
    return False


def _punto(p, nombre: str) -> Punto:
    if not isinstance(p, (list, tuple)) or len(p) != 3:
        raise ValueError(f"'{nombre}' debe ser [x, y, z] en mm.")
    return [float(v) for v in p]


class Tekla:
    def __init__(self, exe_puente: str, rutas_permitidas: list[str],
                 ejecutar: Optional[Callable[[str, dict], dict]] = None):
        self._exe = exe_puente
        self._rutas = list(rutas_permitidas)
        self._ejecutar = ejecutar or _ejecutar_puente

    # ---------- núcleo ----------
    def _llamar(self, op: str, **args) -> dict:
        if op in ESCRITURAS:
            self._exigir_ruta_permitida()
        resp = self._ejecutar(self._exe, {'op': op, **args})
        if not resp.get('ok'):
            raise ErrorTekla(resp.get('error', 'Error desconocido del puente.'))
        return resp.get('datos')

    def _exigir_ruta_permitida(self, ruta: Optional[str] = None) -> None:
        if ruta is None:
            estado = self._ejecutar(self._exe, {'op': 'estado'})
            if not estado.get('ok'):
                raise ErrorTekla(estado.get('error', 'Tekla no responde.'))
            ruta = estado['datos']['ruta']
        if not _dentro_de(ruta, self._rutas):
            raise ErrorTekla(
                f"El modelo '{ruta}' está fuera de las carpetas permitidas para escribir "
                f"({'; '.join(self._rutas) or 'ninguna configurada'}). Añada la carpeta en "
                "config.json → tekla.rutas_permitidas o en la variable TEKLA_MCP_RUTAS.")

    def exigir_archivo_permitido(self, archivo: str) -> None:
        """Rechaza un archivo de salida (informe, captura) fuera de las carpetas permitidas."""
        if not _dentro_de(archivo, self._rutas):
            raise ErrorTekla(
                f"'{archivo}' está fuera de las carpetas permitidas para escribir "
                f"({'; '.join(self._rutas) or 'ninguna configurada'}).")

    # ---------- modelo ----------
    def tekla_estado(self) -> dict:
        """Modelo abierto en Tekla Structures: nombre, ruta, versión y número de piezas."""
        return self._llamar('estado')

    def tekla_crear_modelo(self, carpeta: str, nombre: str, aceptar_licencia_educativa: bool = False) -> dict:
        """Crea un modelo monousuario nuevo en `carpeta`\\`nombre` y lo deja abierto.

        La carpeta debe estar dentro de las rutas permitidas. Requiere Tekla abierto
        con algún modelo cargado (Open API no arranca el programa). Con licencia educativa Tekla pregunta
        antes de guardar; aceptar_licencia_educativa=True responde «Yes» a ese aviso concreto."""
        self._exigir_ruta_permitida(os.path.join(carpeta, nombre))
        Path(carpeta).mkdir(parents=True, exist_ok=True)
        return self._llamar_atendiendo_dialogo('crear_modelo', aceptar_licencia_educativa,
                                               carpeta=carpeta, nombre=nombre)

    def _llamar_atendiendo_dialogo(self, op: str, aceptar_licencia_educativa: bool, **args):
        """Ejecuta `op` y, si se autorizó, responde «Yes» al aviso de licencia educativa que
        Tekla muestra al guardar un modelo nuevo y que deja a Open API esperando."""
        if not aceptar_licencia_educativa:
            return self._llamar(op, **args)
        import captura
        with ThreadPoolExecutor(max_workers=1) as hilo:
            futuro = hilo.submit(self._llamar, op, **args)
            limite = time.monotonic() + TIEMPO_MAXIMO_S
            while not futuro.done() and time.monotonic() < limite:
                time.sleep(1.0)
                try:
                    for d in captura.dialogos():
                        if 'educational license' in d['texto'].lower() and 'Yes' in d['botones']:
                            logger.info("Aviso de licencia educativa aceptado por indicación del usuario.")
                            captura.pulsar_boton(d['ventana'], 'Yes')
                except Exception as e:  # un fallo al mirar los diálogos no debe tapar el resultado del puente
                    logger.warning("No se pudieron atender los diálogos de Tekla: %s", e)
            return futuro.result()

    def tekla_copiar_catalogos(self, carpeta_origen: str) -> dict:
        """Copia al modelo abierto los catálogos de perfiles, materiales y tornillos
        (profdb.bin, matdb.bin, screwdb.db, assdb.db) desde una carpeta de entorno y lo reabre.

        Sin screwdb.db y assdb.db, un grupo de tornillos se crea vacío. Sobrescribe los catálogos
        que el modelo ya tenga; los cambios sin guardar del modelo se pierden al reabrir."""
        if not os.path.isdir(carpeta_origen):
            raise ValueError(f"No existe la carpeta de catálogos: {carpeta_origen}")
        ruta = self._llamar('estado')['ruta']
        self._exigir_ruta_permitida(ruta)
        copiados = []
        for nombre in CATALOGOS:
            origen = os.path.join(carpeta_origen, nombre)
            if os.path.isfile(origen):
                shutil.copyfile(origen, os.path.join(ruta, nombre))
                copiados.append(nombre)
        if not copiados:
            raise ValueError(f"En {carpeta_origen} no hay ninguno de: {', '.join(CATALOGOS)}.")
        return {'copiados': copiados, 'reabierto': self._llamar('abrir_modelo', ruta=ruta)}

    def tekla_abrir_modelo(self, ruta: str) -> bool:
        """Abre la carpeta de modelo indicada. Descarta cambios sin guardar del modelo actual."""
        return self._llamar('abrir_modelo', ruta=ruta)

    def tekla_guardar(self, comentario: str = 'Servidor MCP') -> bool:
        """Guarda el modelo abierto."""
        return self._llamar('guardar', comentario=comentario)

    # ---------- geometría ----------
    def tekla_definir_ejes(self, x: str, y: str, z: str, rotulos_x: str = '', rotulos_y: str = '',
                           rotulos_z: str = '', origen: Optional[Punto] = None) -> dict:
        """Crea o modifica la cuadrícula rectangular.

        `x` e `y` son separaciones acumulativas en mm separadas por espacios ("0 9500 10000");
        `z` son cotas absolutas. Los rótulos se emparejan en orden ("C D E")."""
        args = dict(x=x, y=y, z=z, rotulos_x=rotulos_x, rotulos_y=rotulos_y, rotulos_z=rotulos_z)
        if origen is not None:
            args['origen'] = _punto(origen, 'origen')
        return self._llamar('definir_ejes', **args)

    def tekla_crear_piezas(self, piezas: list[dict]) -> list:
        """Crea vigas y columnas en un solo lote.

        Cada pieza: {"tipo": "viga"|"columna", "nombre", "perfil" ("W21X44"), "material" ("A992"),
        "inicio": [x,y,z], "fin": [x,y,z], "clase", "plano" (LEFT|MIDDLE|RIGHT),
        "rotacion" (FRONT|TOP|BACK|BELOW), "profundidad" (MIDDLE|FRONT|BEHIND)}. Unidades mm."""
        if not piezas:
            raise ValueError("La lista de piezas está vacía.")
        limpias = []
        for i, p in enumerate(piezas):
            for k in ('perfil', 'material', 'inicio', 'fin'):
                if k not in p:
                    raise ValueError(f"A la pieza {i} le falta '{k}'.")
            limpias.append({**p, 'inicio': _punto(p['inicio'], 'inicio'), 'fin': _punto(p['fin'], 'fin')})
        return self._llamar('crear_piezas', piezas=limpias)

    def tekla_crear_placa(self, contorno: list[Punto], perfil: str, material: str, nombre: str = 'PLACA',
                          clase: str = '99', profundidad: str = 'MIDDLE') -> dict:
        """Crea una placa de contorno. `perfil` es el espesor ("PL6.35"); `contorno`, tres o más puntos en mm."""
        if len(contorno) < 3:
            raise ValueError("El contorno necesita al menos tres puntos.")
        return self._llamar('crear_placa', contorno=[_punto(p, 'contorno') for p in contorno], perfil=perfil,
                            material=material, nombre=nombre, clase=clase, profundidad=profundidad)

    def tekla_crear_tornillos(self, id_pieza_principal: int, id_pieza_atornillada: int, inicio: Punto, fin: Punto,
                              norma: str, diametro: float, separaciones_x: list[float], separaciones_y: list[float],
                              holgura: float = 2.0, montaje: str = 'obra', rotacion: str = 'FRONT',
                              desfase_inicio: float = 0.0, longitud_corte: float = 100.0) -> dict:
        """Crea un grupo de tornillos en matriz entre dos piezas.

        `inicio`→`fin` define el eje X del grupo; `separaciones_x` son distancias entre filas a lo largo
        de ese eje y `separaciones_y` las transversales (un 0 = una sola línea). `norma` y `diametro` (mm)
        deben existir en el catálogo de tornillos del modelo. Devuelve las posiciones creadas."""
        return self._llamar('crear_tornillos', pieza_principal=int(id_pieza_principal),
                            pieza_atornillada=int(id_pieza_atornillada), inicio=_punto(inicio, 'inicio'),
                            fin=_punto(fin, 'fin'), norma=norma, diametro=float(diametro),
                            separaciones_x=[float(v) for v in separaciones_x],
                            separaciones_y=[float(v) for v in separaciones_y], holgura=float(holgura),
                            montaje=montaje, rotacion=rotacion, desfase_inicio=float(desfase_inicio),
                            longitud_corte=float(longitud_corte))

    def tekla_crear_soldadura(self, id_pieza_principal: int, id_pieza_secundaria: int, tamano: float,
                              tamano_inferior: Optional[float] = None, montaje: str = 'taller') -> dict:
        """Crea una soldadura de filete entre dos piezas que se tocan. Tamaños en mm."""
        args = dict(pieza_principal=int(id_pieza_principal), pieza_secundaria=int(id_pieza_secundaria),
                    tamano=float(tamano), montaje=montaje)
        if tamano_inferior is not None:
            args['tamano_inferior'] = float(tamano_inferior)
        return self._llamar('crear_soldadura', **args)

    # ---------- consulta ----------
    def tekla_listar_piezas(self, nombre: str = '') -> dict:
        """Lista piezas (filtro opcional por nombre) con perfil, material, extremos, caja del sólido,
        longitud en mm y peso en kg; además los grupos de tornillos, soldaduras y componentes con su id."""
        return self._llamar('listar', nombre=nombre)

    def tekla_borrar(self, ids: list[int]) -> list:
        """Borra del modelo los objetos con esos ids. No se puede deshacer desde el servidor."""
        if not ids:
            raise ValueError("Indique al menos un id.")
        return self._llamar('borrar', ids=[int(i) for i in ids])

    # ---------- vista e informes ----------
    def tekla_seleccionar(self, ids: list[int]) -> bool:
        """Selecciona objetos en la interfaz (el panel de propiedades los muestra)."""
        return self._llamar('seleccionar', ids=[int(i) for i in ids])

    def tekla_ajustar_vista(self, minimo: Punto, maximo: Punto, ajustar_area: bool = True) -> dict:
        """Ajusta el área de trabajo de las vistas visibles a la caja [minimo, maximo] y hace zoom."""
        return self._llamar('vista', min=_punto(minimo, 'minimo'), max=_punto(maximo, 'maximo'),
                            ajustar_area='true' if ajustar_area else 'false')

    def tekla_crear_informe(self, ids: list[int], plantilla: str, archivo: str, titulo: str = '') -> bool:
        """Genera un informe de los objetos indicados con una plantilla del entorno (p. ej. "P_Part_List").

        `archivo` relativo se guarda en la carpeta del modelo; una ruta absoluta debe estar dentro de
        las carpetas permitidas."""
        ruta_modelo = self._llamar('estado')['ruta']
        self.exigir_archivo_permitido(os.path.join(ruta_modelo, archivo))
        return self._llamar('informe', ids=[int(i) for i in ids], plantilla=plantilla, archivo=archivo, titulo=titulo)

    # ---------- cortes ----------
    def tekla_ajustar_extremo(self, id_pieza: int, origen: Punto, eje_x: Punto, eje_y: Punto) -> dict:
        """Ajusta el extremo de una pieza a un plano (alarga o recorta el extremo más cercano).

        El plano pasa por `origen` y contiene los vectores `eje_x` y `eje_y`. Unidades mm."""
        return self._llamar('ajustar_extremo', **self._plano(id_pieza, origen, eje_x, eje_y))

    def tekla_cortar_plano(self, id_pieza: int, origen: Punto, eje_x: Punto, eje_y: Punto) -> dict:
        """Corta una pieza por un plano. Se elimina el lado hacia el que apunta la normal
        `eje_x` × `eje_y`; para quitar el otro lado, intercambie los dos ejes."""
        return self._llamar('cortar_plano', **self._plano(id_pieza, origen, eje_x, eje_y))

    @staticmethod
    def _plano(id_pieza: int, origen: Punto, eje_x: Punto, eje_y: Punto) -> dict:
        return dict(pieza=int(id_pieza), origen=_punto(origen, 'origen'),
                    eje_x=_punto(eje_x, 'eje_x'), eje_y=_punto(eje_y, 'eje_y'))

    def tekla_despuntar(self, id_pieza: int, minimo: Punto, maximo: Punto) -> dict:
        """Despunte rectangular: resta a la pieza la caja [minimo, maximo], alineada con los ejes globales.

        Para despuntar una secundaria contra una viga principal, la caja cubre el ala de la principal
        más la holgura (p. ej. 13 mm) y atraviesa todo el ancho de la secundaria."""
        a, b = _punto(minimo, 'minimo'), _punto(maximo, 'maximo')
        if any(hi <= lo for lo, hi in zip(a, b)):
            raise ValueError("La caja del despunte necesita maximo > minimo en los tres ejes.")
        return self._llamar('despuntar', pieza=int(id_pieza), min=a, max=b)

    def tekla_cortar_con_pieza(self, id_pieza: int, id_pieza_cortante: int) -> dict:
        """Resta a `id_pieza` el volumen de otra pieza. La pieza cortante se elimina del modelo."""
        if int(id_pieza) == int(id_pieza_cortante):
            raise ValueError("La pieza cortante debe ser distinta de la pieza que se corta.")
        return self._llamar('cortar_con_pieza', pieza=int(id_pieza), pieza_cortante=int(id_pieza_cortante))

    # ---------- componentes del catálogo ----------
    def tekla_crear_componente(self, numero: int, id_pieza_principal: int, ids_piezas_secundarias: list[int],
                               atributos: Optional[dict] = None, archivo_atributos: str = 'standard',
                               nombre: str = '', vector_arriba: Optional[Punto] = None,
                               posicion: str = 'COLLISION_PLANE') -> dict:
        """Inserta una unión del catálogo de componentes entre una pieza principal y sus secundarias
        (p. ej. 144 placa de extremo, 146 placa de cortante, 141 angulares). Los componentes de usuario
        llevan `numero` = -1 y su `nombre`.

        `atributos` son los campos del diálogo del componente por su nombre interno; lo que no se indique
        sale de `archivo_atributos`. Devuelve las piezas, tornillos y soldaduras que generó.
        Use tekla_catalogo_componentes para localizar el número."""
        if not ids_piezas_secundarias:
            raise ValueError("Indique al menos una pieza secundaria.")
        args = dict(numero=int(numero), nombre=nombre, pieza_principal=int(id_pieza_principal),
                    piezas_secundarias=[int(i) for i in ids_piezas_secundarias],
                    archivo_atributos=archivo_atributos, posicion=posicion, atributos=dict(atributos or {}))
        if vector_arriba is not None:
            args['vector_arriba'] = _punto(vector_arriba, 'vector_arriba')
        return self._llamar('componente', **args)

    def tekla_crear_detalle(self, numero: int, id_pieza: int, punto: Punto, atributos: Optional[dict] = None,
                            archivo_atributos: str = 'standard', nombre: str = '',
                            vector_arriba: Optional[Punto] = None, tipo_detalle: str = 'END') -> dict:
        """Inserta un detalle del catálogo sobre una sola pieza en `punto` (p. ej. 1004 placa base con
        anclajes, 1014 placa base rigidizada). `tipo_detalle`: END | INTERMEDIATE | INTERMEDIATE_REVERSE.

        Los anclajes de una placa base salen del propio detalle: diámetro, norma y separaciones van en
        `atributos` o en el archivo de atributos."""
        args = dict(numero=int(numero), nombre=nombre, pieza=int(id_pieza), punto=_punto(punto, 'punto'),
                    archivo_atributos=archivo_atributos, tipo_detalle=tipo_detalle,
                    atributos=dict(atributos or {}))
        if vector_arriba is not None:
            args['vector_arriba'] = _punto(vector_arriba, 'vector_arriba')
        return self._llamar('detalle', **args)

    def tekla_catalogo_componentes(self, filtro: str = '') -> list:
        """Componentes disponibles (número, nombre y título) cuyo título, nombre o número contiene `filtro`."""
        return self._llamar('catalogo_componentes', filtro=filtro)

    def tekla_normas_tornillos(self) -> list:
        """Normas de tornillo del catálogo del modelo abierto con sus diámetros en mm.

        Si solo aparecen UNDEFINED_BOLT y UNDEFINED_STUD, al modelo le falta el catálogo:
        use tekla_copiar_catalogos."""
        return self._llamar('normas_tornillos')

    # ---------- planos ----------
    def tekla_listar_planos(self) -> list:
        """Planos del modelo abierto: tipo, marca, nombre, título y estado de actualización."""
        return self._llamar('planos')

    def tekla_numerar(self) -> dict:
        """Numera todas las piezas y conjuntos del modelo (necesario antes de crear planos).

        Open API no numera: el servidor escribe una macro temporal en la carpeta del modelo, la lanza
        y la borra. Devuelve si la numeración quedó al día."""
        return self._llamar('numerar')

    def tekla_crear_plano(self, id_pieza: int, tipo: str = 'pieza', archivo_atributos: str = 'standard') -> dict:
        """Crea el plano de una pieza (`tipo` = "pieza") o de su conjunto ("conjunto") y lo cierra guardado.

        Requiere la numeración al día: use antes tekla_numerar."""
        if tipo not in ('pieza', 'conjunto'):
            raise ValueError("tipo debe ser 'pieza' o 'conjunto'.")
        return self._llamar('crear_plano', pieza=int(id_pieza), tipo=tipo, archivo_atributos=archivo_atributos)
