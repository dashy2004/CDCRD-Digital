# -*- coding: utf-8 -*-
"""Borra las columnas metalicas (W Shapes-Column) y las '12 x 18'.

CUANDO CORRERLO
---------------
DESPUES de `Reemplazo` y despues de verificar visualmente que las columnas
de hormigon quedaron bien. Este es el paso irreversible del flujo.

QUE BORRA — POR IDENTIDAD, NO POR LISTA DE IDS
----------------------------------------------
1. Toda instancia cuya familia sea EXACTAMENTE `W Shapes-Column`.
2. Toda instancia de `Concrete-Rectangular-Column` cuyo tipo sea
   EXACTAMENTE `12 x 18` (los 26 duplicados posicionales de E-045).

NO toca: las 13 maestras de CIMENTACIONES (tipos C1..C7), ni nada marcado
`MCP:reemplazo-columnas` (la obra nueva), ni ninguna otra categoria.

GUARDAS (de ERRORES-IA E-041, E-043, E-044, E-046)
--------------------------------------------------
- El conteo esperado se calcula ANTES de borrar y se muestra. Si no coincide
  con lo previsto (192 + 26 = 218 en la primera corrida), abortar es un click:
  el script pide confirmacion via TaskDialog con los numeros a la vista.
- La identidad se verifica por familia/tipo leidos del elemento, nunca por
  nombre parcial ni por posicion.
- Verificacion posterior POR RELECTURA: cuenta lo que quedo, no lo que pidio.
- Una transaccion unica: el borrado es todo-o-nada a proposito — un borrado
  parcial deja el modelo en un estado que nadie pidio.
- Log incremental con fsync. JSON siempre, completo o no.
"""
__title__ = "Borrado"
__doc__ = "Borra W Shapes-Column y '12 x 18'. Correr DESPUES de verificar el Reemplazo."

import os
import json
import traceback

from pyrevit import revit, script, forms
from pyrevit.api import DB
from System.Collections.Generic import List

doc = revit.doc

MARCA_REEMPLAZO = "MCP:reemplazo-columnas"

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "borrado_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "borrado.json")

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


def comments(el):
    try:
        p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p is None:
            p = el.LookupParameter("Comments")
        return p.AsString() if p is not None else None
    except Exception:
        return None


