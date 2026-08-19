# -*- coding: utf-8 -*-
"""Reemplazo de columnas metalicas por columnas de hormigon CON su acero.

QUE HACE
--------
Por cada instancia de `W Shapes-Column`, copia la columna maestra de hormigon
del tipo correspondiente (C1..C7) JUNTO CON su acero, a la posicion (x,y) de
la metalica, y le fija el nivel base/superior de la metalica con offsets en 0.

NO BORRA NADA. El borrado de las metalicas es un script aparte que se corre
DESPUES de verificar este. Crear primero y borrar despues es reversible:
si esto falla a mitad, las metalicas siguen intactas y se descarta lo creado.

POR QUE EL ACERO VIAJA SOLO
---------------------------
`ElementTransformUtils.CopyElements` copia EXACTAMENTE los ids que recibe. Si
se pasa anfitrion + hospedados en la misma llamada, el acero se re-hospeda en
la copia. Verificado el 2026-08-13: 12 ids -> 12 nuevos, los 11 sets colgando
de la columna copiada. Si se copiara solo la columna, el acero se quedaria.

Y como el acero esta amarrado por constraints a las caras del anfitrion, al
fijar la altura del tramo se readapta solo: las longitudinales cambian de
longitud y los estribos recalculan la cantidad. Tambien verificado.

DISENO (de ERRORES-IA E-040, E-041, E-043, E-045, E-046, E-049)
---------------------------------------------------------------
- **Marca lo que crea** (`Comments = MARCA`). Un generador que marca su obra
  puede limpiarla solo y volver a correr; uno que no, obliga a limpieza manual.
- **Idempotente**: al arrancar borra lo que el mismo script creo antes.
- **Una transaccion por nivel**: un fallo en Story10 no se lleva Story2..Story9.
- **Aborta si falta un prerrequisito de identidad** (maestra, tipo, nivel).
  Nunca sustituye por "la primera disponible": la familia ES el resultado.
- **Verifica releyendo**, no contando lo que pidio.
- Log incremental con fsync ANTES de cada bloque.
- No llama Dispose() sobre objetos de la API.
"""
__title__ = "Reemplazo"
__doc__ = "Crea columnas de hormigon con acero en la posicion de las metalicas. NO borra."

import os
import re
import json
import collections
import traceback

from pyrevit import revit, script
from pyrevit.api import DB
from System.Collections.Generic import List

doc = revit.doc

MARCA = "MCP:reemplazo-columnas"

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "reemplazo_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "reemplazo.json")

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


