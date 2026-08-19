# -*- coding: utf-8 -*-
"""Arma las zapatas con parrilla en dos direcciones.

QUE HACE
--------
Por cada cimentacion cuyas dimensiones coincidan con una fila de la tabla de
armado, crea barras rectas con gancho:
  - direccion X, distribuidas a lo largo de Y
  - direccion Y, distribuidas a lo largo de X

Las aisladas (Z1..Z4) llevan **parrilla inferior sola**. Las combinadas
(6.00x9.00 y 17.00x10.00) llevan **inferior y superior**, segun el detalle
SZ5-SZ5: inferior #8 @ 0.10 y superior #8 @ 0.20.

SE IDENTIFICA POR DIMENSIONES, NO POR NOMBRE
--------------------------------------------
Los nombres de tipo del modelo estuvieron corridos respecto de los planos, asi
que la regla de armado se busca por (Lx, Ly) redondeados. Una zapata sin fila
en la tabla NO se arma: va a `sin_regla` y se reporta. Nunca se le aplica el
armado "del mas parecido" — seria E-043 otra vez.

ORIENTACION DEL GANCHO: MEDIDA, NO SUPUESTA
--------------------------------------------
`RebarTerminationOrientation` es `['Left','Right']`, no `['Up','Down']`: cual
de los dos apunta hacia arriba depende del plano de la barra y del sentido de
la curva. En vez de elegir uno de memoria, el script CREA la barra, lee su
bounding box y comprueba de que lado quedo el doblez. Si la parrilla inferior
tiene el gancho bajando —donde queda fuera del hormigon, sin recubrimiento y
sin anclar nada— invierte la orientacion y vuelve a medir.

FIRMA REAL DE ESTA INSTALACION (volcada 2026-08-14, no recordada)
------------------------------------------------------------------
    Rebar.CreateFromCurves(Document, RebarStyle, RebarBarType, Element host,
                           XYZ norm, IList<Curve>, BarTerminationsData,
                           bool useExistingShapeIfPossible, bool createNewShape)
    BarTerminationsData(Document)          <- constructor de UN argumento
    RebarStyle = Standard | StirrupTie
    RebarShapeDrivenAccessor.SetLayoutAsMaximumSpacing(
        spacing, arrayLength, barsOnNormalSide, includeFirstBar, includeLastBar)

`RebarHookOrientation` NO EXISTE en Revit 2027: verificado en runtime. No se
referencia — el gancho se fija por `BarTerminationsData.HookTypeIdAtStart/End`
con el ElementId de un `RebarHookType` del proyecto, que es la via que si
existe en esta version.

GANCHOS
-------
`Standard - 90 deg.` en AMBOS extremos de cada barra, en las dos direcciones.
Con ganchos la forma deja de ser la recta '00', asi que `createNewShape` va en
True: si la forma con ganchos no existe todavia en el proyecto, Revit tiene que
poder crearla o la llamada falla.

POR QUE `norm` ES PERPENDICULAR A LA BARRA
-------------------------------------------
`norm` define el plano de la barra, y el array de SetLayout se distribuye en la
direccion de esa normal. Barras que corren en X se distribuyen en Y -> norm =
BasisY. Barras que corren en Y -> norm = BasisX.

GUARDAS (E-039, E-041, E-043, E-045, E-046)
-------------------------------------------
- Marca lo que crea y borra su obra previa: idempotente, se puede repetir.
- Aborta si falta el RebarBarType pedido. Nunca sustituye por otro diametro.
- Comprueba que el canto alcance para el recubrimiento antes de armar.
- Verifica RELEYENDO cuantas barras quedaron hospedadas en cada zapata.
- Una transaccion por zapata: un fallo no se lleva las demas.
- Log incremental con fsync antes de cada barra.
"""
__title__ = "ArmarZapatas"
__doc__ = "Parrilla inferior en X e Y para las zapatas. Identifica por dimensiones."

import os
import clr
import json
import traceback

