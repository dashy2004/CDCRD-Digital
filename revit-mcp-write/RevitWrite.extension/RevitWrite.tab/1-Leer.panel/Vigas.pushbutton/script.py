# -*- coding: utf-8 -*-
"""Inventario de vigas (structural framing). SOLO LECTURA.

Paso previo obligatorio antes de reemplazar las vigas metalicas por vigas de
hormigon. Mismo criterio que se uso con las columnas: primero se sabe donde
esta todo y con que dimensiones, despues se decide.

Sin este volcado el reemplazo seria a ciegas: `revit_columns` no daba
coordenadas y por eso hubo que escribir `Inventario`; aca pasa lo mismo, mas
el agravante de que una viga se define por su curva (dos extremos), no por un
punto.

QUE VUELCA POR VIGA
-------------------
- familia, tipo, prefijo de tipo, Mark, nivel
- extremos de la curva (x, y, z de inicio y fin) y longitud
- nivel de referencia y offsets
- seccion (b, h) si la familia los expone
- acero hospedado

Y ademas, contra los planos: agrupa por (familia, tipo) para ver de un vistazo
cuantas metalicas hay y de que tipos.

No modifica nada. No abre transaccion.
"""
__title__ = "Vigas"
__doc__ = "Inventario de vigas con geometria de sus extremos. Solo lectura."

import os
import re
import json
import traceback

from pyrevit import revit, script
from pyrevit.api import DB

doc = revit.doc

def _slug(txt):
    """Nombre de archivo seguro a partir del titulo del documento."""
    return "".join(ch if ch.isalnum() or ch in "-_" else "_"
                   for ch in (txt or "SIN_DOC"))[:60]

M = 0.3048

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "vigas_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "vigas.json")   # se re-apunta con el
                                              # nombre del doc mas abajo

OUT_JSON = os.path.join(LOG_DIR, "vigas_%s.json" % _slug(doc.Title))

out = script.get_output()

try:
    if os.path.isfile(TRACE):
        os.remove(TRACE)
except Exception:
    pass


def trace(msg):
    with open(TRACE, "a") as fh:
        fh.write("%s\n" % msg)
        fh.flush()
        os.fsync(fh.fileno())


def eidv(element_id):
    try:
        return int(element_id.Value)
    except AttributeError:
        return int(element_id.IntegerValue)


def element_name(el):
    if el is None:
        return None
    try:
        return el.Name
    except Exception:
        pass
    try:
        return DB.Element.Name.GetValue(el)
    except Exception:
        pass
    try:
        p = el.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM)
        return p.AsString() if p is not None else None
    except Exception:
        return None


def num_param(el, nombre):
    try:
        p = el.LookupParameter(nombre)
        if p is None or p.StorageType != DB.StorageType.Double:
            return None
        return p.AsDouble() * M
    except Exception:
        return None


def str_param(el, nombre):
    try:
        p = el.LookupParameter(nombre)
        return p.AsString() if p is not None else None
    except Exception:
        return None


