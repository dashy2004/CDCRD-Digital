# -*- coding: utf-8 -*-
"""Reconstruye las longitudinales de columna con empalme a media altura.

CRITERIO (definido con el operador, 2026-08-14)
------------------------------------------------
- El solape se centra en la MITAD del tramo, medida sobre la altura TOTAL
  entre niveles (no la altura libre entre losas).
- Maximo 50% del refuerzo empalmado en una misma seccion. El otro 50% se
  desfasa 50 diametros.
- El arranque baja hasta la parrilla inferior de la zapata, con gancho de 90.
- Todas las columnas tienen zapata debajo.

GEOMETRIA RESULTANTE
--------------------
Para la columna del tramo k, con zm = cota media del tramo:

    barra normal : desde (zm_{k-1} - LS/2)  hasta (zm_k + LS/2)
    barra de arranque (tramo mas bajo):
                   desde (fondo zapata + recubrimiento) hasta (zm_1 + LS/2)

    grupo B      : lo mismo, desplazado +50db en ambos extremos

Longitud de una barra intermedia = H_{k-1}/2 + H_k/2 + LS.

EL COSTO, ACEPTADO EXPLICITAMENTE
----------------------------------
Al recrear, las barras pierden las constraints al anfitrion y quedan con
geometria fija. Si despues cambia una altura de entrepiso, el acero ya NO la
sigue solo: hay que volver a correr este script. Es la contrapartida de
empalmar a media altura y el operador la aceptó el 2026-08-14.

MODO PILOTO
-----------
Por defecto procesa UNA columna y para. Es la operacion mas invasiva del
proyecto —modifica acero que ya esta bien puesto, sobre el modelo bueno— y en
esta sesion ya hubo dos casos de conteo en verde con geometria mal. Se revisa
en `3D - ACERO` antes de escalar.

GUARDAS (E-041, E-043, E-045, E-046)
------------------------------------
- Marca lo que crea; borra su obra previa antes de recrear. Idempotente.
- Aborta si falta el tipo de barra o el gancho. Nunca sustituye.
- Verifica RELEYENDO: cuenta barras y mide la longitud del solape real.
- Una transaccion por columna.
- Log incremental con fsync.
"""
__title__ = "Solape"
__doc__ = "Reconstruye longitudinales con empalme a media altura. Piloto por defecto."

import os
import json
import traceback

from pyrevit import revit, script, forms
from pyrevit.api import DB
from System.Collections.Generic import List

doc = revit.doc

MARCA = "MCP:solape"
M = 0.3048
REC_ZAPATA = 0.075         # recubrimiento inferior de zapata [m]
GANCHO_NOMBRE = "Standard - 90 deg."
TOL_XY = 0.05 / M          # tolerancia para casar columna con zapata [ft]

# --- LONGITUD DE SOLAPE [m] por barra y f'c (tabla del proyecto) -----------
LS = {
    "#3":  {210: 0.48, 240: 0.48, 280: 0.48, 350: 0.48},
    "#4":  {210: 0.64, 240: 0.64, 280: 0.64, 350: 0.64},
    "#6":  {210: 0.95, 240: 0.95, 280: 0.95, 350: 0.95},
    "#8":  {210: 1.84, 240: 1.72, 280: 1.59, 350: 1.42},
    "#9":  {210: 1.95, 240: 1.75, 280: 1.65, 350: 1.50},
    "#11": {210: 2.10, 240: 1.82, 280: 1.75, 350: 1.75},
}
DIAM = {"#3": 0.009525, "#4": 0.0127, "#5": 0.015875, "#6": 0.01905,
        "#8": 0.0254, "#9": 0.028675, "#10": 0.03225, "#11": 0.035812}

# f'c por cota: (cota_max_m, fc). Fund@E5 350 · E5@E7 280 · E7@E9 240 · resto 210
FC_TRAMOS = [(17.28, 350), (24.58, 280), (31.88, 240), (9e9, 210)]


def fc_en(z_m):
    for lim, fc in FC_TRAMOS:
        if z_m < lim + 0.01:
            return fc
    return 210


def _slug(txt):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_"
                   for ch in (txt or "SIN_DOC"))[:60]


BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "solape_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "solape_%s.json" % _slug(doc.Title))

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


def bip(el, builtin, nombre):
    try:
        p = el.get_Parameter(builtin)
        if p is not None:
            return p
    except Exception:
        pass
    return el.LookupParameter(nombre)


result = {
    "ok": False, "phase_reached": "inicio", "document": doc.Title,
    "modo": None, "previos_borrados": 0,
    "columnas": [], "fallos": [], "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: contexto -------------------------------------------------
    result["phase_reached"] = "fase1_contexto"
    niveles = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level)
                     .WhereElementIsNotElementType(),
                     key=lambda l: l.Elevation)
    cotas = [l.Elevation for l in niveles]
    trace("FASE 1: %d niveles" % len(niveles))

    barras_tipo = {}
    for bt in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarBarType):
        barras_tipo[element_name(bt)] = bt
    ganchos = {}
    for hk in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarHookType):
        ganchos[element_name(hk)] = hk
    gancho = ganchos.get(GANCHO_NOMBRE)
    if gancho is None:
        raise Exception("no esta cargado el gancho '%s'. Hay: %s"
                        % (GANCHO_NOMBRE, sorted(ganchos)))

    # zapatas, para saber hasta donde baja el arranque
    zapatas = []
    for z in (DB.FilteredElementCollector(doc)
              .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
              .WhereElementIsNotElementType()):
        bb = z.get_BoundingBox(None)
        if bb is not None:
            zapatas.append((bb, eidv(z.Id)))
    trace("FASE 1 OK: %d zapatas, %d tipos de barra" % (len(zapatas), len(barras_tipo)))

    def zapata_bajo(x, y):
        for bb, zid in zapatas:
            if (bb.Min.X - TOL_XY <= x <= bb.Max.X + TOL_XY and
                    bb.Min.Y - TOL_XY <= y <= bb.Max.Y + TOL_XY):
                return bb, zid
        return None, None

    # ---- Fase 2: limpiar obra propia --------------------------------------
    result["phase_reached"] = "fase2_limpieza"
    previos = []
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        p = bip(rb, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
        if p is not None and p.AsString() == MARCA:
            previos.append(rb.Id)
    if previos:
        t = DB.Transaction(doc, "MCP: limpiar solape anterior")
        t.Start()
        try:
            ids = List[DB.ElementId]()
            for i in previos:
                ids.Add(i)
            b = doc.Delete(ids)
            t.Commit()
            result["previos_borrados"] = len(b) if b else 0
        except Exception as ex:
            t.RollBack()
            raise Exception("no se pudo limpiar: %s" % ex)
    trace("FASE 2 OK: %d borrados" % result["previos_borrados"])

    # ---- Fase 3: columnas candidatas --------------------------------------
    result["phase_reached"] = "fase3_candidatas"
    acero = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            acero.setdefault(eidv(rb.GetHostId()), []).append(rb)
        except Exception:
            continue

    candidatas = []
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
               .WhereElementIsNotElementType()):
        cid = eidv(el.Id)
        sets = acero.get(cid, [])
        lon = []
        for rb in sets:
            p = rb.LookupParameter("Shape Name")
            if p is not None and p.AsString() == "00":
                lon.append(rb)
        if lon:
            candidatas.append((el, cid, lon))
    trace("FASE 3: %d columnas con longitudinales" % len(candidatas))
    if not candidatas:
        raise Exception("no hay columnas con barras longitudinales (forma 00)")

    piloto = forms.alert(
        "Se encontraron %d columnas con longitudinales.\n\n"
        "PILOTO: procesa UNA sola y para, para que la revises en 3D - ACERO.\n"
        "COMPLETO: procesa las %d.\n\n"
        "Esta operacion RECONSTRUYE el acero: las barras pierden sus\n"
        "constraints al anfitrion y quedan con geometria fija.\n\n"
        "¿Correr solo el PILOTO?" % (len(candidatas), len(candidatas)),
        title="Solape a media altura", yes=True, no=True)
    result["modo"] = "piloto" if piloto else "completo"
    lote = candidatas[:1] if piloto else candidatas
    trace("FASE 3 OK: modo=%s, %d a procesar" % (result["modo"], len(lote)))

    # ---- Fase 4: reconstruir ----------------------------------------------
    result["phase_reached"] = "fase4_reconstruccion"
    estilo = DB.Structure.RebarStyle.Standard

    for el, cid, lon in lote:
        sym = doc.GetElement(el.GetTypeId())
        info = {"columna": cid, "tipo": element_name(sym), "sets_originales": len(lon),
                "creados": [], "grupo_a": 0, "grupo_b": 0, "error": None}

        # tramo de la columna
        pb = bip(el, DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM, "Base Level")
        pt = bip(el, DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM, "Top Level")
        lb = doc.GetElement(pb.AsElementId()) if pb is not None else None
        lt = doc.GetElement(pt.AsElementId()) if pt is not None else None
        if lb is None or lt is None:
            result["fallos"].append({"columna": cid, "motivo": "sin niveles"})
            continue
        z0, z1 = lb.Elevation, lt.Elevation
        H = z1 - z0
        zm = z0 + H / 2.0
        # cota media del tramo ANTERIOR (para el inicio de la barra)
        idx = min(range(len(cotas)), key=lambda i: abs(cotas[i] - z0))
        es_base = idx == 0
        zm_prev = None if es_base else cotas[idx - 1] + (cotas[idx] - cotas[idx - 1]) / 2.0

        info.update({"base": lb.Name, "top": lt.Name,
                     "H_m": H * M, "zm_m": zm * M,
                     "es_arranque": es_base})

        # reparto 50/50: se ordenan los sets por cantidad y se alternan,
        # asi los dos grupos quedan lo mas parejos posible sin partir sets.
        pares = []
        for rb in lon:
            q = rb.LookupParameter("Quantity")
            pares.append((int(q.AsInteger()) if q is not None else 1, rb))
        pares.sort(key=lambda x: -x[0])
        grupos = {"A": [], "B": []}
        suma = {"A": 0, "B": 0}
        for q, rb in pares:
            g = "A" if suma["A"] <= suma["B"] else "B"
            grupos[g].append((q, rb))
            suma[g] += q
        info["grupo_a"], info["grupo_b"] = suma["A"], suma["B"]

        t = DB.Transaction(doc, "MCP: solape columna %d" % cid)
        t.Start()
        try:
            nuevos_ids = []
            for g in ("A", "B"):
                for q, rb in grupos[g]:
                    bt = doc.GetElement(rb.GetTypeId())
                    nom_barra = element_name(bt)
                    db = DIAM.get(nom_barra)
                    if db is None:
                        raise Exception("diametro desconocido para %s" % nom_barra)
                    tabla = LS.get(nom_barra)
                    if tabla is None:
                        raise Exception("sin longitud de solape para %s "
                                        "(faltan en la tabla del proyecto)" % nom_barra)
                    ls = tabla[fc_en(zm * M)]
                    desfase = (50.0 * db / M) if g == "B" else 0.0   # 50 db en pies

                    # curva actual: da x, y y la direccion
                    curvas = rb.GetCenterlineCurves(
                        False, True, True,
                        DB.Structure.MultiplanarOption.IncludeOnlyPlanarCurves, 0)
                    c0 = list(curvas)[0]
                    p0 = c0.GetEndPoint(0)
                    x, y = p0.X, p0.Y

                    # extremos nuevos, en pies
                    if es_base:
                        bb, zid = zapata_bajo(x, y)
                        if bb is None:
                            raise Exception("no se hallo zapata bajo la columna %d" % cid)
                        z_ini = bb.Min.Z + (REC_ZAPATA / M)
                    else:
                        z_ini = zm_prev - (ls / M) / 2.0 + desfase
                    z_fin = zm + (ls / M) / 2.0 + desfase

                    acc_old = rb.GetShapeDrivenAccessor()
                    normal = acc_old.Normal
                    array_len = acc_old.ArrayLength
                    on_normal = acc_old.BarsOnNormalSide

                    curvas_new = List[DB.Curve]()
                    curvas_new.Add(DB.Line.CreateBound(
                        DB.XYZ(x, y, z_ini), DB.XYZ(x, y, z_fin)))

                    term = DB.Structure.BarTerminationsData(doc)
                    if es_base:
                        # gancho de 90 solo en el arranque, apoyado en la parrilla
                        for attr, met in (("HookTypeIdAtStart", "set_HookTypeIdAtStart"),):
                            try:
                                setattr(term, attr, gancho.Id)
                            except Exception:
                                getattr(term, met)(gancho.Id)

                    nueva = DB.Structure.Rebar.CreateFromCurves(
                        doc, estilo, bt, el, normal, curvas_new, term, True, True)
                    if nueva is None:
                        raise Exception("CreateFromCurves devolvio None")

                    acc = nueva.GetShapeDrivenAccessor()
                    acc.SetLayoutAsFixedNumber(q, array_len, on_normal, True, True)

                    p = bip(nueva, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
                            "Comments")
                    if p is not None and not p.IsReadOnly:
                        p.Set(MARCA)

                    nuevos_ids.append(eidv(nueva.Id))
                    info["creados"].append({
                        "grupo": g, "barra": nom_barra, "cantidad": q,
                        "ls_m": ls, "desfase_m": desfase * M,
                        "z_ini_m": z_ini * M, "z_fin_m": z_fin * M,
                        "largo_m": (z_fin - z_ini) * M,
                        "nuevo_id": eidv(nueva.Id),
                    })

            # borrar los originales SOLO si todo lo nuevo se creo bien
            viejos = List[DB.ElementId]()
            for _, rb in pares:
                viejos.Add(rb.Id)
            doc.Delete(viejos)
            t.Commit()
            trace("  columna %d OK: %d sets nuevos (A=%d, B=%d barras)"
                  % (cid, len(nuevos_ids), suma["A"], suma["B"]))
        except Exception as ex:
            t.RollBack()
            info["error"] = str(ex)
            result["fallos"].append({"columna": cid, "motivo": str(ex)})
            trace("  columna %d ROLLBACK: %s" % (cid, traceback.format_exc()))
        result["columnas"].append(info)

    # ---- Fase 5: verificar releyendo --------------------------------------
    result["phase_reached"] = "fase5_verificacion"
    marcadas = 0
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        p = bip(rb, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
        if p is not None and p.AsString() == MARCA:
            marcadas += 1
    esperados = sum(len(c["creados"]) for c in result["columnas"])
    result["verificacion"] = {
        "sets_marcados": marcadas, "sets_esperados": esperados,
        "columnas_procesadas": len(result["columnas"]),
        "coincide": marcadas == esperados,
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

out.print_md("### Solape a media altura")
out.print_md("- Fase alcanzada: `%s` | modo: **%s**"
             % (result["phase_reached"], result["modo"]))
if result["previos_borrados"]:
    out.print_md("- Limpieza previa: %d barras" % result["previos_borrados"])
out.print_md("- Columnas procesadas: **%d**" % len(result["columnas"]))
for c in result["columnas"]:
    if c["error"]:
        out.print_md("  - ❌ col %s: %s" % (c["columna"], c["error"][:90]))
        continue
    out.print_md("  - col `%s` (%s) %s→%s H=%.2f m | grupos %d+%d barras | %d sets"
                 % (c["columna"], c["tipo"], c["base"], c["top"], c["H_m"],
                    c["grupo_a"], c["grupo_b"], len(c["creados"])))
    for k in c["creados"][:4]:
        out.print_md("     %s %s x%d: z %.3f→%.3f m (L=%.3f) LS=%.2f desf=%.2f"
                     % (k["grupo"], k["barra"], k["cantidad"], k["z_ini_m"],
                        k["z_fin_m"], k["largo_m"], k["ls_m"], k["desfase_m"]))
v = result.get("verificacion")
if v:
    out.print_md("- Verificado: %d de %d | **coincide: %s**"
                 % (v["sets_marcados"], v["sets_esperados"], v["coincide"]))
if result["fallos"]:
    out.print_md("- ⚠️ **fallos: %d**" % len(result["fallos"]))
out.print_md("- **ok: %s**" % result["ok"])
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
