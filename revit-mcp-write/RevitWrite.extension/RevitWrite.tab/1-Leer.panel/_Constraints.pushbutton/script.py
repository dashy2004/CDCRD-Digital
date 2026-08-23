# -*- coding: utf-8 -*-
"""Analiza los constraints de los Rebar del documento y escribe el resultado
a JSON en disco.

POR QUE ES UN BOTON Y NO UN ENDPOINT
------------------------------------
El 2026-08-13 este mismo analisis, puesto dentro del handler GET /rebar de
pyRevit Routes, tumbo Revit (ERRORES-IA E-049). Hipotesis: los handlers de
Routes corren fuera del contexto de API de Revit, y `RebarConstraintsManager`
no es un lector puro sino el objeto de edicion de constraints (es IDisposable
y expone ApplyRebarConstraints). Instanciarlo 65 veces desde ese hilo mata el
proceso sin excepcion manejable.

Un pushbutton de pyRevit corre en el hilo de UI con contexto de API valido,
que es donde esta API espera ser usada. El resultado sale por archivo, no por
HTTP, asi que el agente lo lee del disco sin tocar el hilo de Revit.

LOG INCREMENTAL CON FSYNC
-------------------------
Un crash duro se lleva el buffer de escritura. Cada paso hace flush + fsync
ANTES de la llamada riesgosa, no despues. Si Revit vuelve a caer, la ultima
linea del log dice exactamente en que set y en que llamada murio, que es la
diferencia entre un diagnostico y otra ronda de adivinanza (E-040).
"""
__title__ = "Constraints"
__doc__ = "Vuelca el estado de constraints de los Rebar a _log/constraints.json"

import os
import json
import traceback

from pyrevit import revit, script
from pyrevit.api import DB

doc = revit.doc

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "constraints_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "constraints.json")

out = script.get_output()


def trace(msg):
    """Escribe y FUERZA a disco. Si Revit muere en la linea siguiente,
    esta ya esta grabada."""
    with open(TRACE, "a") as fh:
        fh.write("%s\n" % msg)
        fh.flush()
        os.fsync(fh.fileno())


# Empezar limpio para que la ultima linea sea inequivoca
try:
    if os.path.isfile(TRACE):
        os.remove(TRACE)
except Exception:
    pass

trace("=== inicio ===")

result = {
    "ok": False,
    "phase_reached": "inicio",
    "constrained_placement_enabled": None,
    "constrained_placement_error": None,
    "sets": [],
    "error": None,
}


def get_param(el, name):
    p = el.LookupParameter(name)
    if p is None:
        return None
    st = p.StorageType
    if st == DB.StorageType.String:
        return p.AsString()
    if st == DB.StorageType.Integer:
        return p.AsInteger()
    if st == DB.StorageType.Double:
        return p.AsDouble()
    return None


def value_string(el, name):
    """Texto legible del parametro (AsValueString). Para enums como
    Layout Rule: mapear el int crudo contra una tabla de enum recordada
    seria E-042."""
    try:
        p = el.LookupParameter(name)
        return p.AsValueString() if p is not None else None
    except Exception:
        return None