from pyrevit import revit, script
from pyrevit.api import DB
from System.Collections.Generic import List

doc = revit.doc

MARCA = "MCP:acero-zapata"
M = 0.3048                 # pies -> metros
REC_INF = 0.075            # recubrimiento inferior [m]  (datos_maestros)
REC_LAT = 0.075            # recubrimiento lateral  [m]
REC_SUP = 0.075            # recubrimiento superior [m]
TOL_DIM = 0.03             # tolerancia al casar dimensiones [m]
GANCHO_NOMBRE = "Standard - 90 deg."   # gancho en AMBOS extremos de cada barra

# --- TABLA DE ARMADO: (Lx, Ly) en metros -> barra y espaciamiento -----------
# Fuente: tabla de armado de zapatas centricas + 00_DATOS/zapatas.csv.
# Las combinadas NO estan: 6.00x9.00 dice "0.20/0.10" sin indicar que
# espaciamiento va en cada direccion, y 17.00x10.00 remite al detalle SZ7,
# que no esta en los datos. Se dejan sin armar a proposito.
#
# `inf` y `sup` son las parrillas inferior y superior. `sup: None` = zapata
# con parrilla inferior solamente (las aisladas Z1..Z4).
#
# Las combinadas llevan las dos, segun el detalle SZ5-SZ5:
# superior #8 @ 0.20 y inferior #8 @ 0.10. El CSV las anotaba como
# "0.20/0.10" sin decir cual iba en cada cara, y el operador confirmo que
# manda el dibujo: la densa abajo.
TABLA = {
    (5.70, 5.70): {"marca": "Z1",
                   "inf": {"barra": "#6", "esp": 0.10}, "sup": None},
    (6.00, 6.00): {"marca": "Z2",
                   "inf": {"barra": "#6", "esp": 0.10}, "sup": None},
    (6.50, 6.50): {"marca": "Z3",
                   "inf": {"barra": "#8", "esp": 0.15}, "sup": None},
    (6.70, 6.70): {"marca": "Z4",
                   "inf": {"barra": "#8", "esp": 0.10}, "sup": None},
    (6.00, 9.00): {"marca": "Z5/Z6",
                   "inf": {"barra": "#8", "esp": 0.10},
                   "sup": {"barra": "#8", "esp": 0.20}},
    (17.00, 10.00): {"marca": "Z7",
                     "inf": {"barra": "#8", "esp": 0.10},
                     "sup": {"barra": "#8", "esp": 0.20}},
}

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "armar_zapatas_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "armar_zapatas.json")

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
    "gancho": {},
    "armadas": [],
    "sin_regla": [],
    "fallos": [],
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: catalogo de barras -------------------------------------
    result["phase_reached"] = "fase1_barras"
    trace("FASE 1: tipos de barra")
    barras = {}
    for bt in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarBarType):
        barras[element_name(bt)] = bt
    requeridas = set()
    for v in TABLA.values():
        for cara in ("inf", "sup"):
            if v.get(cara):
                requeridas.add(v[cara]["barra"])
    faltan = sorted(requeridas - set(barras))
    if faltan:
        # E-043: prerrequisito de identidad ausente = aborto, no sustitucion.
        raise Exception("faltan tipos de barra en el proyecto: %s" % faltan)
    trace("FASE 1 OK: %d tipos, requeridos presentes" % len(barras))

    estilo = DB.Structure.RebarStyle.Standard

    # ---- Gancho: Standard 90 grados en AMBOS extremos -------------------
    # Es un prerrequisito de identidad como el tipo de barra: si el gancho
    # pedido no esta cargado se aborta, no se usa "el primero que haya".
    # Un gancho de estribo en una parrilla de zapata daria una geometria
    # que parece correcta y no lo es (E-043).
    ganchos = {}
    for hk in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarHookType):
        ganchos[element_name(hk)] = hk
    gancho = ganchos.get(GANCHO_NOMBRE)
    if gancho is None:
        raise Exception("no esta cargado el gancho '%s'. Disponibles: %s"
                        % (GANCHO_NOMBRE, sorted(ganchos)))
    result["gancho"] = {"nombre": GANCHO_NOMBRE, "id": eidv(gancho.Id)}
    trace("FASE 1: gancho '%s' id=%d" % (GANCHO_NOMBRE, eidv(gancho.Id)))

    # ---- Fase 2: limpiar obra propia anterior ---------------------------
    result["phase_reached"] = "fase2_limpieza"
    previos = []
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        p = bip(rb, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
        if p is not None and p.AsString() == MARCA:
            previos.append(rb.Id)
    if previos:
        trace("FASE 2: borrando %d barras de corrida anterior" % len(previos))
        t = DB.Transaction(doc, "MCP: limpiar acero de zapatas")
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
            raise Exception("no se pudo limpiar la corrida anterior: %s" % ex)
    trace("FASE 2 OK: %d borrados" % result["previos_borrados"])

    # ---- Fase 3: armar, una transaccion por zapata ----------------------
    result["phase_reached"] = "fase3_armado"
    zapatas = list(DB.FilteredElementCollector(doc)
                   .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
                   .WhereElementIsNotElementType())
    trace("FASE 3: %d cimentaciones" % len(zapatas))

    for z in zapatas:
        zid = eidv(z.Id)
        sym = doc.GetElement(z.GetTypeId())
        tipo_nom = element_name(sym)

        bb = z.get_BoundingBox(None)
        if bb is None:
            result["fallos"].append({"id": zid, "motivo": "sin bounding box"})
            continue
        lx = (bb.Max.X - bb.Min.X) * M
        ly = (bb.Max.Y - bb.Min.Y) * M
        h = (bb.Max.Z - bb.Min.Z) * M

        # buscar la regla por dimensiones, en cualquier orientacion
        regla = None
        for (rlx, rly), r in TABLA.items():
            if ((abs(lx - rlx) < TOL_DIM and abs(ly - rly) < TOL_DIM) or
                    (abs(lx - rly) < TOL_DIM and abs(ly - rlx) < TOL_DIM)):
                regla = r
                break
        if regla is None:
            result["sin_regla"].append({
                "id": zid, "tipo": tipo_nom,
                "lx": round(lx, 2), "ly": round(ly, 2), "h": round(h, 2),
                "motivo": "sin fila en la tabla de armado"})
            trace("  %d (%s) %.2fx%.2f: SIN REGLA, no se arma" % (zid, tipo_nom, lx, ly))
            continue

        # Diametros de cada parrilla (pueden diferir)
        cap_defs = [("inf", regla["inf"])]
        if regla.get("sup"):
            cap_defs.append(("sup", regla["sup"]))

        db_max = max(barras[c[1]["barra"]].BarNominalDiameter * M
                     for c in cap_defs)

        # El canto tiene que dar para todas las capas mas recubrimientos.
        n_capas = 2 * len(cap_defs)          # cada parrilla son 2 capas (X e Y)
        necesario = REC_INF + REC_SUP + n_capas * db_max if regla.get("sup") \
            else REC_INF + 2 * db_max
        if h < necesario:
            result["fallos"].append({
                "id": zid, "tipo": tipo_nom, "h": round(h, 3),
                "motivo": "canto %.3f m insuficiente: hace falta >= %.3f m "
                          "(%d capas)" % (h, necesario, n_capas)})
            trace("  %d: canto insuficiente (%.3f < %.3f)" % (zid, h, necesario))
            continue

        x0, x1 = bb.Min.X + REC_LAT / M, bb.Max.X - REC_LAT / M
        y0, y1 = bb.Min.Y + REC_LAT / M, bb.Max.Y - REC_LAT / M
        z_fondo, z_techo = bb.Min.Z, bb.Max.Z

        # Cotas de cada capa. En la parrilla inferior las barras en X van
        # abajo; en la superior, al reves: las de Y quedan por encima de las
        # de X mirando desde el fondo, pero ambas dentro del recubrimiento
        # superior.
        capas = []
        for cara, d in cap_defs:
            bt_c = barras[d["barra"]]
            db_c = bt_c.BarNominalDiameter * M
            if cara == "inf":
                zx = z_fondo + (REC_INF + db_c / 2.0) / M
                zy = z_fondo + (REC_INF + db_c + db_c / 2.0) / M
            else:
                zx = z_techo - (REC_SUP + db_c / 2.0) / M
                zy = z_techo - (REC_SUP + db_c + db_c / 2.0) / M
            capas.append((cara, d, bt_c, zx, zy))

        t = DB.Transaction(doc, "MCP: armar zapata %d" % zid)
        t.Start()
        try:
            hecho = []
            plan_capas = []
            for cara, d, bt_c, zx, zy in capas:
                plan_capas.append(("%s-X" % cara, cara, bt_c, d,
                                   DB.XYZ(x0, y0, zx), DB.XYZ(x1, y0, zx),
                                   DB.XYZ.BasisY, (y1 - y0) * M))
                plan_capas.append(("%s-Y" % cara, cara, bt_c, d,
                                   DB.XYZ(x0, y0, zy), DB.XYZ(x0, y1, zy),
                                   DB.XYZ.BasisX, (x1 - x0) * M))

            for etiqueta, cara, bt, d, p_ini, p_fin, norm, largo_array in plan_capas:
                espaciado = d["esp"]
                trace("  %d: creando capa %s (%s @ %.2f)"
                      % (zid, etiqueta, d["barra"], espaciado))
                curvas = List[DB.Curve]()
                curvas.Add(DB.Line.CreateBound(p_ini, p_fin))

                # Gancho en AMBOS extremos. La propiedad se asigna de las dos
                # formas posibles porque IronPython expone los property
                # setters de .NET tanto como atributo como metodo `set_*`,
                # y cual funciona depende de como quedo ligado el ensamblado.
                term = DB.Structure.BarTerminationsData(doc)
                gid = gancho.Id
                puesto = []
                for attr, metodo in (("HookTypeIdAtStart", "set_HookTypeIdAtStart"),
                                     ("HookTypeIdAtEnd", "set_HookTypeIdAtEnd")):
                    try:
                        setattr(term, attr, gid)
                        puesto.append(attr)
                    except Exception:
                        try:
                            getattr(term, metodo)(gid)
                            puesto.append(attr)
                        except Exception as ex:
                            raise Exception("no se pudo fijar %s: %s" % (attr, ex))
                trace("    ganchos fijados: %s" % puesto)

                # createNewShape=True: con ganchos la forma deja de ser la
                # recta '00'. Si la forma con ganchos no existe todavia en el
                # proyecto, hay que dejar que Revit la cree o la llamada falla.
                barra = DB.Structure.Rebar.CreateFromCurves(
                    doc, estilo, bt, z, norm, curvas, term, True, True)
                if barra is None:
                    raise Exception("CreateFromCurves devolvio None en capa %s" % etiqueta)

                acc = barra.GetShapeDrivenAccessor()
                acc.SetLayoutAsMaximumSpacing(
                    espaciado / M, largo_array / M, True, True, True)

                # --- orientacion del gancho, VERIFICADA por geometria ------
                # RebarTerminationOrientation es ['Left','Right'], no
                # ['Up','Down']: cual apunta hacia arriba depende del plano de
                # la barra y del sentido de la curva, asi que no se puede
                # fijar de memoria. Se crea, se mide el bounding box y se
                # comprueba de que lado quedo el doblez. Si quedo del lado
                # equivocado, se invierte y se vuelve a medir (E-046: releer,
                # no suponer).
                z_barra = p_ini.Z
                orientaciones = list(DB.Structure.RebarTerminationOrientation
                                     .GetValues(
                                         clr.GetClrType(
                                             DB.Structure.RebarTerminationOrientation))) \
                    if hasattr(DB.Structure.RebarTerminationOrientation, "GetValues") \
                    else [DB.Structure.RebarTerminationOrientation.Left,
                          DB.Structure.RebarTerminationOrientation.Right]

                def gancho_hacia_arriba(rb):
                    """True si el doblez apunta HACIA ADENTRO del hormigon.

                    Parrilla INFERIOR -> el gancho debe SUBIR.
                    Parrilla SUPERIOR -> el gancho debe BAJAR.
                    En ambos casos, hacia el interior de la zapata. Un gancho
                    que apunta hacia afuera queda sin recubrimiento y no ancla
                    nada. El operador reporto el 2026-08-14 que los inferiores
                    bajaban y los superiores subian: los dos al reves.
                    """
                    bbx = rb.get_BoundingBox(None)
                    if bbx is None:
                        return None
                    holgura = 0.02 / M          # 2 cm de tolerancia
                    if cara == "inf":
                        return bbx.Min.Z > z_barra - holgura
                    return bbx.Max.Z < z_barra + holgura

                # Correccion por RECREACION con la normal invertida.
                #
                # El intento anterior usaba GetBarTerminationsData /
                # SetBarTerminationsData, metodos que NUNCA se volcaron. Si no
                # existen, el fallback modificaba el objeto `term` local — que
                # ya se habia consumido al crear la barra — y no hacia nada.
                # Resultado: los ganchos quedaron al reves y el script informo
                # exito. Un "arreglo" que no se puede verificar no es un
                # arreglo.
                #
                # `norm` define el plano de la barra, y el gancho dobla dentro
                # de ese plano: invertir la normal invierte el lado del doblez.
                # Solo usa API ya verificada.
                ok_orient = gancho_hacia_arriba(barra)
                if ok_orient is False:
                    trace("    gancho al reves en %s, recreando con -norm"
                          % etiqueta)
                    ids_borrar = List[DB.ElementId]()
                    ids_borrar.Add(barra.Id)
                    doc.Delete(ids_borrar)

                    term2 = DB.Structure.BarTerminationsData(doc)
                    for attr, metodo in (("HookTypeIdAtStart", "set_HookTypeIdAtStart"),
                                         ("HookTypeIdAtEnd", "set_HookTypeIdAtEnd")):
                        try:
                            setattr(term2, attr, gid)
                        except Exception:
                            getattr(term2, metodo)(gid)

                    curvas2 = List[DB.Curve]()
                    curvas2.Add(DB.Line.CreateBound(p_ini, p_fin))
                    barra = DB.Structure.Rebar.CreateFromCurves(
                        doc, estilo, bt, z, norm.Negate(), curvas2, term2,
                        True, True)
                    if barra is None:
                        raise Exception("recreacion con -norm devolvio None en %s"
                                        % etiqueta)
                    acc = barra.GetShapeDrivenAccessor()
                    acc.SetLayoutAsMaximumSpacing(
                        espaciado / M, largo_array / M, True, True, True)

                    ok_orient = gancho_hacia_arriba(barra)
                    trace("    tras invertir norm: %s" % ok_orient)

                if ok_orient is False:
                    # Se reporta como FALLO, no como aviso enterrado en el log.
                    result.setdefault("ganchos_invertidos", []).append(
                        {"zapata": zid, "capa": etiqueta, "cara": cara})
                    trace("    ERROR: gancho sigue invertido en %s" % etiqueta)

                p = bip(barra, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS,
                        "Comments")
                if p is not None and not p.IsReadOnly:
                    p.Set(MARCA)

                hecho.append({"capa": etiqueta, "id": eidv(barra.Id),
                              "barra": d["barra"], "esp": espaciado, "cara": cara,
                              "cantidad": barra.NumberOfBarPositions})
            t.Commit()
            result["armadas"].append({
                "zapata": zid, "tipo": tipo_nom, "marca_plano": regla["marca"],
                "lx": round(lx, 2), "ly": round(ly, 2), "h": round(h, 2),
                "capas": hecho})
            trace("  %d OK: %s" % (zid, json.dumps(hecho)))
        except Exception as ex:
            t.RollBack()
            result["fallos"].append({"id": zid, "tipo": tipo_nom,
                                     "motivo": str(ex)})
            trace("  %d ROLLBACK: %s" % (zid, traceback.format_exc()))

    # ---- Fase 4: verificar RELEYENDO ------------------------------------
    result["phase_reached"] = "fase4_verificacion"
    trace("FASE 4: relectura")
    por_host = {}
    marcadas = 0
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        p = bip(rb, DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS, "Comments")
        if p is not None and p.AsString() == MARCA:
            marcadas += 1
            try:
                h = eidv(rb.GetHostId())
                por_host[h] = por_host.get(h, 0) + 1
            except Exception:
                continue
    # El esperado se calcula sumando las capas REALMENTE planificadas por
    # zapata, no asumiendo 2 por zapata. Las aisladas llevan 2 (inf X e Y) y
    # las combinadas 4 (inf + sup). La formula vieja (armadas * 2) era
    # correcta cuando todas eran de parrilla inferior y quedo invalida al
    # agregar las combinadas: reporto coincide=False sobre un armado que
    # estaba bien. Una verificacion que no se actualiza con el alcance del
    # script deja de verificar y empieza a mentir.
    esperado = sum(len(a["capas"]) for a in result["armadas"])
    capas_por_zapata = {a["zapata"]: len(a["capas"]) for a in result["armadas"]}
    correctas = len([z for z, n in capas_por_zapata.items()
                     if por_host.get(z, 0) == n])
    result["verificacion"] = {
        "zapatas_armadas": len(result["armadas"]),
        "sets_marcados": marcadas,
        "sets_esperados": esperado,
        "zapatas_con_capas_correctas": correctas,
        "detalle_capas": capas_por_zapata,
        "coincide": (marcadas == esperado
                     and correctas == len(result["armadas"])),
    }
    trace("FASE 4 OK: %s" % json.dumps(result["verificacion"]))

    result["phase_reached"] = "completo"
    result["ok"] = (not result["fallos"]
                    and not result.get("ganchos_invertidos")
                    and result["verificacion"]["coincide"])

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Armado de zapatas")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
if result["previos_borrados"]:
    out.print_md("- Limpieza previa: %d barras" % result["previos_borrados"])
if result.get("gancho"):
    out.print_md("- Gancho: `%s` en ambos extremos" % result["gancho"]["nombre"])
out.print_md("- Zapatas armadas: **%d**" % len(result["armadas"]))
for a in result["armadas"]:
    cant = " + ".join("%s:%s" % (c["capa"], c["cantidad"]) for c in a["capas"])
    out.print_md("  - `%s` %.2fx%.2f (%s) -> %s barras"
                 % (a["tipo"], a["lx"], a["ly"], a["marca_plano"], cant))
if result["sin_regla"]:
    out.print_md("- Sin regla (no armadas): **%d**" % len(result["sin_regla"]))
    for s in result["sin_regla"]:
        out.print_md("  - `%s` %.2f x %.2f m" % (s["tipo"], s["lx"], s["ly"]))
if result["fallos"]:
    out.print_md("- ⚠️ **fallos: %d** — ver JSON" % len(result["fallos"]))
gi = result.get("ganchos_invertidos") or []
if gi:
    out.print_md("- ⚠️ **ganchos invertidos: %d** (no se pudieron corregir)" % len(gi))
else:
    out.print_md("- Ganchos: todos hacia el interior ✓")
v = result.get("verificacion")
if v:
    out.print_md("- Verificado: %d sets marcados de %d esperados | zapatas OK: %d/%d | **coincide: %s**"
                 % (v["sets_marcados"], v["sets_esperados"],
                    v["zapatas_con_capas_correctas"], v["zapatas_armadas"], v["coincide"]))
out.print_md("- **ok: %s**" % result["ok"])
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
