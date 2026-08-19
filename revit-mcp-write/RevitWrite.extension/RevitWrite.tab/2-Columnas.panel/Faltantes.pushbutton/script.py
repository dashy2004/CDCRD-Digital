# -*- coding: utf-8 -*-
"""Repone las 17 columnas que ocupaban las '12 x 18' ya borradas.

POR QUE EXISTE ESTE SCRIPT
--------------------------
Las 26 columnas de tipo `12 x 18` NO eran duplicados de las metalicas: ocupaban
(posicion, nivel) donde no habia ninguna W. Se borraron antes de que el
Reemplazo corregido las cubriera, asi que el edificio quedo con 17 huecos
(ERRORES-IA E-051).

`Reemplazo` no puede repararlo: busca las '12 x 18' en el modelo y ya no estan.
Este script trabaja desde `_log/faltantes.json`, generado a partir del
inventario tomado ANTES del borrado — ahi estan las coordenadas exactas, el
nivel y el tipo inferido de cada una.

DE DONDE SALE EL TIPO
---------------------
Del voto UNANIME de las metalicas que existian en la misma (x,y) en otros
niveles: C3 en tres posiciones (11 metalicas cada una) y C6 en una (17
metalicas). Ninguna posicion tenia votos divididos.

MISMAS GUARDAS QUE `Reemplazo`
------------------------------
- Marca lo que crea con la MISMA marca, asi queda integrado al conjunto y
  `Borrado` lo protege igual.
- Idempotente por (nivel, posicion): si la columna ya existe ahi, la salta.
  Se puede apretar dos veces sin duplicar.
- Aborta si falta la maestra del tipo. Nunca sustituye por otra.
- Verifica releyendo el modelo.
- Log incremental con fsync. JSON siempre.
"""
__title__ = "Faltantes"
__doc__ = "Repone las 17 columnas de las '12 x 18' borradas, desde faltantes.json"

import os
import re
import json
import traceback

from pyrevit import revit, script
from pyrevit.api import DB
from System.Collections.Generic import List

doc = revit.doc

