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
    destino = os.path.normcase(os.path.abspath(ruta))
    for raiz in raices:
        base = os.path.normcase(os.path.abspath(os.path.expandvars(raiz)))
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

    # ---------- modelo ----------
    def tekla_estado(self) -> dict:
        """Modelo abierto en Tekla Structures: nombre, ruta, versión y número de piezas."""
        return self._llamar('estado')

    def tekla_crear_modelo(self, carpeta: str, nombre: str, aceptar_licencia_educativa: bool = False) -> dict:
        """Crea un modelo monousuario nuevo en `carpeta`\\`nombre` y lo deja abierto.

        La carpeta debe estar dentro de las rutas permitidas. Requiere Tekla abierto
        con algún modelo cargado (Open API no arranca el programa). Con licencia educativa Tekla pregunta
        antes de guardar; ceptar_licencia_educativa=True responde «Yes» a ese aviso concreto."""
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
                for d in captura.dialogos():
                    if 'educational license' in d['texto'].lower() and 'Yes' in d['botones']:
                        logger.info("Aviso de licencia educativa aceptado por indicación del usuario.")
                        captura.pulsar_boton(d['ventana'], 'Yes')
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
        longitud en mm y peso en kg; además cuenta grupos de tornillos y soldaduras."""
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
        """Genera un informe de los objetos indicados con una plantilla del entorno (p. ej. "P_Part_List")."""
        return self._llamar('informe', ids=[int(i) for i in ids], plantilla=plantilla, archivo=archivo, titulo=titulo)
