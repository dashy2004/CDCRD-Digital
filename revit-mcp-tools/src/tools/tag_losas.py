# -*- coding: utf-8 -*-
"""tag_losas: etiqueta cada losa con el tag personalizado de losa — Mark
ARRIBA y ESPESOR debajo — en la planta de su nivel.

La familia del tag NO se puede crear por API (limitacion conocida del API de
Revit: FamilyItemFactory no crea labels); tiene que existir como .rfa. La tool
(1) busca la familia cargada en el modelo, (2) si falta la carga de
P["ruta_rfa"], y (3) coloca un IndependentTag por losa en el centroide de su
bbox, borrando antes los tags previos de esa misma familia en la vista
(idempotente). Verifica releyendo el conteo por vista.

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


def run(doc, uidoc, DB, P):
    import os
    marker = P.get("marker") or "MCP:LOSA-ESQ"
    familia = P.get("familia") or FAMILIA_DEFAULT
    tipo = P.get("tipo")
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

    def _todo():
        simbolo = _simbolo_tag(doc, familia, tipo)
        cargada = False
        if simbolo is None:
            ruta = P.get("ruta_rfa")
            if not ruta or not os.path.isfile(ruta):
                raise Exception("'%s': %s" % (familia, RECETA))
            if not doc.LoadFamily(ruta):
                raise Exception("Revit no cargo la familia de '%s' (ya cargada "
                                "con otro contenido? revisarla a mano)" % ruta)
            doc.Regenerate()
            simbolo = _simbolo_tag(doc, familia, tipo)
            if simbolo is None:
                raise Exception("se cargo '%s' pero no aparece como tipo de tag "
                                "de Floors '%s' (revisar Family Category)" %
                                (ruta, familia))
            cargada = True
        activate(simbolo)

        resultados = []
        for view, nivel_vista in vistas:
            en_nivel = por_nivel.get(nivel_vista) or []
            if not en_nivel:
                continue
            borrados = 0
            if P.get("limpiar", True):
                for tid in _tags_de_familia(doc, view, familia):
                    doc.Delete(tid)
                    borrados += 1
            puestos = 0
            for f in sorted(en_nivel, key=lambda x: comment(x)):
                centro = _centro_bbox(f)
                if centro is None:
                    note(e, "losa sin bbox", Exception(str(f.Id)))
                    continue
                try:
                    DB.IndependentTag.Create(
                        doc, simbolo.Id, view.Id, DB.Reference(f), False,
                        DB.TagOrientation.Horizontal, centro)
                    puestos += 1
                except Exception as ex:
                    note(e, "tag en vista %s" % view.Name, ex)
            resultados.append({"vista": view.Name, "nivel": nivel_vista,
                               "losas": len(en_nivel), "tags_puestos": puestos,
                               "tags_borrados": borrados})
        if not resultados:
            raise Exception("ninguna vista coincide con los niveles de las losas")
        doc.Regenerate()
        return resultados, cargada

    resultados, cargada = tx(doc, "plugin-losas: tags de losa (Mark + espesor)",
                             _todo)

    # verificacion releyendo: tags de la familia realmente en cada vista
    verificacion = []
    for r in resultados:
        v = find_view(doc, r["vista"])
        n = len(_tags_de_familia(doc, v, familia)) if v is not None else None
        verificacion.append({"vista": r["vista"], "tags_leidos": n,
                             "ok": n == r["tags_puestos"]})

    return {"marker": marker, "familia": familia, "familia_cargada": cargada,
            "vistas": resultados, "verificacion": verificacion, "errores": e}
