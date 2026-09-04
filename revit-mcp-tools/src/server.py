# -*- coding: utf-8 -*-
"""revit-tools: servidor MCP que expone como herramientas la logica de los
pushbuttons de RevitWrite, para que un agente las ejecute sin la interfaz.

Arquitectura:
    cliente MCP --stdio--> este proceso --HTTP--> pyRevit Routes "revit_mcp"
                                                  POST /revit_mcp/execute_code/
                                                  (dentro de Revit.exe)

Se reutiliza el canal que ya funciona (la extension mcp-server-for-revit-python
registra ese endpoint): no hace falta tocar pyRevit ni reiniciar Revit para
agregar una tool. Cada tool es un archivo en tools/<nombre>.py con

    def run(doc, uidoc, DB, P): ... return dict

El servidor concatena tools/_common.py + el modulo + un pie que llama run()
con los parametros en JSON y hace print(json.dumps(resultado)). Todo ese
texto corre como IronPython dentro de Revit, asi que los modulos son 2.7:
sin f-strings, sin anotaciones. El puerto se descubre por sondeo (pyRevit
sube al siguiente libre si el base esta ocupado) y se cachea.

Agregar una tool nueva = agregar el archivo y registrarla abajo en TOOLS.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
TOOLS_DIR = os.path.join(SRC_DIR, "tools")
BASE_PORT = 48884
PORT_SCAN = 8
TIMEOUT = 600          # exportaciones y tags en 20 hojas tardan
API = "revit_mcp"

mcp = FastMCP("revit-tools")
_port_cache: Optional[int] = None


# ----------------------------------------------------------------------
# Canal HTTP hacia pyRevit
# ----------------------------------------------------------------------

def _post(port: int, code: str, description: str) -> dict:
    url = "http://localhost:%d/%s/execute_code/" % (port, API)
    payload = json.dumps({"code": code, "description": description,
                          "use_transaction": False}).encode("utf-8")
    # text/plain: pyRevit 6.5 sobre IronPython hace json.loads(bytes) con
    # application/json y falla antes de llegar al handler (ver revit-mcp-write).
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "text/plain; charset=utf-8"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        raw = resp.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "respuesta no-JSON", "raw": raw[:2000]}


def _port() -> int:
    global _port_cache
    probe = "print('__revit_tools_ok__')"
    if _port_cache is not None:
        try:
            r = _post(_port_cache, probe, "sonda")
            if "__revit_tools_ok__" in json.dumps(r):
                return _port_cache
        except Exception:
            pass
        _port_cache = None
    errors = []
    for p in range(BASE_PORT, BASE_PORT + PORT_SCAN):
        try:
            r = _post(p, probe, "sonda")
            if "__revit_tools_ok__" in json.dumps(r):
                _port_cache = p
                return p
            errors.append("%d: respuesta inesperada" % p)
        except urllib.error.HTTPError as e:
            errors.append("%d: HTTP %s" % (p, e.code))
        except Exception as e:
            errors.append("%d: %s" % (p, type(e).__name__))
    raise RuntimeError(
        "No responde /%s/execute_code/ en %d-%d. Verificar: Revit abierto con "
        "un documento, extension mcp-server-for-revit-python cargada, routes "
        "habilitadas. Sondeo: %s" % (API, BASE_PORT, BASE_PORT + PORT_SCAN - 1, "; ".join(errors)))


# ----------------------------------------------------------------------
# Ensamblado y ejecucion de una tool
# ----------------------------------------------------------------------

def _read(name: str) -> str:
    path = os.path.join(TOOLS_DIR, name + ".py")
    if not os.path.isfile(path):
        raise FileNotFoundError("no existe la tool '%s' (%s)" % (name, path))
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


_COMMON = None


def _common() -> str:
    global _COMMON
    if _COMMON is None:
        _COMMON = _read("_common")
    return _COMMON


# El resultado viaja en base64 dentro del stdout capturado: asi no importa en
# que campo lo devuelva el endpoint ni como escape las comillas.
# pyRevit 6.5 corre IronPython 3.4: b64decode devuelve bytes y json.loads
# exige str, de ahi los decode/encode explicitos (verificado 2026-09-04).
_FOOTER = """
import json as _json, base64 as _b64
_P = _json.loads(_b64.b64decode(%r).decode("utf-8"))
_R = run(doc, uidoc, DB, _P)
print("__RT__" + _b64.b64encode(_json.dumps(_R, default=str).encode("utf-8")).decode("ascii") + "__RT_END__")
"""


def _run_tool(name: str, params: dict) -> dict:
    import base64
    p64 = base64.b64encode(json.dumps(params or {}).encode("utf-8")).decode("ascii")
    code = _common() + "\n\n" + _read(name) + "\n" + _FOOTER % p64
    r = _post(_port(), code, "revit-tools: " + name)
    text = r if isinstance(r, str) else json.dumps(r)
    m = re.search(r"__RT__([A-Za-z0-9+/=]+)__RT_END__", text)
    if m:
        try:
            return {"ok": True, "tool": name,
                    "result": json.loads(base64.b64decode(m.group(1)).decode("utf-8"))}
        except Exception as e:
            return {"ok": False, "tool": name, "error": "resultado ilegible: %s" % e,
                    "raw": m.group(1)[:2000]}
    return {"ok": False, "tool": name,
            "revit_response": r if isinstance(r, dict) else text[:4000]}


def _doc(name: str) -> str:
    src = _read(name)
    m = re.search(r'"""(.*?)"""', src, re.S)
    return m.group(1).strip() if m else name


# ----------------------------------------------------------------------
# Herramientas
# ----------------------------------------------------------------------

@mcp.tool(description=_doc("estado"))
def revit_estado() -> dict:
    return _run_tool("estado", {})


@mcp.tool(description=_doc("inventario"))
def revit_inventario(categories: list[str] = None, by_level: bool = False) -> dict:
    return _run_tool("inventario", {"categories": categories, "by_level": by_level})


@mcp.tool(description=_doc("vigas"))
def revit_vigas(view_name: str = "", include_rebar: bool = False, max_rows: int = 500) -> dict:
    return _run_tool("vigas", {"view_name": view_name, "include_rebar": include_rebar, "max_rows": max_rows})


@mcp.tool(description=_doc("losas_muros"))
def revit_losas_muros(max_rows: int = 300) -> dict:
    return _run_tool("losas_muros", {"max_rows": max_rows})


@mcp.tool(description=_doc("guardar_modelo"))
def revit_guardar_modelo(save_as: str = "") -> dict:
    return _run_tool("guardar_modelo", {"save_as": save_as})


@mcp.tool(description=_doc("material_vigas"))
def revit_material_vigas(material: str, view_name: str = "", dry_run: bool = False) -> dict:
    return _run_tool("material_vigas", {"material": material, "view_name": view_name, "dry_run": dry_run})


@mcp.tool(description=_doc("sin_hatch_material"))
def revit_sin_hatch_material(material: str, cut_pattern: str = "", surface_pattern: str = None,
                             color_rgb: list[int] = None) -> dict:
    return _run_tool("sin_hatch_material", {"material": material, "cut_pattern": cut_pattern,
                                            "surface_pattern": surface_pattern, "color_rgb": color_rgb})


@mcp.tool(description=_doc("tags_vigas"))
def revit_tags_vigas(view_name: str = "", tag_type: str = "", offset_mm: float = 250.0,
                     skip_edge: bool = True, replace: bool = False) -> dict:
    return _run_tool("tags_vigas", {"view_name": view_name, "tag_type": tag_type, "offset_mm": offset_mm,
                                    "skip_edge": skip_edge, "replace": replace})


@mcp.tool(description=_doc("tags_elementos"))
def revit_tags_elementos(category: str, view_name: str = "", tag_type: str = "",
                         offset_mm: float = None, angle_deg: float = None, replace: bool = False) -> dict:
    p = {"category": category, "view_name": view_name, "tag_type": tag_type, "replace": replace}
    if offset_mm is not None:
        p["offset_mm"] = offset_mm
    if angle_deg is not None:
        p["angle_deg"] = angle_deg
    return _run_tool("tags_elementos", p)


@mcp.tool(description=_doc("color_acero"))
def revit_color_acero(view_name: str = "", colors: dict = None, default_rgb: list[int] = None,
                      straight_shapes: list[str] = None, solid: bool = True, host_category: str = "") -> dict:
    return _run_tool("color_acero", {"view_name": view_name, "colors": colors, "default_rgb": default_rgb,
                                     "straight_shapes": straight_shapes, "solid": solid,
                                     "host_category": host_category})


@mcp.tool(description=_doc("porticos_por_eje"))
def revit_porticos_por_eje(grids: list[str] = None, prefix: str = "PORTICO EJE ", depth_mm: float = 900.0,
                           z_min_mm: float = None, z_max_mm: float = None, blocks: dict = None,
                           template: str = "", scale: int = 100, replace: bool = False) -> dict:
    p = {"grids": grids, "prefix": prefix, "depth_mm": depth_mm, "blocks": blocks,
         "template": template, "scale": scale, "replace": replace}
    if z_min_mm is not None:
        p["z_min_mm"] = z_min_mm
    if z_max_mm is not None:
        p["z_max_mm"] = z_max_mm
    return _run_tool("porticos_por_eje", p)


@mcp.tool(description=_doc("cotas_ejes"))
def revit_cotas_ejes(view_name: str = "", offset_mm: float = 2500.0, dim_type: str = "",
                     replace: bool = False) -> dict:
    return _run_tool("cotas_ejes", {"view_name": view_name, "offset_mm": offset_mm,
                                    "dim_type": dim_type, "replace": replace})


@mcp.tool(description=_doc("exportar_hojas"))
def revit_exportar_hojas(folder: str, prefix: str = "", sheets: list[str] = None,
                         formats: list[str] = None, version: str = "2018", merged: bool = True,
                         clean: bool = False) -> dict:
    return _run_tool("exportar_hojas", {"folder": folder, "prefix": prefix, "sheets": sheets,
                                        "formats": formats, "version": version, "merged": merged,
                                        "clean": clean})


@mcp.tool(description=_doc("acero_vigas"))
def revit_acero_vigas(regla: dict = None, beams: list[int] = None, filtro: dict = None,
                      reglas_por_nivel: dict = None, rec_m: float = 0.04, fraccion_confinada: float = 0.25,
                      holgura_cara_m: float = 0.05, embed_nudo_m: float = 0.30, gancho: str = "Standard - 90 deg.",
                      b_m: float = 0.35, h_m: float = 0.75, purge: bool = True, dry_run: bool = True,
                      limites: dict = None) -> dict:
    """dry_run=True por defecto: devuelve geometria y verificaciones sin escribir."""
    return _run_tool("acero_vigas", {"regla": regla, "beams": beams, "filtro": filtro,
                                     "reglas_por_nivel": reglas_por_nivel, "rec_m": rec_m,
                                     "fraccion_confinada": fraccion_confinada, "holgura_cara_m": holgura_cara_m,
                                     "embed_nudo_m": embed_nudo_m, "gancho": gancho, "b_m": b_m, "h_m": h_m,
                                     "purge": purge, "dry_run": dry_run, "limites": limites})


@mcp.tool(description=_doc("acero_columnas"))
def revit_acero_columnas(regla: dict = None, columns: list[int] = None, filtro: dict = None,
                         reglas_por_tipo: dict = None, rec_m: float = 0.04, gancho: str = "Standard - 135 deg.",
                         b_m: float = 0.40, h_m: float = 0.40, purge: bool = True, dry_run: bool = True,
                         limites: dict = None) -> dict:
    """dry_run=True por defecto: devuelve geometria y verificaciones sin escribir."""
    return _run_tool("acero_columnas", {"regla": regla, "columns": columns, "filtro": filtro,
                                        "reglas_por_tipo": reglas_por_tipo, "rec_m": rec_m, "gancho": gancho,
                                        "b_m": b_m, "h_m": h_m, "purge": purge, "dry_run": dry_run,
                                        "limites": limites})


@mcp.tool()
def revit_ejecutar_tool(name: str, params: dict = None) -> dict:
    """Ejecuta cualquier tool de la carpeta tools/ por nombre con un dict de
    parametros. Es la via para tools nuevas que todavia no tienen wrapper:
    basta con crear tools/<name>.py con run(doc, uidoc, DB, P)."""
    return _run_tool(name, params or {})


@mcp.tool()
def revit_listar_tools() -> dict:
    """Lista las tools disponibles en tools/ con la primera linea de su docstring."""
    out = {}
    for fn in sorted(os.listdir(TOOLS_DIR)):
        if fn.endswith(".py") and not fn.startswith("_"):
            n = fn[:-3]
            out[n] = _doc(n).splitlines()[0]
    return out


if __name__ == "__main__":
    mcp.run(transport="stdio")