result = {
    "ok": False,
    "phase_reached": "inicio",
    "document": doc.Title,
    "a_borrar": {"w_shapes": 0, "doce_por_dieciocho": 0},
    "protegidas": {"maestras": 0, "reemplazo": 0},
    "confirmado_por_operador": False,
    "borrados_con_dependientes": 0,
    "quedan": {},
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: clasificar TODO por identidad --------------------------
    result["phase_reached"] = "fase1_clasificacion"
    trace("FASE 1: clasificando columnas por familia/tipo")
    objetivo = []
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
        tname = element_name(sym) or ""

        if fam == "W Shapes-Column":
            objetivo.append(el.Id)
            result["a_borrar"]["w_shapes"] += 1
        elif fam == "Concrete-Rectangular-Column" and tname == "12 x 18":
            objetivo.append(el.Id)
            result["a_borrar"]["doce_por_dieciocho"] += 1
        elif comments(el) == MARCA_REEMPLAZO:
            result["protegidas"]["reemplazo"] += 1
        elif fam == "Concrete-Rectangular-Column":
            result["protegidas"]["maestras"] += 1

    total = len(objetivo)
    trace("FASE 1 OK: a borrar %d (W=%d, 12x18=%d) | protegidas: reemplazo=%d, otras concreto=%d"
          % (total, result["a_borrar"]["w_shapes"],
             result["a_borrar"]["doce_por_dieciocho"],
             result["protegidas"]["reemplazo"], result["protegidas"]["maestras"]))

    if total == 0:
        raise Exception("no hay nada que borrar: 0 columnas W / 12x18 en el modelo")

    # ---- Fase 2: confirmacion del operador con los numeros a la vista ---
    result["phase_reached"] = "fase2_confirmacion"
    msg = ("Se van a borrar %d columnas:\n\n"
           "  - W Shapes-Column: %d\n"
           "  - Concrete '12 x 18': %d\n\n"
           "Quedan protegidas:\n"
           "  - columnas del Reemplazo (marcadas): %d\n"
           "  - otras de concreto (maestras): %d\n\n"
           "El borrado es UNA transaccion (todo o nada) e IRREVERSIBLE\n"
           "salvo por Ctrl+Z inmediato o por no guardar.\n\n"
           "¿Borrar?" % (total, result["a_borrar"]["w_shapes"],
                         result["a_borrar"]["doce_por_dieciocho"],
                         result["protegidas"]["reemplazo"],
                         result["protegidas"]["maestras"]))
    if not forms.alert(msg, title="Borrado de metalicas",
                       yes=True, no=True, warn_icon=True):
        trace("FASE 2: operador CANCELO")
        result["error"] = "cancelado por el operador"
        raise SystemExit
    result["confirmado_por_operador"] = True
    trace("FASE 2 OK: confirmado")

    # ---- Fase 3: borrar, transaccion unica ------------------------------
    result["phase_reached"] = "fase3_borrado"
    trace("FASE 3: borrando %d elementos" % total)
    t = DB.Transaction(doc, "MCP: borrar columnas metalicas y 12x18")
    t.Start()
    try:
        ids = List[DB.ElementId]()
        for i in objetivo:
            ids.Add(i)
        borrados = doc.Delete(ids)
        t.Commit()
        result["borrados_con_dependientes"] = len(borrados) if borrados else 0
        trace("FASE 3 OK: %d elementos (incluye dependientes en cascada)"
              % result["borrados_con_dependientes"])
    except Exception as ex:
        t.RollBack()
        raise Exception("excepcion al borrar, transaccion revertida: %s" % ex)

    # ---- Fase 4: verificar RELEYENDO ------------------------------------
    result["phase_reached"] = "fase4_verificacion"
    trace("FASE 4: relectura")
    quedan = {"w_shapes": 0, "doce_por_dieciocho": 0,
              "reemplazo": 0, "concreto_otras": 0, "total_columnas": 0}
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        quedan["total_columnas"] += 1
        sym = doc.GetElement(el.GetTypeId())
        if sym is None:
            continue
        try:
            fam = sym.Family.Name
        except Exception:
            continue
        tname = element_name(sym) or ""
        if fam == "W Shapes-Column":
            quedan["w_shapes"] += 1
        elif fam == "Concrete-Rectangular-Column" and tname == "12 x 18":
            quedan["doce_por_dieciocho"] += 1
        elif comments(el) == MARCA_REEMPLAZO:
            quedan["reemplazo"] += 1
        elif fam == "Concrete-Rectangular-Column":
            quedan["concreto_otras"] += 1

    rebar_total = (DB.FilteredElementCollector(doc)
                   .OfCategory(DB.BuiltInCategory.OST_Rebar)
                   .WhereElementIsNotElementType()
                   .GetElementCount())
    quedan["rebar_total"] = rebar_total
    result["quedan"] = quedan
    trace("FASE 4 OK: %s" % json.dumps(quedan))

    result["phase_reached"] = "completo"
    result["ok"] = (quedan["w_shapes"] == 0
                    and quedan["doce_por_dieciocho"] == 0
                    and quedan["reemplazo"] > 0)

except SystemExit:
    pass
except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Borrado de metalicas")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
out.print_md("- A borrar detectadas: W=%d, 12x18=%d" % (
    result["a_borrar"]["w_shapes"], result["a_borrar"]["doce_por_dieciocho"]))
if result["confirmado_por_operador"]:
    out.print_md("- Borrados (con dependientes): **%d**" % result["borrados_con_dependientes"])
    q = result["quedan"]
    if q:
        out.print_md("- Quedan: W=**%d**, 12x18=**%d**, reemplazo=**%d**, "
                     "otras concreto=**%d**, rebar=**%d**"
                     % (q["w_shapes"], q["doce_por_dieciocho"], q["reemplazo"],
                        q["concreto_otras"], q["rebar_total"]))
    out.print_md("- **ok: %s**" % result["ok"])
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"] and result["error"] != "cancelado por el operador":
    out.print_md("- ❌ **ERROR** — ver trace")
