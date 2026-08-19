# -*- coding: utf-8 -*-
"""Crea una vista 3D donde el acero se ve solido y el hormigon translucido.

QUE HACE
--------
Vista 3D isometrica llamada `3D - ACERO`:
  - hormigon (columnas, cimentaciones, vigas, losas, muros) al 90% de
    transparencia, casi fantasma, solo como referencia de contorno
  - acero de refuerzo visible, solido y sin ocultar
  - nivel de detalle Fino: sin esto el acero no se dibuja con su geometria real

POR QUE EL ACERO NO SE VE POR DEFECTO
--------------------------------------
En Revit el `Rebar` tiene estados de visibilidad POR VISTA, ademas de la
visibilidad de categoria. Aunque la categoria este encendida y el hormigon sea
transparente, cada barra puede seguir dibujandose como linea o quedar oculta
detras del solido. Los metodos que lo resuelven son
`SetSolidInView(View3D, bool)` y `SetUnobscuredInView(View, bool)`, aplicados
barra por barra.

Esos dos metodos se resuelven con getattr y se reportan si no existen en esta
version: no se referencian directo (E-040/E-052 — un nombre de la API que no
existe, escrito como referencia literal, mata el script antes de cualquier
manejo de error).

IDEMPOTENTE
-----------
Si ya existe una vista con ese nombre la reutiliza en vez de crear una
segunda. Se puede apretar las veces que haga falta.
"""
__title__ = "VistaAcero"
__doc__ = "Vista 3D con el acero solido y el hormigon al 90% de transparencia."

import os
import json
import traceback

from pyrevit import revit, script
from pyrevit.api import DB

doc = revit.doc

NOMBRE_VISTA = "3D - ACERO"
TRANSPARENCIA = 90          # 0..100

# Categorias de hormigon que se vuelven translucidas
CATS_HORMIGON = [
    "OST_StructuralColumns",
    "OST_StructuralFoundation",
    "OST_StructuralFraming",
    "OST_Floors",
    "OST_Walls",
    "OST_GenericModel",
]

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "vista_acero_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "vista_acero.json")

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