result = {
    "ok": False,
    "phase_reached": "inicio",
    "document": doc.Title,
    "vigas": [],
    "resumen_por_tipo": {},
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: acero hospedado ----------------------------------------
    result["phase_reached"] = "fase1_acero"
    acero = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            acero.setdefault(eidv(rb.GetHostId()), []).append(eidv(rb.Id))
        except Exception:
            continue
    trace("FASE 1 OK: %d anfitriones con acero" % len(acero))

    # ---- Fase 2: vigas ---------------------------------------------------
    result["phase_reached"] = "fase2_vigas"
    vigas = list(DB.FilteredElementCollector(doc)
                 .OfCategory(DB.BuiltInCategory.OST_StructuralFraming)
                 .WhereElementIsNotElementType())
    trace("FASE 2: %d instancias de structural framing" % len(vigas))

    for idx, el in enumerate(vigas):
        vid = eidv(el.Id)
        fila = {
            "id": vid, "familia": None, "tipo": None, "prefijo": None,
            "mark": None, "nivel": None,
            "x0": None, "y0": None, "z0": None,
            "x1": None, "y1": None, "z1": None,
            "largo_m": None,
            "b_m": None, "h_m": None,
            "start_offset_m": None, "end_offset_m": None,
            "acero_sets": len(acero.get(vid, [])),
            "error": None,
        }
        errs = []

        # try POR BLOQUE: un fallo en el tipo no debe llevarse la geometria
        try:
            sym = doc.GetElement(el.GetTypeId())
            if sym is not None:
                fila["tipo"] = element_name(sym)
                try:
                    fila["familia"] = sym.Family.Name
                except Exception as ex:
                    errs.append("familia: %s" % ex)
                if fila["tipo"]:
                    m = re.match(r"^([A-Za-z]+\d+)(?=[-_ ]|$)", fila["tipo"].strip())
                    fila["prefijo"] = m.group(1) if m else None
                # dimensiones de seccion, si la familia las expone
                for nom, clave in (("b", "b_m"), ("Width", "b_m"),
                                   ("h", "h_m"), ("Height", "h_m"),
                                   ("Depth", "h_m")):
                    if fila[clave] is None:
                        v = num_param(sym, nom)
                        if v is not None:
                            fila[clave] = v
        except Exception as ex:
            errs.append("tipo: %s" % ex)

        try:
            fila["mark"] = str_param(el, "Mark")
        except Exception as ex:
            errs.append("mark: %s" % ex)

        try:
            if el.LevelId is not None and eidv(el.LevelId) > 0:
                lv = doc.GetElement(el.LevelId)
                fila["nivel"] = lv.Name if lv is not None else None
            if fila["nivel"] is None:
                p = el.LookupParameter("Reference Level")
                if p is not None:
                    lv = doc.GetElement(p.AsElementId())
                    fila["nivel"] = lv.Name if lv is not None else None
        except Exception as ex:
            errs.append("nivel: %s" % ex)

        try:
            loc = el.Location
            if loc is not None and hasattr(loc, "Curve"):
                c = loc.Curve
                p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
                fila["x0"], fila["y0"], fila["z0"] = p0.X, p0.Y, p0.Z
                fila["x1"], fila["y1"], fila["z1"] = p1.X, p1.Y, p1.Z
                fila["largo_m"] = c.Length * M
        except Exception as ex:
            errs.append("curva: %s" % ex)

        try:
            fila["start_offset_m"] = num_param(el, "Start Level Offset")
            fila["end_offset_m"] = num_param(el, "End Level Offset")
        except Exception as ex:
            errs.append("offsets: %s" % ex)

        if errs:
            fila["error"] = " | ".join(errs)
        result["vigas"].append(fila)
        if idx % 100 == 0:
            trace("  ...%d/%d" % (idx, len(vigas)))

    trace("FASE 2 OK")

    # ---- Fase 3: resumen -------------------------------------------------
    result["phase_reached"] = "fase3_resumen"
    res = {}
    for v in result["vigas"]:
        k = "%s | %s" % (v["familia"], v["tipo"])
        d = res.setdefault(k, {"n": 0, "con_acero": 0, "niveles": {},
                               "largo_min": None, "largo_max": None})
        d["n"] += 1
        if v["acero_sets"]:
            d["con_acero"] += 1
        if v["nivel"]:
            d["niveles"][v["nivel"]] = d["niveles"].get(v["nivel"], 0) + 1
        if v["largo_m"] is not None:
            d["largo_min"] = v["largo_m"] if d["largo_min"] is None else min(d["largo_min"], v["largo_m"])
            d["largo_max"] = v["largo_m"] if d["largo_max"] is None else max(d["largo_max"], v["largo_m"])
    result["resumen_por_tipo"] = res
    trace("FASE 3 OK: %d combinaciones familia|tipo" % len(res))

    result["phase_reached"] = "completo"
    result["ok"] = True

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Inventario de vigas")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
out.print_md("- Vigas: **%d**" % len(result["vigas"]))
con = len([v for v in result["vigas"] if v["acero_sets"]])
out.print_md("- Con acero: **%d**" % con)
err = len([v for v in result["vigas"] if v["error"]])
if err:
    out.print_md("- Con errores de lectura: %d" % err)
out.print_md("- Combinaciones familia|tipo: **%d**" % len(result["resumen_por_tipo"]))
for k, d in sorted(result["resumen_por_tipo"].items(), key=lambda t: -t[1]["n"])[:10]:
    out.print_md("  - `%s` x%d" % (k, d["n"]))
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
