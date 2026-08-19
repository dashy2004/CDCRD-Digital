# -*- coding: utf-8 -*-
"""Replica verticalmente las columnas maestras, con su acero, hasta el ultimo nivel.

QUE HACE
--------
Toma cada columna que tenga acero hospedado y la copia a TODOS los tramos de
nivel por encima del suyo, conservando su posicion (x, y). El acero viaja con
ella y se readapta solo a la altura de cada tramo.

Por que el acero se adapta: esta amarrado por constraints a las caras del
anfitrion (`ToCover`, `FixedDistanceToHostFace`), no a coordenadas. Verificado
el 2026-08-13: al cambiar la altura del host, las longitudinales cambian de
largo y los estribos recalculan la cantidad segun `MaximumSpacing`.

Por que anfitrion y acero van JUNTOS en la misma llamada:
`ElementTransformUtils.CopyElements` copia exactamente los ids que recibe. Si
se copia solo la columna, el acero se queda.

ALCANCE DECIDIDO POR EL OPERADOR (2026-08-14)
----------------------------------------------
Todas las maestras suben hasta el ultimo nivel del documento. Si en el edificio
real alguna columna termina antes, ese recorte es un paso posterior: este
script no lo decide.

GUARDAS (E-041, E-043, E-045, E-046)
------------------------------------
- Marca lo que crea y borra su obra previa: idempotente, se puede repetir.
- Los offsets van en 0: no se reproduce geometria heredada.
- Verifica RELEYENDO cuantas columnas marcadas quedaron y cuantas con acero.
- Una transaccion por tramo: un fallo no se lleva los tramos ya hechos.
- Log incremental con fsync antes de cada tramo.
"""
__title__ = "SubirColumnas"
__doc__ = "Copia las columnas con acero a todos los niveles superiores. Idempotente."

import os
import json
import traceback

from pyrevit import revit, script
from pyrevit.api import DB
from System.Collections.Generic import List

doc = revit.doc

MARCA = "MCP:columna-replicada"
M = 0.3048

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)


def _slug(txt):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_"
                   for ch in (txt or "SIN_DOC"))[:60]


