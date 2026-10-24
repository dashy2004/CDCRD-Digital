# -*- coding: utf-8 -*-
"""Create a copy-only EPS quantity schedule; inspect by default.

Execute through the Python bridge with run(doc, uidoc, DB, config). Does not
edit physical elements. Native schedule membership must equal the inspected
EPS instance IDs, including older individual families. Cut pieces count as
units, not necessarily whole commercial blocks.
"""
import hashlib
import io
import json
import os

try:
    text_type = unicode
except NameError:
    text_type = str


def _write(path, result):
    with io.open(path, 'w', encoding='utf-8') as stream:
        stream.write(text_type(json.dumps(result, ensure_ascii=True, indent=2)))


def run(doc, uidoc, DB, config):
    import System

    p = config
    normalize = lambda path: os.path.normcase(os.path.realpath(path))
    expected = normalize(p['expected_path'])
    if not p['protected_paths'] or normalize(doc.PathName) != expected or expected in [normalize(x) for x in p['protected_paths']]:
        raise ValueError('Documento no autorizado')
    if int(System.Diagnostics.Process.GetCurrentProcess().Id) != p['expected_pid']:
        raise ValueError('PID distinto')
    with io.open(p['lock_path'], encoding='utf-8-sig') as stream:
        lock = json.load(stream)
    if any(lock.get(k) != p['lock_identity'][k] for k in ('owner', 'session', 'task')):
        raise ValueError('Turno distinto')
    if lock.get('process_id') != p['expected_pid'] or lock.get('state') != 'active':
        raise ValueError('Turno inactivo o PID distinto')
    if doc.IsModifiable or doc.IsReadOnly or doc.IsModified:
        raise ValueError('Se exige copia guardada y sin transaccion')
    eps = [e for e in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_GenericModel).WhereElementIsNotElementType()
           if isinstance(e, DB.FamilyInstance) and 'EPS' in e.Symbol.Family.Name and 'VOID' not in e.Symbol.Family.Name]
    ids = sorted(int(e.Id.Value) for e in eps)
    if not ids:
        raise ValueError('Sin instancias EPS')
    digest = hashlib.sha256(json.dumps(ids).encode('utf-8')).hexdigest()
    result = {'status': 'inspected', 'count': len(ids), 'ids_digest': digest}
    if p.get('apply') is not True:
        return result
    if p.get('expected_digest') != digest:
        raise ValueError('Inventario distinto de la inspeccion')
    name = p.get('schedule_name', 'CDX EPS - CANTIDADES INDIVIDUALES')
    if not name.startswith('CDX ') or any(v.Name == name for v in DB.FilteredElementCollector(doc).OfClass(DB.View)):
        raise ValueError('Nombre no autorizado o ya existente')
    if os.path.exists(p['receipt_path']):
        raise ValueError('Conciliar recibo existente antes de reintentar')
    warnings = sorted(w.GetDescriptionText() for w in doc.GetWarnings())
    result['status'] = 'started'
    _write(p['receipt_path'], result)
    failures = []
    class Reject(DB.IFailuresPreprocessor):
        def PreprocessFailures(self, accessor):
            messages = list(accessor.GetFailureMessages())
            failures.extend(m.GetDescriptionText() for m in messages)
            return DB.FailureProcessingResult.ProceedWithRollBack if messages else DB.FailureProcessingResult.Continue
    group = DB.TransactionGroup(doc, 'CDX: cantidades EPS verificadas')
    tx = None
    assimilated = False
    try:
        group.Start()
        tx = DB.Transaction(doc, 'CDX: tabla EPS'); tx.Start()
        failure_options = tx.GetFailureHandlingOptions()
        failure_options.SetFailuresPreprocessor(Reject())
        failure_options.SetClearAfterRollback(True)
        tx.SetFailureHandlingOptions(failure_options)
        view = DB.ViewSchedule.CreateSchedule(doc, DB.ElementId(DB.BuiltInCategory.OST_GenericModel))
        view.Name = name
        definition = view.Definition
        fields = {int(f.ParameterId.Value): f for f in definition.GetSchedulableFields()}
        family = definition.AddField(fields[int(DB.BuiltInParameter.ELEM_FAMILY_PARAM)])
        family.ColumnHeading = 'Familia EPS'
        kind = definition.AddField(fields[int(DB.BuiltInParameter.ELEM_TYPE_PARAM)])
        kind.ColumnHeading = 'Tipo'
        count = definition.AddField(DB.ScheduleFieldType.Count)
        count.ColumnHeading = 'Piezas (incluye recortes)'
        volume = definition.AddField(fields[int(DB.BuiltInParameter.HOST_VOLUME_COMPUTED)])
        volume.ColumnHeading = 'Volumen EPS (m3)'
        options = DB.FormatOptions(DB.UnitTypeId.CubicMeters)
        options.Accuracy = .0001
        volume.SetFormatOptions(options)
        for field in (count, volume):
            if field.CanTotal():
                field.DisplayType = DB.ScheduleFieldDisplayType.Totals
        definition.AddFilter(DB.ScheduleFilter(family.FieldId, DB.ScheduleFilterType.Contains, 'EPS'))
        definition.AddFilter(DB.ScheduleFilter(family.FieldId, DB.ScheduleFilterType.NotContains, 'VOID'))
        definition.IsItemized = False
        for field in (family, kind):
            definition.AddSortGroupField(DB.ScheduleSortGroupField(field.FieldId))
        definition.ShowGrandTotal = True
        definition.ShowGrandTotalCount = True
        definition.ShowGrandTotalTitle = True
        definition.GrandTotalTitle = 'TOTAL PIEZAS EPS'
        doc.Regenerate()
        actual = sorted(int(e.Id.Value) for e in DB.FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType())
        if actual != ids:
            raise ValueError('La tabla no contiene exactamente el inventario EPS')
        if tx.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Transaccion no confirmada')
        if warnings != sorted(w.GetDescriptionText() for w in doc.GetWarnings()):
            raise ValueError('Advertencias nuevas')
        actual = sorted(int(e.Id.Value) for e in DB.FilteredElementCollector(doc, view.Id).WhereElementIsNotElementType())
        if actual != ids:
            raise ValueError('Inventario cambio tras commit')
        if group.Assimilate() != DB.TransactionStatus.Committed:
            raise ValueError('Grupo no confirmado')
        assimilated = True
        result.update(status='applied_unsaved', schedule_id=int(view.Id.Value), schedule_name=name,
                      native_membership_equal=True, element_ids=ids)
        _write(p['receipt_path'], result)
        doc.Save()
        if doc.IsModified:
            raise ValueError('Guardado no confirmado')
        result['status'] = 'saved'
        _write(p['receipt_path'], result)
        return result
    except Exception as exc:
        rollback_errors = []
        for item in (tx, group):
            try:
                if item is not None and item.GetStatus() == DB.TransactionStatus.Started:
                    if item.RollBack() != DB.TransactionStatus.RolledBack:
                        rollback_errors.append('Rollback no confirmado')
                elif item is not None and item.GetStatus() == DB.TransactionStatus.Pending:
                    rollback_errors.append('Transaccion pendiente')
            except Exception as error:
                rollback_errors.append(text_type(error))
        result.update(status='applied_save_unconfirmed' if assimilated else 'rollback_unverified' if rollback_errors else 'rolled_back',
                      error=text_type(exc), rollback_errors=rollback_errors, failures=failures)
        _write(p['receipt_path'], result)
        raise
    finally:
        dispose_errors = []
        for item in (tx, group):
            try:
                if item is not None:
                    item.Dispose()
            except Exception as error:
                dispose_errors.append(text_type(error))
        if dispose_errors:
            result['dispose_errors'] = dispose_errors
            _write(p['receipt_path'], result)
            raise ValueError('Liberacion de transacciones no confirmada')
