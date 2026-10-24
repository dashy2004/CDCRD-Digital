# -*- coding: utf-8 -*-
"""Sustituye un conjunto EPS explicito por FamilyInstances contables.

Inspeccion por defecto. Requiere copia/PID/turno; apply exige digest de la
inspeccion, respaldo SHA256 y autorizacion de sustitucion. Nunca opera VOID.
Acepta solamente prismas rectangulares alineados; piezas maximas opcionales
en XY no agregan nervios. Cada pieza (incluidos recortes) cuenta una unidad.
Las familias son de dimensiones fijas; no son un catalogo comercial aprobado.
No toca el host ni sus cortes. Un recibo existente impide reintentos ciegos.
"""
import hashlib
import io
import json
import math
import os

try:
    text_type = unicode
except NameError:
    text_type = str


def piece_boxes(boxes, max_xy=None, limit=600):
    """Partition [xmin,ymin,zmin,xmax,ymax,zmax] metres without gaps."""
    if not boxes or not 1 <= limit <= 1000:
        raise ValueError('Numero de piezas fuera del limite')
    if max_xy is not None and (len(max_xy) != 2 or any(
            not _finite(v) or v < .05 for v in max_xy)):
        raise ValueError('Tamano de pieza invalido')
    result = []
    for box in boxes:
        if len(box) != 6 or any(not _finite(v) for v in box):
            raise ValueError('Caja no finita')
        if any(box[i+3] - box[i] < .001 for i in range(3)):
            raise ValueError('Caja degenerada')
        axes = []
        for axis in range(2):
            start, end = box[axis], box[axis+3]
            size = max_xy[axis] if max_xy else end-start
            count = max(1, int(math.ceil((end-start)/size-1e-9)))
            if count > limit:
                raise ValueError('Demasiadas piezas')
            cuts = [start+index*size for index in range(count)] + [end]
            # A sub-millimetre remainder is merged, not silently discarded.
            if len(cuts) > 2 and cuts[-1]-cuts[-2] < .001:
                cuts.pop(-2)
            axes.append(list(zip(cuts[:-1], cuts[1:])))
        for x0, x1 in axes[0]:
            for y0, y1 in axes[1]:
                result.append([x0, y0, box[2], x1, y1, box[5]])
                if len(result) > limit:
                    raise ValueError('Demasiadas piezas; no se inicia lote')
    for index, a in enumerate(result):
        for b in result[index+1:]:
            if all(min(a[i+3], b[i+3])-max(a[i], b[i]) > 1e-8 for i in range(3)):
                raise ValueError('Piezas superpuestas')
    return result


def _finite(value):
    return not math.isnan(float(value)) and not math.isinf(float(value))


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode('utf8')).hexdigest()