MARCA = "MCP:reemplazo-columnas"
TOL = 0.02  # pies. Dos columnas mas cerca que esto son la misma posicion.

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
TRACE = os.path.join(LOG_DIR, "faltantes_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "faltantes_resultado.json")
IN_JSON = os.path.join(LOG_DIR, "faltantes.json")

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
        return None


def bip(el, builtin, nombre):
    try:
        p = el.get_Parameter(builtin)
        if p is not None:
            return p
    except Exception:
        pass
    return el.LookupParameter(nombre)


result = {
    "ok": False,
    "phase_reached": "inicio",
    "document": doc.Title,
    "pedidas": 0,
    "ya_existian": [],
    "creadas": [],
    "fallos": [],
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: leer el plan ------------------------------------------
    result["phase_reached"] = "fase1_plan"
    if not os.path.isfile(IN_JSON):
        raise Exception("falta %s" % IN_JSON)
    with open(IN_JSON) as fh:
        plan = json.load(fh)["columnas"]
    result["pedidas"] = len(plan)
    trace("FASE 1 OK: %d columnas en el plan" % len(plan))

    # ---- Fase 2: niveles y maestras ------------------------------------
    result["phase_reached"] = "fase2_contexto"
    niveles = {}
    for lv in (DB.FilteredElementCollector(doc).OfClass(DB.Level)
               .WhereElementIsNotElementType()):
        niveles[lv.Name] = lv
    orden_niv = sorted(niveles.values(), key=lambda l: l.Elevation)

    def nivel_superior(lv):
        for i, x in enumerate(orden_niv):
            if x.Id == lv.Id:
                return orden_niv[i + 1] if i + 1 < len(orden_niv) else None
        return None

    acero_por_host = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            acero_por_host.setdefault(eidv(rb.GetHostId()), []).append(rb.Id)
        except Exception:
            continue

    maestras = {}
    existentes = []
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        sym = doc.GetElement(el.GetTypeId())
        if sym is None:
            continue
        try:
            fam = sym.Family.Name
        except Exception:
            continue
        loc = el.Location
        pt = loc.Point if (loc is not None and hasattr(loc, "Point")) else None
        blp = bip(el, DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, "Base Level")
        bl_el = doc.GetElement(blp.AsElementId()) if blp is not None else None
        if pt is not None and bl_el is not None:
            existentes.append((bl_el.Name, pt))

        if fam != "Concrete-Rectangular-Column":
            continue
        tname = element_name(sym)
        if not tname or not re.match(r"^C\d+$", tname):
            continue
        cid = eidv(el.Id)
        if cid not in acero_por_host or tname in maestras or pt is None:
            continue
        maestras[tname] = {"id": el.Id, "point": pt, "rebar": acero_por_host[cid]}

    trace("FASE 2 OK: maestras=%s | columnas en modelo=%d"
          % (sorted(maestras.keys()), len(existentes)))

    # ---- Fase 3: crear, una transaccion ---------------------------------
    result["phase_reached"] = "fase3_creacion"
    t = DB.Transaction(doc, "MCP: reponer columnas faltantes")
    t.Start()
    try:
        for item in plan:
            niv = item["base_level"]
            tipo = item["tipo"]
            x, y = item["x_ft"], item["y_ft"]

            if niv not in niveles:
                result["fallos"].append({"item": item, "motivo": "nivel inexistente"})
                continue
            if tipo not in maestras:
                result["fallos"].append({"item": item, "motivo": "sin maestra %s" % tipo})
                continue

            # Idempotencia: ya hay una columna en ese nivel y posicion?
            ya = False
            for (nv, pt) in existentes:
                if nv == niv and abs(pt.X - x) < TOL and abs(pt.Y - y) < TOL:
                    ya = True
                    break
            if ya:
                result["ya_existian"].append({"nivel": niv, "tipo": tipo})
                trace("  %s %s: ya existe, se salta" % (niv, tipo))
                continue

            mae = maestras[tipo]
            bl_el = niveles[niv]
            tl_el = nivel_superior(bl_el)
            if tl_el is None:
                result["fallos"].append({"item": item, "motivo": "sin nivel superior"})
                continue

            ids = List[DB.ElementId]()
            ids.Add(mae["id"])
            for r in mae["rebar"]:
                ids.Add(r)

            delta = DB.XYZ(x - mae["point"].X, y - mae["point"].Y, 0.0)
            nuevos = list(DB.ElementTransformUtils.CopyElements(doc, ids, delta))
            col = None
            for nid in nuevos:
                e = doc.GetElement(nid)
                if isinstance(e, DB.FamilyInstance):
                    col = e
                    break
            if col is None:
                raise Exception("no se identifico la columna copiada (%s %s)" % (niv, tipo))

            p = bip(col, DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, "Base Level")
            if p is not None and not p.IsReadOnly:
                p.Set(bl_el.Id)
            p = bip(col, DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM, "Top Level")
            if p is not None and not p.IsReadOnly:
                p.Set(tl_el.Id)
            for b, n in ((DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM, "Base Offset"),
                         (DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM, "Top Offset")):
                p = bip(col, b, n)
                if p is not None and not p.IsReadOnly:
                    p.Set(0.0)
            p = bip(col, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
            if p is not None and not p.IsReadOnly:
                p.Set(MARCA)

            existentes.append((niv, col.Location.Point))
            result["creadas"].append({
                "nueva": eidv(col.Id), "tipo": tipo, "nivel": niv,
                "top": tl_el.Name, "acero": len(nuevos) - 1,
                "origen_12x18": item["origen_id"],
            })
            trace("  %s %s -> id %d (%d sets)" % (niv, tipo, eidv(col.Id), len(nuevos) - 1))
        t.Commit()
        trace("FASE 3 OK: %d creadas" % len(result["creadas"]))
    except Exception as ex:
        t.RollBack()
        raise Exception("excepcion al crear, transaccion revertida: %s" % ex)

    # ---- Fase 4: verificar releyendo ------------------------------------
    result["phase_reached"] = "fase4_verificacion"
    marcadas = 0
    con_acero = 0
    idx = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            h = eidv(rb.GetHostId())
            idx[h] = idx.get(h, 0) + 1
        except Exception:
            continue
    total_col = 0
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        total_col += 1
        p = bip(el, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
        if p is not None and p.AsString() == MARCA:
            marcadas += 1
            if idx.get(eidv(el.Id), 0) > 0:
                con_acero += 1
    result["verificacion"] = {
        "columnas_totales": total_col,
        "marcadas": marcadas,
        "marcadas_con_acero": con_acero,
        "esperado_marcadas": 192 + result["pedidas"],
    }
    trace("FASE 4 OK: %s" % json.dumps(result["verificacion"]))

    result["phase_reached"] = "completo"
    result["ok"] = (not result["fallos"]
                    and marcadas == con_acero
                    and (len(result["creadas"]) + len(result["ya_existian"])
                         == result["pedidas"]))

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Reposicion de faltantes")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
out.print_md("- Pedidas: %d | creadas: **%d** | ya existian: %d"
             % (result["pedidas"], len(result["creadas"]), len(result["ya_existian"])))
v = result.get("verificacion")
if v:
    out.print_md("- Columnas en modelo: **%d** | marcadas: **%d** (con acero: **%d**)"
                 % (v["columnas_totales"], v["marcadas"], v["marcadas_con_acero"]))
    out.print_md("- Marcadas esperadas: %d" % v["esperado_marcadas"])
if result["fallos"]:
    out.print_md("- ⚠️ **fallos: %d** — ver JSON" % len(result["fallos"]))
out.print_md("- **ok: %s**" % result["ok"])
out.print_md("- JSON: `%s`" % OUT_JSON)
