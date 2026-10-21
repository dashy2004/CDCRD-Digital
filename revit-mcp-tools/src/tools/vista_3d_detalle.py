# -*- coding: utf-8 -*-
"""vista_3d_detalle: vista 3D aislada, orientada, con caja de seccion ajustada y ORIENTACION BLOQUEADA.

Diferencia con vista_3d: aqui la vista sirve para ENTREGAR un detalle, no solo
para mirar. Por eso hace tres cosas mas:
  1. aisla categorias (el resto del modelo se oculta en la vista, no se borra);
  2. acota la caja por nivel o por rango de cota, no solo por marca;
  3. bloquea la orientacion (SaveOrientationAndLock), que es el requisito de
     Revit para poder colocar tags en una vista 3D.
Despues: tags_elementos / tags_vigas sobre esta vista, y ver_vista para mirarla.

Parametros:
  name:         nombre de la vista (obligatorio en la practica; default "MCP 3D DETALLE").
  foco:         que define la caja. dict con cualquier combinacion de:
                  categorias: alias a considerar (default columnas, vigas, losas, muros, zapatas)
                  nivel:      nombre de nivel; solo elementos de ese nivel
                  niveles:    lista de nombres de nivel
                  ids:        lista de ElementId (enteros); si viene, manda sobre lo demas
                  marker:     prefijo de Comments (default "" = sin filtrar por marca)
                  z_min_mm / z_max_mm: recorte por cota absoluta
  visibles:     alias de categorias que quedan visibles; None = no se oculta nada.
  ocultar:      alias de categorias a ocultar siempre (p. ej. "importados" para el DWG vinculado).
  aislar:       lista de ElementId: la vista queda con esos elementos y su acero hospedado, y
                nada mas (aislamiento permanente de la vista, no borra nada del modelo).
                Es lo que limpia un detalle: la caja de seccion recorta por geometria, pero el
                acero de los elementos vecinos sigue apareciendo dentro de la caja.
  margen_mm:    holgura de la caja (default 600).
  orientacion:  iso_se (default) | iso_sw | iso_ne | iso_nw | planta | frente | lado.
  estilo:       sombreado (default) | lineas | realista | oculta.
  detalle:      fino (default) | medio | grueso.
  escala:       denominador de escala de la vista (default 50); controla el tamano del texto de los tags.
  lock:         True (default) bloquea la orientacion para poder etiquetar.
  replace:      True borra la vista previa con ese nombre.
"""


def _lvl_name(doc, DB, e):
    try:
        lid = getattr(e, "LevelId", None)
        if lid is not None and eidv(lid) > 0:
            el = doc.GetElement(lid)
            if el is not None:
                return element_name(el)
    except Exception:
        pass
    for pname in ("Base Level", "Reference Level", "Level", "Schedule Level", "Base Constraint"):
        try:
            p = e.LookupParameter(pname)
            if p is not None and p.StorageType == DB.StorageType.ElementId:
                el = doc.GetElement(p.AsElementId())
                if el is not None:
                    return element_name(el)
        except Exception:
            pass
    return None


