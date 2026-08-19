# -*- coding: utf-8 -*-
"""Colorea el acero por diametro y forma en la vista activa (o en 3D - ACERO).

CRITERIO DE COLOR
-----------------
- **Tono base = diametro de barra**. Es el dato que manda en un despiece:
  saber si una barra es #6 o #11 cambia todo.
- **Saturacion = forma**. Las rectas (forma `00`, longitudinales) van en el
  tono pleno; los estribos y ganchos (`01`, `T1`, y demas) van aclarados.
  Asi de un vistazo se separan longitudinales de transversales sin perder la
  lectura del diametro.

POR QUE OVERRIDES POR ELEMENTO Y NO FILTROS DE VISTA
-----------------------------------------------------
Un `ParameterFilterElement` seria mas elegante —aparece en Visibility/Graphics
y alcanza a las barras que se creen despues— pero exige acertar que parametro
es filtrable para la categoria Rebar en esta version, y eso no esta volcado.
Los overrides por elemento usan solo `OverrideGraphicSettings` +
`SetElementOverrides`, API simple y verificable.

Contrapartida honesta: **las barras que se creen despues NO quedan coloreadas**.
Hay que volver a apretar el boton. Es idempotente, asi que no cuesta.

Tambien diagnostica `SetSolidInView`, que en la corrida anterior fallo en las
283 barras sin dejar dicho por que.

SOLO afecta la vista: no toca la geometria ni el modelo.
"""
__title__ = "ColorAcero"
__doc__ = "Colorea el acero por diametro (tono) y forma (saturacion) en la vista."

import os
import json
import traceback

from pyrevit import revit, script
from pyrevit.api import DB

doc = revit.doc
uidoc = revit.uidoc

NOMBRE_VISTA_PREF = "3D - ACERO"

# --- paleta por diametro. Tonos bien separados en el circulo cromatico -----
COLORES = {
    "#3":  (220,  30,  30),    # rojo
    "#4":  (255, 130,   0),    # naranja
    "#5":  (225, 200,   0),    # amarillo
    "#6":  ( 30, 170,  60),    # verde
    "#7":  (  0, 170, 170),    # turquesa
    "#8":  ( 30,  90, 220),    # azul
    "#9":  (130,  60, 200),    # violeta
    "#10": (220,  40, 160),    # magenta
    "#11": (120,  70,  30),    # marron
    "#14": ( 90,  90,  90),    # gris
    "#18": ( 20,  20,  20),    # casi negro
}
COLOR_DEFECTO = (150, 150, 150)

FORMAS_RECTAS = ("00", "0")


def aclarar(rgb, factor=0.55):
    """Mezcla con blanco. Se usa para los estribos: mismo tono, menos peso."""
    return tuple(int(c + (255 - c) * factor) for c in rgb)


def _slug(txt):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_"
                   for ch in (txt or "SIN_DOC"))[:60]


BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "color_acero_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "color_acero_%s.json" % _slug(doc.Title))

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


