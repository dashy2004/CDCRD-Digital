# -*- coding: utf-8 -*-
"""Diagnostico previo al solape: geometria real de las barras longitudinales.

SOLO LECTURA. No modifica nada.

POR QUE HACE FALTA
------------------
El solape a media altura exige RECONSTRUIR las longitudinales: hoy van de losa
a losa y tienen que pasar a ir de media altura a media altura, mas la longitud
de solape. Reconstruir significa borrar cada set y crear uno nuevo con la misma
distribucion en la seccion pero otra curva.

Para eso hace falta saber COMO esta puesta cada barra hoy: su curva real, la
normal de su plano, y los parametros de su layout. Nada de eso se volco todavia,
y recrear sin conocerlo seria inventar la distribucion — el modo de fallo que
en esta sesion ya costo dos correcciones (E-042, E-052).

QUE VUELCA
----------
Por cada set longitudinal (forma recta) de las columnas:
  - curvas de eje (`GetCenterlineCurves`) con sus extremos y longitud
  - normal del plano de la barra, si el accessor la expone
  - layout: regla, cantidad, espaciamiento, longitud de array
  - constraints por handle: tipo y cara del anfitrion
  - cota del host (base y tope) para ubicar la barra dentro de su tramo

Y ademas vuelca la FIRMA de los metodos de geometria que hagan falta para
recrear, resueltos por getattr y reportados si no existen en esta version.

Se limita a `MAX_COLUMNAS` para que la salida sea legible: con una muestra
alcanza para disenar, y el lote completo se procesa despues.
"""
__title__ = "SolapeDiag"
__doc__ = "Vuelca la geometria real de las longitudinales. Solo lectura. Previo al solape."

import os
import clr
import json
import traceback

from pyrevit import revit, script
from pyrevit.api import DB

doc = revit.doc
M = 0.3048
MAX_COLUMNAS = 3          # muestra: alcanza para disenar la recreacion


def _slug(txt):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_"
                   for ch in (txt or "SIN_DOC"))[:60]


BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "solape_diag_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "solape_diag_%s.json" % _slug(doc.Title))

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


def par(el, nombre):
    try:
        p = el.LookupParameter(nombre)
        if p is None:
            return None
        st = p.StorageType
        if st == DB.StorageType.Double:
            return p.AsDouble()
        if st == DB.StorageType.Integer:
            return p.AsInteger()
        if st == DB.StorageType.String:
            return p.AsString()
        return p.AsValueString()
    except Exception:
        return None


