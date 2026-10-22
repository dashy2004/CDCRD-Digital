# -*- coding: utf-8 -*-
"""tag_losas: etiqueta cada losa — Mark ARRIBA y ESPESOR (H=) debajo — en la
planta de su nivel.

DOS MODOS (P["modo"], default "auto"):
- "tag":   IndependentTag con la familia personalizada. La familia NO se
  puede crear por API (limitacion del API de Revit: no hay creacion de
  labels), tiene que existir como .rfa: se busca cargada o se carga de
  P["ruta_rfa"].
- "texto": SIN familia — una nota de texto de dos lineas por losa
  ("L00" / "H=0.15", espesor REAL leido del tipo), marcada con Comments
  MCP:TAG-LOSA para limpiar y regenerar (idempotente). No es parametrica
  (re-correr el boton tras cambiar espesores), pero no depende de nada.
- "auto":  tag si la familia esta disponible; si no, texto.

En ambos modos: se colocan en el centroide del bbox en la planta del nivel,
se borra lo previo de esta tool en la vista, y se verifica releyendo.

Receta de la familia (UNA vez, a mano o la .rfa del despacho):
  Nueva familia -> plantilla "Metric Generic Tag" (tag generico metrico);
  Family Category = Floor Tags (Etiquetas de suelo); label 1 = Mark;
  label 2 DEBAJO = Thickness (espesor; con el tipo por seccion ya aplicado
  muestra el espesor real) y opcionalmente la seccion (parametro compartido
  Seccion_Losa, importado del archivo de parametros del plugin);
  guardar como "CDCRD Tag Losa.rfa" en plugin-losas/revit/familias/
  (los .rfa no van a git, politica del repo).

Parametros (P):
  marker:    prefijo de Comments de las losas (default "MCP:LOSA-ESQ").
  familia:   nombre de la familia de tag (default "CDCRD Tag Losa").
  tipo:      nombre del tipo dentro de la familia (default: el primero).
  ruta_rfa:  .rfa a cargar si la familia no esta en el modelo.
  view_name: una planta concreta (default: la primera planta de cada nivel
             con losas, preferencia EST*, igual que el dibujo del acero).
  limpiar:   True (default) borra los tags previos de la familia en la vista.

UNA transaccion con rollback; no guarda (revit_guardar_modelo despues).
"""

FAMILIA_DEFAULT = "CDCRD Tag Losa"
MARCA_TEXTO = "MCP:TAG-LOSA"

RECETA = ("la familia de tag no esta en el modelo ni hay .rfa que cargar. "
          "Crearla UNA vez (o usar la del despacho): Nueva familia -> "
          "plantilla 'Metric Generic Tag'; Family Category = Floor Tags; "
          "label Mark arriba y label Thickness (espesor) debajo; guardarla "
          "como 'CDCRD Tag Losa.rfa' en plugin-losas/revit/familias/ y "
          "repetir.")


def _nivel_de(view):
    try:
        return view.GenLevel.Name
    except Exception:
        return None


def _vistas(doc, uidoc, nombre, niveles):
    """Igual que acero_losas_plano: la vista pedida, la activa si es planta,
    o la primera planta de cada nivel con losas (preferencia EST*)."""
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
        raise Exception("no hay plantas de los niveles con losas (%s); abre o "
                        "crea la planta del nivel" % sorted(niveles))
    return [(por_nivel[nv], nv) for nv in sorted(por_nivel)]


def _simbolo_tag(doc, familia, tipo):
    for s in DB.FilteredElementCollector(doc) \
            .OfCategory(DB.BuiltInCategory.OST_FloorTags).WhereElementIsElementType():
        try:
            if s.FamilyName != familia:
                continue
        except Exception:
            continue
        if tipo is None or element_name(s) == tipo:
            return s
    return None


def _tags_de_familia(doc, view, familia):
    ids = []
    for t in DB.FilteredElementCollector(doc, view.Id) \
            .OfCategory(DB.BuiltInCategory.OST_FloorTags).WhereElementIsNotElementType():
        try:
            s = doc.GetElement(t.GetTypeId())
            if s is not None and s.FamilyName == familia:
                ids.append(t.Id)
        except Exception:
            pass
    return ids


def _centro_bbox(el):
    bb = el.get_BoundingBox(None)
    if bb is None:
        return None
    return DB.XYZ((bb.Min.X + bb.Max.X) / 2.0, (bb.Min.Y + bb.Max.Y) / 2.0,
                  bb.Max.Z)


def _espesor_m(doc, el):
    try:
        p = el.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)
        if p is not None and p.HasValue:
            return round(p.AsDouble() * 0.3048, 3)
    except Exception:
        pass
    try:
        t = doc.GetElement(el.GetTypeId())
        p = t.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_DEFAULT_THICKNESS_PARAM)
        if p is not None and p.HasValue:
            return round(p.AsDouble() * 0.3048, 3)
    except Exception:
        pass
    return None


