"""Cuencas de aportacion de Civil 3D: listar, crear desde contorno y superficie, parametros hidrologicos y estructura de descarga.

Modulo nativo Cdcrd.Cuencas.V1 (comando CDCRDCUENCASV1) con el mismo transporte
de solicitud y recibo que los demas modulos. Solicitudes y recibos viven en
%LOCALAPPDATA%/CdcrdCivil3dBridge/cuencas, no junto al dibujo.

Ningun coeficiente se supone: coeficiente de escorrentia, tc_min, numero de curva
y trayectoria de flujo entran como parametros; lo que no se indica queda como
lo dejo Civil y la respuesta lo lista en parametros_de_civil. El area, el
perimetro y la longitud de flujo son resultados de la geometria, no entradas.
"""
import math
import ntpath
import os
import re
from pathlib import Path

import puente_cliente as bridge
import transporte
from transporte import ReciboError

MODULE = "cdcrd-cuencas"
COMMAND = "CDCRDCUENCASV1"
VERSION_MINIMA = "0.2.0"
ACCIONES = ("listar", "crear", "actualizar")
METODOS_TC = ("TR55", "usuario", "Kirpich", "FAA")
PARAMETROS = ("coeficiente_escorrentia", "tc_min", "metodo_tc", "trayectoria", "estructura", "numero_curva")
MAX_VERTICES = 2000


def carpeta_intercambio():
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("LOCALAPPDATA no esta definido")
    return Path(base) / "CdcrdCivil3dBridge" / "cuencas"


def _texto(value, key, max_len=200):
    if not isinstance(value, str) or not value.strip() or len(value) > max_len or any(ord(c) < 32 for c in value):
        raise ValueError("Texto requerido: " + key)
    return value


def _numero(value, key, lo, hi):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
        raise ValueError(f"{key} debe ser un numero entre {lo} y {hi}")
    return value


def _puntos(value, key, minimo, con_z=False):
    if not isinstance(value, list) or not minimo <= len(value) <= MAX_VERTICES:
        raise ValueError(f"{key}: lista de {minimo}..{MAX_VERTICES} puntos")
    out = []
    for p in value:
        if not isinstance(p, (list, tuple)) or len(p) not in ((2, 3) if con_z else (2,)):
            raise ValueError("Cada punto de " + key + (" es [x, y] o [x, y, z]" if con_z else " es [x, y]"))
        out.append([_numero(v, key, -1e8, 1e8) for v in p])
    return out


def validar_parametros(datos):
    """Solo las claves presentes; un tc_min explicito (minutos) es siempre un valor de usuario."""
    out = {}
    if datos.get("coeficiente_escorrentia") is not None:
        out["coeficiente_escorrentia"] = _numero(datos["coeficiente_escorrentia"], "coeficiente_escorrentia", 0, 1)
    if datos.get("numero_curva") is not None:
        cn = _numero(datos["numero_curva"], "numero_curva", 1, 100)
        if cn != int(cn):
            raise ValueError("numero_curva debe ser entero")
        out["numero_curva"] = int(cn)
    if datos.get("metodo_tc"):
        if datos["metodo_tc"] not in METODOS_TC:
            raise ValueError("metodo_tc admite " + ", ".join(METODOS_TC))
        out["metodo_tc"] = datos["metodo_tc"]
    if datos.get("tc_min") is not None:
        if out.get("metodo_tc", "usuario") != "usuario":
            raise ValueError("tc_min explicito solo es compatible con metodo_tc=usuario")
        out["tc_min"] = _numero(datos["tc_min"], "tc_min", 0, 14400)
    if datos.get("trayectoria") is not None:
        out["trayectoria"] = _puntos(datos["trayectoria"], "trayectoria", 2, con_z=True)
    if datos.get("estructura"):
        out["estructura"] = _texto(datos["estructura"], "estructura")
    return out


def validar_creacion(datos):
    contorno, polilinea = datos.get("contorno"), datos.get("polilinea")
    if (contorno is None) == (polilinea is None):
        raise ValueError("Indique contorno (vertices) o polilinea (handle), uno solo")
    out = dict(nombre=_texto(datos.get("nombre"), "nombre"), grupo=_texto(datos.get("grupo"), "grupo"), superficie=_texto(datos.get("superficie"), "superficie"))
    if contorno is not None:
        out["contorno"] = _puntos(contorno, "contorno", 3)
    else:
        if not isinstance(polilinea, str) or not re.fullmatch(r"[0-9A-Fa-f]{1,16}", polilinea):
            raise ValueError("polilinea debe ser un handle hexadecimal")
        out["polilinea"] = polilinea.upper()
    if datos.get("estilo"):
        out["estilo"] = _texto(datos["estilo"], "estilo")
    out.update(validar_parametros(datos))
    return out


def validar_actualizacion(datos):
    out = dict(cuenca=_texto(datos.get("cuenca"), "cuenca"))
    cambios = validar_parametros(datos)
    if datos.get("superficie"):
        cambios["superficie"] = _texto(datos["superficie"], "superficie")
    if not cambios:
        raise ValueError("Nada que actualizar: indique " + ", ".join(PARAMETROS + ("superficie",)))
    out.update(cambios)
    return out


