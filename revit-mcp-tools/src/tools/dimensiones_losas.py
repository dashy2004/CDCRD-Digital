# -*- coding: utf-8 -*-
"""Lx/Ly del contorno rectangular de Floor; no son luces de calculo.

Solo segmentos rectos, un contorno, horizontal y rectangular. Lx sigue X y Ly sigue Y del sistema configurado (global por defecto).
Para plantas giradas exige declarar el angulo de los ejes. No usa bounding box.
Un shaft separado puede recortar el solido: estas dimensiones describen
el perfil exterior, no certifican su area neta ni sus apoyos.
Se actualizan al ejecutar la herramienta; no instala un updater permanente.
"""
import io
import json
import math
import os

GUIDS = {'Lx': '2c4ca27b-a552-47a2-b412-849c249a50c1',
         'Ly': 'f9b89e1d-e894-48af-b570-0bd163e23141'}


def rectangle_lengths(points, angle_degrees=0.0, tolerance=1e-6):
    """Four ordered corners, metres. Reject sloped/degenerate/nonrectangular."""
    if len(points) != 4 or any(len(p) != 3 for p in points):
        raise ValueError('Se requieren cuatro vertices XYZ')
    if any(math.isnan(float(x)) or math.isinf(float(x)) for p in points for x in p):
        raise ValueError('Coordenadas no finitas')
    if max(p[2] for p in points) - min(p[2] for p in points) > tolerance:
        raise ValueError('Contorno inclinado')
    edges = [(points[(i + 1) % 4][0] - p[0],
              points[(i + 1) % 4][1] - p[1]) for i, p in enumerate(points)]
    lengths = [math.hypot(*e) for e in edges]
    if min(lengths) <= tolerance:
        raise ValueError('Lado degenerado')
    for i, e in enumerate(edges):
        other = edges[(i + 1) % 4]
        if abs(e[0]*other[0] + e[1]*other[1]) > tolerance * lengths[i] * lengths[(i+1)%4]:
            raise ValueError('Contorno no rectangular')
    if abs(lengths[0]-lengths[2]) > tolerance or abs(lengths[1]-lengths[3]) > tolerance:
        raise ValueError('Lados opuestos diferentes')
    if math.isnan(float(angle_degrees)) or math.isinf(float(angle_degrees)):
        raise ValueError('Angulo no finito')
    angle = math.radians(angle_degrees)
    axis = (math.cos(angle), math.sin(angle))
    projected = [(x*axis[0]+y*axis[1], -x*axis[1]+y*axis[0]) for x,y in edges]
    if any(min(abs(x), abs(y)) > tolerance for x,y in projected):
        raise ValueError('Ejes del contorno no coinciden con el sistema declarado')
    return max(abs(e[0]) for e in projected), max(abs(e[1]) for e in projected)


def validate_scope(P, path, pid, lock):
    normal = lambda s: os.path.normcase(os.path.realpath(s))
    if not P.get('expected_path') or not P.get('protected_paths'):
        raise ValueError('Faltan copia y fuentes protegidas')
    if normal(path) != normal(P['expected_path']) or normal(path) in [normal(s) for s in P['protected_paths']]:
        raise ValueError('Documento no autorizado o protegido')
    if int(pid) != int(P.get('expected_pid', -1)):
        raise ValueError('PID diferente')
    if lock.get('state') != 'active' or not all(P.get('lock_identity', {}).get(k) and
            P['lock_identity'][k] == lock.get(k) for k in ('owner', 'session', 'task')):
        raise ValueError('Turno exclusivo diferente')
    ids = P.get('floor_ids') or []
    if not ids or len(ids) > 500 or len(ids) != len(set(ids)):
        raise ValueError('floor_ids vacio o duplicado')