def _textos_marca(doc, view):
    ids = []
    for tn in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.TextNote):
        p = tn.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p is not None and (p.AsString() or "") == MARCA_TEXTO:
            ids.append(tn.Id)
    return ids


def run(doc, uidoc, DB, P):
    import os
    marker = P.get("marker") or "MCP:LOSA-ESQ"
    familia = P.get("familia") or FAMILIA_DEFAULT
    tipo = P.get("tipo")
    modo = P.get("modo") or "auto"
    e = errs()

    losas = [f for f in collector(doc, DB.BuiltInCategory.OST_Floors)
             if has_mark(f, marker)]
    if not losas:
        raise Exception("ninguna losa con Comments '%s*'" % marker)
    por_nivel = {}
    for f in losas:
        nv = level_name(doc, f.LevelId)
        por_nivel.setdefault(nv, []).append(f)

    vistas = _vistas(doc, uidoc, P.get("view_name"), set(por_nivel))

    def _mark_de(f):
        p = f.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
        return (p.AsString() or "") if p is not None else ""

    def _todo():
        simbolo = None
        cargada = False
        if modo != "texto":
            simbolo = _simbolo_tag(doc, familia, tipo)
            if simbolo is None:
                ruta = P.get("ruta_rfa")
                if ruta and os.path.isfile(ruta):
                    if not doc.LoadFamily(ruta):
                        raise Exception("Revit no cargo la familia de '%s' (ya "
                                        "cargada con otro contenido?)" % ruta)
                    doc.Regenerate()
                    simbolo = _simbolo_tag(doc, familia, tipo)
                    if simbolo is None:
                        raise Exception("se cargo '%s' pero no aparece como tipo "
                                        "de tag de Floors '%s' (revisar Family "
                                        "Category)" % (ruta, familia))
                    cargada = True
                elif modo == "tag":
                    raise Exception("'%s': %s" % (familia, RECETA))
            if simbolo is not None:
                activate(simbolo)
        usa_texto = simbolo is None
        tipo_texto = doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType) \
            if usa_texto else None

        resultados = []
        for view, nivel_vista in vistas:
            en_nivel = por_nivel.get(nivel_vista) or []
            if not en_nivel:
                continue
            borrados = 0
            if P.get("limpiar", True):
                previos = _tags_de_familia(doc, view, familia) + \
                    _textos_marca(doc, view)
                for tid in previos:
                    doc.Delete(tid)
                    borrados += 1
            puestos = 0
            for f in sorted(en_nivel, key=_mark_de):
                centro = _centro_bbox(f)
                if centro is None:
                    note(e, "losa sin bbox", Exception(str(f.Id)))
                    continue
                try:
                    if usa_texto:
                        esp = _espesor_m(doc, f)
                        texto = _mark_de(f) or "?"
                        if esp is not None:
                            texto += "\nH=%.2f" % esp
                        tn = DB.TextNote.Create(doc, view.Id, centro, texto,
                                                tipo_texto)
                        p = tn.get_Parameter(
                            DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
                        if p is not None:
                            p.Set(MARCA_TEXTO)
                    else:
                        DB.IndependentTag.Create(
                            doc, simbolo.Id, view.Id, DB.Reference(f), False,
                            DB.TagOrientation.Horizontal, centro)
                    puestos += 1
                except Exception as ex:
                    note(e, "etiqueta en vista %s" % view.Name, ex)
            resultados.append({"vista": view.Name, "nivel": nivel_vista,
                               "losas": len(en_nivel), "tags_puestos": puestos,
                               "tags_borrados": borrados})
        if not resultados:
            raise Exception("ninguna vista coincide con los niveles de las losas")
        # sin doc.Regenerate() explicito: el Commit ya regenera (E-137)
        return resultados, cargada, usa_texto

    exigir_ram("etiquetar las losas")
    resultados, cargada, usa_texto = tx(
        doc, "plugin-losas: tags de losa (Mark + espesor)", _todo)

    # verificacion releyendo lo realmente colocado en cada vista
    verificacion = []
    for r in resultados:
        v = find_view(doc, r["vista"])
        if v is None:
            n = None
        elif usa_texto:
            n = len(_textos_marca(doc, v))
        else:
            n = len(_tags_de_familia(doc, v, familia))
        verificacion.append({"vista": r["vista"], "tags_leidos": n,
                             "ok": n == r["tags_puestos"]})

    return {"marker": marker, "familia": familia, "familia_cargada": cargada,
            "modo": "texto" if usa_texto else "tag",
            "vistas": resultados, "verificacion": verificacion, "errores": e}
