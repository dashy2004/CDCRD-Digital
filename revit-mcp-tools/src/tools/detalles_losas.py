# -*- coding: utf-8 -*-
"""Plantilla geometrica de losas en Drafting Views nativas, con texto GR.

inspect prepara tres detalles y su digest; apply exige ese digest, copia,
PID, turno exclusivo y documento guardado. Crea vistas nuevas, nunca borra
ni reemplaza vistas existentes. Unidades de entrada: metros. No calcula
armado ni modifica elementos fisicos. No instala actualizacion automatica.
"""
import hashlib
import io
import json
import math
import ntpath
import os


def positive(value, name, lower, upper):
    if isinstance(value, bool):
        raise ValueError('Valor booleano: ' + name)
    number = float(value)
    if math.isnan(number) or math.isinf(number) or not lower <= number <= upper:
        raise ValueError('Valor fuera de rango: ' + name)
    return number


def build_spec(P):
    """Pure geometry; no engineering defaults or model-dependent values."""
    g = P['geometry']
    h = positive(g['height_m'], 'height_m', .17, .60)
    t = positive(g['topping_m'], 'topping_m', .03, .20)
    b = positive(g['block_m'], 'block_m', .20, 1.00)
    r = positive(g['rib_m'], 'rib_m', .10, .40)
    wall = positive(g['wall_m'], 'wall_m', .08, .40)
    gap = positive(g['wall_gap_m'], 'wall_gap_m', 0, .20)
    if h-t < .05:
        raise ValueError('Altura util de bovedilla menor a 5 cm')
    prefix = P.get('view_prefix', '')
    if not prefix.startswith('CDX ') or len(prefix) > 70 or any(c in prefix for c in '{}[]|;<>?`~\\\n\r'):
        raise ValueError('view_prefix debe iniciar CDX y no contener caracteres reservados')
    text_type = P.get('text_type_name', '')
    if not isinstance(text_type, str) or 'GR' not in text_type or len(text_type) > 100:
        raise ValueError('Declarar nombre exacto de texto GR')
    dimension_type = P.get('dimension_type_name', '')
    if not isinstance(dimension_type, str) or 'GR' not in dimension_type or len(dimension_type) > 100:
        raise ValueError('Declarar nombre exacto de cota GR')
    views = []

    def view(suffix):
        v = {'name': prefix + ' - ' + suffix, 'scale': 10,
             'lines': [], 'notes': [], 'dimensions': []}
        views.append(v)
        return v

    def line(v, a, c):
        index = len(v['lines'])
        v['lines'].append([list(a), list(c)])
        return index

    def rect(v, x, y, w, d):
        pts = [(x,y),(x+w,y),(x+w,y+d),(x,y+d)]
        return [line(v, pts[i], pts[(i+1)%4]) for i in range(4)]

    def note(v, x, y, text):
        v['notes'].append({'point': [x,y], 'text': text})

    def dim(v, a, c, refs, expected):
        v['dimensions'].append({'line': [a,c], 'refs': refs, 'expected_m': expected})

    width = 3*b+4*r
    v = view('01 SECCION')
    outer = rect(v, 0, 0, width, h)
    line(v, (0,h-t), (width,h-t))
    for i in range(3):
        rect(v, r+i*(r+b), 0, b, h-t)
    dim(v, (0,-.12), (width,-.12), [outer[3],outer[1]], width)
    dim(v, (-.12,0), (-.12,h), [outer[0],outer[2]], h)
    note(v, 0, h+.30, 'SECCION GEOMETRICA | unidades: m | escala 1:10')
    note(v, 0, h+.21, 'Bovedilla %.2f | nervio %.2f | topping %.2f | HB %.2f' % (b,r,t,h-t))
    note(v, 0, -.27, 'REFERENCIA GEOMETRICA. Armado y uso pendientes de validacion.')
    note(v, 0, -.36, 'Sin barras prescritas. No representa una seccion de un pano concreto.')

    v = view('02 MODULACION')
    depth = 2*b+3*r
    outer = rect(v, 0, 0, width, depth)
    for i in range(3):
        for j in range(2):
            rect(v, r+i*(r+b), r+j*(r+b), b, b)
    dim(v, (0,-.12), (width,-.12), [outer[3],outer[1]], width)
    dim(v, (-.12,0), (-.12,depth), [outer[0],outer[2]], depth)
    note(v, 0, depth+.22, 'MODULACION DE REFERENCIA | 2 direcciones | escala 1:10')
    note(v, 0, depth+.13, '6 bovedillas de %.2f x %.2f | nervios %.2f' % (b,b,r))
    note(v, 0, -.27, 'El esquema 2D no genera cantidades. Contar instancias EPS del modelo.')
    note(v, 0, -.36, 'Macizados, bordes y huecos se definen para cada pano.')

    v = view('03 MURO Y BOVEDILLA')
    outer = rect(v, 0, 0, width, h)
    line(v, (0,h-t), (width,h-t))
    for i in range(3):
        rect(v, r+i*(r+b), 0, b, h-t)
    center = r+b/2
    wall_edges = rect(v, center-wall/2, -.60-gap, wall, .60)
    dim(v, (0,-.85-gap), (width,-.85-gap), [outer[3],outer[1]], width)
    if gap > .001:
        dim(v, (-.12,-gap), (-.12,0), [wall_edges[2],outer[0]], gap)
    note(v, 0, h+.30, 'COORDINACION MURO / BOVEDILLA | escala 1:10')
    note(v, 0, h+.21, 'Coronacion bajo intrados; el muro no penetra el volumen EPS.')
    note(v, center+wall/2+.12, -.24-gap, 'MURO | espesor %.2f' % wall)
    note(v, center+wall/2+.12, -.33-gap, 'Separacion ilustrativa %.3f m; no define junta constructiva.' % gap)
    note(v, 0, -1.02-gap, 'REGLA DE COORDINACION. Verificar contacto real y funcion del muro.')
    return {'schema': 'cdx.slab.drafting/1', 'units': 'm', 'views': views,
            'text_type_name': text_type, 'dimension_type_name': dimension_type, 'geometry': dict(g),
            'engineering_approved': False, 'model_linked': False}


