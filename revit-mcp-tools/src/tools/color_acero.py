# -*- coding: utf-8 -*-
"""color_acero: colorea las barras de refuerzo de una vista por diametro (tipo de barra).

Del pushbutton ColorAcero. Overrides por elemento (no cambia el modelo), barras
rectas con el color base y estribos/otras formas aclarados, opcionalmente
solidas en 3D. Parametros:
  view_name:     vista 3D destino; vacio = vista activa.
  colors:        {"#3": [r,g,b], ...} por nombre de tipo de barra; lo que no este usa default.
  default_rgb:   [r,g,b] para tipos sin color (default [128,128,128]).
  straight_shapes: nombres de Shape considerados "recta" (default ["00","01"]).
  solid:         True intenta Rebar.SetSolidInView (default True).
  host_category: "framing" | "columns" | "" para limitar a barras hospedadas en esa categoria.
La leyenda devuelta (tipo -> rgb, n) es la que hay que poner en el plano.
NO PROBADA en vivo en la conversion (el modelo de referencia no tenia acero).
"""


def run(doc, uidoc, DB, P):
    view = active_or_named_view(doc, uidoc, P.get("view_name"))
    colors = P.get("colors") or {}
    default = P.get("default_rgb") or [128, 128, 128]
    straight = set(P.get("straight_shapes") or ["00", "01"])
    solid = bool(P.get("solid", True))
    host_cat = P.get("host_category") or ""
    HOST = {"framing": DB.BuiltInCategory.OST_StructuralFraming, "columns": DB.BuiltInCategory.OST_StructuralColumns}
    host_bic = HOST.get(host_cat)

    def aclarar(rgb):
        return [int(c + (255 - c) * 0.45) for c in rgb]
    out = {"view": view.Name, "barras": 0, "coloreadas": 0, "solid_ok": 0,
           "leyenda": {}, "errores": {}}
    barras = []
    for rb in collector(doc, DB.BuiltInCategory.OST_Rebar):
        if host_bic is not None:
            try:
                h = doc.GetElement(rb.GetHostId())
                if h is None or h.Category is None or eidv(h.Category.Id) != int(host_bic):
                    continue
            except Exception:
                continue
        barras.append(rb)
    out["barras"] = len(barras)
    plan = []
    for rb in barras:
        nom = type_name(doc, rb) or "?"
        forma = None
        try:
            p = rb.LookupParameter("Shape Name")
            forma = p.AsString() if p is not None else None
        except Exception:
            pass
        base = colors.get(nom, default)
        recta = (forma or "") in straight
        rgb = base if recta else aclarar(base)
        clave = "%s %s" % (nom, "recta" if recta else "estribo/otro")
        plan.append((rb, rgb))
        L = out["leyenda"].setdefault(clave, {"rgb": list(rgb), "n": 0})
        L["n"] += 1

    def work():
        solido = None
        try:
            solido = DB.FillPatternElement.GetFillPatternElementByName(doc, DB.FillPatternTarget.Drafting, "<Solid fill>")
        except Exception:
            pass
        for rb, rgb in plan:
            try:
                ogs = DB.OverrideGraphicSettings()
                col = DB.Color(rgb[0], rgb[1], rgb[2])
                ogs.SetProjectionLineColor(col)
                ogs.SetCutLineColor(col)
                try:
                    ogs.SetSurfaceForegroundPatternColor(col)
                    ogs.SetCutForegroundPatternColor(col)
                    if solido is not None:
                        ogs.SetSurfaceForegroundPatternId(solido.Id)
                        ogs.SetCutForegroundPatternId(solido.Id)
                        ogs.SetSurfaceForegroundPatternVisible(True)
                        ogs.SetCutForegroundPatternVisible(True)
                except Exception:
                    pass
                ogs.SetProjectionLineWeight(4)
                view.SetElementOverrides(rb.Id, ogs)
                out["coloreadas"] += 1
                if solid:
                    m = getattr(rb, "SetSolidInView", None)
                    if m is not None:
                        try:
                            m(view, True)
                            out["solid_ok"] += 1
                        except Exception:
                            pass
            except Exception as ex:
                k = "%s: %s" % (type(ex).__name__, str(ex)[:120])
                out["errores"][k] = out["errores"].get(k, 0) + 1
    tx(doc, "tools: color de acero", work)
    out["ok"] = out["coloreadas"] == out["barras"]
    return out
