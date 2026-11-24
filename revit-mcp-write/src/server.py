# -*- coding: utf-8 -*-
"""revit-write - servidor MCP stdio que traduce herramientas a pyRevit Routes.

Arquitectura:
    cliente MCP  --stdio-->  este proceso  --HTTP-->  pyRevit Routes
                                                     (dentro de Revit.exe)

El puerto NO se asume. pyRevit arranca en el puerto configurado y sube al
siguiente libre si esta ocupado (serverinfo._get_next_available_port), asi que
se descubre por sondeo y se cachea.
"""

import json
import urllib.request
import urllib.error
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

BASE_PORT = 48884
PORT_SCAN = 8          # 48884..48891
TIMEOUT = 120          # las escrituras grandes tardan
API = "revitwrite"

mcp = FastMCP("revit-write")
_port_cache: Optional[int] = None


def _call(path: str, method: str = "GET", payload: Any = None, port: int = None) -> dict:
    url = "http://localhost:%d/%s%s" % (port, API, path)
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        # NO usar application/json: pyRevit 6.5.3 sobre IronPython 3.4 hace
        # json.loads(bytes) en server.py:89 y eso lanza
        # "the JSON object must be str, not 'bytes'" antes de invocar el
        # handler. Con text/plain pyRevit pasa los bytes crudos y el
        # endpoint los decodifica.
        headers["Content-Type"] = "text/plain; charset=utf-8"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"ok": False, "error": "respuesta no-JSON", "raw": raw[:2000]}


def _port() -> int:
    """Descubre el puerto real del servidor de routes."""
    global _port_cache
    if _port_cache is not None:
        try:
            _call("/status", port=_port_cache)
            return _port_cache
        except Exception:
            _port_cache = None

    errors = []
    for p in range(BASE_PORT, BASE_PORT + PORT_SCAN):
        try:
            r = _call("/status", port=p)
            if isinstance(r, dict) and r.get("ok"):
                _port_cache = p
                return p
            errors.append("%d: respuesta inesperada" % p)
        except urllib.error.HTTPError as e:
            errors.append("%d: HTTP %s" % (p, e.code))
        except Exception as e:
            errors.append("%d: %s" % (p, type(e).__name__))
    raise RuntimeError(
        "No hay servidor RevitWrite escuchando en %d-%d. "
        "Verificar: (1) Revit abierto, (2) [routes] enabled=true en "
        "pyRevit_config.ini, (3) Revit reiniciado despues de habilitarlo, "
        "(4) la extension RevitWrite.extension cargo sin error "
        "(revisar _log/revitwrite.log). Sondeo: %s"
        % (BASE_PORT, BASE_PORT + PORT_SCAN - 1, "; ".join(errors))
    )


def _go(path: str, method: str = "GET", payload: Any = None) -> dict:
    try:
        return _call(path, method=method, payload=payload, port=_port())
    except RuntimeError as e:
        return {"ok": False, "error": str(e)}
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:2000]
        return {"ok": False, "error": "HTTP %s desde Revit" % e.code, "detail": detail}
    except Exception as e:
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


# ------------------------------------------------------------------ lectura

@mcp.tool()
def revit_status() -> dict:
    """Estado del documento abierto en Revit y conteos de niveles, columnas y acero.
    Usar primero para confirmar que el puente esta vivo."""
    return _go("/status")


@mcp.tool()
def revit_levels() -> dict:
    """Lista los niveles con su cota en pies y metros, ordenados de abajo hacia arriba."""
    return _go("/levels")


@mcp.tool()
def revit_columns() -> dict:
    """Lista las columnas estructurales con id, familia, tipo, Mark y nivel."""
    return _go("/columns")


@mcp.tool()
def revit_rebar() -> dict:
    """Lista los sets de acero con id, id del anfitrion, Host Mark, tipo de barra,
    forma, cantidad y longitud."""
    return _go("/rebar")


