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


if __name__ == "__main__":
    mcp.run()
