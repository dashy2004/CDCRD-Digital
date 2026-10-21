# -*- coding: utf-8 -*-
"""uso_losa: lee las losas esquematicas (marker en Comments) con su Uso_Losa y
Tipo_Losa_PM, y opcionalmente asigna por Mark el uso de la Tabla 4 y/o el tipo
de losa segun apoyos calculado por plugin-losas.

Parametros (P):
  marker:   prefijo de Comments de las losas a listar (default "MCP:LOSA-ESQ").
  asignar:  {Mark: id_uso_tabla4} a escribir en el parametro Uso_Losa (opcional).
  escribir_tipos: {Mark: texto} a escribir en Tipo_Losa_PM (opcional; el texto
            sale de `plugin-losas tipos` -> tipos_pm.json["asignar_en_revit"]:
            codigo DL por apoyos + bordes empotrados).
  crear_parametro: True para crear los parametros de proyecto que falten
            (texto, instancia, categoria Floors). Sin la bandera y sin el
            parametro, la escritura falla con aviso (default False).

Devuelve una fila por losa (mark, nivel, lx/ly/area en m, espesor, uso_losa,
tipo_losa_pm) y los conteos. Esta tool no calcula el tipo (eso es de
plugin_losas.tipos_pm, testeado): solo escribe texto. Escritura en UNA
transaccion con rollback; no guarda (usar revit_guardar_modelo despues).
"""

PARAM_USO = "Uso_Losa"
PARAM_TIPO = "Tipo_Losa_PM"
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


def _texto_param(el, nombre):
    p = el.LookupParameter(nombre)
    if p is None:
        return None
    try:
        return p.AsString()
    except Exception:
        return None


def _mark_de(el):
    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    if p is None:
        return None
    return p.AsString()


def _crear_parametro_texto(doc, DB, nombre):
    """Parametro de proyecto de texto (instancia) sobre Floors, via archivo de
    parametros compartidos temporal (el mecanismo estandar)."""
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
        definicion = grupo.Definitions.get_Item(nombre)
        if definicion is None:
            opciones = DB.ExternalDefinitionCreationOptions(nombre, DB.SpecTypeId.String.Text)
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
    escribir_tipos = P.get("escribir_tipos") or {}
    crear = bool(P.get("crear_parametro"))
    e = errs()

    losas = [f for f in collector(doc, DB.BuiltInCategory.OST_Floors)
             if has_mark(f, marker)]
    if not losas:
        raise Exception("ninguna losa con Comments '%s*'" % marker)

    parametros_creados = []
    asignadas = 0
    tipos_escritos = 0

    if asignar or escribir_tipos:
        marks_modelo = {}
        for f in losas:
            mk = _mark_de(f)
            if mk:
                marks_modelo[mk] = f
        faltan = [k for k in list(asignar.keys()) + list(escribir_tipos.keys())
                  if k not in marks_modelo]
        if faltan:
            raise Exception("marks sin losa en el modelo: %s" % sorted(set(faltan)))

        def _escribir():
            creados = []
            pendientes = []
            if asignar and losas[0].LookupParameter(PARAM_USO) is None:
                pendientes.append(PARAM_USO)
            if escribir_tipos and losas[0].LookupParameter(PARAM_TIPO) is None:
                pendientes.append(PARAM_TIPO)
            if pendientes:
                if not crear:
                    raise Exception("faltan los parametros %s; repetir con "
                                    "crear_parametro=true" % pendientes)
                for nombre in pendientes:
                    _crear_parametro_texto(doc, DB, nombre)
                    creados.append(nombre)
                doc.Regenerate()
            n_uso = 0
            n_tipo = 0
            for mk, f in marks_modelo.items():
                if mk in asignar:
                    set_param(f, PARAM_USO, asignar[mk])
                    n_uso += 1
                if mk in escribir_tipos:
                    set_param(f, PARAM_TIPO, escribir_tipos[mk])
                    n_tipo += 1
            return n_uso, n_tipo, creados
        asignadas, tipos_escritos, parametros_creados = \
            tx(doc, "plugin-losas: Uso_Losa / Tipo_Losa_PM", _escribir)

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
        filas.append({"revit_id": eidv(f.Id), "mark": _mark_de(f),
                      "nivel": level_name(doc, f.LevelId),
                      "lx": lx, "ly": ly, "z_tope": z,
                      "area_m2": area, "espesor_m": _espesor_m(doc, f),
                      "uso_losa": _texto_param(f, PARAM_USO),
                      "tipo_losa_pm": _texto_param(f, PARAM_TIPO),
                      "tipo_revit": type_name(doc, f)})

    return {"marker": marker, "losas": filas, "total": len(filas),
            "parametro_uso_existe": losas[0].LookupParameter(PARAM_USO) is not None,
            "parametro_tipo_existe": losas[0].LookupParameter(PARAM_TIPO) is not None,
            "parametros_creados": parametros_creados,
            "asignadas": asignadas, "tipos_escritos": tipos_escritos,
            "errores": e}
