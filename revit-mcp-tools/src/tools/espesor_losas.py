# -*- coding: utf-8 -*-
"""espesor_losas: refleja el ESPESOR real de cada losa en el modelo.

Hoy las losas llevan un tipo generico unico (p. ej. "Generic - 0.25") y la
seccion decidida (L12/L15/L20/L20A/L25A) no se ve. Esta tool crea (si falta)
un tipo de Floor por seccion — nombre = seccion, espesor total = h de la
biblioteca — duplicando el tipo actual de las losas, y cambia el tipo de cada
losa segun el payload de `plugin-losas secciones` (secciones_losas.json ->
asignar_en_revit).

Parametros (P):
  asignar:      {Mark: seccion}  (payload "asignar")
  tipos_floor:  {seccion: h_m}   (payload "tipos_floor"; espesor total en m)
  nombres_tipo: {seccion: nombre del tipo} (payload "nombres_tipo"; el nombre
                lleva el espesor con "H=", p. ej. "L15 H=0.15" — pedido de
                Emil. Default: la seccion a secas). Un tipo existente con el
                nombre viejo (seccion a secas) se RENOMBRA al nuevo.
  marker:       prefijo de Comments de las losas (default "MCP:LOSA-ESQ").
  solo_marks:   lista de Marks (modo piloto: aplicar a una, revisar, seguir).

Cambiar el tipo REGENERA la geometria: tras el commit la tool RELEE espesor y
tipo de cada losa tocada y reporta en "mal" las que no coincidan (tolerancia
1 mm). UNA transaccion con rollback; NO guarda (revit_guardar_modelo despues).
"""

TOL_M = 0.001


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


def _mark_de(el):
    p = el.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK)
    return p.AsString() if p is not None else None


def _tipos_floor_por_nombre(doc):
    out = {}
    for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType):
        n = element_name(t)
        if n:
            out[n] = t
    return out


def _fijar_espesor_tipo(tipo, h_m):
    """Pone el espesor TOTAL del tipo en h_m cargando la diferencia a la capa
    estructural (core). Falla limpio si el tipo no tiene CompoundStructure."""
    cs = tipo.GetCompoundStructure()
    if cs is None:
        raise Exception("el tipo '%s' no tiene estructura de capas editable"
                        % element_name(tipo))
    h_ft = float(h_m) / 0.3048
    delta = h_ft - cs.GetWidth()
    if abs(delta) * 0.3048 <= TOL_M:
        return False
    idx = cs.GetFirstCoreLayerIndex()
    if idx < 0:
        idx = 0
    ancho = cs.GetLayerWidth(idx) + delta
    if ancho <= 0:
        raise Exception("ajustar '%s' a %.3f m deja la capa core en %.4f ft"
                        % (element_name(tipo), h_m, ancho))
    cs.SetLayerWidth(idx, ancho)
    tipo.SetCompoundStructure(cs)
    return True


def run(doc, uidoc, DB, P):
    marker = P.get("marker") or "MCP:LOSA-ESQ"
    asignar = dict(P.get("asignar") or {})
    tipos_floor = dict(P.get("tipos_floor") or {})
    nombres = dict(P.get("nombres_tipo") or {})
    solo = P.get("solo_marks")
    if not asignar:
        raise Exception("falta 'asignar' ({Mark: seccion} de secciones_losas.json)")
    if solo:
        solo = set(solo)
        asignar = dict((mk, s) for mk, s in asignar.items() if mk in solo)
        if not asignar:
            raise Exception("solo_marks no coincide con ningun Mark de 'asignar'")
    for mk, seccion in asignar.items():
        if seccion not in tipos_floor:
            raise Exception("%s pide la seccion '%s' pero 'tipos_floor' no trae "
                            "su espesor" % (mk, seccion))

    losas = [f for f in collector(doc, DB.BuiltInCategory.OST_Floors)
             if has_mark(f, marker)]
    por_mark = {}
    for f in losas:
        mk = _mark_de(f)
        if mk:
            por_mark[mk] = f
    faltan = sorted(mk for mk in asignar if mk not in por_mark)
    if faltan:
        raise Exception("marks sin losa en el modelo: %s" % faltan)

    def _aplicar():
        existentes = _tipos_floor_por_nombre(doc)
        creados, ajustados, renombrados = [], [], []
        destinos = {}
        for seccion in sorted(set(asignar.values())):
            h_m = tipos_floor[seccion]
            nombre = nombres.get(seccion) or seccion
            tipo = existentes.get(nombre)
            if tipo is None and nombre != seccion and seccion in existentes:
                # migracion: la corrida anterior creo el tipo sin "H="
                tipo = existentes.pop(seccion)
                tipo.Name = nombre
                existentes[nombre] = tipo
                renombrados.append("%s -> %s" % (seccion, nombre))
            if tipo is None:
                base = None
                for mk, s in sorted(asignar.items()):
                    if s == seccion:
                        base = doc.GetElement(por_mark[mk].GetTypeId())
                        break
                tipo = dup_type(doc, base, nombre)
                _fijar_espesor_tipo(tipo, h_m)
                existentes[nombre] = tipo
                creados.append(nombre)
            elif _fijar_espesor_tipo(tipo, h_m):
                ajustados.append(nombre)
            destinos[seccion] = tipo
        cambiadas = 0
        for mk, seccion in sorted(asignar.items()):
            f = por_mark[mk]
            destino = destinos[seccion]
            if f.GetTypeId() != destino.Id:
                f.ChangeTypeId(destino.Id)
                cambiadas += 1
        doc.Regenerate()
        return creados, ajustados, renombrados, cambiadas

    creados, ajustados, renombrados, cambiadas = tx(
        doc, "plugin-losas: espesor real (tipos por seccion)", _aplicar)

    # verificacion releyendo (cambiar tipo regenera geometria)
    filas, mal = [], []
    for mk, seccion in sorted(asignar.items()):
        f = por_mark[mk]
        leido = _espesor_m(doc, f)
        tipo = type_name(doc, f)
        pedido = tipos_floor[seccion]
        esperado = nombres.get(seccion) or seccion
        ok = (tipo == esperado and leido is not None and
              abs(leido - pedido) <= TOL_M)
        fila = {"mark": mk, "seccion": seccion, "espesor_pedido_m": pedido,
                "tipo_leido": tipo, "espesor_leido_m": leido, "ok": ok}
        filas.append(fila)
        if not ok:
            mal.append(fila)

    return {"marker": marker, "losas": filas, "total": len(filas),
            "cambiadas": cambiadas, "tipos_creados": creados,
            "tipos_ajustados": ajustados, "tipos_renombrados": renombrados,
            "mal": mal}