def run(doc, uidoc, DB, P):
    name = P.get("name", "MCP 3D DETALLE")
    foco = P.get("foco") or {}
    cats = foco.get("categorias") or ["columnas", "vigas", "losas", "muros", "zapatas"]
    marker = foco.get("marker") or ""
    niveles = foco.get("niveles") or ([foco["nivel"]] if foco.get("nivel") else None)
    ids = foco.get("ids") or None
    zmin = foco.get("z_min_mm")
    zmax = foco.get("z_max_mm")
    mg = ft(float(P.get("margen_mm", 600.0)))
    E = errs()
    lo = [1e12, 1e12, 1e12]
    hi = [-1e12, -1e12, -1e12]
    n = 0
    vistos = {}

    def acumula(e):
        bb = e.get_BoundingBox(None)
        if bb is None:
            return False
        if zmin is not None and mm(bb.Max.Z) < float(zmin):
            return False
        if zmax is not None and mm(bb.Min.Z) > float(zmax):
            return False
        for i, (a, b) in enumerate(((bb.Min.X, bb.Max.X), (bb.Min.Y, bb.Max.Y), (bb.Min.Z, bb.Max.Z))):
            lo[i] = min(lo[i], a)
            hi[i] = max(hi[i], b)
        return True

    if ids:
        for i in ids:
            try:
                e = doc.GetElement(DB.ElementId(int(i)))
                if e is not None and acumula(e):
                    n += 1
            except Exception as ex:
                note(E, "id %s" % i, ex)
    else:
        for alias in cats:
            c = 0
            try:
                for e in collector(doc, bic_of(alias)):
                    try:
                        if marker and not has_mark(e, marker):
                            continue
                        if niveles:
                            ln = _lvl_name(doc, DB, e)
                            if ln not in niveles:
                                continue
                        if acumula(e):
                            n += 1
                            c += 1
                    except Exception as ex:
                        note(E, "bbox " + alias, ex)
            except Exception as ex:
                note(E, "cat " + alias, ex)
            vistos[alias] = c
    if n == 0:
        raise Exception("el foco no selecciono ningun elemento: cats=%s niveles=%s marker='%s' ids=%s" % (cats, niveles, marker, ids))
    if zmin is not None:
        lo[2] = max(lo[2], ft(float(zmin)))
    if zmax is not None:
        hi[2] = min(hi[2], ft(float(zmax)))

    vft = None
    for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType):
        if v.ViewFamily == DB.ViewFamily.ThreeDimensional:
            vft = v
            break
    if vft is None:
        raise Exception("no hay ViewFamilyType 3D")
    existing = None
    for v in DB.FilteredElementCollector(doc).OfClass(DB.View3D):
        if not v.IsTemplate and v.Name == name:
            existing = v
            break
    ORI = {"iso_se": DB.XYZ(1, -1, -1), "iso_sw": DB.XYZ(-1, -1, -1), "iso_ne": DB.XYZ(1, 1, -1),
           "iso_nw": DB.XYZ(-1, 1, -1), "planta": DB.XYZ(0, 0, -1), "frente": DB.XYZ(0, 1, 0),
           "lado": DB.XYZ(-1, 0, 0)}
    STY = {"sombreado": DB.DisplayStyle.Shading, "lineas": DB.DisplayStyle.Wireframe,
           "realista": DB.DisplayStyle.Realistic, "oculta": DB.DisplayStyle.HLR}
    DET = {"fino": DB.ViewDetailLevel.Fine, "medio": DB.ViewDetailLevel.Medium, "grueso": DB.ViewDetailLevel.Coarse}
    fwd = ORI.get(P.get("orientacion", "iso_se"), ORI["iso_se"])
    out = {"name": name, "elementos_en_caja": n, "por_categoria": vistos,
           "caja_mm": {"min": [round(mm(x), 1) for x in lo], "max": [round(mm(x), 1) for x in hi]},
           "ocultas": [], "excepciones": E}
    if existing is not None and P.get("replace"):
        leave_view(doc, uidoc, [existing.Id])

    def work():
        v = existing
        if v is not None and P.get("replace"):
            doc.Delete(v.Id)
            v = None
        if v is None:
            v = DB.View3D.CreateIsometric(doc, vft.Id)
            v.Name = name
            out["accion"] = "creada"
        else:
            out["accion"] = "reutilizada"
            try:
                if v.IsLocked:
                    v.Unlock()
            except Exception as ex:
                note(E, "unlock", ex)
        try:
            f = fwd.Normalize()
            if abs(f.X) + abs(f.Y) < 1e-6:
                up2 = DB.XYZ(0, 1, 0)
            else:
                right = f.CrossProduct(DB.XYZ(0, 0, 1)).Normalize()
                up2 = right.CrossProduct(f).Normalize()
            v.SetOrientation(DB.ViewOrientation3D(DB.XYZ(0, 0, 0), up2, f))
        except Exception as ex:
            note(E, "orientacion", ex)
        bb = DB.BoundingBoxXYZ()
        bb.Min = DB.XYZ(lo[0] - mg, lo[1] - mg, lo[2] - mg)
        bb.Max = DB.XYZ(hi[0] + mg, hi[1] + mg, hi[2] + mg)
        v.IsSectionBoxActive = True
        v.SetSectionBox(bb)
        try:
            v.DisplayStyle = STY.get(P.get("estilo", "sombreado"), DB.DisplayStyle.Shading)
            v.DetailLevel = DET.get(P.get("detalle", "fino"), DB.ViewDetailLevel.Fine)
            v.Scale = int(P.get("escala", 50))
        except Exception as ex:
            note(E, "estilo", ex)
        for a in (P.get("ocultar") or []):
            if a in ("importados", "cad"):
                # los DWG vinculados viven en subcategorias propias de OST_ImportObjectStyles,
                # con ElementId real: no se alcanzan por BuiltInCategory.
                seen = set()
                for ii in DB.FilteredElementCollector(doc).OfClass(DB.ImportInstance).WhereElementIsNotElementType():
                    try:
                        c = ii.Category
                        if c is None or eidv(c.Id) in seen:
                            continue
                        seen.add(eidv(c.Id))
                        if v.CanCategoryBeHidden(c.Id) and not v.GetCategoryHidden(c.Id):
                            v.SetCategoryHidden(c.Id, True)
                            out["ocultas"].append(getattr(c, "Name", "import"))
                    except Exception as ex:
                        note(E, "ocultar import", ex)
                continue
            try:
                cid = DB.ElementId(bic_of(a))
                if v.CanCategoryBeHidden(cid) and not v.GetCategoryHidden(cid):
                    v.SetCategoryHidden(cid, True)
                    out["ocultas"].append(a)
            except Exception as ex:
                note(E, "ocultar " + str(a), ex)
        vis = P.get("visibles")
        if vis:
            keep = set()
            for a in vis:
                try:
                    keep.add(str(bic_of(a)))
                except Exception as ex:
                    note(E, "visible " + str(a), ex)
            for a in sorted(set(CAT.values())):
                try:
                    bic = getattr(DB.BuiltInCategory, a)
                    if str(bic) in keep:
                        continue
                    cid = DB.ElementId(bic)
                    if v.CanCategoryBeHidden(cid) and not v.GetCategoryHidden(cid):
                        v.SetCategoryHidden(cid, True)
                        out["ocultas"].append(a)
                except Exception as ex:
                    note(E, "ocultar " + a, ex)
            for a in vis:
                try:
                    cid = DB.ElementId(bic_of(a))
                    if v.GetCategoryHidden(cid):
                        v.SetCategoryHidden(cid, False)
                except Exception as ex:
                    note(E, "mostrar " + str(a), ex)
        ais = P.get("aislar")
        if ais:
            keep = set(int(i) for i in ais)
            eids = [DB.ElementId(int(i)) for i in keep]
            for rb in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_Rebar).WhereElementIsNotElementType():
                try:
                    if eidv(rb.GetHostId()) in keep:
                        eids.append(rb.Id)
                except Exception:
                    pass
            try:
                v.IsolateElementsTemporary(id_list(eids))
                v.ConvertTemporaryHideIsolateToPermanent()
                out["aislados"] = len(eids)
            except Exception as ex:
                note(E, "aislar", ex)
        if P.get("lock", True):
            try:
                v.SaveOrientationAndLock()
                out["bloqueada"] = True
            except Exception as ex:
                out["bloqueada"] = False
                note(E, "lock", ex)
        out["id"] = eidv(v.Id)
    tx(doc, "tools: vista 3d detalle", work)
    out["ok"] = E["n"] == 0
    return out
