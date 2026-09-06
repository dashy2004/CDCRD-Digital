# -*- coding: utf-8 -*-
"""tipos: crea tipos de columna, viga, zapata, losa y muro duplicando uno base y fijando dimensiones.

Parametros:
  tipos: lista de especificaciones:
    {"categoria": "columna", "nombre": "C40x40", "base": "", "params_mm": {"b": 400, "h": 400}}
    {"categoria": "viga",    "nombre": "V30x50", "base": "", "params_mm": {"b": 300, "h": 500}}
    {"categoria": "zapata",  "nombre": "Z120",   "base": "", "params_mm": {"Width": 1200, "Length": 1200, "Foundation Thickness": 400}}
    {"categoria": "losa",    "nombre": "LOSA 15", "base": "", "espesor_mm": 150, "material": ""}
    {"categoria": "muro",    "nombre": "MURO 20", "base": "", "espesor_mm": 200, "material": ""}
    base: nombre del tipo a duplicar ('Tipo' o 'Familia: Tipo'); vacio = el primero de la categoria.
    params_mm: parametros de tipo por su nombre en la familia (b/h en las familias de hormigon de
    Autodesk; otras familias usan otros nombres: la respuesta lista los disponibles si uno falta).
    material: nombre de material a asignar (Structural Material en familias; capa de nucleo en losa/muro).
  dry_run: True solo informa (default True).
Cada dimension se lee de vuelta despues de escribirla (E-045: el espesor de
losa/muro no se hereda; hay que fijarlo y verificarlo). Idempotente: si el
nombre ya existe se informa y no se duplica.
"""


def run(doc, uidoc, DB, P):
    specs = P.get("tipos") or []
    if not specs:
        raise Exception("falta 'tipos'")
    dry = bool(P.get("dry_run", True))
    FAM = {"columna": DB.BuiltInCategory.OST_StructuralColumns, "viga": DB.BuiltInCategory.OST_StructuralFraming,
           "zapata": DB.BuiltInCategory.OST_StructuralFoundation}
    SYS = {"losa": (DB.FloorType, DB.BuiltInCategory.OST_Floors), "muro": (DB.WallType, DB.BuiltInCategory.OST_Walls)}
    E = errs()
    out = {"dry_run": dry, "plan": [], "creados": [], "existian": [], "errores": [], "excepciones": E}
    mats = dict((element_name(mt), mt) for mt in DB.FilteredElementCollector(doc).OfClass(DB.Material))

    def sys_types(cls, bic):
        res = []
        for t in DB.FilteredElementCollector(doc).OfClass(cls):
            try:
                if bic == DB.BuiltInCategory.OST_Walls and t.Kind != DB.WallKind.Basic:
                    continue
            except Exception:
                pass
            res.append(t)
        return res

    def type_params_len(t):
        names = []
        for p in t.Parameters:
            try:
                if str(p.StorageType) == "Double" and not p.IsReadOnly and p.Definition.GetDataType() == DB.SpecTypeId.Length:
                    names.append(p.Definition.Name)
            except Exception:
                pass
        return sorted(set(names))

    jobs = []
    for s in specs:
        cat = s.get("categoria")
        name = s.get("nombre")
        if not cat or not name:
            raise Exception("cada tipo necesita 'categoria' y 'nombre'")
        if cat in FAM:
            pool = symbols(doc, FAM[cat])
            exists = [t for t in pool if element_name(t) == name]
        elif cat in SYS:
            pool = sys_types(SYS[cat][0], SYS[cat][1])
            exists = [t for t in pool if element_name(t) == name]
        else:
            raise Exception("categoria '%s' no soportada; usar columna, viga, zapata, losa o muro" % cat)
        base = None
        if s.get("base"):
            for t in pool:
                if element_name(t) == s["base"] or family_and_type(t) == s["base"]:
                    base = t
                    break
            if base is None:
                raise Exception("no existe el tipo base '%s' para %s; hay: %s" % (s["base"], cat, sorted(set(family_and_type(t) for t in pool))[:30]))
        elif pool:
            base = pool[0]
        item = {"categoria": cat, "nombre": name, "accion": "existe" if exists else ("crear" if base is not None else "sin_base"),
                "base": family_and_type(base) if base is not None else None}
        if base is not None and cat in FAM:
            item["params_disponibles"] = type_params_len(base)
        if s.get("material") and s["material"] not in mats:
            raise Exception("no existe el material '%s'; hay: %s" % (s["material"], sorted(mats.keys())[:40]))
        out["plan"].append(item)
        if item["accion"] == "sin_base":
            out["errores"].append([name, "no hay ningun tipo de %s en el documento para duplicar; cargar una familia primero" % cat])
        jobs.append((s, cat, name, base, exists))
    if dry:
        return out

    def work():
        for s, cat, name, base, exists in jobs:
            if exists:
                out["existian"].append(name)
                continue
            if base is None:
                continue
            try:
                nt = dup_type(doc, base, name)
                rec = {"categoria": cat, "nombre": name, "id": eidv(nt.Id), "base": family_and_type(base), "verificado_mm": {}}
                if cat in FAM:
                    for pn, val in (s.get("params_mm") or {}).items():
                        try:
                            rec["verificado_mm"][pn] = set_param(nt, pn, val)
                        except Exception as ex:
                            note(E, "%s.%s" % (name, pn), ex)
                            rec.setdefault("params_fallidos", []).append(pn)
                    if s.get("material"):
                        try:
                            set_param(nt, DB.BuiltInParameter.STRUCTURAL_MATERIAL_PARAM, mats[s["material"]].Id)
                            rec["material"] = s["material"]
                        except Exception as ex:
                            note(E, name + " material", ex)
                    activate(nt)
                else:
                    cs = nt.GetCompoundStructure()
                    idx = cs.GetFirstCoreLayerIndex()
                    if idx < 0:
                        idx = 0
                    if s.get("espesor_mm") is not None:
                        cs.SetLayerWidth(idx, ft(s["espesor_mm"]))
                    if s.get("material"):
                        cs.SetMaterialId(idx, mats[s["material"]].Id)
                        rec["material"] = s["material"]
                    nt.SetCompoundStructure(cs)
                    doc.Regenerate()
                    rec["verificado_mm"]["espesor"] = mm(nt.GetCompoundStructure().GetWidth())
                    rec["capas"] = nt.GetCompoundStructure().LayerCount
                out["creados"].append(rec)
            except Exception as ex:
                out["errores"].append([name, "%s: %s" % (type(ex).__name__, str(ex)[:160])])
    tx(doc, "tools: tipos", work)
    out["ok"] = not out["errores"]
    return out
