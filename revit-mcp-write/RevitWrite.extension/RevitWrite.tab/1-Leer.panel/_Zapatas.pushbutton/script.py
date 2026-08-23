# -*- coding: utf-8 -*-
"""Inventario de zapatas + firma real de la API de acero. SOLO LECTURA.

DOS COSAS EN UN BOTON, LAS DOS DE LECTURA
-----------------------------------------
1. **Inventario de cimentaciones**: tipo, dimensiones REALES (no las del plano),
   espesor, posicion, nivel y acero hospedado. Sirve para contrastar el modelo
   contra `00_DATOS/zapatas.csv`, que reporta tres espesores mal y una zapata
   faltante.

2. **Volcado de la firma de creacion de Rebar** de ESTA instalacion: metodos de
   `Rebar`, tipos de barra cargados, formas disponibles y tipos de gancho.

El punto 2 existe porque las zapatas no tienen acero: no hay maestra de la cual
copiar, hay que CREAR barras. Los dos intentos previos por esa via murieron
escribiendo contra una API recordada en vez de leida (ERRORES-IA E-040, E-042).
La regla que salio de ahi: volcar la superficie real ANTES de escribir la
primera linea contra ella.

No modifica nada. No abre transaccion.
"""
__title__ = "Zapatas"
__doc__ = "Inventario de cimentaciones + firma real de la API de Rebar. Solo lectura."

import os
import clr
import json
import traceback

from pyrevit import revit, script
from pyrevit.api import DB

doc = revit.doc

def _slug(txt):
    """Nombre de archivo seguro a partir del titulo del documento."""
    return "".join(ch if ch.isalnum() or ch in "-_" else "_"
                   for ch in (txt or "SIN_DOC"))[:60]


BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "zapatas_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "zapatas.json")   # se re-apunta con el
                                              # nombre del doc mas abajo

OUT_JSON = os.path.join(LOG_DIR, "zapatas_%s.json" % _slug(doc.Title))

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


def todos_los_parametros(el):
    """Todos los parametros con valor. En zapatas las dimensiones viven en
    parametros de tipo o de instancia segun la familia, y adivinar el nombre
    es como se pierde una hora."""
    d = {}
    try:
        for p in el.Parameters:
            try:
                nom = p.Definition.Name
            except Exception:
                continue
            try:
                st = p.StorageType
                if st == DB.StorageType.Double:
                    d[nom] = {"ft": p.AsDouble(), "m": p.AsDouble() * 0.3048,
                              "txt": p.AsValueString()}
                elif st == DB.StorageType.Integer:
                    d[nom] = p.AsInteger()
                elif st == DB.StorageType.String:
                    v = p.AsString()
                    if v:
                        d[nom] = v
                elif st == DB.StorageType.ElementId:
                    e = doc.GetElement(p.AsElementId())
                    if e is not None:
                        d[nom] = element_name(e)
            except Exception:
                continue
    except Exception:
        pass
    return d


