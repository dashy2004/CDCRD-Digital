# -*- coding: utf-8 -*-
"""acero_losas_modelar: modela en 3D el acero de las losas (Rebar reales).

Consume el plan_modelado.json de `plugin-losas modelado` (sets de barras con
solape 50db mitad y mitad, nervios de aligeradas y bastones de apoyo) y crea
los Rebar con la RECETA DE LA CASA (GenerarAceroVigas/ArmarZapatas, firma real
de esta instalacion, Revit 2027):

    Rebar.CreateFromCurves(Document, RebarStyle.Standard, RebarBarType, host,
                           XYZ norm, IList<Curve>, BarTerminationsData,
                           True, True)
    + GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(n, paso, True,
                           True, True) para repartir el set.

GUARDAS (las del criterio del proyecto):
- MODO PILOTO por defecto: solo la PRIMERA losa (orden de Mark); revisar en
  3D y repetir con todas=true. solo_marks elige losas concretas.
- UNA transaccion POR LOSA; un fallo no arrastra a las demas (va a 'fallos').
- Marca su obra (Comments = "MCP:ACERO-LOSA-3D") y borra la previa de cada
  losa antes de recrear: idempotente.
- Nunca inventa un RebarBarType: si el diametro pedido no esta cargado, esa
  losa falla con diagnostico exacto.
- Verifica RELEYENDO: sets y barras hospedadas en cada losa tras el commit.
- Los bastones cruzan al pano vecino (anfitrion = losa_i): pueden avisar de
  recubrimiento en el borde, es la geometria pedida (L/4 + L/4).

Parametros (P):
  plan:       ruta del plan_modelado.json (obligatorio).
  marker:     prefijo de Comments de las losas (default "MCP:LOSA-ESQ").
  todas:      True procesa todas las losas del plan (default False = piloto).
  solo_marks: lista de Marks concretos (anula el piloto).
  limpiar:    True (default) borra el acero MCP:ACERO-LOSA-3D previo por losa.

No guarda (revit_guardar_modelo despues).
"""

MARCA = "MCP:ACERO-LOSA-3D"
M_A_FT = 1.0 / 0.3048

ALIAS_DIAMETRO = {
    "#3": ["3/8\"", "#3", "N3", "10M"],
    "#4": ["1/2\"", "#4", "N4", "13M"],
    "#5": ["5/8\"", "#5", "N5", "16M"],
    "#6": ["3/4\"", "#6", "N6", "20M"],
    "#8": ["1\"", "#8", "N8", "25M"],
}


def _mark_de(el):
    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    return p.AsString() if p is not None else None


def _tipos_barra(doc):
    out = {}
    for bt in DB.FilteredElementCollector(doc).OfClass(DB.Structure.RebarBarType):
        n = element_name(bt)
        if n:
            out[n] = bt
    return out


def _resolver_barra(tipos, diam):
    for alias in ALIAS_DIAMETRO.get(diam, [diam]):
        if alias in tipos:
            return tipos[alias]
    raise Exception("no hay RebarBarType para %s (alias probados %s; cargados: %s)"
                    % (diam, ALIAS_DIAMETRO.get(diam, [diam]), sorted(tipos)[:20]))


def _espesor_ft(doc, losa):
    try:
        p = losa.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)
        if p is not None and p.HasValue:
            return p.AsDouble()
    except Exception:
        pass
    t = doc.GetElement(losa.GetTypeId())
    p = t.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_DEFAULT_THICKNESS_PARAM)
    if p is None or not p.HasValue:
        raise Exception("no se pudo leer el espesor de la losa %s" % _mark_de(losa))
    return p.AsDouble()


def _acero_previo(doc, losa):
    ids = []
    for r in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar):
        try:
            if eidv(r.GetHostId()) != eidv(losa.Id):
                continue
        except Exception:
            continue
        p = r.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p is not None and (p.AsString() or "") == MARCA:
            ids.append(r.Id)
    return ids


def _contar_acero(doc, losa):
    sets, barras = 0, 0
    for rid in _acero_previo(doc, losa):
        r = doc.GetElement(rid)
        sets += 1
        try:
            barras += r.NumberOfBarPositions
        except Exception:
            barras += 1
    return sets, barras


