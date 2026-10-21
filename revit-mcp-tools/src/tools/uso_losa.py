# -*- coding: utf-8 -*-
"""uso_losa: lee las losas esquematicas (marker en Comments) con sus parametros
del plugin de losas, y asigna por Mark lo que el panel/CLI decidio.

Parametros (P):
  marker:   prefijo de Comments de las losas a listar (default "MCP:LOSA-ESQ").
  asignar:  {Mark: id_uso_tabla4} -> parametro Uso_Losa (opcional).
  escribir_tipos: {Mark: texto} -> Tipo_Losa_PM (tipo segun apoyos; el texto
            sale de `plugin-losas tipos` -> tipos_pm.json["asignar_en_revit"]).
  escribir_secciones: {Mark: seccion} -> Seccion_Losa (L12/L15/L20 macizas,
            L20A/L25A-1D/2D aligeradas, o "auto" si rige el reglamento).
  escribir_aceros: {Mark: {"x": txt, "y": txt, "apoyo": txt}} -> Acero_X,
            Acero_Y, Acero_Apoyo (armadura comercial, editable en el panel).
  crear_parametro: True para crear los parametros de proyecto que falten
            (texto, instancia, categoria Floors; default False).

Devuelve una fila por losa con todos esos parametros y los conteos escritos.
Esta tool NO calcula nada (los calculos viven en plugin_losas/puente_losas,
testeados): solo escribe texto. UNA transaccion con rollback; no guarda
(usar revit_guardar_modelo despues).
"""

PARAM_USO = "Uso_Losa"
PARAM_TIPO = "Tipo_Losa_PM"
PARAM_SECCION = "Seccion_Losa"
PARAM_ACERO_X = "Acero_X"
PARAM_ACERO_Y = "Acero_Y"
PARAM_ACERO_APOYO = "Acero_Apoyo"
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
    crear = bool(P.get("crear_parametro"))
    e = errs()

    # escrituras pedidas: (parametro, {Mark: texto})
    escrituras = []
    if P.get("asignar"):
        escrituras.append((PARAM_USO, dict(P["asignar"])))
    if P.get("escribir_tipos"):
        escrituras.append((PARAM_TIPO, dict(P["escribir_tipos"])))
    if P.get("escribir_secciones"):
        escrituras.append((PARAM_SECCION, dict(P["escribir_secciones"])))
    for mark, aceros in (P.get("escribir_aceros") or {}).items():
        for clave, nombre in (("x", PARAM_ACERO_X), ("y", PARAM_ACERO_Y),
                              ("apoyo", PARAM_ACERO_APOYO)):
            if aceros.get(clave):
                destino = None
                for nom, valores in escrituras:
                    if nom == nombre:
                        destino = valores
                if destino is None:
                    destino = {}
                    escrituras.append((nombre, destino))
                destino[mark] = aceros[clave]

    losas = [f for f in collector(doc, DB.BuiltInCategory.OST_Floors)
             if has_mark(f, marker)]
    if not losas:
        raise Exception("ninguna losa con Comments '%s*'" % marker)

    parametros_creados = []
    conteos = {}

    if escrituras:
        marks_modelo = {}
        for f in losas:
            mk = _mark_de(f)
            if mk:
                marks_modelo[mk] = f
        faltan = set()
        for _, valores in escrituras:
            for mk in valores:
                if mk not in marks_modelo:
                    faltan.add(mk)
        if faltan:
            raise Exception("marks sin losa en el modelo: %s" % sorted(faltan))

        def _escribir():
            creados = []
            pendientes = [nombre for nombre, _ in escrituras
                          if losas[0].LookupParameter(nombre) is None]
            if pendientes:
                if not crear:
                    raise Exception("faltan los parametros %s; repetir con "
                                    "crear_parametro=true" % pendientes)
                for nombre in pendientes:
                    _crear_parametro_texto(doc, DB, nombre)
                    creados.append(nombre)
                doc.Regenerate()
            cuenta = {}
            for nombre, valores in escrituras:
                n = 0
                for mk, texto in valores.items():
                    set_param(marks_modelo[mk], nombre, texto)
                    n += 1
                cuenta[nombre] = n
            return cuenta, creados
        conteos, parametros_creados = tx(doc, "plugin-losas: parametros de losa", _escribir)

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
                      "seccion_losa": _texto_param(f, PARAM_SECCION),
                      "acero_x": _texto_param(f, PARAM_ACERO_X),
                      "acero_y": _texto_param(f, PARAM_ACERO_Y),
                      "acero_apoyo": _texto_param(f, PARAM_ACERO_APOYO),
                      "tipo_revit": type_name(doc, f)})

    return {"marker": marker, "losas": filas, "total": len(filas),
            "parametros_creados": parametros_creados,
            "escritos": conteos, "errores": e}
