# -*- coding: utf-8 -*-
"""Inventario completo de columnas estructurales -> JSON.

POR QUE ESTE SCRIPT EXISTE
--------------------------
El endpoint `/columns` del MCP devuelve id, tipo, familia, Mark y nivel, pero
NO la ubicacion. Y `revit_copy` traslada por vector (dx,dy,dz): sin XYZ no hay
forma de llevar un elemento a la posicion de otro. Este script cierra ese hueco
leyendo LocationPoint y bounding box directamente desde el hilo de UI.

SOLO LECTURA. No abre transaccion, no modifica nada. Es el paso previo a
cualquier reemplazo: primero se sabe donde esta todo, despues se decide.

DISENO (derivado de ERRORES-IA E-040, E-043, E-047, E-049)
----------------------------------------------------------
- Fases numeradas, con la ultima alcanzada guardada en el JSON.
- Log incremental con fsync ANTES de cada bloque, no despues: un crash duro
  se lleva el buffer.
- El JSON se escribe SIEMPRE, completo o no.
- Ningun campo se omite en silencio: lo que falla queda en 'error' del propio
  elemento. Un campo ausente no es un campo vacio.
- NO se llama Dispose() sobre objetos de la API (ver E-049).
"""
__title__ = "Inventario"
__doc__ = "Vuelca las columnas estructurales con coordenadas y niveles a _log/inventario.json"

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


BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "inventario_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "inventario.json")   # se re-apunta con el
                                              # nombre del doc mas abajo

OUT_JSON = os.path.join(LOG_DIR, "inventario_%s.json" % _slug(doc.Title))

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


def eid_value(element_id):
    try:
        return int(element_id.Value)
    except AttributeError:
        return int(element_id.IntegerValue)


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
    if st == DB.StorageType.ElementId:
        return eid_value(p.AsElementId())
    return None


def element_name(el):
    """Nombre de un elemento, con fallbacks.

    `DB.Element.Name.GetValue(el)` funciona en el contexto de pyRevit Routes
    pero NO en el de pushbutton: ahi `Element.Name` se liga como
    getset_descriptor de Python y no expone GetValue. Verificado el 2026-08-14
    con las 231 columnas fallando. La misma expresion es correcta en un
    contexto e invalida en el otro, asi que se prueban las tres vias.
    """
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
        if p is not None:
            return p.AsString()
    except Exception:
        pass
    return None


def level_name(elid):
    if elid is None:
        return None
    lv = doc.GetElement(elid) if not isinstance(elid, int) else doc.GetElement(
        DB.ElementId(elid))
    return lv.Name if lv is not None else None


result = {
    "ok": False,
    "phase_reached": "inicio",
    "document": None,
    "levels": [],
    "columns": [],
    "error": None,
}

trace("=== inicio ===")