@mcp.tool()
def revit_find(category: str = "OST_StructuralColumns",
               family: str = None,
               type_name: str = None,
               level: str = None) -> dict:
    """Busca instancias filtrando por categoria, familia, tipo y nivel.
    Sirve para armar conjuntos exactos de ids sin adivinar.

    Args:
        category: BuiltInCategory, ej. OST_StructuralColumns, OST_Rebar.
        family: nombre exacto de familia, ej. 'W Shapes-Column'.
        type_name: nombre exacto de tipo, ej. 'C1'.
        level: nombre exacto de nivel, ej. 'Story5'.
    """
    return _go("/find", "POST", {
        "category": category, "family": family,
        "type": type_name, "level": level,
    })


@mcp.tool()
def revit_reflect(type_name: str, member: str = "") -> dict:
    """Vuelca la firma REAL de un tipo de la API de Revit de esta instalacion:
    metodos, estatico o no, tipo de retorno y parametros.

    Usar SIEMPRE antes de escribir codigo contra una parte de la API que no se
    haya usado en este Revit. Volcar antes de suponer.

    Args:
        type_name: ruta bajo Autodesk.Revit.DB, ej. 'Structure.Rebar',
            'ElementTransformUtils', 'Structure.RebarConstraintsManager'.
        member: filtro por substring del nombre, ej. 'host', 'constraint'.
    """
    return _go("/reflect", "POST", {"type_name": type_name, "member": member})


# ---------------------------------------------------------------- escritura

@mcp.tool()
def revit_delete(ids: list[int]) -> dict:
    """Borra elementos por id dentro de una transaccion.

    Devuelve deleted_count, que INCLUYE dependientes borrados en cascada
    (por ejemplo, el acero hospedado en una columna que se borra). Comparar
    ese numero contra len(ids) antes de dar la operacion por entendida.
    """
    return _go("/delete", "POST", {"ids": ids})


