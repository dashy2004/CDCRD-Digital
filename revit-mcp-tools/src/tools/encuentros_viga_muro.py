# -*- coding: utf-8 -*-
"""Corrige encuentros viga-muro mediante aberturas nativas, con ensayo reversible.

Requiere pares [wall_id, beam_id], expected_document, expected_pid,
protected_documents y lock {path, owner, session, task}. dry_run=True ensaya y
revierte TODO. Para aplicar, pasar dry_run=False y allowed_column_floor_joins
con exactamente las uniones propuestas por el ensayo y allowed_native_cleanup_ids
para los registros internos sin categoria verificados. No guarda el documento.
Solo muros basicos no estructurales y encuentros rectos horizontales.
Conserva vigas, losas, muros y tags geometricamente; admite regeneracion de
columnas adyacentes, documentada y sin aumentar interferencias locales.
Falla cerrado ante geometria no soportada, booleanos fallidos o avisos nuevos.
"""

import os
import json


def _wm_close(a, b, tol=1e-7):
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(_wm_close(a[k], b[k], tol) for k in a)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_wm_close(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, float) or isinstance(b, float):
        return a is not None and b is not None and abs(a - b) <= tol
    return a == b


def _wm_identity(path, pid, P, lock):
    expected = P.get('expected_document')
    protected = P.get('protected_documents')
    normalize = lambda p: os.path.normcase(os.path.abspath(p))
    if not expected or not protected or not P.get('expected_pid'):
        raise ValueError('Faltan documento, PID o documentos protegidos')
    if normalize(path) != normalize(expected) or pid != int(P['expected_pid']):
        raise ValueError('Documento/PID inesperado')
    if normalize(path) in [normalize(p) for p in protected]:
        raise ValueError('El documento activo esta protegido')
    spec = P.get('lock', {})
    if any(not spec.get(k) or spec[k] != lock.get(k) for k in ('owner', 'session', 'task')):
        raise ValueError('El turno pertenece a otro operador')
    if lock.get('state') != 'active' or int(lock.get('process_id', -1)) != pid:
        raise ValueError('Turno/PID no activo')


def _wm_pairs(raw):
    if not raw or len(raw) > 20:
        raise ValueError('Se requieren entre 1 y 20 pares')
    pairs = [tuple(int(x) for x in p) for p in raw]
    if any(len(p) != 2 or min(p) <= 0 or p[0] == p[1] for p in pairs):
        raise ValueError('Par invalido')
    if len(set(pairs)) != len(pairs) or len(set(p[0] for p in pairs)) != len(pairs):
        raise ValueError('Pares/muros repetidos no soportados')
    return pairs


def _wm_new_overlaps(before, after, tol=1e-7):
    return [dict(ids=list(k), before_ft3=before.get(k, 0.0), after_ft3=v)
            for k, v in sorted(after.items()) if v - before.get(k, 0.0) > tol]


def _wm_require_join_plan(proposed, allowed, dry):
    if not dry and set(map(tuple, proposed)) != set(map(tuple, allowed)):
        raise ValueError('Las uniones columna-losa no coinciden con el ensayo autorizado')