try:
    result["phase_reached"] = "fase1_documento"
    result["document"] = doc.Title
    trace("FASE 1: documento = %s" % doc.Title)

    # ---- Fase 2: niveles (para resolver cotas sin adivinar) -------------
    result["phase_reached"] = "fase2_niveles"
    trace("FASE 2: niveles")
    lv_col = (DB.FilteredElementCollector(doc)
              .OfClass(DB.Level)
              .WhereElementIsNotElementType())
    for lv in sorted(lv_col, key=lambda x: x.Elevation):
        result["levels"].append({
            "id": eid_value(lv.Id),
            "name": lv.Name,
            "elevation_ft": lv.Elevation,
            "elevation_m": lv.Elevation * 0.3048,
        })
    trace("FASE 2 OK: %d niveles" % len(result["levels"]))

    # ---- Fase 3: indice de acero por anfitrion --------------------------
    # Se arma UNA vez. Preguntarle a cada columna cuanto acero tiene seria
    # N consultas; asi es una pasada.
    result["phase_reached"] = "fase3_indice_acero"
    trace("FASE 3: indice de acero por host")
    rebar_por_host = {}
    rb_col = (DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_Rebar)
              .WhereElementIsNotElementType())
    for rb in rb_col:
        try:
            h = eid_value(rb.GetHostId())
        except Exception:
            continue
        rebar_por_host.setdefault(h, []).append(eid_value(rb.Id))
    trace("FASE 3 OK: %d anfitriones con acero" % len(rebar_por_host))

    # ---- Fase 4: columnas ----------------------------------------------
    result["phase_reached"] = "fase4_columnas"
    trace("FASE 4: columnas")
    col = (DB.FilteredElementCollector(doc)
           .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
           .WhereElementIsNotElementType())
    columnas = list(col)
    trace("FASE 4: %d instancias" % len(columnas))

    for idx, el in enumerate(columnas):
        cid = eid_value(el.Id)
        row = {
            "id": cid,
            "family": None,
            "type": None,
            "type_prefix": None,
            "mark": get_param(el, "Mark"),
            "level": None,
            "x_ft": None, "y_ft": None, "z_ft": None,
            "base_level": None, "top_level": None,
            "base_offset_ft": get_param(el, "Base Offset"),
            "top_offset_ft": get_param(el, "Top Offset"),
            "bbox_min_z_ft": None, "bbox_max_z_ft": None,
            "bbox_lx_m": None, "bbox_ly_m": None,
            "b_m": None, "h_m": None,
            "rebar_ids": rebar_por_host.get(cid, []),
            "error": None,
        }
        # Un try POR BLOQUE, no uno global. Con un solo try envolviendo todo,
        # un fallo leyendo el nombre del tipo se lleva tambien las coordenadas
        # y el bounding box, que son independientes — fue exactamente lo que
        # paso en la primera corrida (2026-08-14): 231 columnas sin un solo
        # dato util por un AttributeError en un campo de los diez.
        errores = []

        try:
            sym = doc.GetElement(el.GetTypeId())
            if sym is not None:
                row["type"] = element_name(sym)
                try:
                    row["family"] = sym.Family.Name
                except Exception as ex:
                    errores.append("family: %s" % ex)
                # Prefijo de tipo C1..C7. Hay DOS convenciones de nombre en el
                # modelo y partir por guion solo cubre una:
                #   C1-E9-T_1200x500  -> guion despues del tipo
                #   C7_600x400        -> guion BAJO despues del tipo
                # Partir por "-" dejaba las 4 columnas C7 sin clasificar y me
                # hizo afirmar que el tipo C7 no se usaba en el edificio
                # (2026-08-14). Se extrae con regex sobre el patron real.
                if row["type"]:
                    m = re.match(r"^(C\d+)(?=[-_]|$)", row["type"].strip())
                    row["type_prefix"] = m.group(1) if m else None
        except Exception as ex:
            errores.append("tipo: %s" % ex)

        try:
            if el.LevelId is not None:
                row["level"] = level_name(el.LevelId)
        except Exception as ex:
            errores.append("level: %s" % ex)

        try:
            loc = el.Location
            if loc is not None and hasattr(loc, "Point"):
                p = loc.Point
                row["x_ft"], row["y_ft"], row["z_ft"] = p.X, p.Y, p.Z
        except Exception as ex:
            errores.append("location: %s" % ex)

        try:
            bl = get_param(el, "Base Level")
            tl = get_param(el, "Top Level")
            row["base_level"] = level_name(bl) if bl else None
            row["top_level"] = level_name(tl) if tl else None
        except Exception as ex:
            errores.append("base/top level: %s" % ex)

        try:
            bb = el.get_BoundingBox(None)
            if bb is not None:
                row["bbox_min_z_ft"] = bb.Min.Z
                row["bbox_max_z_ft"] = bb.Max.Z
                row["bbox_lx_m"] = (bb.Max.X - bb.Min.X) * 0.3048
                row["bbox_ly_m"] = (bb.Max.Y - bb.Min.Y) * 0.3048
        except Exception as ex:
            errores.append("bbox: %s" % ex)

        # Dimensiones de SECCION, del tipo. Decisivas para saber si el acero
        # de un modelo encaja en las columnas de otro: dos tipos pueden
        # llamarse igual (C1, C2...) y medir distinto. Nombre igual no prueba
        # objeto igual — ya paso en esta sesion con las zapatas.
        try:
            sym = doc.GetElement(el.GetTypeId())
            if sym is not None:
                for nombres, clave in ((("b", "Width", "Ancho"), "b_m"),
                                       (("h", "Depth", "Height", "Peralte"), "h_m")):
                    for n in nombres:
                        if row[clave] is not None:
                            break
                        p = sym.LookupParameter(n)
                        if p is not None and p.StorageType == DB.StorageType.Double:
                            row[clave] = p.AsDouble() * 0.3048
        except Exception as ex:
            errores.append("seccion: %s" % ex)

        if errores:
            row["error"] = " | ".join(errores)
            trace("  %d: %s" % (cid, row["error"]))

        result["columns"].append(row)
        if idx % 50 == 0:
            trace("  ...%d/%d" % (idx, len(columnas)))

    trace("FASE 4 OK")
    result["phase_reached"] = "completo"
    result["ok"] = True

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase_reached=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Inventario")
out.print_md("- Documento: `%s`" % result["document"])
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
out.print_md("- Niveles: **%d**" % len(result["levels"]))
out.print_md("- Columnas: **%d**" % len(result["columns"]))
con_acero = len([c for c in result["columns"] if c["rebar_ids"]])
out.print_md("- Columnas con acero: **%d**" % con_acero)
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- **ERROR**: ver trace")
