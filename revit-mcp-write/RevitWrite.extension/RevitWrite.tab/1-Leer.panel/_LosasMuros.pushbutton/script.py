# -*- coding: utf-8 -*-
"""Inventario de losas y muros. SOLO LECTURA.

Paso previo a tres trabajos distintos que el operador planteo:
  1. Bovedillas y acero en las losas (la de E6 se repetiria hasta E15).
  2. Dividir por piso los muros de hormigon MH, que hoy suben completos.
  3. Verificar solapes de barras.

Sin este volcado los tres serian a ciegas. Igual que con columnas y zapatas:
primero se sabe que hay y donde, despues se decide.

QUE VUELCA
----------
LOSAS  : tipo, espesor, nivel, area, perimetro, bbox, offset, acero hospedado
MUROS  : tipo, espesor, nivel base y superior, altura real, largo, bbox,
         si es estructural, y acero hospedado

Para los muros interesa especialmente `base_constraint` / `top_constraint` y
la altura: es el dato que dice si un muro cruza varios pisos de una pieza.

No modifica nada. No abre transaccion.
"""
__title__ = "LosasMuros"
__doc__ = "Inventario de losas y muros con espesores, niveles y alturas. Solo lectura."

import os
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
M2 = M * M

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "losas_muros_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "losas_muros.json")   # se re-apunta con el
                                              # nombre del doc mas abajo

OUT_JSON = os.path.join(LOG_DIR, "losas_muros_%s.json" % _slug(doc.Title))

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


def num(el, nombre):
    try:
        p = el.LookupParameter(nombre)
        if p is None or p.StorageType != DB.StorageType.Double:
            return None
        return p.AsDouble()
    except Exception:
        return None


def nivel_de(el, nombre_param):
    try:
        p = el.LookupParameter(nombre_param)
        if p is None:
            return None
        e = doc.GetElement(p.AsElementId())
        return element_name(e) if e is not None else None
    except Exception:
        return None