def run(doc, uidoc, DB, P):
    import System
    import io
    dry = P.get('dry_run', True)
    if not isinstance(dry, bool):
        raise ValueError('dry_run debe ser booleano')
    pairs = _wm_pairs(P.get('pairs'))
    with io.open(P.get('lock', {}).get('path', ''), 'r', encoding='utf-8-sig') as f:
        lock = json.load(f)
    _wm_identity(doc.PathName, int(System.Diagnostics.Process.GetCurrentProcess().Id), P, lock)
    if doc.IsModifiable or doc.IsReadOnly or doc.IsFamilyDocument or doc.IsWorkshared:
        raise ValueError('Se requiere copia local editable, sin transaccion abierta')
    tol = 1e-7  # ft3 for Boolean volumes; geometric equivalence tolerance
    failures = []
    warning_guid = '505d84a1-67e4-4987-8287-21ad1792ffe9'
    framing = int(DB.BuiltInCategory.OST_StructuralFraming)
    columns = int(DB.BuiltInCategory.OST_StructuralColumns)

    def eid(e):
        return int(e.Id.Value)

    def get(i):
        return doc.GetElement(DB.ElementId(int(i)))

    def xyz(p):
        return [float(p.X), float(p.Y), float(p.Z)]

    def parameters(e, writable=False):
        result = {}
        for p in e.Parameters:
            if writable and p.IsReadOnly:
                continue
            st = str(p.StorageType)
            if st == 'Double':
                val = float(p.AsDouble())
            elif st == 'Integer':
                val = int(p.AsInteger())
            elif st == 'ElementId':
                val = int(p.AsElementId().Value)
            elif st == 'String':
                val = p.AsString()
            else:
                val = None
            result[str(int(p.Id.Value))] = [st, val]
        return result

    def solid(e):
        opts = DB.Options()
        opts.DetailLevel = DB.ViewDetailLevel.Fine
        found = []

        def walk(geo):
            for x in geo:
                if isinstance(x, DB.Solid) and x.Volume > 1e-9:
                    found.append(DB.SolidUtils.CreateTransformed(x, DB.Transform.Identity))
                elif isinstance(x, DB.GeometryInstance):
                    walk(x.GetInstanceGeometry())
        geo = e.get_Geometry(opts)
        if geo:
            walk(geo)
        if not found:
            return None
        result = found[0]
        for x in found[1:]:
            result = boolean(result, x, DB.BooleanOperationsType.Union)
        return result

    def boolean(a, b, operation):
        return DB.BooleanOperationsUtils.ExecuteBooleanOperation(a, b, operation)

    def bbox(s):
        b = s.GetBoundingBox()
        pts = [b.Transform.OfPoint(DB.XYZ(x, y, z)) for x in (b.Min.X, b.Max.X)
               for y in (b.Min.Y, b.Max.Y) for z in (b.Min.Z, b.Max.Z)]
        return [[min(xyz(p)[n] for p in pts) for n in range(3)],
                [max(xyz(p)[n] for p in pts) for n in range(3)]]

    def overlap(a, b):
        am, ax = bbox(a)
        bm, bx = bbox(b)
        if any(min(ax[n], bx[n]) - max(am[n], bm[n]) <= 1e-8 for n in range(3)):
            return 0.0
        return float(boolean(a, b, DB.BooleanOperationsType.Intersect).Volume)

    def delta(a, b):
        return float(boolean(a, b, DB.BooleanOperationsType.Difference).Volume
                     + boolean(b, a, DB.BooleanOperationsType.Difference).Volume)

    def warning_set():
        return sorted((str(w.GetFailureDefinitionId().Guid),
                       tuple(sorted(int(i.Value) for i in w.GetFailingElements())))
                      for w in doc.GetWarnings())

    def tags():
        return sorted((eid(t), int(t.GetTypeId().Value), int(t.OwnerViewId.Value),
                       t.TagText, xyz(t.TagHeadPosition),
                       sorted(int(i.Value) for i in t.GetTaggedLocalElementIds()))
                      for t in DB.FilteredElementCollector(doc).OfClass(DB.IndependentTag))

    class Reject(DB.IFailuresPreprocessor):
        def PreprocessFailures(self, accessor):
            messages = list(accessor.GetFailureMessages())
            options = accessor.GetFailureHandlingOptions().SetClearAfterRollback(True)
            accessor.SetFailureHandlingOptions(options)
            failures.extend(m.GetDescriptionText() for m in messages)
            return (DB.FailureProcessingResult.ProceedWithRollBack if messages
                    else DB.FailureProcessingResult.Continue)

    def transaction(name):
        t = DB.Transaction(doc, name)
        t.Start()
        t.SetFailureHandlingOptions(t.GetFailureHandlingOptions()
                                   .SetFailuresPreprocessor(Reject()).SetClearAfterRollback(True))
        return t

    before_warnings = warning_set()
    before_tags = tags()
    jobs, existing = [], []
    allowed_columns = set()
    for wi, bi in pairs:
        w, b = get(wi), get(bi)
        if not isinstance(w, DB.Wall) or not isinstance(b, DB.FamilyInstance):
            raise ValueError('Se requiere muro y viga existentes')
        if int(b.Category.Id.Value) != framing or w.WallType.Kind != DB.WallKind.Basic:
            raise ValueError('Categoria/tipo no soportados')
        if w.get_Parameter(DB.BuiltInParameter.WALL_STRUCTURAL_SIGNIFICANT).AsInteger():
            raise ValueError('No se modifican muros estructurales')
        if w.Pinned or int(w.GroupId.Value) != -1 or w.SketchId.Value != -1:
            raise ValueError('Muro fijado, agrupado o perfil existente no soportado')
        if not isinstance(w.Location.Curve, DB.Line) or not isinstance(b.Location.Curve, DB.Line):
            raise ValueError('Solo ejes rectos')
        if abs(w.Location.Curve.Direction.Z) > 1e-8 or abs(b.Location.Curve.Direction.Z) > 1e-8:
            raise ValueError('Solo ejes horizontales')
        if abs(abs(w.Location.Curve.Direction.DotProduct(b.Location.Curve.Direction)) - 1.0) > 1e-8:
            raise ValueError('Los ejes no son paralelos')
        key = (warning_guid, tuple(sorted((wi, bi))))
        if key not in before_warnings:
            if DB.JoinGeometryUtils.AreElementsJoined(doc, w, b) or overlap(solid(w), solid(b)) > tol:
                raise ValueError('Par sin aviso pero encuentro no resuelto')
            existing.append([wi, bi])
            continue
        if not DB.JoinGeometryUtils.AreElementsJoined(doc, w, b):
            raise ValueError('El aviso no corresponde a una union existente')
        if not DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, b, w):
            raise ValueError('La viga debe cortar al muro')
        for i in DB.JoinGeometryUtils.GetJoinedElements(doc, w):
            e = doc.GetElement(i)
            if e.Category and int(e.Category.Id.Value) == columns:
                allowed_columns.add(eid(e))
        jobs.append((wi, bi))
    if not jobs:
        return {'ok': True, 'status': 'already_resolved', 'dry_run': dry,
                'pairs': existing, 'warnings': len(before_warnings), 'saved': False}

    # Global structural elements plus all native model solids near the target walls.
    # CAD imports and linked documents are explicitly outside the geometric contract.
    ids = set()
    for cat in (DB.BuiltInCategory.OST_StructuralFraming, DB.BuiltInCategory.OST_StructuralColumns,
                DB.BuiltInCategory.OST_Walls, DB.BuiltInCategory.OST_Floors):
        ids.update(eid(e) for e in DB.FilteredElementCollector(doc).OfCategory(cat).WhereElementIsNotElementType())
    excluded = set()
    for wi, bi in jobs:
        b = get(wi).get_BoundingBox(None)
        margin = DB.XYZ(1, 1, 1)
        outline = DB.Outline(b.Min - margin, b.Max + margin)
        for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().WherePasses(DB.BoundingBoxIntersectsFilter(outline)):
            if isinstance(e, (DB.ImportInstance, DB.RevitLinkInstance)):
                excluded.add(eid(e))
            elif e.Category and e.Category.CategoryType == DB.CategoryType.Model:
                ids.add(eid(e))
    if len(ids) > 4000:
        raise ValueError('Lote demasiado grande; subdividir el ensayo')
    saved = {i: solid(get(i)) for i in sorted(ids)}
    saved = {i: s for i, s in saved.items() if s is not None}
    beam_ids = [eid(e) for e in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_StructuralFraming).WhereElementIsNotElementType()]
    beam_params = {i: parameters(get(i)) for i in beam_ids}
    column_params = {i: parameters(get(i), True) for i in allowed_columns}
    original_ids = set(int(i.Value) for i in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElementIds())
    original_classes = {i: get(i).GetType().FullName for i in original_ids if get(i) is not None}
    internal_candidates = set(i for i in original_classes
                              if original_classes[i] == 'Autodesk.Revit.DB.Element'
                              and get(i).Category is None and not get(i).Name
                              and int(get(i).GetTypeId().Value) == -1
                              and int(get(i).OwnerViewId.Value) == -1
                              and get(i).get_BoundingBox(None) is None
                              and all(p.IsReadOnly for p in get(i).Parameters))
    out = {'ok': False, 'dry_run': dry, 'status': 'rolled_back', 'saved': False,
           'warnings_before': len(before_warnings), 'openings': [], 'column_floor_joins': [],
           'excluded_imports_links': sorted(excluded), 'checked_solids': len(saved),
           'tolerance_ft3': tol, 'failures': failures}
    group = DB.TransactionGroup(doc, 'Resolver encuentros viga-muro verificados')
    group.Start()
    t = None
    try:
        t = transaction('Aberturas de encuentro viga-muro')
        for wi, bi in jobs:
            w, b = get(wi), get(bi)
            origin = w.Location.Curve.GetEndPoint(0)
            u = w.Location.Curve.Direction
            axis = [b.Location.Curve.GetEndPoint(0), b.Location.Curve.GetEndPoint(1)]
            left = max(0.0, min((p - origin).DotProduct(u) for p in axis))
            right = min(w.Location.Curve.Length, max((p - origin).DotProduct(u) for p in axis))
            zb = bbox(saved[bi])[0][2]
            wb = w.get_BoundingBox(None)
            zt = wb.Max.Z
            if right - left <= doc.Application.ShortCurveTolerance or not wb.Min.Z < zb < zt:
                raise ValueError('Abertura superior fuera del muro')
            aa = origin + u * left + DB.XYZ(0, 0, zb - origin.Z)
            bb = origin + u * right + DB.XYZ(0, 0, zt - origin.Z)
            opening = doc.Create.NewOpening(w, aa, bb)
            DB.JoinGeometryUtils.UnjoinGeometry(doc, w, b)
            out['openings'].append({'id': eid(opening), 'wall': wi, 'beam': bi,
                                    'corners_ft': [xyz(aa), xyz(bb)]})
        if t.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Revit rechazo las aberturas')

        # Resolve only newly increased column-floor overlaps from wall regeneration.
        current = {i: solid(get(i)) for i in saved}
        proposed = []
        for ci in sorted(allowed_columns):
            if ci not in saved or delta(saved[ci], current[ci]) <= tol:
                continue
            for fi in sorted(saved):
                if not isinstance(get(fi), DB.Floor):
                    continue
                if overlap(current[ci], current[fi]) - overlap(saved[ci], saved[fi]) > tol:
                    proposed.append([ci, fi])
        _wm_require_join_plan(proposed, P.get('allowed_column_floor_joins', []), dry)
        if proposed:
            t = transaction('Uniones columna-losa comprobadas')
            for ci, fi in proposed:
                col, floor = get(ci), get(fi)
                if DB.JoinGeometryUtils.AreElementsJoined(doc, col, floor):
                    raise ValueError('Union columna-losa preexistente requiere revision')
                DB.JoinGeometryUtils.JoinGeometry(doc, floor, col)
                if not DB.JoinGeometryUtils.IsCuttingElementInJoin(doc, floor, col):
                    DB.JoinGeometryUtils.SwitchJoinOrder(doc, floor, col)
            if t.Commit() != DB.TransactionStatus.Committed:
                raise ValueError('Revit rechazo las uniones columna-losa')
        out['column_floor_joins'] = proposed
        current = {i: solid(get(i)) for i in saved}
        changes = []
        comparisons = []
        for i in sorted(saved):
            d = delta(saved[i], current[i])
            comparisons.append({'id': i, 'symdiff_ft3': d,
                                'before': {'volume_ft3': float(saved[i].Volume), 'bbox_ft': bbox(saved[i])},
                                'after': {'volume_ft3': float(current[i].Volume), 'bbox_ft': bbox(current[i])}})
            if d > tol:
                changes.append({'id': i, 'symdiff_ft3': d, 'volume_before_ft3': float(saved[i].Volume),
                                'volume_after_ft3': float(current[i].Volume)})
        out['solid_changes'] = changes
        out['solid_comparisons'] = comparisons
        if any(r['id'] not in allowed_columns for r in changes):
            raise ValueError('Cambio geometrico fuera de columnas adyacentes')
        if any(not _wm_close(beam_params[i], parameters(get(i))) for i in beam_ids):
            raise ValueError('Cambio de parametros de viga')
        if any(not _wm_close(column_params[i], parameters(get(i), True)) for i in allowed_columns):
            raise ValueError('Cambio de parametros editables de columna')
        if before_tags != tags():
            raise ValueError('Cambio de tags')
        out['removed_elements'] = [{'id': i, 'class': original_classes.get(i)} for i in original_ids if get(i) is None]
        removed = set(r['id'] for r in out['removed_elements'])
        if removed - internal_candidates:
            raise ValueError('Se elimino un elemento de modelo o documentacion')
        if not dry and removed != set(P.get('allowed_native_cleanup_ids', [])):
            raise ValueError('Limpieza interna no coincide con los registros comprobados')
        old_intersections, new_intersections = {}, {}
        for r in changes:
            for j in saved:
                key = tuple(sorted((r['id'], j)))
                if key[0] == key[1] or key in old_intersections:
                    continue
                a, b = key
                old_intersections[key] = overlap(saved[a], saved[b])
                new_intersections[key] = overlap(current[a], current[b])
        out['new_overlaps'] = _wm_new_overlaps(old_intersections, new_intersections, tol)
        out['checked_intersections'] = len(old_intersections)
        out['pair_overlaps_ft3'] = [overlap(current[wi], current[bi]) for wi, bi in jobs]
        after_warnings = warning_set()
        target_keys = set((warning_guid, tuple(sorted(p))) for p in jobs)
        if set(after_warnings) != set(before_warnings) - target_keys:
            raise ValueError('Avisos inesperados o avisos objetivo sin resolver')
        if out['new_overlaps'] or any(v > tol for v in out['pair_overlaps_ft3']):
            raise ValueError('Se detectaron solapes nuevos')
        out.update(ok=True, warnings_after=len(after_warnings),
                   beams_checked=len(beam_ids), beams_unchanged=True,
                   model_annotation_elements_preserved=True, tags_unchanged=True)
        if dry:
            group.RollBack()
            out['status'] = 'validated_rollback'
        else:
            if group.Assimilate() != DB.TransactionStatus.Committed:
                raise ValueError('No se confirmo el grupo')
            out['status'] = 'applied_unsaved'
    except Exception as ex:
        out['error'] = str(ex)
        out['ok'] = False
    finally:
        if t and t.GetStatus() == DB.TransactionStatus.Started:
            t.RollBack()
        if group.GetStatus() == DB.TransactionStatus.Started:
            group.RollBack()
        group.Dispose()
    out['warnings_current'] = len(warning_set())
    return out
