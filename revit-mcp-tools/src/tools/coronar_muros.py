# -*- coding: utf-8 -*-
"""Baja coronaciones de muros no estructurales bajo losa/viga en una copia.

Usa cota nominal inferior de losa (no el fondo de las cavidades EPS).
P: expected_path/PID/protected_paths/lock_path/lock_identity, action inspect,
simulate o apply, walls [{id,top_m,source_elements:[{kind,id}],
expected_top_offset_m,expected_top_level_id}], receipt_path.
Top Offset y desvinculacion superior. Las vigas y losas conservan sus solidos.
Regeneracion de columnas y uniones columna-losa requieren opciones explicitas,
ensayo previo y comparacion de solapes. duplicate_columns solo admite pares
explicitos geometricamente iguales, sin dependientes ni datos distintos salvo
IfcGUID. No escribe parametros de columnas/vigas/losas ni bases de muro.
"""
import io,json,os,hashlib
try:text_type=unicode
except NameError:text_type=str


def select_top(floor_bottoms, beam_bottoms):
    """Walls below a slab keep its underside; beam joins provide local notches."""
    values=floor_bottoms or beam_bottoms
    if not values:raise ValueError('Sin estructura superior comprobada')
    import math
    if any(math.isnan(v) or math.isinf(v) for v in values):raise ValueError('Cota no finita')
    return min(values)


def close_values(a,b,tol=1e-7):
    if isinstance(a,dict) and isinstance(b,dict):return set(a)==set(b) and all(close_values(a[k],b[k],tol) for k in a)
    if isinstance(a,(tuple,list)) and isinstance(b,(tuple,list)):return len(a)==len(b) and all(close_values(x,y,tol) for x,y in zip(a,b))
    if isinstance(a,float) or isinstance(b,float):return a is not None and b is not None and abs(a-b)<=tol
    return a==b


def validate_apply_plan(config, joins, columns):
    if set(map(tuple,joins))!=set(map(tuple,config.get('expected_column_floor_joins',[]))):raise ValueError('Uniones distintas al ensayo')
    if set(columns)!=set(config.get('expected_changed_columns',[])):raise ValueError('Columnas distintas al ensayo')


def horizontal_beam_bottom(e,DB):
    curve=e.Location.Curve
    if not isinstance(curve,DB.Line) or abs(curve.Direction.Z)>1e-8:raise ValueError('Viga inclinada excluida')
    options=DB.Options();options.DetailLevel=DB.ViewDetailLevel.Fine
    def walk(gs):
        for g in gs:
            if isinstance(g,DB.Solid) and g.Volume>1e-9:yield g
            elif isinstance(g,DB.GeometryInstance):
                for s in walk(g.GetInstanceGeometry()):yield s
    bottoms=[]
    for s in walk(e.get_Geometry(options)):
        for f in s.Faces:
            if not isinstance(f,DB.PlanarFace):raise ValueError('Viga con caras curvas excluida')
            nz=f.FaceNormal.Z
            if abs(nz)>1e-8 and abs(abs(nz)-1)>1e-8:raise ValueError('Viga con fondo/cara inclinada excluida')
            if nz<-.99:bottoms.append(f.Origin.Z*.3048)
    if not bottoms or max(bottoms)-min(bottoms)>1e-6:raise ValueError('Fondo de viga no uniforme')
    return min(bottoms)


def run(doc,uidoc,DB,P):
    owned=[]
    try:return _run(doc,uidoc,DB,P,owned)
    finally:
        for s in owned:s.Dispose()