result = {
    "ok": False,
    "phase_reached": "inicio",
    "document": doc.Title,
    "niveles": [],
    "losas": [],
    "muros": [],
    "resumen_losas": {},
    "resumen_muros": {},
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: niveles y acero ----------------------------------------
    result["phase_reached"] = "fase1_contexto"
    for lv in sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level)
                     .WhereElementIsNotElementType(),
                     key=lambda x: x.Elevation):
        result["niveles"].append({"nombre": lv.Name,
                                  "cota_m": lv.Elevation * M})
    acero = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            acero.setdefault(eidv(rb.GetHostId()), 0)
            acero[eidv(rb.GetHostId())] += 1
        except Exception:
            continue
    trace("FASE 1 OK: %d niveles, %d anfitriones con acero"
          % (len(result["niveles"]), len(acero)))

    # ---- Fase 2: losas ---------------------------------------------------
    result["phase_reached"] = "fase2_losas"
    losas = list(DB.FilteredElementCollector(doc)
                 .OfCategory(DB.BuiltInCategory.OST_Floors)
                 .WhereElementIsNotElementType())
    trace("FASE 2: %d losas" % len(losas))
    for el in losas:
        lid = eidv(el.Id)
        fila = {"id": lid, "tipo": None, "familia": None, "nivel": None,
                "espesor_m": None, "area_m2": None, "perimetro_m": None,
                "offset_m": None, "bbox_m": None,
                "acero_sets": acero.get(lid, 0), "error": None}
        errs = []
        try:
            sym = doc.GetElement(el.GetTypeId())
            if sym is not None:
                fila["tipo"] = element_name(sym)
                try:
                    fila["familia"] = sym.FamilyName
                except Exception:
                    pass
                v = num(sym, "Default Thickness")
                if v is None:
                    v = num(sym, "Thickness")
                fila["espesor_m"] = v * M if v is not None else None
        except Exception as ex:
            errs.append("tipo: %s" % ex)
        try:
            fila["nivel"] = nivel_de(el, "Level")
            if fila["nivel"] is None and el.LevelId is not None:
                lv = doc.GetElement(el.LevelId)
                fila["nivel"] = lv.Name if lv is not None else None
        except Exception as ex:
            errs.append("nivel: %s" % ex)
        try:
            a = num(el, "Area")
            fila["area_m2"] = a * M2 if a is not None else None
            p = num(el, "Perimeter")
            fila["perimetro_m"] = p * M if p is not None else None
            o = num(el, "Height Offset From Level")
            fila["offset_m"] = o * M if o is not None else None
        except Exception as ex:
            errs.append("params: %s" % ex)
        try:
            bb = el.get_BoundingBox(None)
            if bb is not None:
                fila["bbox_m"] = {"lx": (bb.Max.X - bb.Min.X) * M,
                                  "ly": (bb.Max.Y - bb.Min.Y) * M,
                                  "h": (bb.Max.Z - bb.Min.Z) * M,
                                  "min_z": bb.Min.Z * M}
        except Exception as ex:
            errs.append("bbox: %s" % ex)
        if errs:
            fila["error"] = " | ".join(errs)
        result["losas"].append(fila)
    trace("FASE 2 OK")

    # ---- Fase 3: muros ---------------------------------------------------
    result["phase_reached"] = "fase3_muros"
    muros = list(DB.FilteredElementCollector(doc)
                 .OfCategory(DB.BuiltInCategory.OST_Walls)
                 .WhereElementIsNotElementType())
    trace("FASE 3: %d muros" % len(muros))
    for el in muros:
        mid = eidv(el.Id)
        fila = {"id": mid, "tipo": None, "familia": None,
                "espesor_m": None, "estructural": None,
                "base": None, "top": None,
                "base_offset_m": None, "top_offset_m": None,
                "altura_m": None, "largo_m": None,
                "bbox_m": None, "acero_sets": acero.get(mid, 0), "error": None}
        errs = []
        try:
            sym = doc.GetElement(el.GetTypeId())
            if sym is not None:
                fila["tipo"] = element_name(sym)
                try:
                    fila["familia"] = sym.FamilyName
                except Exception:
                    pass
                v = num(sym, "Width")
                fila["espesor_m"] = v * M if v is not None else None
        except Exception as ex:
            errs.append("tipo: %s" % ex)
        try:
            fila["base"] = nivel_de(el, "Base Constraint")
            fila["top"] = nivel_de(el, "Top Constraint")
            b = num(el, "Base Offset")
            t = num(el, "Top Offset")
            fila["base_offset_m"] = b * M if b is not None else None
            fila["top_offset_m"] = t * M if t is not None else None
            h = num(el, "Unconnected Height")
            fila["altura_m"] = h * M if h is not None else None
            lg = num(el, "Length")
            fila["largo_m"] = lg * M if lg is not None else None
        except Exception as ex:
            errs.append("params: %s" % ex)
        try:
            p = el.LookupParameter("Structural")
            fila["estructural"] = bool(p.AsInteger()) if p is not None else None
        except Exception:
            pass
        try:
            bb = el.get_BoundingBox(None)
            if bb is not None:
                fila["bbox_m"] = {"lx": (bb.Max.X - bb.Min.X) * M,
                                  "ly": (bb.Max.Y - bb.Min.Y) * M,
                                  "h": (bb.Max.Z - bb.Min.Z) * M,
                                  "min_z": bb.Min.Z * M,
                                  "max_z": bb.Max.Z * M}
        except Exception as ex:
            errs.append("bbox: %s" % ex)
        if errs:
            fila["error"] = " | ".join(errs)
        result["muros"].append(fila)
    trace("FASE 3 OK")

    # ---- Fase 4: resumenes ----------------------------------------------
    result["phase_reached"] = "fase4_resumen"
    rl = {}
    for l in result["losas"]:
        k = "%s | esp=%s" % (l["tipo"], round(l["espesor_m"], 3)
                             if l["espesor_m"] else "?")
        d = rl.setdefault(k, {"n": 0, "niveles": {}, "area_total": 0.0,
                              "con_acero": 0})
        d["n"] += 1
        if l["nivel"]:
            d["niveles"][l["nivel"]] = d["niveles"].get(l["nivel"], 0) + 1
        if l["area_m2"]:
            d["area_total"] += l["area_m2"]
        if l["acero_sets"]:
            d["con_acero"] += 1
    result["resumen_losas"] = rl

    rm = {}
    for m in result["muros"]:
        k = "%s | esp=%s" % (m["tipo"], round(m["espesor_m"], 3)
                             if m["espesor_m"] else "?")
        d = rm.setdefault(k, {"n": 0, "tramos": {}, "con_acero": 0,
                              "altura_min": None, "altura_max": None})
        d["n"] += 1
        tramo = "%s -> %s" % (m["base"], m["top"])
        d["tramos"][tramo] = d["tramos"].get(tramo, 0) + 1
        if m["acero_sets"]:
            d["con_acero"] += 1
        hh = (m["bbox_m"] or {}).get("h")
        if hh:
            d["altura_min"] = hh if d["altura_min"] is None else min(d["altura_min"], hh)
            d["altura_max"] = hh if d["altura_max"] is None else max(d["altura_max"], hh)
    result["resumen_muros"] = rm
    trace("FASE 4 OK: %d tipos de losa, %d tipos de muro" % (len(rl), len(rm)))

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

out.print_md("### Losas y muros")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
out.print_md("- Losas: **%d** | con acero: %d"
             % (len(result["losas"]),
                len([l for l in result["losas"] if l["acero_sets"]])))
for k, d in sorted(result["resumen_losas"].items(), key=lambda t: -t[1]["n"])[:8]:
    out.print_md("  - `%s` x%d — %d niveles, %.0f m2"
                 % (k, d["n"], len(d["niveles"]), d["area_total"]))
out.print_md("- Muros: **%d** | con acero: %d"
             % (len(result["muros"]),
                len([m for m in result["muros"] if m["acero_sets"]])))
for k, d in sorted(result["resumen_muros"].items(), key=lambda t: -t[1]["n"])[:8]:
    alt = "%.1f-%.1f m" % (d["altura_min"] or 0, d["altura_max"] or 0)
    out.print_md("  - `%s` x%d — alturas %s, %d tramos distintos"
                 % (k, d["n"], alt, len(d["tramos"])))
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