def ejecutar(dibujo, pid, *, accion, simular=True, timeout=180, **datos):
    if not isinstance(dibujo, str) or not ntpath.isabs(dibujo):
        raise ValueError("Ruta DWG absoluta requerida")
    if accion not in ACCIONES or not isinstance(simular, bool):
        raise ValueError("Accion o simulacion invalida")
    if accion == "listar":
        datos = dict(cuenca=_texto(datos["cuenca"], "cuenca")) if datos.get("cuenca") else {}
    elif accion == "crear":
        datos = validar_creacion(datos)
    else:
        datos = validar_actualizacion(datos)
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or ntpath.normcase(info["dibujo"]) != ntpath.normcase(dibujo) or info["insunits"] != 6:
        raise ValueError("Documento Civil o unidades distintos a lo esperado")
    transporte.exigir_puente_libre()
    carpeta = carpeta_intercambio()
    carpeta.mkdir(parents=True, exist_ok=True)
    transporte.exigir_version(MODULE, COMMAND, carpeta, pid, VERSION_MINIMA)
    return transporte.despachar(MODULE, COMMAND, carpeta, pid, dict(datos, dibujo=dibujo, accion=accion, simular=simular), timeout)


def registrar(mcp, ok):
    import json

    def call(dibujo, pid, **kwargs):
        try:
            return ok(ejecutar(dibujo, pid, **kwargs))
        except ReciboError as exc:
            return ok({"error": str(exc), "receipt": exc.receipt})
        except (ValueError, TypeError, KeyError, OSError, RuntimeError) as exc:
            return ok({"error": str(exc)})

    def opcionales(coeficiente_escorrentia, tc_min, metodo_tc, trayectoria, estructura, numero_curva):
        """Los numericos negativos y los textos vacios significan 'no indicado'."""
        return dict(coeficiente_escorrentia=coeficiente_escorrentia if coeficiente_escorrentia >= 0 else None, tc_min=tc_min if tc_min >= 0 else None,
                    metodo_tc=metodo_tc or None, trayectoria=json.loads(trayectoria) if trayectoria else None, estructura=estructura or None,
                    numero_curva=numero_curva if numero_curva > 0 else None)

    @mcp.tool()
    def listar_cuencas(dibujo: str, pid: int, cuenca: str = "") -> str:
        """Lista las cuencas de aportacion del dibujo (o una, por nombre o handle) con sus parametros hidrologicos.

        De cada una: grupo, area (m2 y ha), perimetro, superficie de referencia,
        coeficiente de escorrentia y metodo, tc y metodo de tc, longitud de
        flujo, pendiente media, punto de descarga y punto mas distante, numero
        de curva, red y estructura de descarga y los segmentos de la
        trayectoria de flujo. tc_min en minutos (la API guarda horas: tc_h).
        Lectura sin cambios.
        """
        return call(dibujo, pid, accion="listar", cuenca=cuenca or None)

    @mcp.tool()
    def crear_cuenca(dibujo: str, pid: int, nombre: str, grupo: str, superficie: str, contorno: str = "", polilinea: str = "",
                     coeficiente_escorrentia: float = -1.0, tc_min: float = -1.0, metodo_tc: str = "", trayectoria: str = "", estructura: str = "",
                     numero_curva: int = 0, estilo: str = "", simular: bool = True, confirmar: bool = False) -> str:
        """Crea una cuenca de aportacion (Catchment) desde un contorno y una superficie.

        contorno JSON [[x, y], ...] o polilinea (handle de una polilinea ligera
        o 3D cerrada y sin arcos; solo planta). grupo se crea si no existe.
        Parametros opcionales, ninguno supuesto: coeficiente_escorrentia (0..1),
        tc_min (minutos; fija el metodo de usuario),
        metodo_tc (TR55, usuario, Kirpich, FAA), trayectoria JSON
        [[x, y] o [x, y, z], ...] del punto mas distante a la descarga,
        estructura (handle, nombre o red/estructura de una red de gravedad) y
        numero_curva. Verifica que el area de la cuenca sea la del contorno y
        relee cada parametro pedido; si algo no coincide no guarda nada. La
        respuesta lista en parametros_de_civil lo que quedo con el valor que
        asigno Civil. Simula por defecto (crea, verifica y aborta).
        """
        if not confirmar:
            return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        if bool(contorno) == bool(polilinea):
            return ok({"error": "Indique contorno o polilinea, uno solo"})
        try:
            extra = opcionales(coeficiente_escorrentia, tc_min, metodo_tc, trayectoria, estructura, numero_curva)
            pts = json.loads(contorno) if contorno else None
        except ValueError as exc:
            return ok({"error": str(exc)})
        return call(dibujo, pid, accion="crear", simular=simular, nombre=nombre, grupo=grupo, superficie=superficie, contorno=pts,
                    polilinea=polilinea or None, estilo=estilo or None, **extra)

    @mcp.tool()
    def actualizar_cuenca(dibujo: str, pid: int, cuenca: str, coeficiente_escorrentia: float = -1.0, tc_min: float = -1.0, metodo_tc: str = "",
                          trayectoria: str = "", estructura: str = "", numero_curva: int = 0, superficie: str = "",
                          simular: bool = True, confirmar: bool = False) -> str:
        """Escribe parametros hidrologicos de una cuenca existente y la asocia a una estructura de red de gravedad.

        Solo cambia lo indicado (mismos parametros que crear_cuenca, mas
        superficie). Devuelve la lectura de antes y de despues; relee cada
        valor y, si no coincide con lo pedido, no guarda nada. Simula por
        defecto.
        """
        if not confirmar:
            return ok({"error": "Operacion de escritura: requiere confirmar=True"})
        try:
            extra = opcionales(coeficiente_escorrentia, tc_min, metodo_tc, trayectoria, estructura, numero_curva)
        except ValueError as exc:
            return ok({"error": str(exc)})
        return call(dibujo, pid, accion="actualizar", simular=simular, cuenca=cuenca, superficie=superficie or None, **extra)