def _file_hash(path):
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        while True:
            chunk = stream.read(1024*1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _start_transaction(DB, document, name, preprocessor, cleanup_errors):
    tx = DB.Transaction(document,name)
    try:
        if tx.Start() != DB.TransactionStatus.Started:
            raise ValueError('Transaccion no iniciada')
        tx.SetFailureHandlingOptions(tx.GetFailureHandlingOptions().SetFailuresPreprocessor(preprocessor).SetClearAfterRollback(True))
        return tx
    except Exception:
        try:
            if tx.GetStatus() == DB.TransactionStatus.Started and tx.RollBack() != DB.TransactionStatus.RolledBack:
                cleanup_errors.append('Rollback de inicio no confirmado')
        except Exception as error:
            cleanup_errors.append(str(error))
        try:
            tx.Dispose()
        except Exception as error:
            cleanup_errors.append(str(error))
        raise


def run(doc, uidoc, DB, P):
    import clr
    import System
    from System.Collections.Generic import List
    clr.AddReference('Microsoft.VisualBasic')
    from Microsoft.VisualBasic.Devices import ComputerInfo

    norm = lambda path: os.path.normcase(os.path.realpath(path))
    protected = P.get('protected_paths') or []
    if not protected or norm(doc.PathName) != norm(P['expected_path']) or norm(doc.PathName) in [norm(p) for p in protected]:
        raise ValueError('Documento no autorizado')
    if int(System.Diagnostics.Process.GetCurrentProcess().Id) != P['expected_pid']:
        raise ValueError('PID diferente')
    with io.open(P['lock_path'], encoding='utf-8-sig') as stream:
        lock = json.load(stream)
    if lock.get('state') != 'active' or lock.get('process_id') != P['expected_pid'] or not all(
            P.get('lock_identity', {}).get(k) and lock.get(k) == P['lock_identity'][k]
            for k in ('owner', 'session', 'task')):
        raise ValueError('Turno diferente')
    if doc.IsModifiable or doc.IsReadOnly or doc.IsWorkshared:
        raise ValueError('Estado de documento no admitido')
    if int(ComputerInfo().AvailablePhysicalMemory/1048576) < 768:
        raise ValueError('RAM libre <768 MB; no se inicia lote')
    source = doc.GetElement(DB.ElementId(System.Int64(P['source_id'])))
    if not isinstance(source, DB.FamilyInstance) or int(source.Category.Id.Value) != int(DB.BuiltInCategory.OST_GenericModel):
        raise ValueError('Origen no es familia de modelo generico')
    family_name = source.Symbol.Family.Name
    if 'EPS' not in family_name.upper() or 'VOID' in family_name.upper():
        raise ValueError('Origen no identificado como EPS; los vacios no se sustituyen')
    if source.Pinned or source.GroupId != DB.ElementId.InvalidElementId or source.SuperComponent is not None:
        raise ValueError('EPS fijado, agrupado o anidado')
    if source.AssemblyInstanceId != DB.ElementId.InvalidElementId or source.DesignOption is not None:
        raise ValueError('EPS pertenece a ensamblaje u opcion de diseno')
    phases = (source.CreatedPhaseId,source.DemolishedPhaseId)
    if source.Host is not None or list(DB.JoinGeometryUtils.GetJoinedElements(doc, source)):
        raise ValueError('EPS hospedado o unido: requiere revision especifica')
    allow_cut = source.Symbol.Family.get_Parameter(DB.BuiltInParameter.FAMILY_ALLOW_CUT_WITH_VOIDS)
    if allow_cut is None or allow_cut.AsInteger() != 0:
        raise ValueError('Familia puede cortar elementos o no declara su estado')
    dependent_ids = [int(e.Value) for e in source.GetDependentElements(None) if e != source.Id]
    if dependent_ids:
        raise ValueError('EPS tiene dependientes: %s' % dependent_ids)
    tagged = [int(tag.Id.Value) for tag in DB.FilteredElementCollector(doc).OfClass(DB.IndependentTag)
              if source.Id in list(tag.GetTaggedLocalElementIds())]
    if tagged:
        raise ValueError('EPS tiene etiquetas: %s' % tagged)

    options = DB.Options()
    options.DetailLevel = DB.ViewDetailLevel.Fine
    def solids(geometry, strict=False):
        if geometry is None:
            return
        for item in geometry:
            if isinstance(item, DB.Solid):
                if item.Volume > 1e-9:
                    yield item
                elif strict and item.Faces.Size:
                    raise ValueError('Geometria sin volumen no admitida en EPS')
            elif isinstance(item, DB.GeometryInstance):
                for solid in solids(item.GetInstanceGeometry(),strict):
                    yield solid
            elif strict:
                raise ValueError('Geometria EPS no admitida: '+str(item.GetType()))
    def volume_intersection(a, b):
        common = DB.BooleanOperationsUtils.ExecuteBooleanOperation(a, b, DB.BooleanOperationsType.Intersect)
        try:
            return common.Volume
        finally:
            common.Dispose()
    def prism(box):
        x, y, z, xx, yy, zz = [v/.3048 for v in box]
        points = [DB.XYZ(x,y,z), DB.XYZ(xx,y,z), DB.XYZ(xx,yy,z), DB.XYZ(x,yy,z)]
        loop = DB.CurveLoop()
        for i in range(4):
            loop.Append(DB.Line.CreateBound(points[i], points[(i+1)%4]))
        return DB.GeometryCreationUtilities.CreateExtrusionGeometry(List[DB.CurveLoop]([loop]), DB.XYZ.BasisZ, zz-z)
    def shape(element):
        rows = []
        for solid in solids(element.get_Geometry(options)):
            pts = sorted(set(tuple(round(float(v),7) for v in (p.X,p.Y,p.Z))
                             for edge in solid.Edges for p in edge.Tessellate()))
            rows.append([round(solid.Volume,7), pts, sorted(round(face.Area,7) for face in solid.Faces)])
        return _digest(sorted(rows))
    def warnings():
        return set((w.GetDescriptionText(),tuple(sorted(int(i.Value) for i in w.GetFailingElements())))
                   for w in doc.GetWarnings())
    boxes = []
    for solid in solids(source.get_Geometry(options),True):
        parts = list(DB.SolidUtils.SplitVolumes(solid))
        try:
            for part in parts:
                if any(not isinstance(face, DB.PlanarFace) for face in part.Faces):
                    raise ValueError('EPS curvo no admitido')
                points = [p for edge in part.Edges for p in edge.Tessellate()]
                box = [min(getattr(p, axis) for p in points)*.3048 for axis in ('X','Y','Z')]
                box += [max(getattr(p, axis) for p in points)*.3048 for axis in ('X','Y','Z')]
                cube = prism(box)
                try:
                    common = volume_intersection(part, cube)
                    if abs(part.Volume+cube.Volume-2*common)*.3048**3 > 1e-8:
                        raise ValueError('EPS no es prisma rectangular alineado')
                finally:
                    cube.Dispose()
                boxes.append(box)
        finally:
            for part in parts:
                part.Dispose()
    pieces = piece_boxes(boxes, P.get('max_piece_xy_m'), P.get('max_pieces',600))
    source_shape = shape(source)
    source_uid = source.UniqueId
    source_comment = source.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).AsString() or ''
    plan_digest = _digest([source_uid, source_shape, pieces,[int(i.Value) for i in phases]])
    receipt = {'status':'inspected', 'source_id':P['source_id'], 'source_unique_id':source_uid,
               'family':family_name, 'cells':len(boxes), 'piece_count':len(pieces),
               'piece_boxes_m':pieces, 'plan_digest':plan_digest, 'quantity_basis':'geometric_pieces_including_cuts',
               'volume_m3':sum((b[3]-b[0])*(b[4]-b[1])*(b[5]-b[2]) for b in pieces),
               'commercial_catalog_verified':False, 'dependent_ids':dependent_ids, 'tag_ids':tagged}
    if P.get('inspect_only',True):
        return receipt
    if P.get('replacement_authorized') is not True or P.get('expected_digest') != plan_digest:
        raise ValueError('Falta autorizacion o la geometria cambio desde la inspeccion')
    backup = P['backup_path']
    if norm(backup) == norm(doc.PathName) or _file_hash(backup) != P['backup_sha256'].lower():
        raise ValueError('Respaldo no verificado')
    if os.path.exists(P['receipt_path']):
        raise ValueError('Recibo existente: conciliar estado antes de reintentar')
    if not os.path.isdir(P['family_dir']):
        raise ValueError('Directorio de familias ausente')
    # Signature of every physical category that must remain unchanged.
    categories = (DB.BuiltInCategory.OST_Floors, DB.BuiltInCategory.OST_Walls,
                  DB.BuiltInCategory.OST_StructuralFraming, DB.BuiltInCategory.OST_StructuralColumns,
                  DB.BuiltInCategory.OST_StructuralFoundation, DB.BuiltInCategory.OST_GenericModel)
    def protected_shapes():
        result = {}
        for category in categories:
            for element in DB.FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType():
                if int(element.Id.Value) == P['source_id'] or int(element.Id.Value) in created:
                    continue
                result[int(element.Id.Value)] = shape(element)
        return result
    created = []
    before_shapes = protected_shapes()
    before_warnings = warnings()
    failures = []
    transaction_cleanup_errors = []
    class Reject(DB.IFailuresPreprocessor):
        def PreprocessFailures(self, accessor):
            messages = list(accessor.GetFailureMessages())
            failures.extend(m.GetDescriptionText() for m in messages)
            return DB.FailureProcessingResult.ProceedWithRollBack if messages else DB.FailureProcessingResult.Continue
    def transaction(document, name):
        return _start_transaction(DB,document,name,Reject(),transaction_cleanup_errors)
    def write():
        with io.open(P['receipt_path'],'w',encoding='utf8') as stream:
            stream.write(text_type(json.dumps(receipt,indent=2)))
    # A receipt is persisted before creating families or changing the project.
    receipt['status'] = 'started'
    write()
    group = tx = None
    project_committed = False
    files = {}
    def dimensions(box):
        return tuple(round(box[i+3]-box[i],8) for i in range(3))
    def provenance(dims):
        return 'CDX:EPS:PIEZA:v1;'+_digest(dims)
    def validate_symbol(symbol, dims):
        if int(symbol.Category.Id.Value) != int(DB.BuiltInCategory.OST_GenericModel):
            raise ValueError('Pieza fuera de categoria Modelos genericos')
        for bip in (DB.BuiltInParameter.FAMILY_AUTOJOIN,DB.BuiltInParameter.FAMILY_ALLOW_CUT_WITH_VOIDS):
            flag = symbol.Family.get_Parameter(bip)
            if flag is None or flag.AsInteger() != 0:
                raise ValueError('Familia de pieza admite corte o union automatica')
        marker = symbol.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_COMMENTS)
        if marker is None or marker.AsString() != provenance(dims):
            raise ValueError('Familia sin procedencia comprobada')
        for label, value in zip(('CDX_Largo','CDX_Ancho','CDX_Alto'),dims):
            parameter = symbol.LookupParameter(label)
            if parameter is None or abs(parameter.AsDouble()*.3048-value)>1e-7:
                raise ValueError('Dimensiones declaradas de pieza incorrectas')
    try:
        # Sequential family documents bound RAM consumption.
        for dims in sorted(set(dimensions(box) for box in pieces)):
            name = 'CDX_EPS_PIEZA_'+_digest(dims)[:16]
            matching = [s for s in DB.FilteredElementCollector(doc).OfClass(DB.FamilySymbol) if s.Family.Name == name]
            if matching:
                if len(matching) != 1:
                    raise ValueError('Familia de pieza ambigua')
                validate_symbol(matching[0],dims)
                files[dims] = (name,None,matching[0].Id)
                continue
            path = os.path.join(P['family_dir'],name+'.rfa')
            if os.path.exists(path):
                raise ValueError('Familia en disco sin conciliar; no sobrescribir')
            fd = doc.Application.NewFamilyDocument(P['family_template'])
            ft = None
            try:
                if int(fd.OwnerFamily.FamilyCategory.Id.Value) != int(DB.BuiltInCategory.OST_GenericModel):
                    raise ValueError('Plantilla no es de Modelos genericos')
                ft = transaction(fd,'CDX: pieza EPS fija')
                fd.FamilyManager.NewType('PIEZA')
                fd.OwnerFamily.get_Parameter(DB.BuiltInParameter.FAMILY_AUTOJOIN).Set(0)
                fd.OwnerFamily.get_Parameter(DB.BuiltInParameter.FAMILY_ALLOW_CUT_WITH_VOIDS).Set(0)
                sp = DB.SketchPlane.Create(fd,DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisZ,DB.XYZ.Zero))
                pts = [DB.XYZ(x/.3048,y/.3048,0) for x,y in ((0,0),(dims[0],0),(dims[0],dims[1]),(0,dims[1]))]
                arr = DB.CurveArray()
                for i in range(4):
                    arr.Append(DB.Line.CreateBound(pts[i],pts[(i+1)%4]))
                profile = DB.CurveArrArray()
                profile.Append(arr)
                extrusion = fd.FamilyCreate.NewExtrusion(True,profile,sp,dims[2]/.3048)
                material = fd.GetElement(DB.Material.Create(fd,'EPS geometrico - densidad sin validar'))
                material.Color = DB.Color(220,225,230)
                extrusion.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM).Set(material.Id)
                for label, value in zip(('CDX_Largo','CDX_Ancho','CDX_Alto'),dims):
                    parameter = fd.FamilyManager.AddParameter(label,DB.GroupTypeId.Geometry,DB.SpecTypeId.Length,False)
                    # Formula makes the dimension metadata immutable and honest.
                    fd.FamilyManager.SetFormula(parameter,'%.8f m' % value)
                if ft.Commit() != DB.TransactionStatus.Committed:
                    raise ValueError('Familia rechazada')
                save = DB.SaveAsOptions()
                save.OverwriteExistingFile = False
                fd.SaveAs(path,save)
                files[dims] = (name,path,None)
            finally:
                cleanup_errors = []
                if ft is not None:
                    try:
                        if ft.GetStatus() == DB.TransactionStatus.Started and ft.RollBack() != DB.TransactionStatus.RolledBack:
                            cleanup_errors.append('Rollback de familia no confirmado')
                    except Exception as cleanup_error:
                        cleanup_errors.append(str(cleanup_error))
                    try:
                        ft.Dispose()
                    except Exception as cleanup_error:
                        cleanup_errors.append(str(cleanup_error))
                try:
                    if not fd.Close(False):
                        cleanup_errors.append('Familia no cerrada')
                except Exception as cleanup_error:
                    cleanup_errors.append(str(cleanup_error))
                if cleanup_errors:
                    receipt['family_cleanup_errors'] = cleanup_errors
                    raise ValueError('Limpieza de familia no confirmada: '+'; '.join(cleanup_errors))
        if int(ComputerInfo().AvailablePhysicalMemory/1048576) < 768:
            raise ValueError('RAM libre <768 MB tras preparar familias; proyecto intacto')
        group = DB.TransactionGroup(doc,'CDX: individualizar EPS comprobado')
        if group.Start() != DB.TransactionStatus.Started:
            raise ValueError('Grupo no iniciado')
        tx = transaction(doc,'CDX: sustituir solo conjunto EPS')
        symbols = {}
        for dims, (name,path,symbol_id) in files.items():
            if path:
                reference = clr.Reference[DB.Family]()
                if not doc.LoadFamily(path,reference):
                    raise ValueError('Familia no cargada')
                symbol_id = list(reference.Value.GetFamilySymbolIds())[0]
            symbol = doc.GetElement(symbol_id)
            if path:
                if not symbol.get_Parameter(DB.BuiltInParameter.ALL_MODEL_TYPE_COMMENTS).Set(provenance(dims)):
                    raise ValueError('Procedencia de familia no registrada')
            validate_symbol(symbol,dims)
            if not symbol.IsActive:
                symbol.Activate()
            symbols[dims] = symbol
        doc.Regenerate()
        for index, box in enumerate(pieces):
            instance = doc.Create.NewFamilyInstance(DB.XYZ(*[v/.3048 for v in box[:3]]),symbols[dimensions(box)],DB.Structure.StructuralType.NonStructural)
            created.append(int(instance.Id.Value))
            if instance.CreatedPhaseId != phases[0]:
                instance.CreatedPhaseId = phases[0]
            if instance.DemolishedPhaseId != phases[1]:
                instance.DemolishedPhaseId = phases[1]
            instance.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).Set(
                source_comment+' | CDX:EPS:PIEZA;source=%s;piece=%s/%s' % (P['source_id'],index+1,len(pieces)))
        doc.Regenerate()
        def verify_pieces():
            for element_id, box in zip(created,pieces):
                element = doc.GetElement(DB.ElementId(System.Int64(element_id)))
                if element is None:
                    raise ValueError('Pieza desaparecio tras regeneracion')
                if (element.CreatedPhaseId,element.DemolishedPhaseId) != phases:
                    raise ValueError('Fases de pieza distintas del origen')
                native = list(solids(element.get_Geometry(options),True))
                if len(native) != 1:
                    raise ValueError('Cada pieza debe contener un unico solido')
                material_ids = set(int(face.MaterialElementId.Value) for face in native[0].Faces)
                if not material_ids or any(doc.GetElement(DB.ElementId(System.Int64(i))) is None or
                        doc.GetElement(DB.ElementId(System.Int64(i))).Name != 'EPS geometrico - densidad sin validar'
                        for i in material_ids):
                    raise ValueError('Material de pieza no identificado como EPS geometrico')
                cube = prism(box)
                try:
                    common = sum(volume_intersection(s,cube) for s in native)
                    delta = sum(s.Volume for s in native)+cube.Volume-2*common
                    if abs(delta)*.3048**3 > 1e-8:
                        raise ValueError('Pieza difiere en forma o posicion')
                finally:
                    cube.Dispose()
        verify_pieces()
        deleted = sorted(int(i.Value) for i in doc.Delete(source.Id))
        if deleted != [P['source_id']]:
            raise ValueError('Eliminacion arrastra elementos ajenos: %s' % deleted)
        if tx.Commit() != DB.TransactionStatus.Committed:
            raise ValueError('Sustitucion rechazada')
        verify_pieces()
        if doc.GetElement(DB.ElementId(System.Int64(P['source_id']))) is not None:
            raise ValueError('Conjunto de origen sigue presente')
        if protected_shapes() != before_shapes:
            raise ValueError('Geometria protegida cambio; revertir lote')
        if warnings()-before_warnings:
            raise ValueError('Nuevas advertencias; revertir lote')
        receipt.update(piece_ids=created,deleted_ids=deleted,protected_geometry_unchanged=True,
                       family_paths=[path for name,path,symbol_id in files.values() if path],failures=failures)
        if P.get('simulate_only',False):
            if group.RollBack() != DB.TransactionStatus.RolledBack:
                raise ValueError('Simulacion no revertida')
            receipt['status'] = 'simulation_passed_rolled_back'
        else:
            if group.Assimilate() != DB.TransactionStatus.Committed:
                raise ValueError('Grupo no confirmado')
            project_committed = True
            receipt['status'] = 'applied_unsaved'
            write()
            if P.get('save',False):
                doc.Save()
                if doc.IsModified:
                    raise ValueError('Guardado no confirmado')
                receipt['status'] = 'saved'
        write()
        return receipt
    except Exception as error:
        rollback_errors = []
        for item in (tx,group):
            try:
                if item is not None and item.GetStatus() == DB.TransactionStatus.Started:
                    if item.RollBack() != DB.TransactionStatus.RolledBack:
                        rollback_errors.append('Estado de rollback no confirmado')
            except Exception as rollback_error:
                rollback_errors.append(str(rollback_error))
        receipt.update(status='applied_unsaved' if project_committed else 'rollback_unverified' if rollback_errors or transaction_cleanup_errors or receipt.get('family_cleanup_errors') else 'error_inspect_before_retry',
                       error=str(error),rollback_errors=rollback_errors,transaction_cleanup_errors=transaction_cleanup_errors,failures=failures)
        write()
        raise
    finally:
        dispose_errors = []
        for item in (tx,group):
            try:
                if item is not None:
                    item.Dispose()
            except Exception as error:
                dispose_errors.append(str(error))
        if dispose_errors:
            receipt['dispose_errors'] = dispose_errors
            write()
            raise ValueError('Liberacion de transacciones no confirmada: '+'; '.join(dispose_errors))
