# -*- coding: utf-8 -*-
"""acero_losas_plano: dibuja el armado de losas en la vista de planta y crea
la tabla de detalles (schedule) con los parametros del plugin de losas.

Toma el plan_acero.json de `plugin-losas plano` (trazos en metros: principal,
temperatura y bastones adicionales, con sus rotulos) y lo traza como LINEAS DE
DETALLE + NOTAS DE TEXTO en la vista, todas con Comments "MCP:ACERO-LOSA"
para poder limpiarlas y redibujar (idempotente). La tabla es un Schedule de
Floors con Mark, Uso_Losa, Tipo_Losa_PM, Seccion_Losa y Acero_X/Y/Apoyo.

Parametros (P):
  plan:      ruta del plan_acero.json (obligatorio).
  view_name: vista de planta destino (default: la vista activa).
  limpiar:   True (default) borra el dibujo MCP:ACERO-LOSA previo de la vista.
  tabla:     True (default) crea/rehace el schedule "MCP Tabla de losas".

Solo se dibujan las losas cuyo nivel coincide con el de la vista. Un trazo
usa simbologia nativa (lineas + texto): si el despacho aporta familias de
simbolo de baston/gancho, se podran colocar instancias en su lugar (pendiente).
UNA transaccion con rollback; no guarda.
"""

MARCA_DIBUJO = "MCP:ACERO-LOSA"
NOMBRE_TABLA = "MCP Tabla de losas"
M_A_FT = 1.0 / 0.3048


def _nivel_de(view):
    try:
        return view.GenLevel.Name
    except Exception:
        return None


def _vistas(doc, uidoc, nombre, niveles):
    """Las vistas de planta destino, emparejadas con su nivel.

    Con ``view_name`` se usa esa vista; si no, la activa cuando es de planta;
    y si la activa no sirve (p. ej. la Project View), se busca SOLA la primera
    planta de cada nivel que tenga losas en el plan (preferencia a las que
    empiezan por EST)."""
    if nombre:
        v = active_or_named_view(doc, uidoc, nombre)
        if not isinstance(v, DB.ViewPlan):
            raise Exception("la vista '%s' no es de planta" % v.Name)
        return [(v, _nivel_de(v))]
    try:
        activa = uidoc.ActiveView if uidoc is not None else doc.ActiveView
    except Exception:
        activa = None
    if isinstance(activa, DB.ViewPlan):
        return [(activa, _nivel_de(activa))]
    por_nivel = {}
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan):
        if v.IsTemplate:
            continue
        nv = _nivel_de(v)
        if nv not in niveles:
            continue
        actual = por_nivel.get(nv)
        if actual is None or (v.Name.upper().startswith("EST") and
                              not actual.Name.upper().startswith("EST")):
            por_nivel[nv] = v
    if not por_nivel:
        raise Exception("la vista activa no es de planta y no hay plantas de los "
                        "niveles con losas (%s); abre o crea la planta del nivel" %
                        sorted(niveles))
    return [(por_nivel[nv], nv) for nv in sorted(por_nivel)]


def _poner_marca(el):
    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
    if p is not None:
        p.Set(MARCA_DIBUJO)


def _z_de_vista(doc, view):
    candidatos = []
    try:
        candidatos.append(view.Origin.Z)
    except Exception:
        pass
    try:
        candidatos.append(view.GenLevel.ProjectElevation)
    except Exception:
        pass
    candidatos.append(0.0)
    return candidatos


def _dibujar_trazo(doc, view, trazo, z, e, origen):
    ox, oy = origen
    puntos = trazo["puntos"]
    for k in range(len(puntos) - 1):
        x0, y0 = puntos[k]
        x1, y1 = puntos[k + 1]
        linea = DB.Line.CreateBound(DB.XYZ((x0 + ox) * M_A_FT, (y0 + oy) * M_A_FT, z),
                                    DB.XYZ((x1 + ox) * M_A_FT, (y1 + oy) * M_A_FT, z))
        try:
            dc = doc.Create.NewDetailCurve(view, linea)
            _poner_marca(dc)
        except Exception as ex:
            e["n"] += 1
            if len(e["items"]) < 20:
                e["items"].append("linea %s: %s" % (trazo.get("texto"), ex))
            return 0
    return 1


def _nota(doc, view, texto, pos, z, tipo_texto, e, origen):
    if not texto:
        return 0
    ox, oy = origen
    try:
        tn = DB.TextNote.Create(doc, view.Id,
                                DB.XYZ((pos[0] + ox) * M_A_FT, (pos[1] + oy) * M_A_FT, z),
                                texto, tipo_texto)
        _poner_marca(tn)
        return 1
    except Exception as ex:
        e["n"] += 1
        if len(e["items"]) < 20:
            e["items"].append("nota %s: %s" % (texto, ex))
        return 0