@mcp.tool()
def revit_copy(ids: list[int], dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> dict:
    """Copia elementos con una traslacion, en PIES (unidad interna de Revit).

    Copiar juntos un anfitrion y su acero preserva el vinculo de hospedaje,
    que es la via para replicar armado sin crear barras por API.

    Rechaza traslacion nula.
    """
    return _go("/copy", "POST", {"ids": ids, "dx": dx, "dy": dy, "dz": dz})


@mcp.tool()
def revit_set_param(name: str, ids: list[int] = None, value: Any = None,
                    assignments: list[dict] = None) -> dict:
    """Fija un parametro de instancia y RELEE el valor para confirmarlo.

    Dos formas de uso:
      - mismo valor para varios: name + ids + value
      - valor distinto por elemento: name + assignments=[{"id":..,"value":..}]

    La respuesta trae 'verified' con el valor releido de cada elemento y
    'skipped' con el motivo de cada omision.
    """
    payload = {"name": name}
    if assignments:
        payload["assignments"] = assignments
    else:
        payload["ids"] = ids or []
        payload["value"] = value
    return _go("/set_param", "POST", payload)


# ---------------------------------------------------------------------- MEP

def _sin_nulos(**campos) -> dict:
    return {k: v for k, v in campos.items() if v is not None}


@mcp.tool()
def revit_mep_conectores(categorias: list[str] = None, ids: list[int] = None,
                         max_elementos: int = None,
                         documento: str = None) -> dict:
    """Audita conectores MEP. SOLO LECTURA: no abre transacciones.

    Por elemento y en total: conectores, libres (IsConnected=False en
    conectores fisicos), dominio (tuberia/electrico/ducto), clasificacion y
    nombre del sistema, y diametro.

    Unidades: diametro_mm en mm (solo tuberia redonda), radio_interno_pies
    en pies (valor interno), posicion_m en metros.

    Args:
        categorias: BuiltInCategory, ej. ['OST_PlumbingFixtures']. Sin
            categorias ni ids recorre las categorias MEP con conectores.
        ids: ids de elementos (excluyente con categorias).
        max_elementos: tope del detalle por elemento; los totales no se recortan.
        documento: titulo o ruta de un documento YA abierto; por defecto el activo.
    """
    return _go("/mep/conectores", "POST", _sin_nulos(
        categorias=categorias, ids=ids, max_elementos=max_elementos,
        documento=documento))


@mcp.tool()
def revit_mep_conectar(tipo_tuberia: Any, tipo_sistema: Any, pendiente: float,
                       ramal: int = None, ramales: list[int] = None,
                       aparatos: list[int] = None, categoria: str = None,
                       union: str = "te", nivel: Any = None,
                       diametro_mm: float = None, salida_mm: float = None,
                       tramo_minimo_mm: float = None,
                       margen_extremo_mm: float = None,
                       clasificaciones: list[str] = None,
                       revertir_sueltos: bool = True, lote: int = 25,
                       desde: int = 0, confirmar: bool = False,
                       documento: str = None) -> dict:
    """Conecta aparatos sanitarios o rociadores a un ramal y VERIFICA cada
    conector (IsConnected tras Regenerate, dentro de la transaccion).

    ENSAYO POR DEFECTO: con confirmar=False todo se ejecuta, se verifica y
    se confirma dentro de un grupo de transacciones que luego se revierte
    entero; los ids de la respuesta son efimeros. 'ensayo_valido' dice si
    Revit acepto ese Commit y 'errores' trae sus fallos. Solo confirmar=True
    deja el Commit. Nunca guarda el documento. Revisar 'ensayo_valido',
    'sueltos', 'conexiones', 'errores' y 'advertencias' antes de confirmar.
    Con confirmar=True, 'ok' es False si la transaccion no quedo Committed.

    Un lote de aparatos por llamada y una transaccion por lote. Para seguir:
    desde=<siguiente> y ramales=<ramales_siguientes> de la respuesta anterior
    (la te parte el ramal en tramos nuevos).

    Unidades: pendiente en m/m (0.02 = 2 %; 0 para presion); diametro_mm,
    salida_mm, tramo_minimo_mm y margen_extremo_mm en mm; entronque_m y
    posicion_m (salida) en metros.

    Args:
        tipo_tuberia: id o nombre exacto del PipeType.
        tipo_sistema: id o nombre exacto del PipingSystemType.
        pendiente: m/m, de 0 a 0.5. El tramo sube al alejarse del ramal.
        ramal: id de la tuberia destino (o 'ramales').
        ramales: ids candidatos; cada conector usa el tramo mas cercano.
        aparatos: ids de aparatos (o 'categoria').
        categoria: 'OST_PlumbingFixtures' u 'OST_Sprinklers'.
        union: 'te' (BreakCurve + NewTeeFitting) o 'takeoff'.
        nivel: id o nombre; por defecto el nivel de referencia del ramal.
        diametro_mm: diametro de los tramos nuevos; por defecto el del conector.
        salida_mm: tramo recto inicial si el conector no es vertical (300).
        tramo_minimo_mm: tramo mas corto que se intenta construir (50).
        margen_extremo_mm: distancia minima del entronque a un extremo (150).
        clasificaciones: PipeSystemType aceptados en el conector del aparato;
            por defecto la clasificacion del tipo de sistema.
        revertir_sueltos: deshace el trazado de un conector si algo queda suelto.
        lote: aparatos por llamada (1-200). desde: indice inicial.
        confirmar: True hace Commit; False (defecto) es ensayo con RollBack.
        documento: titulo o ruta de un documento YA abierto; por defecto el activo.
    """
    return _go("/mep/conectar", "POST", _sin_nulos(
        tipo_tuberia=tipo_tuberia, tipo_sistema=tipo_sistema,
        pendiente=pendiente, ramal=ramal, ramales=ramales, aparatos=aparatos,
        categoria=categoria, union=union, nivel=nivel, diametro_mm=diametro_mm,
        salida_mm=salida_mm, tramo_minimo_mm=tramo_minimo_mm,
        margen_extremo_mm=margen_extremo_mm, clasificaciones=clasificaciones,
        revertir_sueltos=revertir_sueltos, lote=lote, desde=desde,
        confirmar=confirmar, documento=documento))


@mcp.tool()
def revit_mep_circuitos(tablero: Any, limite_va: float,
                        luminarias: list[int] = None, nivel: Any = None,
                        max_luminarias: int = None, max_circuitos: int = None,
                        lote: int = 25, desde: int = 0,
                        confirmar: bool = False,
                        documento: str = None) -> dict:
    """Agrupa luminarias en circuitos de potencia hacia un tablero
    (ElectricalSystem.Create + SelectPanel) y verifica cada circuito.

    ENSAYO POR DEFECTO: con confirmar=False los circuitos se crean y se leen
    dentro de la transaccion y luego se revierten (RollBack); los ids son
    efimeros. Solo confirmar=True hace Commit. Nunca guarda el documento.

    limite_va es OBLIGATORIO (no hay valor por defecto). La carga de cada
    luminaria se lee del modelo; la que no tiene dato queda en 'sin_circuito'
    con motivo: sin_conector_electrico, ya_en_circuito, sin_carga,
    sin_tension_o_polos, incompatible_con_tablero, excede_limite,
    supera_max_circuitos o error_api.

    Unidades: limite_va y carga_va en VA; tension_v en V.

    Args:
        tablero: id del tablero o nombre exacto del panel.
        limite_va: carga aparente maxima por circuito, en VA.
        luminarias: ids; por defecto todas las de OST_LightingFixtures.
        nivel: id o nombre de nivel para filtrar luminarias.
        max_luminarias: maximo de luminarias por circuito.
        max_circuitos: maximo de circuitos a planear.
        lote: circuitos por llamada (1-200). desde: indice del primer circuito.
        confirmar: True hace Commit; False (defecto) es ensayo con RollBack.
        documento: titulo o ruta de un documento YA abierto; por defecto el activo.
    """
    return _go("/mep/circuitos", "POST", _sin_nulos(
        tablero=tablero, limite_va=limite_va, luminarias=luminarias,
        nivel=nivel, max_luminarias=max_luminarias,
        max_circuitos=max_circuitos, lote=lote, desde=desde,
        confirmar=confirmar, documento=documento))


@mcp.tool()
def revit_mep_tablero(tablero: Any, sistema: str = None, crear: dict = None,
                      confirmar: bool = False, documento: str = None) -> dict:
    """Lee, o crea y asigna, el sistema de distribucion de un tablero electrico.

    Sin 'sistema' ni 'crear' es SOLO LECTURA: devuelve el sistema actual del
    tablero y 'sistemas_disponibles' con sus tensiones. Un tablero sin
    sistema asignado no admite circuitos (revit_mep_circuitos lo exige).

    ENSAYO POR DEFECTO: Revit valida la compatibilidad entre el sistema y el
    tablero al confirmar; el ensayo hace ese Commit dentro de un grupo que
    despues se revierte, y 'ensayo_valido' dice si Revit lo acepto. Un
    sistema incompatible da 'errores' con "Selected distribution system type
    is invalid!", sin dialogo. Solo confirmar=True deja el cambio. Nunca
    guarda el documento.

    Todas las tensiones van en VOLTIOS, tal cual (208, 120). No las convierta
    a unidades internas.

    Args:
        tablero: id del tablero o nombre exacto del panel.
        sistema: nombre de un sistema de distribucion que ya existe.
        crear: definicion de uno nuevo (excluyente con 'sistema'):
            {"nombre", "fase": "monofasico"|"trifasico",
             "configuracion": "estrella"|"delta" (solo trifasico),
             "hilos": 2-4, "linea_linea_v", "linea_tierra_v",
             "tolerancia_pct": 10}. Reutiliza los tipos de tension que ya
            existan con ese valor y crea los que falten con +-tolerancia_pct.
        confirmar: True hace Commit; False (defecto) es ensayo.
        documento: titulo o ruta de un documento YA abierto; por defecto el activo.
    """
    return _go("/mep/tablero", "POST", _sin_nulos(
        tablero=tablero, sistema=sistema, crear=crear, confirmar=confirmar,
        documento=documento))


if __name__ == "__main__":
    mcp.run()