def bip(el, builtin, nombre):
    """Parametro por BuiltInParameter, con fallback a nombre visible."""
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
    "maestras": {},
    "creadas": [],
    "por_nivel": {},
    "desde_12x18": 0,
    "fallos": [],
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: niveles ------------------------------------------------
    result["phase_reached"] = "fase1_niveles"
    trace("FASE 1: niveles")
    niveles = {}
    for lv in DB.FilteredElementCollector(doc).OfClass(DB.Level).WhereElementIsNotElementType():
        niveles[lv.Name] = lv
    trace("FASE 1 OK: %d niveles" % len(niveles))

    # ---- Fase 2: limpiar corrida anterior propia ------------------------
    # E-045: el script borra LO SUYO y recrea. No pide limpieza manual.
    result["phase_reached"] = "fase2_limpieza"
    trace("FASE 2: buscando obra de corridas anteriores")
    previos = []
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        p = bip(el, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
        if p is not None and p.AsString() == MARCA:
            previos.append(el.Id)
    if previos:
        trace("FASE 2: borrando %d columnas de una corrida anterior" % len(previos))
        t = DB.Transaction(doc, "MCP: limpiar corrida anterior")
        t.Start()
        try:
            ids = List[DB.ElementId]()
            for i in previos:
                ids.Add(i)
            borrados = doc.Delete(ids)
            t.Commit()
            result["previos_borrados"] = len(borrados) if borrados else 0
            trace("FASE 2 OK: %d elementos borrados (con dependientes)"
                  % result["previos_borrados"])
        except Exception as ex:
            t.RollBack()
            raise Exception("no se pudo limpiar la corrida anterior: %s" % ex)
    else:
        trace("FASE 2 OK: no hay obra previa")

    # ---- Fase 3: identificar maestras -----------------------------------
    # Maestra = columna de hormigon en CIMENTACIONES, de tipo C1..C7, CON acero.
    # Se resuelve en runtime; nada de ids hardcodeados que envejecen.
    result["phase_reached"] = "fase3_maestras"
    trace("FASE 3: identificando maestras")

    acero_por_host = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            acero_por_host.setdefault(eidv(rb.GetHostId()), []).append(rb.Id)
        except Exception:
            continue

    maestras = {}
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
        if fam != "Concrete-Rectangular-Column":
            continue
        tname = element_name(sym)
        if not tname or not re.match(r"^C\d+$", tname):
            continue
        cid = eidv(el.Id)
        if cid not in acero_por_host:
            continue
        if tname in maestras:
            continue
        loc = el.Location
        if loc is None or not hasattr(loc, "Point"):
            continue
        maestras[tname] = {
            "id": el.Id,
            "point": loc.Point,
            "rebar": acero_por_host[cid],
            "symbol": sym,
        }
        result["maestras"][tname] = {
            "id": cid,
            "sets_acero": len(acero_por_host[cid]),
        }
    trace("FASE 3 OK: maestras = %s" % sorted(maestras.keys()))
    if not maestras:
        raise Exception("no se encontro ninguna columna maestra con acero")

    # ---- Fase 4: recolectar metalicas y agrupar por nivel ----------------
    result["phase_reached"] = "fase4_recoleccion"
    trace("FASE 4: recolectando metalicas")
    objetivos = {}
    sin_maestra = []
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        sym = doc.GetElement(el.GetTypeId())
        if sym is None:
            continue
        try:
            if sym.Family.Name != "W Shapes-Column":
                continue
        except Exception:
            continue
        tname = element_name(sym) or ""
        # Dos convenciones de nombre: 'C1-E9-T_1200x500' y 'C7_600x400'
        m = re.match(r"^(C\d+)(?=[-_]|$)", tname.strip())
        pref = m.group(1) if m else None

        loc = el.Location
        pt = loc.Point if (loc is not None and hasattr(loc, "Point")) else None

        bl = bip(el, DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, "Base Level")
        tl = bip(el, DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM, "Top Level")
        bl_el = doc.GetElement(bl.AsElementId()) if bl is not None else None
        tl_el = doc.GetElement(tl.AsElementId()) if tl is not None else None

        info = {
            "id": eidv(el.Id),
            "tipo": tname,
            "prefijo": pref,
            "punto": pt,
            "base": bl_el.Name if bl_el is not None else None,
            "top": tl_el.Name if tl_el is not None else None,
            "base_lv": bl_el,
            "top_lv": tl_el,
        }
        # E-043: prerrequisito de identidad faltante = se REPORTA, no se
        # sustituye por un default. Una columna con el tipo equivocado es un
        # entregable que parece correcto y no lo es.
        if pref is None or pref not in maestras or pt is None or bl_el is None:
            info["motivo"] = ("sin prefijo" if pref is None else
                              "sin maestra %s" % pref if pref not in maestras else
                              "sin punto" if pt is None else "sin nivel base")
            sin_maestra.append({k: v for k, v in info.items()
                                if k not in ("punto", "base_lv", "top_lv")})
            continue
        objetivos.setdefault(bl_el.Name, []).append(info)

    total_w = sum(len(v) for v in objetivos.values())
    trace("FASE 4 OK: %d metalicas mapeadas, %d sin mapear"
          % (total_w, len(sin_maestra)))

    # ---- Fase 4b: las columnas '12 x 18' -------------------------------
    # NO son duplicados de las metalicas: ocupan (posicion, nivel) donde NO
    # hay ninguna W. Verificado 2026-08-14 — 0 de 26 tienen metalica en su
    # mismo nivel. Borrarlas sin reemplazo perderia 17 columnas del edificio
    # (ERRORES-IA E-051). Su tipo real se infiere por la posicion: las W de
    # esa misma (x,y) en otros niveles votan, y el voto tiene que ser UNANIME.
    result["phase_reached"] = "fase4b_doce_por_dieciocho"
    trace("FASE 4b: columnas '12 x 18'")

    # voto de tipo por posicion, tomado de las metalicas
    voto = {}
    for niv_lista in objetivos.values():
        for o in niv_lista:
            k = (round(o["punto"].X, 2), round(o["punto"].Y, 2))
            voto.setdefault(k, collections.Counter())[o["prefijo"]] += 1

    # niveles ordenados por cota, para calcular el nivel superior
    orden_niv = sorted(niveles.values(), key=lambda l: l.Elevation)

    def nivel_superior(lv):
        for i, x in enumerate(orden_niv):
            if x.Id == lv.Id:
                return orden_niv[i + 1] if i + 1 < len(orden_niv) else None
        return None

    vistos_12 = {}
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        sym = doc.GetElement(el.GetTypeId())
        if sym is None:
            continue
        try:
            if sym.Family.Name != "Concrete-Rectangular-Column":
                continue
        except Exception:
            continue
        if (element_name(sym) or "") != "12 x 18":
            continue

        loc = el.Location
        pt = loc.Point if (loc is not None and hasattr(loc, "Point")) else None
        bl = bip(el, DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, "Base Level")
        bl_el = doc.GetElement(bl.AsElementId()) if bl is not None else None
        if pt is None or bl_el is None:
            sin_maestra.append({"id": eidv(el.Id), "tipo": "12 x 18",
                                "motivo": "sin punto o sin nivel base"})
            continue

        k = (round(pt.X, 2), round(pt.Y, 2))
        cnt = voto.get(k)
        # E-043: sin voto unanime NO se inventa un tipo. Se reporta y se salta.
        if not cnt or len(cnt) != 1:
            sin_maestra.append({
                "id": eidv(el.Id), "tipo": "12 x 18",
                "motivo": "tipo no inferible por posicion: %s"
                          % (dict(cnt) if cnt else "sin W en esa posicion")})
            continue
        pref = list(cnt)[0]
        if pref not in maestras:
            sin_maestra.append({"id": eidv(el.Id), "tipo": "12 x 18",
                                "motivo": "sin maestra %s" % pref})
            continue

        # Deduplicar por (nivel, posicion): hay 9 pares encimados, residuo de
        # la misma corrida contaminada. Se crea UNA por posicion+nivel.
        clave = (bl_el.Name, k)
        if clave in vistos_12:
            continue

        # El Top Level de la '12 x 18' arrastra basura (varias tienen
        # base == top). Se calcula el nivel superior por cota: determinista.
        tl_el = nivel_superior(bl_el)
        if tl_el is None:
            sin_maestra.append({"id": eidv(el.Id), "tipo": "12 x 18",
                                "motivo": "no hay nivel superior a %s" % bl_el.Name})
            continue

        vistos_12[clave] = True
        objetivos.setdefault(bl_el.Name, []).append({
            "id": eidv(el.Id),
            "tipo": "12 x 18",
            "prefijo": pref,
            "punto": pt,
            "base": bl_el.Name,
            "top": tl_el.Name,
            "base_lv": bl_el,
            "top_lv": tl_el,
        })

    total_obj = sum(len(v) for v in objetivos.values())
    result["desde_12x18"] = len(vistos_12)
    trace("FASE 4b OK: %d columnas unicas desde '12 x 18' | objetivo total %d"
          % (len(vistos_12), total_obj))
    result["fallos"] = sin_maestra

    # ---- Fase 5: crear, una transaccion POR NIVEL ------------------------
    result["phase_reached"] = "fase5_creacion"
    orden = sorted(objetivos.keys(), key=lambda n: niveles[n].Elevation
                   if n in niveles else 0)
    trace("FASE 5: creando en %d niveles" % len(orden))

    for nivel in orden:
        lote = objetivos[nivel]
        trace("  --- %s: %d columnas ---" % (nivel, len(lote)))
        t = DB.Transaction(doc, "MCP: columnas hormigon %s" % nivel)
        t.Start()
        hechas = []
        try:
            for obj in lote:
                mae = maestras[obj["prefijo"]]
                origen = mae["point"]
                destino = obj["punto"]
                delta = DB.XYZ(destino.X - origen.X,
                               destino.Y - origen.Y,
                               0.0)

                ids = List[DB.ElementId]()
                ids.Add(mae["id"])
                for r in mae["rebar"]:
                    ids.Add(r)

                nuevos = DB.ElementTransformUtils.CopyElements(doc, ids, delta)
                nuevos = list(nuevos)
                if not nuevos:
                    raise Exception("CopyElements no devolvio nada para id %s"
                                    % obj["id"])

                # La columna es el elemento copiado que es FamilyInstance
                col_nueva = None
                for nid in nuevos:
                    e = doc.GetElement(nid)
                    if isinstance(e, DB.FamilyInstance):
                        col_nueva = e
                        break
                if col_nueva is None:
                    raise Exception("no se identifico la columna copiada de %s"
                                    % obj["id"])

                # Nivel y offsets: la geometria de las metalicas NO se
                # reproduce (todas traen Top Offset = 9 ft de una corrida
                # contaminada). Offsets en 0.
                p = bip(col_nueva, DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
                        "Base Level")
                if p is not None and not p.IsReadOnly:
                    p.Set(obj["base_lv"].Id)
                if obj["top_lv"] is not None:
                    p = bip(col_nueva, DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM,
                            "Top Level")
                    if p is not None and not p.IsReadOnly:
                        p.Set(obj["top_lv"].Id)
                for b, n in ((DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM,
                              "Base Offset"),
                             (DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM,
                              "Top Offset")):
                    p = bip(col_nueva, b, n)
                    if p is not None and not p.IsReadOnly:
                        p.Set(0.0)

                # Marca de autoria: permite limpiar y re-correr (E-045)
                p = bip(col_nueva, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
                        "Comments")
                if p is not None and not p.IsReadOnly:
                    p.Set(MARCA)

                hechas.append({
                    "origen_w": obj["id"],
                    "nueva": eidv(col_nueva.Id),
                    "tipo": obj["prefijo"],
                    "nivel": nivel,
                    "acero": len(nuevos) - 1,
                })
            t.Commit()
            result["creadas"].extend(hechas)
            result["por_nivel"][nivel] = len(hechas)
            trace("  %s OK: %d creadas" % (nivel, len(hechas)))
        except Exception as ex:
            t.RollBack()
            msg = "%s: %s" % (nivel, ex)
            trace("  %s ROLLBACK: %s" % (nivel, traceback.format_exc()))
            result["fallos"].append({"nivel": nivel, "motivo": str(ex),
                                     "revertidas": len(lote)})
            result["por_nivel"][nivel] = 0

    # ---- Fase 6: verificar RELEYENDO ------------------------------------
    # E-046: una escritura que no lanza no es una escritura que aplico.
    result["phase_reached"] = "fase6_verificacion"
    trace("FASE 6: verificacion por relectura")
    marcadas = 0
    con_acero = 0
    acero_idx = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            acero_idx[eidv(rb.GetHostId())] = acero_idx.get(
                eidv(rb.GetHostId()), 0) + 1
        except Exception:
            continue
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        p = bip(el, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
        if p is not None and p.AsString() == MARCA:
            marcadas += 1
            if acero_idx.get(eidv(el.Id), 0) > 0:
                con_acero += 1
    result["verificacion"] = {
        "creadas_reportadas": len(result["creadas"]),
        "marcadas_en_modelo": marcadas,
        "marcadas_con_acero": con_acero,
        "metalicas_objetivo": total_obj,
        "coincide": (marcadas == len(result["creadas"]) == total_obj
                     and con_acero == marcadas),
    }
    trace("FASE 6 OK: %s" % json.dumps(result["verificacion"]))

    result["phase_reached"] = "completo"
    result["ok"] = len(result["fallos"]) == 0 and result["verificacion"]["coincide"]

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Reemplazo de columnas")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
out.print_md("- Maestras usadas: **%s**" % ", ".join(sorted(result["maestras"].keys())))
if result["previos_borrados"]:
    out.print_md("- Limpieza de corrida anterior: %d elementos" % result["previos_borrados"])
out.print_md("- Columnas creadas: **%d**  (de metalicas: %d | de '12 x 18': %d)"
             % (len(result["creadas"]),
                len(result["creadas"]) - result["desde_12x18"],
                result["desde_12x18"]))
v = result.get("verificacion")
if v:
    out.print_md("- Verificadas en modelo: **%d** (con acero: **%d**)"
                 % (v["marcadas_en_modelo"], v["marcadas_con_acero"]))
    out.print_md("- Objetivo: %d | **coincide: %s**" % (v["metalicas_objetivo"], v["coincide"]))
if result["fallos"]:
    out.print_md("- ⚠️ **fallos: %d** — ver JSON" % len(result["fallos"]))
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR GLOBAL** — ver trace")
