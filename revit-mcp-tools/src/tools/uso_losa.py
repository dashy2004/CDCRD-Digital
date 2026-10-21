# -*- coding: utf-8 -*-
"""uso_losa: lee las losas esquematicas (marker en Comments) y su Uso_Losa, y
opcionalmente asigna el uso de la Tabla 4 por Mark (plugin-losas).

Parametros (P):
  marker:   prefijo de Comments de las losas a listar (default "MCP:LOSA-ESQ").
  asignar:  {Mark: id_uso_tabla4} a escribir en el parametro Uso_Losa (opcional).
  crear_parametro: True para crear el parametro de proyecto Uso_Losa (texto,
            instancia, categoria Floors) si el modelo no lo tiene (default False:
            sin el parametro y sin esta bandera, asignar falla con aviso).

Devuelve una fila por losa (mark, nivel, lx/ly/area en m, espesor, uso_losa) y
los conteos de la asignacion. Los ids de uso son los de plugin-losas
(usos_tabla4: Tabla 4 del CDCRD, datos/machine/cargas_vivas.json); esta tool
no valida el id contra la tabla (eso lo hace el panel/CLI del plugin), solo
escribe texto. Escritura en UNA transaccion con rollback; no guarda (usar
revit_guardar_modelo despues).
"""

PARAM_USO = "Uso_Losa"
GRUPO_PARAMS = "CDCRD plugin-losas"


def _bbox_m(el):
    bb = el.get_BoundingBox(None)
    if bb is None:
        return None, None, None
    return m(bb.Max.X - bb.Min.X), m(bb.Max.Y - bb.Min.Y), m(bb.Max.Z)


def _espesor_m(doc, el):
    try:
        p = el.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)
        if p is not None and p.HasValue:
            return m(p.AsDouble())
    except Exception:
        pass
    try:
        t = doc.GetElement(el.GetTypeId())
        p = t.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_DEFAULT_THICKNESS_PARAM)
        if p is not None and p.HasValue:
            return m(p.AsDouble())
    except Exception:
        pass
    return None


def _uso_actual(el):
    p = el.LookupParameter(PARAM_USO)
    if p is None:
        return None
    try:
        return p.AsString()
    except Exception:
        return None


def _crear_parametro_uso(doc, DB):
    """Parametro de proyecto Uso_Losa (texto, instancia) sobre Floors, via
    archivo de parametros compartidos temporal (el mecanismo estandar)."""
    import os
    import tempfile
    app = doc.Application
    anterior = app.SharedParametersFilename
    ruta = os.path.join(tempfile.gettempdir(), "cdcrd_uso_losa_params.txt")
    if not os.path.exists(ruta):
        f = open(ruta, "w")
        f.close()
    app.SharedParametersFilename = ruta
    try:
        archivo = app.OpenSharedParameterFile()
        grupo = None
        for g in archivo.Groups:
            if g.Name == GRUPO_PARAMS:
                grupo = g
                break
        if grupo is None:
            grupo = archivo.Groups.Create(GRUPO_PARAMS)
        definicion = grupo.Definitions.get_Item(PARAM_USO)
        if definicion is None:
            opciones = DB.ExternalDefinitionCreationOptions(PARAM_USO, DB.SpecTypeId.String.Text)
            definicion = grupo.Definitions.Create(opciones)
        cats = app.Create.NewCategorySet()
        cats.Insert(doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Floors))
        enlace = app.Create.NewInstanceBinding(cats)
        mapa = doc.ParameterBindings
        if not mapa.Insert(definicion, enlace, DB.GroupTypeId.Data):
            mapa.ReInsert(definicion, enlace, DB.GroupTypeId.Data)
    finally:
        if anterior:
            app.SharedParametersFilename = anterior
    return True


def run(doc, uidoc, DB, P):
    marker = P.get("marker") or "MCP:LOSA-ESQ"
    asignar = P.get("asignar") or {}
    crear = bool(P.get("crear_parametro"))
    e = errs()

    losas = [f for f in collector(doc, DB.BuiltInCategory.OST_Floors)
             if has_mark(f, marker)]
    if not losas:
        raise Exception("ninguna losa con Comments '%s*'" % marker)

    tiene_param = losas[0].LookupParameter(PARAM_USO) is not None
    parametro_creado = False
    asignadas = 0

    if asignar:
        def _escribir():
            creado = False
            if not tiene_param:
                if not crear:
                    raise Exception("el modelo no tiene el parametro %s; "
                                    "repetir con crear_parametro=true" % PARAM_USO)
                _crear_parametro_uso(doc, DB)
                creado = True
            doc.Regenerate()
            n = 0
            for f in losas:
                mk = None
                p_mark = f.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
                if p_mark is not None:
                    mk = p_mark.AsString()
                if mk and mk in asignar:
                    set_param(f, PARAM_USO, asignar[mk])
                    n += 1
            faltan = [k for k in asignar
                      if k not in [x.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString()
                                   for x in losas]]
            if faltan:
                raise Exception("marks sin losa en el modelo: %s (rollback)" % faltan)
            return n, creado
        asignadas, parametro_creado = tx(doc, "plugin-losas: Uso_Losa", _escribir)
        tiene_param = True

    filas = []
    for f in losas:
        lx, ly, z = _bbox_m(f)
        area = None
        try:
            p = f.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED)
            if p is not None and p.HasValue:
                area = round(p.AsDouble() * 0.09290304, 2)
        except Exception:
            e["n"] += 1
        mk = None
        try:
            mk = f.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString()
        except Exception:
            e["n"] += 1
        filas.append({"revit_id": eidv(f.Id), "mark": mk,
                      "nivel": level_name(doc, f.LevelId),
                      "lx": lx, "ly": ly, "z_tope": z,
                      "area_m2": area, "espesor_m": _espesor_m(doc, f),
                      "uso_losa": _uso_actual(f),
                      "tipo_revit": type_name(doc, f)})

    return {"marker": marker, "losas": filas, "total": len(filas),
            "parametro_uso_existe": tiene_param,
            "parametro_creado": parametro_creado,
            "asignadas": asignadas, "errores": e}