def spec_digest(spec):
    return hashlib.sha256(json.dumps(spec, sort_keys=True, separators=(',', ':'),
                                    ensure_ascii=True).encode('utf-8')).hexdigest()


def validate_scope(P, path, pid, lock):
    norm = lambda s: os.path.normcase(os.path.realpath(s))
    paths = P.get('protected_paths')
    if (not isinstance(paths, (list, tuple)) or not paths or
            any(not isinstance(x, str) or not (ntpath.isabs(x) or os.path.isabs(x)) for x in paths) or
            not isinstance(P.get('expected_path'), str) or
            not (ntpath.isabs(P['expected_path']) or os.path.isabs(P['expected_path']))):
        raise ValueError('Faltan copia y originales protegidos')
    if norm(path) != norm(P['expected_path']) or norm(path) in [norm(x) for x in P['protected_paths']]:
        raise ValueError('Documento fuera de alcance')
    if int(P.get('expected_pid', -1)) != int(pid) or int(lock.get('process_id', -1)) != int(pid):
        raise ValueError('PID distinto')
    identity = P.get('lock_identity', {})
    if lock.get('state') != 'active' or not all(identity.get(k) and identity[k] == lock.get(k)
                                               for k in ('owner','session','task')):
        raise ValueError('Turno distinto')