def _run(doc,uidoc,DB,P,owned):
    import System
    norm=lambda p:os.path.normcase(os.path.realpath(p))
    if not P.get('protected_paths') or norm(doc.PathName)!=norm(P['expected_path']) or norm(doc.PathName) in [norm(p) for p in P['protected_paths']]:raise ValueError('Copia no autorizada')
    if int(System.Diagnostics.Process.GetCurrentProcess().Id)!=P['expected_pid']:raise ValueError('PID diferente')
    with io.open(P['lock_path'],encoding='utf-8-sig') as stream:lock=json.load(stream)
    if lock.get('state')!='active' or lock.get('process_id')!=P['expected_pid'] or not all(P.get('lock_identity',{}).get(k) and P['lock_identity'][k]==lock.get(k) for k in ['owner','session','task']):raise ValueError('Turno diferente')
    if doc.IsReadOnly or doc.IsModifiable or doc.IsFamilyDocument or doc.IsWorkshared:raise ValueError('Se requiere copia local editable sin transaccion abierta')
    action=P.get('action','inspect')
    if action not in ['inspect','simulate','apply']:raise ValueError('Accion desconocida')
    if action=='apply' and any(k not in P for k in ['expected_column_floor_joins','expected_changed_columns','expected_internal_cleanup_ids']):raise ValueError('Falta plan del ensayo previo')
    rows=P.get('walls') or []
    if not rows or len(rows)>200 or len(set(r['id'] for r in rows))!=len(rows):raise ValueError('Lote vacio, excesivo o duplicado')
    plans=[]
    for row in rows:
        wall=doc.GetElement(DB.ElementId(System.Int64(row['id'])))
        if not isinstance(wall,DB.Wall) or wall.Pinned or wall.GroupId!=DB.ElementId.InvalidElementId or wall.SketchId!=DB.ElementId.InvalidElementId:raise ValueError('Muro no simple/editable')
        if wall.get_Parameter(DB.BuiltInParameter.WALL_STRUCTURAL_SIGNIFICANT).AsInteger()!=0:raise ValueError('Muro estructural excluido')
        top_level=wall.get_Parameter(DB.BuiltInParameter.WALL_HEIGHT_TYPE).AsElementId()
        offset=wall.get_Parameter(DB.BuiltInParameter.WALL_TOP_OFFSET)
        if int(top_level.Value)!=row['expected_top_level_id'] or abs(offset.AsDouble()*.3048-row['expected_top_offset_m'])>1e-7:raise ValueError('Restriccion superior cambio')
        level=doc.GetElement(top_level)
        if not isinstance(level,DB.Level) or offset.IsReadOnly:raise ValueError('Restriccion superior no compatible')
        wb=wall.get_BoundingBox(None);floors=[];beams=[]
        for source in row['source_elements']:
            e=doc.GetElement(DB.ElementId(System.Int64(source['id'])));b=e.get_BoundingBox(None) if e else None
            if b is None or min(wb.Max.X,b.Max.X)<=max(wb.Min.X,b.Min.X) or min(wb.Max.Y,b.Max.Y)<=max(wb.Min.Y,b.Min.Y):raise ValueError('Estructura sin cruce XY')
            if source['kind']=='floor' and isinstance(e,DB.Floor):
                top_faces=[e.GetGeometryObjectFromReference(r) for r in DB.HostObjectUtils.GetTopFaces(e)]
                if not top_faces or any(not isinstance(f,DB.PlanarFace) or abs(f.FaceNormal.Z-1)>1e-8 for f in top_faces):raise ValueError('Losa inclinada excluida')
                floors.append(b.Max.Z*.3048-e.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM).AsDouble()*.3048)
            elif source['kind']=='beam' and e.Category.Id==DB.ElementId(DB.BuiltInCategory.OST_StructuralFraming):beams.append(horizontal_beam_bottom(e,DB))
            else:raise ValueError('Fuente incompatible')
        target=select_top(floors,beams)
        if abs(target-row['top_m'])>1e-6 or target<=wb.Min.Z*.3048+.1 or target>wb.Max.Z*.3048+1e-6:raise ValueError('Cota no implica una bajada o conservacion valida')
        plans.append((wall,(target-level.ProjectElevation*.3048)/.3048,row))
    receipt={'action':action,'planned':len(plans),'rows':rows,'removed_element_ids':[]}
    if action=='inspect':return receipt
    if action=='apply' and os.path.exists(P['receipt_path']):raise ValueError('Recibo existente: inspeccionar antes de repetir')
    options=DB.Options();options.DetailLevel=DB.ViewDetailLevel.Fine
    tol=1e-8 # cubic metres, physical Boolean volume; topology alone is not shape.
    def solids(e):
        def walk(gs):
            for g in gs:
                if isinstance(g,DB.Solid) and g.Volume>1e-9:yield g
                elif isinstance(g,DB.GeometryInstance):
                    for s in walk(g.GetInstanceGeometry()):yield s
        geo=e.get_Geometry(options)
        return list(walk(geo)) if geo else []
    def shape(ss):
        records=[]
        for s in ss:
            vertices=sorted(set(tuple(round(float(v),7) for v in [p.X,p.Y,p.Z]) for edge in s.Edges for p in edge.Tessellate()))
            records.append({'volume':round(s.Volume,7),'vertices':vertices,'areas':sorted(round(f.Area,7) for f in s.Faces)})
        return hashlib.sha256(json.dumps(sorted(records,key=lambda v:json.dumps(v,sort_keys=True)),sort_keys=True).encode('utf8')).hexdigest()
    def bounds(ss):
        points=[]
        for s in ss:
            b=s.GetBoundingBox()
            points.extend(b.Transform.OfPoint(DB.XYZ(x,y,z)) for x in (b.Min.X,b.Max.X) for y in (b.Min.Y,b.Max.Y) for z in (b.Min.Z,b.Max.Z))
        return [[min(getattr(p,c) for p in points) for c in ['X','Y','Z']],[max(getattr(p,c) for p in points) for c in ['X','Y','Z']]] if points else None
    bounds_cache={}
    def cached_bounds(ss):
        key=id(ss)
        if key not in bounds_cache:bounds_cache[key]=(ss,bounds(ss))
        return bounds_cache[key][1]
    def intersect(a,b):
        ab=cached_bounds(a);bb=cached_bounds(b)
        if not ab or not bb or any(min(ab[1][k],bb[1][k])-max(ab[0][k],bb[0][k])<=1e-8 for k in range(3)):return 0.
        volume=0.
        for x in a:
            for y in b:
                s=DB.BooleanOperationsUtils.ExecuteBooleanOperation(x,y,DB.BooleanOperationsType.Intersect)
                try:volume+=s.Volume*.3048**3
                finally:s.Dispose()
        return volume
    def difference_volume(a,b):
        volume=0.
        for source in a:
            s=DB.SolidUtils.Clone(source)
            try:
                for cutter in b:
                    if s.Volume<1e-9:break
                    result=DB.BooleanOperationsUtils.ExecuteBooleanOperation(s,cutter,DB.BooleanOperationsType.Difference)
                    s.Dispose();s=result
                volume+=s.Volume*.3048**3
            finally:s.Dispose()
        return volume
    def delta(a,b):return difference_volume(a,b)+difference_volume(b,a)
    def parameters(e,omit_ifc=False,editable_only=True,omit_ids=None):
        out={}
        for p in e.Parameters:
            if (editable_only and p.IsReadOnly) or (omit_ifc and p.Definition.Name=='IfcGUID') or int(p.Id.Value) in (omit_ids or set()):continue
            st=str(p.StorageType)
            out[str(p.Id.Value)]=[st,p.AsDouble() if st=='Double' else p.AsInteger() if st=='Integer' else int(p.AsElementId().Value) if st=='ElementId' else p.AsString() if st=='String' else None]
        return out
    def get(i):return doc.GetElement(DB.ElementId(System.Int64(i)))
    def is_column(e):return e.Category.Id==DB.ElementId(DB.BuiltInCategory.OST_StructuralColumns)
    protected=[]
    for category in [DB.BuiltInCategory.OST_StructuralFraming,DB.BuiltInCategory.OST_Floors,DB.BuiltInCategory.OST_StructuralColumns,DB.BuiltInCategory.OST_GenericModel,DB.BuiltInCategory.OST_Rebar,DB.BuiltInCategory.OST_Walls]:
        protected.extend(list(DB.FilteredElementCollector(doc).OfCategory(category).WhereElementIsNotElementType()))
    def clone(s):
        result=DB.SolidUtils.Clone(s);owned.append(result);return result
    before={int(e.Id.Value):[clone(s) for s in solids(e)] for e in protected}
    fingerprints={i:shape(ss) for i,ss in before.items()}
    editable_before={int(e.Id.Value):parameters(e) for e in protected if not isinstance(e,DB.Wall)}
    wall_parameter_exceptions=set(int(x) for x in [DB.BuiltInParameter.WALL_TOP_OFFSET,DB.BuiltInParameter.WALL_TOP_IS_ATTACHED])
    wall_parameters={int(e.Id.Value):parameters(e,omit_ids=wall_parameter_exceptions) for e in protected if isinstance(e,DB.Wall)}
    wall_locations={int(e.Id.Value):[[e.Location.Curve.GetEndPoint(n).X,e.Location.Curve.GetEndPoint(n).Y,e.Location.Curve.GetEndPoint(n).Z] for n in [0,1]] for e in protected if isinstance(e,DB.Wall)}
    original_ids=set(int(i.Value) for i in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElementIds())
    model_annotation_ids=set(int(e.Id.Value) for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType() if e.Category is not None)
    internal_candidates=set(i for i in original_ids-model_annotation_ids if get(i).GetType().FullName=='Autodesk.Revit.DB.Element' and not get(i).Name and get(i).GetTypeId()==DB.ElementId.InvalidElementId and get(i).OwnerViewId==DB.ElementId.InvalidElementId and get(i).get_BoundingBox(None) is None and all(p.IsReadOnly for p in get(i).Parameters))
    wall_ids=set(r['id'] for r in rows)
    adjacent_columns=set(int(i.Value) for wall,o,r in plans for i in DB.JoinGeometryUtils.GetJoinedElements(doc,wall) if is_column(doc.GetElement(i)))
    duplicates=P.get('duplicate_columns',[])
    removed=set()
    for pair in duplicates:
        keep,remove=get(pair['keep']),get(pair['remove'])
        if keep is None or remove is None or keep.Id==remove.Id or not is_column(keep) or not is_column(remove):raise ValueError('Par duplicado invalido')
        if pair['remove'] in removed or any(p['keep']==pair['remove'] for p in duplicates):raise ValueError('Plan de duplicados encadenado')
        if pair['keep'] not in adjacent_columns or pair['remove'] not in adjacent_columns:raise ValueError('Duplicado ajeno a los encuentros')
        if any(e.Pinned or e.GroupId!=DB.ElementId.InvalidElementId or set(int(i.Value) for i in e.GetDependentElements(None))!={int(e.Id.Value)} for e in [keep,remove]):raise ValueError('Duplicado con dependencias o fijado')
        if keep.GetTypeId()!=remove.GetTypeId() or not close_values(parameters(keep,True,False),parameters(remove,True,False)) or delta(before[pair['keep']],before[pair['remove']])>tol:raise ValueError('Columnas distintas')
        if set(int(i.Value) for i in DB.JoinGeometryUtils.GetJoinedElements(doc,keep))!=set(int(i.Value) for i in DB.JoinGeometryUtils.GetJoinedElements(doc,remove)):raise ValueError('Uniones distintas en duplicados')
        for e in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
            if hasattr(e,'GetHostId') and e.GetHostId()==remove.Id:raise ValueError('Duplicado hospeda elementos')
            if isinstance(e,DB.IndependentTag) and remove.Id in list(e.GetTaggedLocalElementIds()):raise ValueError('Duplicado etiquetado')
        removed.add(pair['remove'])
    warn=lambda:set((w.GetDescriptionText(),tuple(sorted(int(i.Value) for i in w.GetFailingElements()))) for w in doc.GetWarnings())
    beam_wall_joins=P.get('beam_wall_joins',[])
    if len(beam_wall_joins)>200 or len(set(map(tuple,beam_wall_joins)))!=len(beam_wall_joins):raise ValueError('Plan viga-muro excesivo o duplicado')
    for wi,bi in beam_wall_joins:
        if wi not in wall_ids or bi not in before or get(bi).Category.Id!=DB.ElementId(DB.BuiltInCategory.OST_StructuralFraming):raise ValueError('Par viga-muro fuera del alcance')
        if DB.JoinGeometryUtils.AreElementsJoined(doc,get(wi),get(bi)) or intersect(before[wi],before[bi])<=tol:raise ValueError('Par debe tener solape real sin union previa')
    warnings_before=warn()
    failures=[]
    class Reject(DB.IFailuresPreprocessor):
        def PreprocessFailures(self,accessor):
            messages=list(accessor.GetFailureMessages());failures.extend(m.GetDescriptionText() for m in messages)
            return DB.FailureProcessingResult.ProceedWithRollBack if messages else DB.FailureProcessingResult.Continue
    transactions=[]
    def transaction(name):
        t=DB.Transaction(doc,name)
        try:
            if t.Start()!=DB.TransactionStatus.Started:raise ValueError('Transaccion no iniciada')
            t.SetFailureHandlingOptions(t.GetFailureHandlingOptions().SetFailuresPreprocessor(Reject()).SetClearAfterRollback(True))
            transactions.append(t);return t
        except:
            if t.GetStatus()==DB.TransactionStatus.Started:t.RollBack()
            t.Dispose();raise
    path=P['receipt_path'] if action=='apply' else P['receipt_path']+'.'+action+'.json'
    receipt['status']='started'
    with io.open(path,'w',encoding='utf8') as stream:stream.write(text_type(json.dumps(receipt,indent=2)))
    group=DB.TransactionGroup(doc,'CDX: coronacion bajo estructura');tx=None
    try:
        if group.Start()!=DB.TransactionStatus.Started:raise ValueError('Grupo no iniciado')
        tx=transaction('CDX: bajar muros sin tocar vigas ni losas')
        for pair in duplicates:
            deleted=set(int(i.Value) for i in doc.Delete(get(pair['remove']).Id))
            if deleted!={pair['remove']}:raise ValueError('Borrado afecta otras dependencias')
        for wall,offset,row in plans:
            for target_id in list(wall.GetAttachmentIds(DB.AttachmentLocation.Top)):wall.RemoveAttachment(target_id,DB.AttachmentLocation.Top)
            if not wall.get_Parameter(DB.BuiltInParameter.WALL_TOP_OFFSET).Set(offset):raise ValueError('Offset no actualizado')
        for wi,bi in beam_wall_joins:
            wall,beam=get(wi),get(bi)
            DB.JoinGeometryUtils.JoinGeometry(doc,beam,wall)
            if not DB.JoinGeometryUtils.IsCuttingElementInJoin(doc,beam,wall):DB.JoinGeometryUtils.SwitchJoinOrder(doc,beam,wall)
        if tx.Commit()!=DB.TransactionStatus.Committed:raise ValueError('Transaccion no confirmada')
        receipt['beam_wall_joins']=beam_wall_joins
        after={i:solids(get(i)) for i in before if i not in removed}
        proposed=[]
        for ci in sorted(adjacent_columns-removed):
            if delta(before[ci],after[ci])<=tol:continue
            for fi in sorted(i for i in before if isinstance(get(i),DB.Floor)):
                if intersect(after[ci],after[fi])-intersect(before[ci],before[fi])>tol:proposed.append([ci,fi])
        receipt['column_floor_joins']=proposed
        if proposed:
            if P.get('allow_column_floor_joins') is not True:raise ValueError('Regeneracion exige uniones columna-losa explicitas')
            tx=transaction('CDX: resolver solapes columna-losa comprobados')
            for ci,fi in proposed:
                col,floor=get(ci),get(fi)
                if DB.JoinGeometryUtils.AreElementsJoined(doc,col,floor):raise ValueError('Union columna-losa previa requiere revision')
                DB.JoinGeometryUtils.JoinGeometry(doc,floor,col)
                if not DB.JoinGeometryUtils.IsCuttingElementInJoin(doc,floor,col):DB.JoinGeometryUtils.SwitchJoinOrder(doc,floor,col)
            if tx.Commit()!=DB.TransactionStatus.Committed:raise ValueError('Uniones no confirmadas')
            after={i:solids(get(i)) for i in before if i not in removed}
        changed=[i for i,ss in after.items() if fingerprints[i]!=shape(ss) and delta(before[i],ss)>tol]
        column_changes=sorted(i for i in changed if i in adjacent_columns)
        receipt['changed_columns']=column_changes
        if column_changes and P.get('allow_column_regeneration') is not True:raise ValueError('Columnas regeneradas fuera de permiso')
        unexpected=set(changed)-wall_ids-set(column_changes)
        receipt['protected_geometry_changed']=sorted(unexpected)
        if unexpected:raise ValueError('Cambio geometrico protegido')
        if any(not close_values(editable_before[i],parameters(get(i))) for i in editable_before if i not in removed):raise ValueError('Parametro protegido cambio')
        if any(not close_values(wall_parameters[i],parameters(get(i),omit_ids=wall_parameter_exceptions)) for i in wall_parameters):raise ValueError('Base u otro parametro de muro cambio')
        if any(not close_values(wall_locations[i],[[get(i).Location.Curve.GetEndPoint(n).X,get(i).Location.Curve.GetEndPoint(n).Y,get(i).Location.Curve.GetEndPoint(n).Z] for n in [0,1]]) for i in wall_locations):raise ValueError('Ubicacion de muro cambio')
        receipt['new_overlaps']=[];checked=set()
        for i in changed:
            for j in after:
                key=tuple(sorted([i,j]))
                if i==j or key in checked:continue
                checked.add(key)
                a=intersect(before[i],before[j]);b=intersect(after[i],after[j])
                if b-a>tol:receipt['new_overlaps'].append({'ids':key,'before_m3':a,'after_m3':b})
        receipt['checked_intersections']=len(checked)
        if receipt['new_overlaps']:raise ValueError('Solapes nuevos')
        if any(intersect(after[wi],after[bi])>tol or not DB.JoinGeometryUtils.IsCuttingElementInJoin(doc,get(bi),get(wi)) for wi,bi in beam_wall_joins):raise ValueError('Encuentro viga-muro no despejado')
        receipt['new_warnings']=[{'text':s,'ids':ids} for s,ids in warn()-warnings_before]
        receipt['warnings_after']=[{'text':s,'ids':ids} for s,ids in warn()]
        for wall,offset,row in plans:
            if abs(wall.get_Parameter(DB.BuiltInParameter.WALL_TOP_OFFSET).AsDouble()-offset)>1e-7 or list(wall.GetAttachmentIds(DB.AttachmentLocation.Top)):raise ValueError('Restriccion superior no confirmada')
            if wall.get_BoundingBox(None).Max.Z*.3048>row['top_m']+1e-6:raise ValueError('Coronacion no alcanzada')
            if difference_volume(after[row['id']],before[row['id']])>tol:raise ValueError('Muro aumento geometria')
        final_ids=set(int(i.Value) for i in DB.FilteredElementCollector(doc).WhereElementIsNotElementType().ToElementIds())
        if (original_ids-final_ids)&model_annotation_ids!=removed or (final_ids-original_ids):raise ValueError('Altas/bajas inesperadas')
        receipt['removed_element_ids']=sorted(removed)
        receipt['internal_cleanup_ids']=sorted((original_ids-final_ids)-model_annotation_ids)
        if set(receipt['internal_cleanup_ids'])-internal_candidates:raise ValueError('Eliminacion interna no comprobada')
        receipt['physical_changes']=[{'id':i,'before_m3':sum(s.Volume for s in before[i])*.3048**3,'after_m3':sum(s.Volume for s in after[i])*.3048**3,'symdiff_m3':delta(before[i],after[i])} for i in sorted(changed)]
        if receipt['new_warnings']:raise ValueError('Advertencias nuevas')
        if action=='simulate':
            if group.RollBack()!=DB.TransactionStatus.RolledBack:raise ValueError('Rollback no confirmado')
            receipt['status']='simulation_passed_rolled_back'
        else:
            validate_apply_plan(P,proposed,column_changes)
            if set(receipt['internal_cleanup_ids'])!=set(P['expected_internal_cleanup_ids']):raise ValueError('Limpieza interna distinta al ensayo')
            if group.Assimilate()!=DB.TransactionStatus.Committed:raise ValueError('Grupo no confirmado')
            receipt['status']='applied';doc.Save();receipt['saved']=not doc.IsModified
    except Exception as ex:
        receipt['error']=str(ex);receipt['failures']=failures
        receipt['status']='applied_unsaved' if group.GetStatus()==DB.TransactionStatus.Committed else 'rejected_rolled_back'
        try:
            if tx is not None and tx.GetStatus()==DB.TransactionStatus.Started and tx.RollBack()!=DB.TransactionStatus.RolledBack:raise ValueError('Rollback de transaccion no confirmado')
            if group.GetStatus()==DB.TransactionStatus.Started and group.RollBack()!=DB.TransactionStatus.RolledBack:raise ValueError('Rollback de grupo no confirmado')
            if group.GetStatus() not in [DB.TransactionStatus.RolledBack,DB.TransactionStatus.Committed]:receipt['status']='rollback_unverified'
        except Exception as rollback_error:
            receipt['status']='rollback_unverified';receipt['rollback_error']=str(rollback_error)
    finally:
        for t in transactions:t.Dispose()
        group.Dispose()
    with io.open(path,'w',encoding='utf8') as stream:stream.write(text_type(json.dumps(receipt,indent=2)))
    return receipt