result = {
    "ok": False,
    "phase_reached": "inicio",
    "document": doc.Title,
    "api": {},
    "columnas": [],
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: firma de los metodos de geometria ----------------------
    # Resueltos por nombre y reportados si faltan: referenciarlos directo es
    # lo que rompio el volcado anterior (E-052).
    result["phase_reached"] = "fase1_api"
    trace("FASE 1: firma de metodos de geometria")
    for nombre in ("GetCenterlineCurves", "GetShapeDrivenAccessor",
                   "GetFullGeometryForView", "ComputeDrivingCurves",
                   "GetBarTerminationsData", "SetBarTerminationsData",
                   "GetHookTypeId", "GetDistanceToHostFace"):
        result["api"][nombre] = hasattr(DB.Structure.Rebar, nombre)
        trace("  Rebar.%s: %s" % (nombre, result["api"][nombre]))

    try:
        ct = clr.GetClrType(DB.Structure.Rebar)
        firmas = []
        for m in ct.GetMethods():
            if m.Name in ("GetCenterlineCurves", "ComputeDrivingCurves"):
                firmas.append({
                    "nombre": m.Name,
                    "params": [{"n": p.Name, "t": p.ParameterType.FullName}
                               for p in m.GetParameters()],
                    "retorna": m.ReturnType.FullName,
                })
        result["api"]["firmas"] = firmas
    except Exception as ex:
        result["api"]["firmas"] = [{"error": str(ex)}]

    acc_metodos = []
    try:
        cta = clr.GetClrType(DB.Structure.RebarShapeDrivenAccessor)
        for m in cta.GetMethods():
            if m.Name.startswith(("get_", "Get")) and not m.Name.startswith("get_Is"):
                acc_metodos.append(m.Name)
    except Exception as ex:
        acc_metodos = ["error: %s" % ex]
    result["api"]["accessor_getters"] = sorted(set(acc_metodos))
    trace("FASE 1 OK")

    # ---- Fase 2: niveles --------------------------------------------------
    result["phase_reached"] = "fase2_niveles"
    niveles = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level)
                     .WhereElementIsNotElementType(),
                     key=lambda l: l.Elevation)
    result["niveles"] = [{"nombre": l.Name, "cota_m": l.Elevation * M}
                         for l in niveles]

    # ---- Fase 3: muestra de columnas -------------------------------------
    result["phase_reached"] = "fase3_muestra"
    acero = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            acero.setdefault(eidv(rb.GetHostId()), []).append(rb)
        except Exception:
            continue

    cols = []
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        cid = eidv(el.Id)
        if cid in acero:
            cols.append((el, cid))
    trace("FASE 3: %d columnas con acero, se toman %d" % (len(cols), MAX_COLUMNAS))

    for el, cid in cols[:MAX_COLUMNAS]:
        sym = doc.GetElement(el.GetTypeId())
        fila = {"id": cid, "tipo": element_name(sym), "sets": [],
                "base_level": None, "top_level": None,
                "base_z_m": None, "top_z_m": None}
        try:
            for clave, bipar in (("base_level", DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM),
                                 ("top_level", DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM)):
                p = el.get_Parameter(bipar)
                lv = doc.GetElement(p.AsElementId()) if p is not None else None
                fila[clave] = lv.Name if lv is not None else None
                if lv is not None:
                    fila["base_z_m" if clave == "base_level" else "top_z_m"] = \
                        lv.Elevation * M
        except Exception as ex:
            fila["error_niveles"] = str(ex)

        for rb in acero[cid]:
            s = {"id": eidv(rb.Id),
                 "shape": par(rb, "Shape Name"),
                 "bar_type": None,
                 "quantity": par(rb, "Quantity"),
                 "layout_rule": None,
                 "bar_length_ft": par(rb, "Bar Length"),
                 "spacing_ft": par(rb, "Spacing"),
                 "curvas": [], "normal": None, "array_length_ft": None,
                 "constraints": [], "error": None}
            errs = []
            try:
                bt = doc.GetElement(rb.GetTypeId())
                s["bar_type"] = element_name(bt)
            except Exception as ex:
                errs.append("bar_type: %s" % ex)
            try:
                p = rb.LookupParameter("Layout Rule")
                s["layout_rule"] = p.AsValueString() if p is not None else None
            except Exception as ex:
                errs.append("layout: %s" % ex)

            # --- curvas de eje: lo que hace falta para recrear ---
            try:
                m = getattr(rb, "GetCenterlineCurves", None)
                if m is not None:
                    # firma habitual: (adjustForSelfIntersection, suppressHooks,
                    #                  suppressBendRadius, multiplanarOption, barPositionIndex)
                    curvas = None
                    for args in ((False, True, True,
                                  DB.Structure.MultiplanarOption.IncludeOnlyPlanarCurves, 0),
                                 (False, True, True)):
                        try:
                            curvas = m(*args)
                            break
                        except Exception:
                            continue
                    if curvas is not None:
                        for c in curvas:
                            p0, p1 = c.GetEndPoint(0), c.GetEndPoint(1)
                            s["curvas"].append({
                                "tipo": type(c).__name__,
                                "p0": [p0.X, p0.Y, p0.Z], "p1": [p1.X, p1.Y, p1.Z],
                                "largo_ft": c.Length,
                                "vertical": abs(p1.Z - p0.Z) > abs(p1.X - p0.X) + abs(p1.Y - p0.Y),
                            })
                    else:
                        errs.append("GetCenterlineCurves: ninguna firma funciono")
            except Exception as ex:
                errs.append("curvas: %s" % ex)

            # --- accessor: normal y longitud de array ---
            try:
                acc = rb.GetShapeDrivenAccessor()
                if acc is not None:
                    for nom in ("Normal", "BarsOnNormalSide", "ArrayLength"):
                        try:
                            v = getattr(acc, nom, None)
                            if v is None:
                                continue
                            if nom == "Normal":
                                s["normal"] = [v.X, v.Y, v.Z]
                            elif nom == "ArrayLength":
                                s["array_length_ft"] = float(v)
                            else:
                                s[nom] = bool(v)
                        except Exception:
                            continue
            except Exception as ex:
                errs.append("accessor: %s" % ex)

            # --- constraints por handle ---
            try:
                mgr = rb.GetRebarConstraintsManager()
                if mgr is not None:
                    for h in mgr.GetAllConstrainedHandles():
                        c = mgr.GetCurrentConstraintOnHandle(h)
                        if c is None:
                            continue
                        d = {}
                        for nom, f in (("tipo", "GetConstraintType"),
                                       ("cara", "GetRebarConstraintTargetHostFaceType"),
                                       ("dist_cara", "GetDistanceToTargetHostFace"),
                                       ("dist_cover", "GetDistanceToTargetCover")):
                            try:
                                d[nom] = str(getattr(c, f)())
                            except Exception:
                                d[nom] = None
                        s["constraints"].append(d)
            except Exception as ex:
                errs.append("constraints: %s" % ex)

            if errs:
                s["error"] = " | ".join(errs)
            fila["sets"].append(s)
        result["columnas"].append(fila)
        trace("  columna %d: %d sets volcados" % (cid, len(fila["sets"])))

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

out.print_md("### Diagnostico de solape")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
out.print_md("- Columnas de muestra: **%d**" % len(result["columnas"]))
n = sum(len(c["sets"]) for c in result["columnas"])
out.print_md("- Sets volcados: **%d**" % n)
disp = [k for k, v in result["api"].items() if v is True]
out.print_md("- Metodos disponibles: %s" % ", ".join(disp))
falt = [k for k, v in result["api"].items() if v is False]
if falt:
    out.print_md("- **No disponibles**: %s" % ", ".join(falt))
con_curvas = sum(1 for c in result["columnas"] for s in c["sets"] if s["curvas"])
out.print_md("- Sets con curvas leidas: **%d** de %d" % (con_curvas, n))
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