def run(doc, uidoc, DB, P):
    import System
    with io.open(P['lock_path'], encoding='utf-8-sig') as stream:
        lock = json.load(stream)
    validate_scope(P, doc.PathName, System.Diagnostics.Process.GetCurrentProcess().Id, lock)
    if doc.IsModifiable or doc.IsReadOnly or doc.IsFamilyDocument:
        raise ValueError('Documento no editable o transaccion abierta')
    action = P.get('action', 'inspect')
    if action not in ('inspect', 'apply'):
        raise ValueError('Accion desconocida')
    spec = build_spec(P)
    digest = spec_digest(spec)
    text_types = [e for e in DB.FilteredElementCollector(doc).OfClass(DB.TextNoteType)
                  if e.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() == spec['text_type_name']]
    if len(text_types) != 1:
        raise ValueError('Texto GR inexistente o ambiguo')
    dim_types = [e for e in DB.FilteredElementCollector(doc).OfClass(DB.DimensionType)
                 if e.StyleType == DB.DimensionStyleType.Linear and
                 e.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() == spec['dimension_type_name']]
    if len(dim_types) != 1:
        raise ValueError('Cota GR inexistente o ambigua')
    dim_name = P['view_prefix'] + ' - COTAS METROS'
    dim_collision = any(e.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString() == dim_name
                        for e in DB.FilteredElementCollector(doc).OfClass(DB.DimensionType))
    families = [e for e in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                if e.ViewFamily == DB.ViewFamily.Drafting]
    if not families:
        raise ValueError('No hay tipo Drafting')
    existing = set(v.Name for v in DB.FilteredElementCollector(doc).OfClass(DB.View))
    collisions = [v['name'] for v in spec['views'] if v['name'] in existing]
    result = {'ok': True, 'action': action, 'spec': spec, 'digest': digest,
              'name_collisions': collisions, 'dimension_type_exists': dim_collision,
              'created': [], 'saved': False}
    if action == 'inspect':
        return result
    if P.get('expected_digest') != digest:
        raise ValueError('Digest distinto; inspeccionar la propuesta primero')
    if collisions or dim_collision:
        raise ValueError('Vistas existentes; no se reemplazan ni duplican')
    if doc.IsModified:
        raise ValueError('Guardar cambios previos antes de apply')
    import clr
    clr.AddReference('Microsoft.VisualBasic')
    from Microsoft.VisualBasic.Devices import ComputerInfo
    if int(ComputerInfo().AvailablePhysicalMemory / 1048576) < 512:
        raise ValueError('RAM libre insuficiente (<512 MB)')
    def warnings():
        return sorted((str(w.GetFailureDefinitionId().Guid), tuple(sorted(int(i.Value) for i in w.GetFailingElements())))
                      for w in doc.GetWarnings())
    before_warnings = warnings()
    xyz = lambda p: DB.XYZ(p[0]/.3048, p[1]/.3048, 0)
    group = DB.TransactionGroup(doc, 'CDX detalles geometricos de losas')
    class RejectFailures(DB.IFailuresPreprocessor):
        def PreprocessFailures(self, accessor):
            return (DB.FailureProcessingResult.ProceedWithRollBack if list(accessor.GetFailureMessages())
                    else DB.FailureProcessingResult.Continue)
    tx = None
    try:
        group.Start()
        tx = DB.Transaction(doc, 'CDX crear detalles nativos GR')
        tx.Start()
        options = tx.GetFailureHandlingOptions()
        options.SetFailuresPreprocessor(RejectFailures())
        options.SetClearAfterRollback(True)
        tx.SetFailureHandlingOptions(options)
        dim_type = dim_types[0].Duplicate(dim_name)
        fmt = DB.FormatOptions(DB.UnitTypeId.Meters)
        fmt.Accuracy = .001
        dim_type.SetUnitsFormatOptions(fmt)
        actual_format = dim_type.GetUnitsFormatOptions()
        if actual_format.UseDefault or actual_format.GetUnitTypeId() != DB.UnitTypeId.Meters:
            raise ValueError('Formato de cotas no esta en metros')
        result['dimension_type_id'] = int(dim_type.Id.Value)
        result['dimension_unit'] = actual_format.GetUnitTypeId().TypeId
        for item in spec['views']:
            view = DB.ViewDrafting.Create(doc, families[0].Id)
            view.Name = item['name']
            view.Scale = item['scale']
            curves = [doc.Create.NewDetailCurve(view, DB.Line.CreateBound(xyz(a), xyz(b))) for a,b in item['lines']]
            doc.Regenerate()
            dimensions = []
            for dim in item['dimensions']:
                refs = DB.ReferenceArray()
                for index in dim['refs']:
                    refs.Append(curves[index].GeometryCurve.Reference)
                d = doc.Create.NewDimension(view, DB.Line.CreateBound(xyz(dim['line'][0]), xyz(dim['line'][1])), refs, dim_type)
                dimensions.append((d, dim['expected_m']))
            notes = [DB.TextNote.Create(doc, view.Id, xyz(n['point']), n['text'], text_types[0].Id)
                     for n in item['notes']]
            doc.Regenerate()
            for d, expected in dimensions:
                if d.Value is None or abs(float(d.Value)*.3048 - expected) > 1e-6:
                    raise ValueError('Cota no coincide con geometria')
            result['created'].append({'id': int(view.Id.Value), 'name': view.Name,
                'curves': [int(c.Id.Value) for c in curves],
                'notes': [int(n.Id.Value) for n in notes],
                'dimensions': [{'id':int(d.Id.Value), 'value_m':float(d.Value)*.3048,
                                'display':d.ValueString} for d,_ in dimensions]})
        if tx.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Transaccion no confirmada')
        if warnings() != before_warnings:
            raise ValueError('Advertencias cambiaron; revertir grupo')
        if group.Assimilate() != DB.TransactionStatus.Committed:
            raise ValueError('Grupo no confirmado')
    finally:
        if tx is not None and tx.GetStatus() == DB.TransactionStatus.Started:
            tx.RollBack()
        if group.GetStatus() == DB.TransactionStatus.Started:
            group.RollBack()
    return result