result = {
    "ok": False,
    "phase_reached": "inicio",
    "document": doc.Title,
    "cimentaciones": [],
    "tipos_de_barra": [],
    "formas_de_barra": [],
    "tipos_de_gancho": [],
    "api_rebar": {},
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: acero hospedado, indice inverso ------------------------
    result["phase_reached"] = "fase1_indice_acero"
    trace("FASE 1: indice de acero por anfitrion")
    acero = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            h = eidv(rb.GetHostId())
            acero.setdefault(h, []).append(eidv(rb.Id))
        except Exception:
            continue
    trace("FASE 1 OK: %d anfitriones con acero" % len(acero))

    # ---- Fase 2: cimentaciones -----------------------------------------
    result["phase_reached"] = "fase2_cimentaciones"
    trace("FASE 2: cimentaciones")
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
               .WhereElementIsNotElementType()):
        cid = eidv(el.Id)
        fila = {
            "id": cid,
            "familia": None,
            "tipo": None,
            "mark": None,
            "nivel": None,
            "x_ft": None, "y_ft": None, "z_ft": None,
            "bbox_m": None,
            "acero_sets": len(acero.get(cid, [])),
            "params_instancia": {},
            "params_tipo": {},
            "error": None,
        }
        errs = []
        try:
            sym = doc.GetElement(el.GetTypeId())
            if sym is not None:
                fila["tipo"] = element_name(sym)
                try:
                    fila["familia"] = sym.Family.Name
                except Exception as ex:
                    errs.append("familia: %s" % ex)
                fila["params_tipo"] = todos_los_parametros(sym)
        except Exception as ex:
            errs.append("tipo: %s" % ex)

        try:
            fila["params_instancia"] = todos_los_parametros(el)
            fila["mark"] = fila["params_instancia"].get("Mark")
        except Exception as ex:
            errs.append("params: %s" % ex)

        try:
            if el.LevelId is not None:
                lv = doc.GetElement(el.LevelId)
                fila["nivel"] = lv.Name if lv is not None else None
        except Exception as ex:
            errs.append("nivel: %s" % ex)

        try:
            loc = el.Location
            if loc is not None and hasattr(loc, "Point"):
                p = loc.Point
                fila["x_ft"], fila["y_ft"], fila["z_ft"] = p.X, p.Y, p.Z
        except Exception as ex:
            errs.append("location: %s" % ex)

        try:
            bb = el.get_BoundingBox(None)
            if bb is not None:
                F = 0.3048
                fila["bbox_m"] = {
                    "lx": (bb.Max.X - bb.Min.X) * F,
                    "ly": (bb.Max.Y - bb.Min.Y) * F,
                    "h": (bb.Max.Z - bb.Min.Z) * F,
                    "min_z": bb.Min.Z * F, "max_z": bb.Max.Z * F,
                }
        except Exception as ex:
            errs.append("bbox: %s" % ex)

        if errs:
            fila["error"] = " | ".join(errs)
        result["cimentaciones"].append(fila)
    trace("FASE 2 OK: %d cimentaciones" % len(result["cimentaciones"]))

    # ---- Fase 3: catalogo de acero disponible ---------------------------
    # Sin RebarBarType cargados no se puede crear una sola barra. Es un
    # prerrequisito de identidad: si falta, hay que abortar, no improvisar.
    result["phase_reached"] = "fase3_catalogo"
    trace("FASE 3: catalogo de acero")
    for bt in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarBarType):
        try:
            result["tipos_de_barra"].append({
                "id": eidv(bt.Id),
                "nombre": element_name(bt),
                "diametro_ft": bt.BarNominalDiameter,
                "diametro_mm": bt.BarNominalDiameter * 304.8,
            })
        except Exception as ex:
            result["tipos_de_barra"].append({"nombre": element_name(bt),
                                             "error": str(ex)})
    for sh in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarShape):
        result["formas_de_barra"].append({"id": eidv(sh.Id),
                                          "nombre": element_name(sh)})
    for hk in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarHookType):
        result["tipos_de_gancho"].append({"id": eidv(hk.Id),
                                          "nombre": element_name(hk)})
    trace("FASE 3 OK: %d tipos de barra, %d formas, %d ganchos"
          % (len(result["tipos_de_barra"]), len(result["formas_de_barra"]),
             len(result["tipos_de_gancho"])))

    # ---- Fase 4: firma REAL de la API de creacion -----------------------
    # E-042: reflexion a ciegas es adivinar con mas pasos. Se vuelca la
    # superficie real antes de escribir contra ella.
    result["phase_reached"] = "fase4_firma_api"
    trace("FASE 4: firma de la API")

    def volcar(clase, filtro=""):
        """Vuelca los metodos de una clase .NET.

        En IronPython una clase .NET expuesta NO tiene `.GetType()` de
        instancia: hay que pedir su System.Type con `clr.GetClrType()`.
        Llamar `Clase.GetType()` revienta con
        "'type' object has no attribute 'GetType'" — verificado 2026-08-14.
        El endpoint /reflect de startup.py ya lo hacia bien; el error fue
        escribir esta funcion de nuevo en vez de copiar la que funcionaba.
        """
        salida = []
        try:
            ctype = clr.GetClrType(clase)
        except Exception as ex:
            return [{"error": "GetClrType: %s" % ex}]
        try:
            for m in ctype.GetMethods():
                nom = m.Name
                if filtro and filtro.lower() not in nom.lower():
                    continue
                try:
                    ps = [{"nombre": p.Name, "tipo": p.ParameterType.FullName}
                          for p in m.GetParameters()]
                except Exception:
                    ps = None
                salida.append({
                    "nombre": nom,
                    "estatico": m.IsStatic,
                    "retorna": m.ReturnType.FullName if m.ReturnType else None,
                    "params": ps,
                })
        except Exception as ex:
            return [{"error": str(ex)}]
        return salida

    # Cada volcado va aislado: si uno falla, los demas igual se recogen.
    # Los nombres van como STRING y se resuelven con getattr dentro del try.
    #
    # Referenciar `DB.Structure.RebarHookOrientation` directo en la tupla la
    # mata entera ANTES de entrar al bucle: Python evalua la tupla completa
    # primero, asi que un nombre inexistente se lleva los ocho volcados y no
    # uno. Ese nombre, ademas, no existe en Revit 2027 — es literalmente
    # ERRORES-IA E-040, repetido el 2026-08-14 teniendo la nota leida.
    #
    # La regla de E-040 era: no referenciar enums de refuerzo por nombre,
    # resolverlos por reflexion. Esto la aplica.
    for etiqueta, ruta, filtro in (
            ("Rebar.Create*", "Rebar", "Create"),
            ("Rebar.otros", "Rebar", ""),
            ("RebarShapeDrivenAccessor.SetLayout*",
             "RebarShapeDrivenAccessor", "SetLayout"),
            ("RebarBarType.Create", "RebarBarType", "Create"),
            ("RebarShape.Create", "RebarShape", "Create"),
            ("BarTerminationsData", "BarTerminationsData", ""),
            ("RebarStyle", "RebarStyle", ""),
            ("RebarHookOrientation", "RebarHookOrientation", ""),
            ("RebarHookType", "RebarHookType", ""),
    ):
        try:
            clase = getattr(DB.Structure, ruta, None)
            if clase is None:
                result["api_rebar"][etiqueta] = [
                    {"error": "no existe DB.Structure.%s en este Revit" % ruta}]
                trace("  %s: NO EXISTE en esta version" % ruta)
                continue
            result["api_rebar"][etiqueta] = volcar(clase, filtro)
            trace("  volcado %s: %d metodos" % (etiqueta, len(result["api_rebar"][etiqueta])))
        except Exception as ex:
            result["api_rebar"][etiqueta] = [{"error": str(ex)}]
            trace("  volcado %s FALLO: %s" % (etiqueta, ex))

    # Constructores y valores de enum: sin esto no se puede instanciar
    # BarTerminationsData ni elegir un RebarStyle sin adivinar el nombre.
    # Mismo criterio: nombres como string, resueltos con getattr.
    result["constructores"] = {}
    for ruta in ("BarTerminationsData", "RebarHookType", "RebarCoverType"):
        try:
            clase = getattr(DB.Structure, ruta, None)
            if clase is None:
                result["constructores"][ruta] = [{"error": "no existe en este Revit"}]
                continue
            ct = clr.GetClrType(clase)
            result["constructores"][ruta] = [
                [{"nombre": p.Name, "tipo": p.ParameterType.FullName}
                 for p in c.GetParameters()]
                for c in ct.GetConstructors()]
        except Exception as ex:
            result["constructores"][ruta] = [{"error": str(ex)}]

    # Los VALORES del enum se sacan del propio tipo, nunca de una lista
    # recordada: los nombres de enum de refuerzo cambian entre versiones.
    result["enums"] = {}
    # RebarTerminationOrientation aparece en la firma de
    # BarTerminationsData.set_TerminationOrientationAtStart/End y es lo que
    # decide hacia donde dobla el gancho. Hace falta para que los ganchos de
    # la parrilla inferior apunten hacia ARRIBA y no hacia el terreno.
    for ruta in ("RebarStyle", "RebarHookOrientation", "RebarLayoutRule",
                 "RebarConstraintType", "RebarConstraintTargetHostFaceType",
                 "RebarTerminationOrientation", "RebarRoundingOrientation",
                 "RebarHookOrientation2"):
        try:
            clase = getattr(DB.Structure, ruta, None)
            if clase is None:
                result["enums"][ruta] = ["<no existe en este Revit>"]
                continue
            ct = clr.GetClrType(clase)
            result["enums"][ruta] = [str(v) for v in ct.GetEnumValues()]
        except Exception as ex:
            result["enums"][ruta] = ["error: %s" % ex]

    n = sum(len(v) for v in result["api_rebar"].values())
    trace("FASE 4 OK: %d metodos volcados | enums: %s"
          % (n, {k: len(v) for k, v in result["enums"].items()}))

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

out.print_md("### Zapatas — inventario y API")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
out.print_md("- Cimentaciones: **%d**" % len(result["cimentaciones"]))
con = len([c for c in result["cimentaciones"] if c["acero_sets"] > 0])
out.print_md("- Con acero: **%d**" % con)
out.print_md("- Tipos de barra cargados: **%d**" % len(result["tipos_de_barra"]))
out.print_md("- Formas de barra: **%d** | ganchos: **%d**"
             % (len(result["formas_de_barra"]), len(result["tipos_de_gancho"])))
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