def _crear_set(doc, losa, registro, z_ft, origen, tipos):
    from System.Collections.Generic import List
    ox, oy = origen
    (x0, y0), (x1, y1) = registro["linea"]
    p0 = DB.XYZ((x0 + ox) * M_A_FT, (y0 + oy) * M_A_FT, z_ft)
    p1 = DB.XYZ((x1 + ox) * M_A_FT, (y1 + oy) * M_A_FT, z_ft)
    curvas = List[DB.Curve]()
    curvas.Add(DB.Line.CreateBound(p0, p1))
    normal = DB.XYZ.BasisY if registro["eje"] == "X" else DB.XYZ.BasisX
    bt = _resolver_barra(tipos, registro["diam"])
    term = DB.Structure.BarTerminationsData(doc)
    barra = DB.Structure.Rebar.CreateFromCurves(
        doc, DB.Structure.RebarStyle.Standard, bt, losa, normal, curvas,
        term, True, True)
    if barra is None:
        raise Exception("CreateFromCurves devolvio None (%s %s de %s)" %
                        (registro["clase"], registro["eje"], registro["mark"]))
    n = int(registro["n"])
    if n > 1:
        paso_ft = registro["paso_m"] * M_A_FT
        acc = barra.GetShapeDrivenAccessor()
        try:
            acc.SetLayoutAsNumberWithSpacing(n, paso_ft, True, True, True)
        except Exception:
            acc.SetLayoutAsMaximumSpacing(paso_ft, (n - 1) * paso_ft, True, True, True)
    p = barra.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p is not None and not p.IsReadOnly:
        p.Set(MARCA)
    return n


def run(doc, uidoc, DB, P):
    import io
    import json
    ruta = P.get("plan")
    if not ruta:
        raise Exception("falta 'plan' (plan_modelado.json de `plugin-losas modelado`)")
    plan = json.load(io.open(ruta, encoding="utf-8"))
    marker = P.get("marker") or "MCP:LOSA-ESQ"
    origen = plan.get("origen_m") or [0.0, 0.0]
    rec_ft = (plan.get("recubrimiento_m") or 0.025) * M_A_FT
    sep_ft = (plan.get("separacion_capas_m") or 0.003) * M_A_FT
    e = errs()

    por_mark = {}
    for f in collector(doc, DB.BuiltInCategory.OST_Floors):
        if has_mark(f, marker):
            mk = _mark_de(f)
            if mk:
                por_mark[mk] = f

    losas_plan = [x for x in plan.get("losas") or [] if x.get("sets")]
    marks_plan = [x["mark"] for x in losas_plan]
    if P.get("solo_marks"):
        elegidos = [m for m in marks_plan if m in set(P["solo_marks"])]
    elif P.get("todas"):
        elegidos = marks_plan
    else:
        elegidos = marks_plan[:1]      # MODO PILOTO: una losa, revisar, seguir
    if not elegidos:
        raise Exception("ninguna losa del plan coincide con lo pedido")
    faltan = sorted(m for m in elegidos if m not in por_mark)
    if faltan:
        raise Exception("marks del plan sin losa en el modelo: %s" % faltan)

    bastones_por_host = {}
    for b in plan.get("bastones") or []:
        bastones_por_host.setdefault(b["set"]["mark"], []).append(b["set"])

    tipos = _tipos_barra(doc)

    def _z_ft(losa, registro):
        bb = losa.get_BoundingBox(None)
        z_top = bb.Max.Z
        z_bot = z_top - _espesor_ft(doc, losa)
        db_ft = registro["db_m"] * M_A_FT
        desplome = (registro["orden"] - 1) * (db_ft + sep_ft)
        if registro["capa"] == "superior":
            return z_bot + _espesor_ft(doc, losa) - rec_ft - db_ft / 2.0 - desplome
        return z_bot + rec_ft + db_ft / 2.0 + desplome

    resultados, fallos = [], []
    for x in losas_plan:
        mk = x["mark"]
        if mk not in elegidos:
            continue
        losa = por_mark[mk]
        registros = list(x["sets"]) + bastones_por_host.get(mk, [])
        t = DB.Transaction(doc, "MCP: acero 3D losa %s" % mk)
        t.Start()
        try:
            borrados = 0
            if P.get("limpiar", True):
                for rid in _acero_previo(doc, losa):
                    doc.Delete(rid)
                    borrados += 1
            sets_creados, barras_plan = 0, 0
            for registro in registros:
                barras_plan += _crear_set(doc, losa, registro,
                                          _z_ft(losa, registro), origen, tipos)
                sets_creados += 1
            t.Commit()
        except Exception as ex:
            t.RollBack()
            fallos.append({"mark": mk, "error": str(ex)[:300]})
            continue
        sets_leidos, barras_leidas = _contar_acero(doc, losa)   # releyendo
        resultados.append({"mark": mk, "sets_plan": len(registros),
                           "sets_leidos": sets_leidos,
                           "barras_plan": barras_plan,
                           "barras_leidas": barras_leidas,
                           "previos_borrados": borrados,
                           "ok": sets_leidos == len(registros) and
                                 barras_leidas == barras_plan})

    pendientes = [m for m in marks_plan if m not in elegidos]
    return {"marca": MARCA, "piloto": not (P.get("todas") or P.get("solo_marks")),
            "losas": resultados, "fallos": fallos,
            "pendientes": pendientes[:50], "n_pendientes": len(pendientes),
            "errores": e}