def digest(el, eid_int):
    d = {
        "id": eid_int,
        # --- identidad, para poder cruzar sin depender del puente HTTP ---
        "host_id": None,
        "host_mark": get_param(el, "Host Mark"),
        "schedule_mark": get_param(el, "Schedule Mark"),
        "shape": get_param(el, "Shape Name"),
        "quantity": get_param(el, "Quantity"),
        "bar_length_ft": get_param(el, "Bar Length"),
        "layout_rule": value_string(el, "Layout Rule"),
        "spacing_ft": get_param(el, "Spacing"),
        # --- constraints ---
        "shape_driven": None,
        "constraints_editable": None,
        "handles_total": None,
        "handles_constrained": None,
        "host_face_types": {},
        "constraint_types": {},
        "error": None,
    }
    mgr = None
    try:
        try:
            d["host_id"] = int(el.GetHostId().Value)
        except Exception:
            pass

        trace("  %d: IsRebarShapeDriven" % eid_int)
        d["shape_driven"] = bool(el.IsRebarShapeDriven())

        trace("  %d: ConstraintsCanBeEdited" % eid_int)
        d["constraints_editable"] = bool(el.ConstraintsCanBeEdited())

        trace("  %d: GetRebarConstraintsManager" % eid_int)
        mgr = el.GetRebarConstraintsManager()
        if mgr is None:
            d["error"] = "GetRebarConstraintsManager devolvio None"
            return d

        trace("  %d: GetAllHandles" % eid_int)
        all_h = mgr.GetAllHandles()
        trace("  %d: GetAllConstrainedHandles" % eid_int)
        con_h = mgr.GetAllConstrainedHandles()
        d["handles_total"] = int(all_h.Count)
        d["handles_constrained"] = int(con_h.Count)
        trace("  %d: handles %d/%d" % (eid_int, d["handles_constrained"],
                                       d["handles_total"]))

        for i, h in enumerate(con_h):
            trace("  %d: GetCurrentConstraintOnHandle %d" % (eid_int, i))
            c = mgr.GetCurrentConstraintOnHandle(h)
            if c is None:
                continue
            try:
                ct = str(c.GetConstraintType())
            except Exception:
                ct = "<error>"
            d["constraint_types"][ct] = d["constraint_types"].get(ct, 0) + 1
            try:
                ft = str(c.GetRebarConstraintTargetHostFaceType())
            except Exception:
                ft = "<no-host-face>"
            d["host_face_types"][ft] = d["host_face_types"].get(ft, 0) + 1
    except Exception as ex:
        d["error"] = "%s: %s" % (type(ex).__name__, ex)
        trace("  %d: EXCEPCION %s" % (eid_int, d["error"]))
    # NO llamar mgr.Dispose(). RebarConstraintsManager es IDisposable, pero su
    # ciclo de vida lo gestiona Revit: disponerlo a mano deja estado interno
    # colgando y el proceso revienta MINUTOS DESPUES, ya fuera de este script.
    # Dos caidas de Revit el 2026-08-13/14 siguieron a corridas COMPLETAS de
    # este boton (ok=True, JSON escrito) — el retardo es justo lo que hace que
    # el sintoma no apunte a su causa. Hipotesis con experimento: sin Dispose,
    # no deberia volver a caer.
    return d


try:
    # ---- Fase 1: flag estatico de documento (1 sola llamada) -----------
    result["phase_reached"] = "fase1_flag_estatico"
    trace("FASE 1: IsRebarConstrainedPlacementEnabled")
    try:
        result["constrained_placement_enabled"] = bool(
            DB.Structure.RebarConstraintsManager
            .IsRebarConstrainedPlacementEnabled
        )
        trace("FASE 1 OK: %s" % result["constrained_placement_enabled"])
    except Exception as ex:
        result["constrained_placement_error"] = str(ex)
        trace("FASE 1 ERROR: %s" % ex)

    # ---- Fase 2: recoleccion (sin tocar constraints) -------------------
    result["phase_reached"] = "fase2_recoleccion"
    trace("FASE 2: recolectando rebar")
    bars = list(
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_Rebar)
        .WhereElementIsNotElementType()
    )
    trace("FASE 2 OK: %d sets" % len(bars))

    # ---- Fase 3: UN set primero ---------------------------------------
    # Si el manager tumba Revit, que se lleve una sola llamada y no 65.
    result["phase_reached"] = "fase3_primer_set"
    trace("FASE 3: primer set")
    first = bars[0]
    fid = int(first.Id.Value)
    result["sets"].append(digest(first, fid))
    trace("FASE 3 OK")

    # ---- Fase 4: el resto ---------------------------------------------
    result["phase_reached"] = "fase4_resto"
    trace("FASE 4: los %d restantes" % (len(bars) - 1))
    for el in bars[1:]:
        result["sets"].append(digest(el, int(el.Id.Value)))
    trace("FASE 4 OK")

    result["phase_reached"] = "completo"
    result["ok"] = True

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

# Escribir SIEMPRE, completo o no. Un volcado parcial con phase_reached
# es un dato; un archivo ausente no dice nada.
with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase_reached=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Constraints")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
out.print_md("- Placement habilitado: `%s`" % result["constrained_placement_enabled"])
out.print_md("- Sets analizados: **%d**" % len(result["sets"]))
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- **ERROR**: ver trace")