def _limpiar(doc, view):
    ids = []
    for clase in (DB.CurveElement, DB.TextNote):
        for el in DB.FilteredElementCollector(doc, view.Id).OfClass(clase):
            p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
            if p is not None and (p.AsString() or "") == MARCA_DIBUJO:
                ids.append(el.Id)
    for i in ids:
        doc.Delete(i)
    return len(ids)


def _rehacer_tabla(doc, parametros):
    # ids primero y borrar despues: eliminar dentro de la iteracion del
    # collector invalida el iterador ("The iterator cannot proceed...")
    previas = [vs.Id for vs in DB.FilteredElementCollector(doc).OfClass(DB.ViewSchedule)
               if vs.Name == NOMBRE_TABLA]
    for vid in previas:
        doc.Delete(vid)
    tabla = DB.ViewSchedule.CreateSchedule(
        doc, DB.ElementId(DB.BuiltInCategory.OST_Floors))
    tabla.Name = NOMBRE_TABLA
    definicion = tabla.Definition
    disponibles = {}
    for sf in definicion.GetSchedulableFields():
        try:
            disponibles[sf.GetName(doc)] = sf
        except Exception:
            pass
    agregados = []
    campo_mark = None
    for nombre in parametros:
        if nombre in disponibles:
            campo = definicion.AddField(disponibles[nombre])
            agregados.append(nombre)
            if nombre == "Mark":
                campo_mark = campo
    if campo_mark is not None:
        orden = DB.ScheduleSortGroupField(campo_mark.FieldId)
        definicion.AddSortGroupField(orden)
    return agregados


def run(doc, uidoc, DB, P):
    import io
    import json
    ruta = P.get("plan")
    if not ruta:
        raise Exception("falta 'plan' (plan_acero.json de `plugin-losas plano`)")
    plan = json.load(io.open(ruta, encoding="utf-8"))
    origen = plan.get("origen_m") or [0.0, 0.0]
    e = errs()
    niveles_plan = set(x.get("nivel") for x in plan.get("losas") or [] if x.get("nivel"))
    vistas = _vistas(doc, uidoc, P.get("view_name"), niveles_plan)
    tipo_texto = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)

    tandas = []     # (view, nivel, losas, apoyos)
    for view, nivel_vista in vistas:
        losas = [x for x in plan.get("losas") or []
                 if nivel_vista is None or x.get("nivel") == nivel_vista]
        apoyos = [x for x in plan.get("apoyos") or []
                  if nivel_vista is None or x.get("nivel") == nivel_vista]
        if losas:
            tandas.append((view, nivel_vista, losas, apoyos))
    if not tandas:
        raise Exception("el plan no trae losas de los niveles de las vistas (%s)" %
                        [v.Name for v, _ in vistas])

    def _dibujar_en(view, losas, apoyos):
        lineas = [0]
        notas = [0]
        z_valida = [None]

        def dibujar(trazo):
            if z_valida[0] is None:
                for z in _z_de_vista(doc, view):
                    antes = e["n"]
                    if _dibujar_trazo(doc, view, trazo, z, e, origen) and e["n"] == antes:
                        z_valida[0] = z
                        lineas[0] += 1
                        notas[0] += _nota(doc, view, trazo.get("texto"),
                                          trazo["pos_texto"], z, tipo_texto, e, origen)
                        return
                raise Exception("no se pudo trazar en '%s': %s" %
                                (view.Name, e["items"][-3:]))
            lineas[0] += _dibujar_trazo(doc, view, trazo, z_valida[0], e, origen)
            notas[0] += _nota(doc, view, trazo.get("texto"), trazo["pos_texto"],
                              z_valida[0], tipo_texto, e, origen)

        for losa in losas:
            for trazo in losa["trazos"]:
                dibujar(trazo)
        for a in apoyos:
            dibujar(a["trazo"])
        return lineas[0], notas[0]

    def _todo():
        resultados = []
        for view, nivel_vista, losas, apoyos in tandas:
            borradas = _limpiar(doc, view) if P.get("limpiar", True) else 0
            lineas, notas = _dibujar_en(view, losas, apoyos)
            resultados.append({"vista": view.Name, "nivel": nivel_vista,
                               "losas_dibujadas": len(losas), "bastones": len(apoyos),
                               "trazos": lineas, "notas": notas,
                               "elementos_borrados": borradas})
        campos = _rehacer_tabla(doc, plan.get("tabla_parametros") or []) \
            if P.get("tabla", True) else []
        return resultados, campos

    resultados, campos = tx(doc, "MCP: acero de losas en planta", _todo)
    try:    # abrir la primera planta dibujada (operacion de UI, fuera de transaccion)
        if uidoc is not None:
            uidoc.ActiveView = tandas[0][0]
    except Exception:
        pass
    return {"vistas": resultados,
            "tabla": {"nombre": NOMBRE_TABLA, "campos": campos} if campos else None,
            "errores": e}
