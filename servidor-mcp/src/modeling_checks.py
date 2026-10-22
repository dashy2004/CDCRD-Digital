"""Checks over an explicit snapshot; does not acquire or alter an ETABS model."""
import math
from pathlib import PureWindowsPath

from etabs_procedure import get_procedure, prepare_modeling, unique


def audit_modeling(profile: str, project: dict, snapshot: dict) -> dict:
    p, expected = get_procedure(profile), prepare_modeling(profile, project)
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot debe ser un objeto")
    findings = []

    def issue(code, obj, message, status=None, **details):
        pending = {"missing", "geometry_missing", "spectrum_unverified", "seismic_pending",
                   "missing_diaphragm", "persistence"}
        findings.append({"code": code, "object": obj, "message": message,
                         "status": status or ("pending" if code in pending else "difference"),
                         **details})

    def matches(actual, desired):
        if isinstance(desired, bool):
            return type(actual) is bool and actual == desired
        if isinstance(desired, dict):
            return (isinstance(actual, dict) and actual.keys() == desired.keys() and
                    all(matches(actual[k], v) for k, v in desired.items()))
        if isinstance(desired, list):
            return (isinstance(actual, list) and len(actual) == len(desired) and
                    all(matches(a, b) for a, b in zip(actual, desired)))
        if type(desired) in (int, float):
            return (type(actual) in (int, float) and math.isfinite(actual) and
                    math.isclose(actual, desired, rel_tol=1e-9, abs_tol=1e-9))
        return actual == desired

    def equal(actual, desired, obj):
        if not matches(actual, desired):
            issue("setting", obj, f"Esperado {desired!r}; recibido {actual!r}",
                  status="pending" if actual is None else "difference",
                  expected=desired, observed=actual)

    def points(obj):
        vertices = obj.get("vertices_m")
        if (not isinstance(vertices, list) or len(vertices) < 3 or
                any(not isinstance(v, list) or len(v) != 3 or
                    any(type(x) not in (int, float) or not math.isfinite(x) for x in v)
                    for v in vertices)):
            issue("geometry_missing", obj["id"], "Faltan vertices XYZ finitos en metros")
            return None
        if len(set(map(tuple, vertices))) != len(vertices):
            issue("duplicate_vertex", obj["id"], "Vertices repetidos")
            return None
        for v in vertices:
            if any(abs(x / p["geometry_grid_m"] - round(x / p["geometry_grid_m"])) > 1e-7
                   for x in v):
                issue("grid", obj["id"], "Coordenada fuera de reticula 0.05 m; no se ajusta automaticamente")
                break
        origin = vertices[0]
        vectors = [[v[i] - origin[i] for i in range(3)] for v in vertices[1:]]
        normal = None
        for a, b in zip(vectors, vectors[1:]):
            n = [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]]
            length = math.sqrt(sum(x*x for x in n))
            if length > 1e-10:
                normal = [x / length for x in n]
                break
        if normal is None:
            issue("degenerate", obj["id"], "Area sin plano definido")
            return None
        if any(abs(sum(x*y for x, y in zip(v, normal))) > 1e-6 for v in vectors):
            issue("nonplanar", obj["id"], "Shell no coplanar")
        return vertices

    actual_path = snapshot.get("model_path")
    if not isinstance(actual_path, str) or PureWindowsPath(actual_path) != PureWindowsPath(expected["model_path"]):
        issue("identity", "model_path", "El snapshot no corresponde al EDB solicitado")
    equal(snapshot.get("units"), p["units"], "units")
    for key in ("mass_source", "pdelta", "modal_max_modes"):
        equal(snapshot.get(key), expected[key], key)
    actual_patterns = snapshot.get("patterns")
    if not isinstance(actual_patterns, list):
        issue("missing", "patterns", "Faltan patrones")
    else:
        indexed = {row["name"]: row for row in unique(actual_patterns, "name")}
        for pat in expected["patterns"]:
            if pat["name"] not in indexed:
                issue("missing_pattern", pat["name"], "Patron requerido ausente del inventario leido",
                      expected=pat["name"], observed="ausente")
                continue
            observed = indexed.get(pat["name"], {})
            for key, value in pat.items():
                equal(observed.get(key), value, f"{pat['name']}.{key}")
        if not project["has_parking"] and "LiveP" in indexed:
            issue("parking", "LiveP", "Perfil sin parqueos; reconciliar patron existente, no borrar automaticamente")
    if expected["spectrum"] is None or not expected["spectrum"]["cases"]:
        issue("spectrum_unverified", "MOPC", "Falta cotejo de curva para generar EX/EY")
    else:
        equal(snapshot.get("spectrum_cases"), expected["spectrum"]["cases"], "spectrum_cases")
    if project.get("seismic") and any(project["seismic"].get(k) == "pending"
                                    for k in ("reentrant", "nonorthogonal", "torsion")):
        issue("seismic_pending", "MOPC", "Decisiones de penalizacion pendientes")
    definitions = snapshot.get("slab_definitions")
    if not isinstance(definitions, list) or not definitions:
        issue("missing", "slab_definitions", "Faltan definiciones, incluidas las no utilizadas")
    else:
        for prop in unique(definitions, "name"):
            equal(prop.get("modeling_type"), "Shell-Thick", prop["name"])
            if prop.get("type") in ("Ribbed", "Waffle"):
                h, t = prop.get("h_m"), prop.get("topping_m")
                if (type(h) not in (int, float) or type(t) not in (int, float) or
                        not math.isfinite(h) or not math.isfinite(t) or not 0 < t < h):
                    issue("topping", prop["name"], "Topping debe estar incluido dentro del peralte",
                          status="pending" if h is None or t is None else "difference")
    slabs = snapshot.get("slabs")
    groups, shapes = {}, set()
    if not isinstance(slabs, list) or not slabs:
        issue("missing", "slabs", "Faltan asignaciones de losas")
    else:
        for slab in unique(slabs):
            sid = slab["id"]
            vertices = points(slab)
            if vertices is None:
                continue
            shape = frozenset(map(tuple, vertices))
            if shape in shapes:
                issue("duplicate_shell", sid, "Shell geometricamente duplicado")
            shapes.add(shape)
            if slab.get("is_opening") is True:
                if slab.get("load_components") != []:
                    issue("loaded_opening", sid, "Hueco con carga o carga desconocida",
                          status="pending" if slab.get("load_components") is None else "difference")
                continue
            equal(slab.get("is_opening"), False, sid + ".is_opening")
            zs = [v[2] for v in vertices]
            inclined = max(zs) - min(zs) > 1e-6
            diaphragm = slab.get("diaphragm")
            if inclined:
                if diaphragm not in (None, ""):
                    issue("inclined_diaphragm", sid, "Rampa con diafragma horizontal")
                if "diaphragm" not in slab:
                    issue("missing", sid, "Falta confirmar ausencia de diafragma")
            else:
                if not isinstance(diaphragm, str) or not diaphragm:
                    issue("missing_diaphragm", sid, "Losa plana sin diafragma confirmado")
                else:
                    story, block = slab.get("story"), slab.get("structural_block")
                    if not story or not block:
                        issue("missing", sid, "Falta story o cuerpo estructural")
                    key = (story, diaphragm)
                    groups.setdefault(key, []).append((sid, zs[0], block))
            directions = slab.get("directions")
            if directions not in (1, 2) or isinstance(directions, bool):
                issue("missing", sid, "Direccion resistente sin confirmar por esquema")
            elif directions == 1:
                equal(slab.get("mesh"), "No Auto Mesh", sid + ".mesh")
            elif slab.get("mesh") in (None, "", "Default", "No Auto Mesh"):
                issue("mesh", sid, "Losa 2D requiere mallado y conexion verificados",
                      status="pending" if slab.get("mesh") is None else "difference")
            components = slab.get("load_components")
            if not isinstance(components, list) or any(not isinstance(c, str) for c in components):
                issue("missing", sid, "Falta inventario de componentes de carga")
            else:
                if len(components) != len(set(components)):
                    issue("duplicate_load", sid, "Componente de carga repetido")
                if "set" in components and any(c in components for c in ("direct_finishes", "direct_live")):
                    issue("duplicate_load", sid, "Set y carga directa repiten acabados/viva")
                if slab.get("support") == "cantilever" and "masonry" in components:
                    issue("cantilever_masonry", sid, "Vuelo con mamposteria")
                if slab.get("support") not in ("cantilever", "supported"):
                    issue("missing", sid, "Falta tipo de apoyo")
    for (story, diaphragm), members in groups.items():
        if max(v[1] for v in members) - min(v[1] for v in members) > 1e-6:
            issue("mixed_elevations", f"{story}/{diaphragm}", "Diafragma mezcla alturas dentro del story")
        if len({v[2] for v in members}) > 1:
            issue("mixed_blocks", f"{story}/{diaphragm}", "Diafragma une cuerpos independientes")
    # Empty collections are explicit statements; absent collections remain unknown.
    for key in ("walls", "frames", "joints"):
        rows = snapshot.get(key)
        if not isinstance(rows, list):
            issue("missing", key, "Falta inventario")
            continue
        for obj in unique(rows):
            if key == "walls":
                equal(obj.get("mesh"), "Auto Rectangular", obj["id"] + ".mesh")
            elif key == "frames":
                equal(obj.get("rigid_zone_factor"), 1, obj["id"] + ".rigid_zone_factor")
            else:
                if obj.get("at_base") is True:
                    equal(obj.get("restraints"), [True] * 6, obj["id"] + ".restraints")
                elif obj.get("at_base") is not False:
                    issue("missing", obj["id"], "Falta at_base")
                if obj.get("diaphragm") not in (None, "", "From Shell Object"):
                    key = (obj.get("story"), obj["diaphragm"])
                    z = obj.get("z_m")
                    if type(z) not in (int, float) or not math.isfinite(z):
                        issue("missing", obj["id"], "Falta cota del nudo")
                    elif key not in groups or any(abs(z - m[1]) > 1e-6 for m in groups[key]):
                        issue("joint_diaphragm", obj["id"], "Asignacion explicita sin grupo compatible")
    check = snapshot.get("check_model")
    if not isinstance(check, dict):
        check = {}
    if check.get("completed") is not True or check.get("warnings") != []:
        issue("check_model", "native", "Check Model ausente, incompleto o con avisos",
              status="difference" if check.get("completed") is True else "pending")
    if snapshot.get("saved_readback_verified") is not True:
        issue("persistence", "native", "Persistencia no acreditada")
    return {"profile": profile, "findings": findings, "checked_snapshot_matches": not findings,
            "model_modified": False, "analysis_authorized": False,
            "scope": "Comprobaciones del snapshot aportado; no certifica su origen ni sustituye planos, conectividad completa o diseno"}
