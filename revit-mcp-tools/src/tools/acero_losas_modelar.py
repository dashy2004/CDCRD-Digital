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
- Nunca SUSTITUYE un diametro por otro. Si el diametro pedido no esta
  cargado, esa losa falla con diagnostico exacto; con crear_tipos_barra=true
  la tool crea ANTES los RebarBarType del catalogo que falten (nombre del
  despacho, diametro nominal exacto, transaccion propia, verificados
  releyendo) -- necesario en modelos sin ningun tipo de barra (CLUB PN).
- Verifica RELEYENDO: sets y barras hospedadas en cada losa tras el commit.
- GUARDA DE RAM (crash 2026-10-22): bajo RAM_MINIMA_MB no arranca, y entre
  losas se detiene limpio dejando lo hecho; log incremental con fsync en
  %TEMP%\\plugin_losas_modelado.log (la ultima losa intentada sobrevive a
  un crash).
- Los bastones cruzan al pano vecino (anfitrion = losa_i): pueden avisar de
  recubrimiento en el borde, es la geometria pedida (L/4 + L/4).

Parametros (P):
  plan:       ruta del plan_modelado.json (obligatorio).
  marker:     prefijo de Comments de las losas (default "MCP:LOSA-ESQ").
  todas:      True procesa todas las losas del plan (default False = piloto).
  solo_marks: lista de Marks concretos (anula el piloto).
  limpiar:    True (default) borra el acero MCP:ACERO-LOSA-3D previo por losa.
  crear_tipos_barra: True crea los RebarBarType del catalogo que falten
              (default False: sin tipos cargados, las losas fallan).