TRACE = os.path.join(LOG_DIR, "subir_columnas_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "subir_columnas_%s.json" % _slug(doc.Title))

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
    "previos_borrados": 0,
    "maestras": [],
    "niveles": [],
    "creadas": [],
    "por_tramo": {},
    "fallos": [],
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: niveles ordenados por cota ------------------------------
    result["phase_reached"] = "fase1_niveles"
    niveles = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level)
                     .WhereElementIsNotElementType(),
                     key=lambda l: l.Elevation)
    result["niveles"] = [{"nombre": l.Name, "cota_m": l.Elevation * M}
                         for l in niveles]
    trace("FASE 1 OK: %d niveles, de %s a %s"
          % (len(niveles), niveles[0].Name, niveles[-1].Name))
    if len(niveles) < 2:
        raise Exception("hacen falta al menos 2 niveles")

    # ---- Fase 2: limpiar obra propia anterior ----------------------------
    result["phase_reached"] = "fase2_limpieza"
    previos = []
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        p = bip(el, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
        if p is not None and p.AsString() == MARCA:
            previos.append(el.Id)
    if previos:
        trace("FASE 2: borrando %d columnas de corrida anterior" % len(previos))
        t = DB.Transaction(doc, "MCP: limpiar replicas anteriores")
        t.Start()
        try:
            ids = List[DB.ElementId]()
            for i in previos:
                ids.Add(i)
            borr = doc.Delete(ids)
            t.Commit()
            result["previos_borrados"] = len(borr) if borr else 0
        except Exception as ex:
            t.RollBack()
            raise Exception("no se pudo limpiar: %s" % ex)
    trace("FASE 2 OK: %d borrados" % result["previos_borrados"])

    # ---- Fase 3: identificar maestras ------------------------------------
    # Maestra = columna CON acero hospedado. No se filtra por familia ni por
    # nombre: el acero es la senal de que esa columna esta detallada, y es la
    # unica que importa. Filtrar por familia habria dejado fuera las
    # importadas, que son justamente las que tienen el armado.
    result["phase_reached"] = "fase3_maestras"
    acero_por_host = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            acero_por_host.setdefault(eidv(rb.GetHostId()), []).append(rb.Id)
        except Exception:
            continue

    maestras = []
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        cid = eidv(el.Id)
        if cid not in acero_por_host:
            continue
        p = bip(el, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
        if p is not None and p.AsString() == MARCA:
            continue          # no replicar una replica
        loc = el.Location
        if loc is None or not hasattr(loc, "Point"):
            result["fallos"].append({"id": cid, "motivo": "sin LocationPoint"})
            continue
        blp = bip(el, DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, "Base Level")
        bl = doc.GetElement(blp.AsElementId()) if blp is not None else None
        if bl is None:
            result["fallos"].append({"id": cid, "motivo": "sin nivel base"})
            continue
        sym = doc.GetElement(el.GetTypeId())
        maestras.append({
            "el": el, "id": cid, "punto": loc.Point,
            "base": bl, "tipo": element_name(sym),
            "rebar": acero_por_host[cid],
        })
        result["maestras"].append({
            "id": cid, "tipo": element_name(sym), "nivel": bl.Name,
            "sets": len(acero_por_host[cid])})
    trace("FASE 3 OK: %d maestras con acero" % len(maestras))
    if not maestras:
        raise Exception("no se encontro ninguna columna con acero para replicar")

    # ---- Fase 4: replicar, una transaccion por tramo ---------------------
    result["phase_reached"] = "fase4_replicacion"
    idx_por_nombre = {l.Name: i for i, l in enumerate(niveles)}

    for i in range(len(niveles) - 1):
        base_lv, top_lv = niveles[i], niveles[i + 1]
        # las maestras que ya viven en este tramo no se duplican
        pendientes = [m for m in maestras
                      if idx_por_nombre.get(m["base"].Name, -1) != i]
        if not pendientes:
            trace("  tramo %s -> %s: nada que hacer" % (base_lv.Name, top_lv.Name))
            continue

        trace("  --- %s -> %s (%.2f m): %d columnas ---"
              % (base_lv.Name, top_lv.Name,
                 (top_lv.Elevation - base_lv.Elevation) * M, len(pendientes)))
        t = DB.Transaction(doc, "MCP: columnas %s" % base_lv.Name)
        t.Start()
        hechas = []
        try:
            for m in pendientes:
                dz = base_lv.Elevation - m["base"].Elevation
                ids = List[DB.ElementId]()
                ids.Add(m["el"].Id)
                for r in m["rebar"]:
                    ids.Add(r)

                nuevos = list(DB.ElementTransformUtils.CopyElements(
                    doc, ids, DB.XYZ(0.0, 0.0, dz)))
                col = None
                for nid in nuevos:
                    e = doc.GetElement(nid)
                    if isinstance(e, DB.FamilyInstance):
                        col = e
                        break
                if col is None:
                    raise Exception("no se identifico la copia de %s" % m["id"])

                p = bip(col, DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
                        "Base Level")
                if p is not None and not p.IsReadOnly:
                    p.Set(base_lv.Id)
                p = bip(col, DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM,
                        "Top Level")
                if p is not None and not p.IsReadOnly:
                    p.Set(top_lv.Id)
                for b, n in ((DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM,
                              "Base Offset"),
                             (DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM,
                              "Top Offset")):
                    p = bip(col, b, n)
                    if p is not None and not p.IsReadOnly:
                        p.Set(0.0)
                p = bip(col, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
                        "Comments")
                if p is not None and not p.IsReadOnly:
                    p.Set(MARCA)

                hechas.append({"origen": m["id"], "nueva": eidv(col.Id),
                               "tipo": m["tipo"], "base": base_lv.Name,
                               "top": top_lv.Name, "acero": len(nuevos) - 1})
            t.Commit()
            result["creadas"].extend(hechas)
            result["por_tramo"]["%s->%s" % (base_lv.Name, top_lv.Name)] = len(hechas)
            trace("  OK: %d creadas" % len(hechas))
        except Exception as ex:
            t.RollBack()
            result["fallos"].append({"tramo": "%s->%s" % (base_lv.Name, top_lv.Name),
                                     "motivo": str(ex)})
            result["por_tramo"]["%s->%s" % (base_lv.Name, top_lv.Name)] = 0
            trace("  ROLLBACK: %s" % traceback.format_exc())

    # ---- Fase 5: verificar releyendo -------------------------------------
    result["phase_reached"] = "fase5_verificacion"
    idx = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            h = eidv(rb.GetHostId())
            idx[h] = idx.get(h, 0) + 1
        except Exception:
            continue
    marcadas = 0
    marcadas_con_acero = 0
    total_col = 0
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        total_col += 1
        p = bip(el, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
        if p is not None and p.AsString() == MARCA:
            marcadas += 1
            if idx.get(eidv(el.Id), 0) > 0:
                marcadas_con_acero += 1
    result["verificacion"] = {
        "columnas_totales": total_col,
        "replicas_marcadas": marcadas,
        "replicas_con_acero": marcadas_con_acero,
        "creadas_reportadas": len(result["creadas"]),
        "coincide": (marcadas == len(result["creadas"])
                     and marcadas_con_acero == marcadas),
    }
    trace("FASE 5 OK: %s" % json.dumps(result["verificacion"]))

    result["phase_reached"] = "completo"
    result["ok"] = not result["fallos"] and result["verificacion"]["coincide"]

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Replicar columnas a niveles superiores")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
if result["previos_borrados"]:
    out.print_md("- Limpieza previa: %d elementos" % result["previos_borrados"])
out.print_md("- Maestras detectadas: **%d**" % len(result["maestras"]))
out.print_md("- Columnas creadas: **%d**" % len(result["creadas"]))
v = result.get("verificacion")
if v:
    out.print_md("- En modelo: **%d** columnas | replicas: **%d** (con acero: **%d**)"
                 % (v["columnas_totales"], v["replicas_marcadas"],
                    v["replicas_con_acero"]))
    out.print_md("- **coincide: %s**" % v["coincide"])
if result["fallos"]:
    out.print_md("- ⚠️ **fallos: %d** — ver JSON" % len(result["fallos"]))
out.print_md("- **ok: %s**" % result["ok"])
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