def run(doc, uidoc, DB, P):
    import System
    with io.open(P['lock_path'], encoding='utf-8-sig') as stream:
        lock = json.load(stream)
    validate_scope(P, doc.PathName, System.Diagnostics.Process.GetCurrentProcess().Id, lock)
    if doc.IsReadOnly or doc.IsModifiable:
        raise ValueError('Documento bloqueado o transaccion abierta')
    action = P.get('action', 'inspect')
    if action not in ('inspect', 'apply'):
        raise ValueError('Accion desconocida')
    rows = []
    for id_value in P['floor_ids']:
        floor = doc.GetElement(DB.ElementId(System.Int64(id_value)))
        if not isinstance(floor, DB.Floor):
            raise ValueError('El elemento no es Floor: %s' % id_value)
        sketch = doc.GetElement(floor.SketchId)
        loops = list(sketch.Profile) if sketch else []
        if len(loops) != 1 or len(list(loops[0])) != 4 or any(not isinstance(c, DB.Line) for c in loops[0]):
            raise ValueError('Se requiere perfil rectangular unico: %s' % id_value)
        points = [[float(c.GetEndPoint(0).X)*.3048, float(c.GetEndPoint(0).Y)*.3048,
                   float(c.GetEndPoint(0).Z)*.3048] for c in loops[0]]
        lx, ly = rectangle_lengths(points, P.get('angle_degrees', 0.0))
        rows.append({'id': id_value, 'Lx_m': lx, 'Ly_m': ly,
                     'mark': floor.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString()})
    # Existing definitions must be ours, instance-bound to floors and dimensionally Length.
    definitions = {}
    it = doc.ParameterBindings.ForwardIterator()
    while it.MoveNext():
        definition = it.Key
        if definition.Name not in GUIDS:
            continue
        element = doc.GetElement(definition.Id)
        if (not isinstance(element, DB.SharedParameterElement) or
                str(element.GuidValue).lower() != GUIDS[definition.Name] or
                definition.GetDataType() != DB.SpecTypeId.Length or
                not isinstance(it.Current, DB.InstanceBinding) or
                not it.Current.Categories.Contains(doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Floors))):
            raise ValueError('Parametro existente incompatible: ' + definition.Name)
        definitions[definition.Name] = definition
    if action == 'apply':
        import clr
        clr.AddReference('Microsoft.VisualBasic')
        from Microsoft.VisualBasic.Devices import ComputerInfo
        # This bounded batch writes at most 1000 scalar values; no solids/families.
        if int(ComputerInfo().AvailablePhysicalMemory / 1048576) < 512:
            raise ValueError('RAM libre insuficiente (<512 MB)')
        old_file = doc.Application.SharedParametersFilename
        temporary = None
        tx = None
        try:
            if len(definitions) != 2:
                temporary = System.IO.Path.GetTempFileName()
                with io.open(temporary, 'w', encoding='utf-8') as stream:
                    stream.write(u'# CDX shared parameters\n*META\tVERSION\tMINVERSION\nMETA\t2\t1\n*GROUP\tID\tNAME\n*PARAM\tGUID\tNAME\tDATATYPE\tDATACATEGORY\tGROUP\tVISIBLE\tDESCRIPTION\tUSERMODIFIABLE\tHIDEWHENNOVALUE\n')
                doc.Application.SharedParametersFilename = temporary
                shared = doc.Application.OpenSharedParameterFile()
                if shared is None:
                    raise ValueError('Archivo temporal de parametros invalido')
                group = shared.Groups.Create('CDX Geometria')
                for key in ('Lx', 'Ly'):
                    if key in definitions:
                        continue
                    option = DB.ExternalDefinitionCreationOptions(key, DB.SpecTypeId.Length)
                    option.GUID = System.Guid(GUIDS[key])
                    option.UserModifiable = False
                    option.Description = ('Dimension geometrica del lado %s del perfil rectangular exterior. '
                        'No es luz entre apoyos; actualizar con dimensiones_losas tras editar el contorno.'
                        % ('X del sistema declarado' if key == 'Lx' else 'Y del sistema declarado'))
                    definitions[key] = group.Definitions.Create(option)
            tx = DB.Transaction(doc, 'CDX: actualizar Lx Ly de losas')
            tx.Start()
            cats = doc.Application.Create.NewCategorySet()
            cats.Insert(doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Floors))
            for key, definition in definitions.items():
                if isinstance(definition, DB.ExternalDefinition):
                    if not doc.ParameterBindings.Insert(definition, doc.Application.Create.NewInstanceBinding(cats), DB.GroupTypeId.Geometry):
                        raise ValueError('No se pudo enlazar ' + key)
            doc.Regenerate()
            for row in rows:
                floor = doc.GetElement(DB.ElementId(System.Int64(row['id'])))
                for key in ('Lx', 'Ly'):
                    p = floor.get_Parameter(System.Guid(GUIDS[key]))
                    value = row[key + '_m'] / .3048
                    if p is None or not p.Set(value):
                        raise ValueError('No se pudo actualizar ' + key)
                    if abs(p.AsDouble() - value) > 1e-9:
                        raise ValueError('Lectura diferente ' + key)
            if tx.Commit() != DB.TransactionStatus.Committed:
                raise ValueError('Transaccion no confirmada')
        finally:
            if tx is not None and tx.GetStatus() == DB.TransactionStatus.Started:
                tx.RollBack()
            doc.Application.SharedParametersFilename = old_file
            if temporary:
                System.IO.File.Delete(temporary)
    return {'ok': True, 'action': action, 'rows': rows, 'meaning': 'outer_profile_declared_xy',
            'automatic_updater': False, 'engineering_span': False}