No guarda (revit_guardar_modelo despues).
"""

MARCA = "MCP:ACERO-LOSA-3D"
M_A_FT = 1.0 / 0.3048

# Guarda de memoria (E-133/E-134 + crash del 2026-10-22, journal 0283: Revit
# murio sin excepcion en pleno comando del boton con 211-505 MB libres).
# Bajo este umbral NO se arranca, y entre losas se PARA limpio en vez de
# tumbar la sesion; lo hecho hasta ahi queda commiteado.
RAM_MINIMA_MB = 700


def _ram_disponible_mb():
    try:
        import clr
        clr.AddReference("Microsoft.VisualBasic")
        from Microsoft.VisualBasic.Devices import ComputerInfo
        return int(ComputerInfo().AvailablePhysicalMemory / (1024 * 1024))
    except Exception:
        return None


def _log(linea):
    """Log incremental con fsync: un crash deja escrita la ultima losa."""
    import datetime
    import io
    import os
    import tempfile
    ruta = os.path.join(tempfile.gettempdir(), "plugin_losas_modelado.log")
    try:
        f = io.open(ruta, "a", encoding="utf-8")
        try:
            f.write("%s %s\n" % (datetime.datetime.now().isoformat(), linea))
            f.flush()
            os.fsync(f.fileno())
        finally:
            f.close()
    except Exception:
        pass
    return ruta

ALIAS_DIAMETRO = {
    "#3": ["3/8\"", "#3", "N3", "10M"],
    "#4": ["1/2\"", "#4", "N4", "13M"],
    "#5": ["5/8\"", "#5", "N5", "16M"],
    "#6": ["3/4\"", "#6", "N6", "20M"],
    "#8": ["1\"", "#8", "N8", "25M"],
}

# Nombre primario (convencion del despacho, la misma de GenerarAceroVigas y
# PRIMIS) y diametro nominal [m] de cada barra del catalogo. Se usan SOLO
# para crear el RebarBarType exacto cuando el modelo no trae ninguno
# (crear_tipos_barra=true): crear el tipo con su diametro real NO es
# sustituir un diametro por otro, que sigue prohibido.
NOMBRE_TIPO = {"#3": "3/8\"", "#4": "1/2\"", "#5": "5/8\"",
               "#6": "3/4\"", "#8": "1\""}
DIAMETROS_CATALOGO = {"#3": 0.009525, "#4": 0.0127, "#5": 0.015875,
                      "#6": 0.01905, "#8": 0.0254}


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
    raise Exception("no hay RebarBarType para %s (alias probados %s; cargados: %s); "
                    "repetir con crear_tipos_barra=true para crear los del catalogo"
                    % (diam, ALIAS_DIAMETRO.get(diam, [diam]), sorted(tipos)[:20]))


def _crear_tipos_barra(doc, faltantes):
    """Crea los RebarBarType del catalogo que falten (CLUB PN no trae
    ninguno), con su diametro nominal exacto, en transaccion propia, y
    verifica releyendo el diametro."""
    creados = []
    t = DB.Transaction(doc, "MCP: tipos de barra del catalogo")
    t.Start()
    try:
        for diam in sorted(faltantes):
            if diam not in DIAMETROS_CATALOGO:
                raise Exception("barra %s fuera del catalogo %s"
                                % (diam, sorted(DIAMETROS_CATALOGO)))
            d_ft = DIAMETROS_CATALOGO[diam] * M_A_FT
            bt = DB.Structure.RebarBarType.Create(doc)
            bt.Name = NOMBRE_TIPO[diam]
            puesto = False
            for prop in ("BarNominalDiameter", "BarModelDiameter", "BarDiameter"):
                try:
                    setattr(bt, prop, d_ft)
                    puesto = True
                except Exception:
                    pass
            if not puesto:
                raise Exception("no se pudo fijar el diametro de %s" % NOMBRE_TIPO[diam])
            creados.append(NOMBRE_TIPO[diam])
        t.Commit()
    except Exception:
        t.RollBack()
        raise
    # verificacion releyendo: nombre y diametro (tolerancia 0.1 mm)
    tipos = _tipos_barra(doc)
    for diam in sorted(faltantes):
        bt = tipos.get(NOMBRE_TIPO[diam])
        if bt is None:
            raise Exception("el tipo %s no aparece tras crearlo" % NOMBRE_TIPO[diam])
        leido = None
        for prop in ("BarNominalDiameter", "BarModelDiameter", "BarDiameter"):
            try:
                leido = getattr(bt, prop)
                break
            except Exception:
                pass
        if leido is None or abs(leido / M_A_FT - DIAMETROS_CATALOGO[diam]) > 0.0001:
            raise Exception("diametro releido de %s no coincide (%s)"
                            % (NOMBRE_TIPO[diam], leido))
    return creados


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
    tipos_creados = []
    necesarios = set()
    for x in losas_plan:
        for registro in x["sets"]:
            necesarios.add(registro["diam"])
    for b in plan.get("bastones") or []:
        necesarios.add(b["set"]["diam"])
    faltantes = set(d for d in necesarios
                    if not any(a in tipos for a in ALIAS_DIAMETRO.get(d, [d])))
    if faltantes and P.get("crear_tipos_barra"):
        tipos_creados = _crear_tipos_barra(doc, faltantes)
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

    ram = _ram_disponible_mb()
    if ram is not None and ram < RAM_MINIMA_MB:
        raise Exception("solo %d MB de RAM libre (minimo %d): cerrar "
                        "aplicaciones (y la VM: wsl --shutdown) antes de "
                        "modelar; con la maquina asi Revit se cae "
                        "(E-133/E-134, crash del 2026-10-22)" %
                        (ram, RAM_MINIMA_MB))

    resultados, fallos = [], []
    procesados = set()
    detenido_por_ram = None
    ruta_log = _log("CORRIDA: %d losas elegidas de %d; RAM %s MB" %
                    (len(elegidos), len(marks_plan), ram))
    for x in losas_plan:
        mk = x["mark"]
        if mk not in elegidos:
            continue
        ram = _ram_disponible_mb()
        if ram is not None and ram < RAM_MINIMA_MB:
            detenido_por_ram = {"ram_mb": ram, "antes_de": mk}
            _log("DETENIDO por RAM (%d MB) antes de %s" % (ram, mk))
            break
        losa = por_mark[mk]
        registros = list(x["sets"]) + bastones_por_host.get(mk, [])
        _log("INICIO %s: %d sets (RAM %s MB)" % (mk, len(registros), ram))
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
            _log("FALLO %s: %s" % (mk, str(ex)[:200]))
            fallos.append({"mark": mk, "error": str(ex)[:300]})
            procesados.add(mk)
            continue
        procesados.add(mk)
        sets_leidos, barras_leidas = _contar_acero(doc, losa)   # releyendo
        _log("OK %s: %d sets, %d barras" % (mk, sets_leidos, barras_leidas))
        resultados.append({"mark": mk, "sets_plan": len(registros),
                           "sets_leidos": sets_leidos,
                           "barras_plan": barras_plan,
                           "barras_leidas": barras_leidas,
                           "previos_borrados": borrados,
                           "ok": sets_leidos == len(registros) and
                                 barras_leidas == barras_plan})

    pendientes = [m for m in marks_plan if m not in procesados]
    return {"marca": MARCA, "piloto": not (P.get("todas") or P.get("solo_marks")),
            "tipos_barra_creados": tipos_creados,
            "losas": resultados, "fallos": fallos,
            "detenido_por_ram": detenido_por_ram, "log": ruta_log,
            "pendientes": pendientes[:50], "n_pendientes": len(pendientes),
            "errores": e}