def eidv(e):
    try:
        return int(e.Value)
    except AttributeError:
        return int(e.IntegerValue)


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
    "ok": False, "phase_reached": "inicio", "document": doc.Title,
    "vista": None, "coloreadas": 0, "leyenda": {},
    "solid_ok": 0, "errores_solid": {}, "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: elegir la vista -----------------------------------------
    result["phase_reached"] = "fase1_vista"
    vista = None
    for v in (DB.FilteredElementCollector(doc).OfClass(DB.View3D)
              .WhereElementIsNotElementType()):
        if element_name(v) == NOMBRE_VISTA_PREF and not v.IsTemplate:
            vista = v
            break
    if vista is None:
        vista = doc.ActiveView
    if vista is None or vista.IsTemplate:
        raise Exception("no hay vista utilizable: abri '3D - ACERO' o una vista 3D")
    result["vista"] = element_name(vista)
    trace("FASE 1 OK: vista '%s' (id %d)" % (result["vista"], eidv(vista.Id)))

    # ---- Fase 2: clasificar las barras ------------------------------------
    result["phase_reached"] = "fase2_clasificacion"
    barras = list(DB.FilteredElementCollector(doc)
                  .OfCategory(DB.BuiltInCategory.OST_Rebar)
                  .WhereElementIsNotElementType())
    trace("FASE 2: %d barras" % len(barras))

    plan = []          # (elemento, rgb, clave_leyenda)
    for rb in barras:
        bt = doc.GetElement(rb.GetTypeId())
        nom = element_name(bt) or "?"
        forma = None
        try:
            p = rb.LookupParameter("Shape Name")
            forma = p.AsString() if p is not None else None
        except Exception:
            pass
        base = COLORES.get(nom, COLOR_DEFECTO)
        recta = (forma or "") in FORMAS_RECTAS
        rgb = base if recta else aclarar(base)
        clave = "%s %s" % (nom, "recta" if recta else "estribo/otro")
        plan.append((rb, rgb, clave))
        result["leyenda"][clave] = {"rgb": list(rgb),
                                    "n": result["leyenda"].get(clave, {}).get("n", 0) + 1}
    trace("FASE 2 OK: %d combinaciones" % len(result["leyenda"]))

    # ---- Fase 3: aplicar overrides ----------------------------------------
    result["phase_reached"] = "fase3_overrides"
    t = DB.Transaction(doc, "MCP: colorear acero")
    t.Start()
    try:
        solido = DB.FillPatternElement.GetFillPatternElementByName(
            doc, DB.FillPatternTarget.Drafting, "<Solid fill>")
        for rb, rgb, _ in plan:
            ogs = DB.OverrideGraphicSettings()
            col = DB.Color(rgb[0], rgb[1], rgb[2])
            ogs.SetProjectionLineColor(col)
            ogs.SetCutLineColor(col)
            try:
                ogs.SetSurfaceForegroundPatternColor(col)
                ogs.SetCutForegroundPatternColor(col)
                if solido is not None:
                    ogs.SetSurfaceForegroundPatternId(solido.Id)
                    ogs.SetCutForegroundPatternId(solido.Id)
                    ogs.SetSurfaceForegroundPatternVisible(True)
                    ogs.SetCutForegroundPatternVisible(True)
            except Exception:
                pass
            ogs.SetProjectionLineWeight(4)
            vista.SetElementOverrides(rb.Id, ogs)
            result["coloreadas"] += 1
        t.Commit()
    except Exception as ex:
        t.RollBack()
        raise Exception("no se pudieron aplicar los overrides: %s" % ex)
    trace("FASE 3 OK: %d coloreadas" % result["coloreadas"])

    # ---- Fase 4: acero solido, con el error a la vista --------------------
    result["phase_reached"] = "fase4_solido"
    t = DB.Transaction(doc, "MCP: acero solido")
    t.Start()
    try:
        for rb in barras:
            m = getattr(rb, "SetSolidInView", None)
            if m is None:
                continue
            try:
                m(vista, True)
                result["solid_ok"] += 1
            except Exception as ex:
                k = "%s: %s" % (type(ex).__name__, ex)
                result["errores_solid"][k] = result["errores_solid"].get(k, 0) + 1
        t.Commit()
    except Exception as ex:
        t.RollBack()
        trace("FASE 4: transaccion revertida: %s" % ex)
    for k, v in result["errores_solid"].items():
        trace("  SetSolidInView fallo x%d: %s" % (v, k))
    trace("FASE 4 OK: solido %d de %d" % (result["solid_ok"], len(barras)))

    result["phase_reached"] = "completo"
    result["ok"] = result["coloreadas"] == len(barras)

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Color del acero")
out.print_md("- Vista: `%s`" % result["vista"])
out.print_md("- Barras coloreadas: **%d**" % result["coloreadas"])
out.print_md("- Solido: %d de %d" % (result["solid_ok"], result["coloreadas"]))
for k, v in result["errores_solid"].items():
    out.print_md("  - ⚠️ `%s` x%d" % (k[:110], v))
out.print_md("**Leyenda**")
for k in sorted(result["leyenda"]):
    d = result["leyenda"][k]
    r, g, b = d["rgb"]
    out.print_md("- `%s` — RGB(%d,%d,%d) — %d barras" % (k, r, g, b, d["n"]))
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