result = {
    "ok": False,
    "phase_reached": "inicio",
    "document": doc.Title,
    "vista": {},
    "categorias_translucidas": [],
    "categorias_no_halladas": [],
    "acero": {"total": 0, "solid_ok": 0, "unobscured_ok": 0},
    "metodos_disponibles": {},
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: comprobar que la API de visibilidad exista -------------
    result["phase_reached"] = "fase1_api"
    trace("FASE 1: metodos de visibilidad de Rebar")
    for nombre in ("SetSolidInView", "SetUnobscuredInView",
                   "IsSolidInView", "IsUnobscuredInView"):
        existe = hasattr(DB.Structure.Rebar, nombre)
        result["metodos_disponibles"][nombre] = existe
        trace("  %s: %s" % (nombre, existe))

    # ---- Fase 2: obtener o crear la vista -------------------------------
    result["phase_reached"] = "fase2_vista"
    trace("FASE 2: vista '%s'" % NOMBRE_VISTA)

    vista = None
    for v in (DB.FilteredElementCollector(doc).OfClass(DB.View3D)
              .WhereElementIsNotElementType()):
        if element_name(v) == NOMBRE_VISTA and not v.IsTemplate:
            vista = v
            break

    if vista is not None:
        result["vista"] = {"id": eidv(vista.Id), "nombre": NOMBRE_VISTA,
                           "reutilizada": True}
        trace("FASE 2: la vista ya existia, se reutiliza (id %d)" % eidv(vista.Id))
    else:
        # tipo de vista 3D: prerrequisito, si no hay se aborta
        vft = None
        for f in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
            if f.ViewFamily == DB.ViewFamily.ThreeDimensional:
                vft = f
                break
        if vft is None:
            raise Exception("no hay ViewFamilyType 3D en el proyecto")

        t = DB.Transaction(doc, "MCP: crear vista 3D de acero")
        t.Start()
        try:
            vista = DB.View3D.CreateIsometric(doc, vft.Id)
            try:
                vista.Name = NOMBRE_VISTA
            except Exception:
                # nombre en uso por una vista de otro tipo
                vista.Name = NOMBRE_VISTA + " (MCP)"
            t.Commit()
        except Exception as ex:
            t.RollBack()
            raise Exception("no se pudo crear la vista: %s" % ex)
        result["vista"] = {"id": eidv(vista.Id), "nombre": element_name(vista),
                           "reutilizada": False}
        trace("FASE 2 OK: creada id %d" % eidv(vista.Id))

    # ---- Fase 3: detalle fino + transparencias --------------------------
    result["phase_reached"] = "fase3_overrides"
    trace("FASE 3: detalle fino y transparencias")
    t = DB.Transaction(doc, "MCP: overrides de vista de acero")
    t.Start()
    try:
        # Sin detalle Fino el acero no dibuja su geometria real
        try:
            vista.DetailLevel = DB.ViewDetailLevel.Fine
        except Exception as ex:
            trace("  no se pudo fijar DetailLevel: %s" % ex)

        for cat_nombre in CATS_HORMIGON:
            bic = getattr(DB.BuiltInCategory, cat_nombre, None)
            if bic is None:
                result["categorias_no_halladas"].append(cat_nombre)
                continue
            cat = DB.Category.GetCategory(doc, bic)
            if cat is None:
                result["categorias_no_halladas"].append(cat_nombre)
                continue
            try:
                ogs = DB.OverrideGraphicSettings()
                ogs.SetSurfaceTransparency(TRANSPARENCIA)
                vista.SetCategoryOverrides(cat.Id, ogs)
                result["categorias_translucidas"].append(cat_nombre)
            except Exception as ex:
                trace("  %s: no se pudo aplicar override: %s" % (cat_nombre, ex))
                result["categorias_no_halladas"].append(cat_nombre)

        # la categoria de acero, encendida sin transparencia
        bic_rb = getattr(DB.BuiltInCategory, "OST_Rebar", None)
        if bic_rb is not None:
            cat_rb = DB.Category.GetCategory(doc, bic_rb)
            if cat_rb is not None:
                try:
                    vista.SetCategoryHidden(cat_rb.Id, False)
                except Exception as ex:
                    trace("  no se pudo mostrar OST_Rebar: %s" % ex)
        t.Commit()
    except Exception as ex:
        t.RollBack()
        raise Exception("no se pudieron aplicar los overrides: %s" % ex)
    trace("FASE 3 OK: %d categorias translucidas" % len(result["categorias_translucidas"]))

    # ---- Fase 4: acero solido y sin ocultar, barra por barra ------------
    result["phase_reached"] = "fase4_acero"
    barras = list(DB.FilteredElementCollector(doc)
                  .OfCategory(DB.BuiltInCategory.OST_Rebar)
                  .WhereElementIsNotElementType())
    result["acero"]["total"] = len(barras)
    trace("FASE 4: %d barras" % len(barras))

    t = DB.Transaction(doc, "MCP: acero solido en vista")
    t.Start()
    try:
        # Los errores se REGISTRAN, no se tragan. En la corrida del 2026-08-14
        # SetSolidInView fallo en las 283 barras y el script solo informo
        # "solid: 0", sin decir por que: un except vacio convierte un
        # diagnostico en un misterio.
        errores_solid = {}
        errores_unobs = {}
        for rb in barras:
            m = getattr(rb, "SetSolidInView", None)
            if m is not None:
                try:
                    m(vista, True)
                    result["acero"]["solid_ok"] += 1
                except Exception as ex:
                    k = "%s: %s" % (type(ex).__name__, ex)
                    errores_solid[k] = errores_solid.get(k, 0) + 1
            m = getattr(rb, "SetUnobscuredInView", None)
            if m is not None:
                try:
                    m(vista, True)
                    result["acero"]["unobscured_ok"] += 1
                except Exception as ex:
                    k = "%s: %s" % (type(ex).__name__, ex)
                    errores_unobs[k] = errores_unobs.get(k, 0) + 1
        result["acero"]["errores_solid"] = errores_solid
        result["acero"]["errores_unobscured"] = errores_unobs
        for k, v in errores_solid.items():
            trace("  SetSolidInView fallo x%d: %s" % (v, k))
        for k, v in errores_unobs.items():
            trace("  SetUnobscuredInView fallo x%d: %s" % (v, k))
        t.Commit()
    except Exception as ex:
        t.RollBack()
        raise Exception("no se pudo fijar la visibilidad del acero: %s" % ex)
    trace("FASE 4 OK: solido %d, sin ocultar %d"
          % (result["acero"]["solid_ok"], result["acero"]["unobscured_ok"]))

    result["phase_reached"] = "completo"
    result["ok"] = (result["acero"]["solid_ok"] == result["acero"]["total"]
                    and len(result["categorias_translucidas"]) > 0)

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Vista de acero")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
v = result["vista"]
if v:
    out.print_md("- Vista: `%s` (%s)"
                 % (v.get("nombre"), "reutilizada" if v.get("reutilizada") else "creada"))
out.print_md("- Categorias al %d%% de transparencia: **%d**"
             % (TRANSPARENCIA, len(result["categorias_translucidas"])))
a = result["acero"]
out.print_md("- Acero: **%d** barras | solido: %d | sin ocultar: %d"
             % (a["total"], a["solid_ok"], a["unobscured_ok"]))
for etq, clave in (("solido", "errores_solid"), ("sin ocultar", "errores_unobscured")):
    for k, v in (a.get(clave) or {}).items():
        out.print_md("  - ⚠️ %s fallo x%d: `%s`" % (etq, v, k[:110]))
if result["categorias_no_halladas"]:
    out.print_md("- No aplicadas: %s" % ", ".join(result["categorias_no_halladas"]))
out.print_md("- **ok: %s**" % result["ok"])
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
