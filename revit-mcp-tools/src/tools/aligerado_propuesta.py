# -*- coding: utf-8 -*-
"""Propuesta geometrica acotada: una losa por llamada, dos instancias agrupadas.

P incluye copia/PID/turno, floor_id, h_m, bounds_m, section (1D/2D), topping_m,
rib_m, pitch_m, border_m, family_template, family_dir y receipt_path.
El umbral de 0.16 m es una regla del procedimiento elegido, no un calculo.
No modifica vigas ni arma losas. Rechaza hosts con Rebar o vacios previos.
Excepcion explicita: operation=supplement completa hasta25rectangulos de la
misma reticula, con expected_void_ids exactos; conserva tipo y cortes previos.
Omite cavidades que no quepan completamente en el solido real (shafts/uniones).
Conserva una familia de vacios y una de EPS por pano: geometria editable en
familia, sin crear una instancia de proyecto por cada bloque.
"""
import io,json,math,os,hashlib
try:
    text_type=unicode
except NameError:
    text_type=str


def section_for_existing_thickness(h_m, direction):
    if direction not in ('1D','2D') or math.isnan(h_m) or math.isinf(h_m) or h_m <= 0:
        raise ValueError('Espesor o direccion invalida')
    if h_m <= .16 + 1e-9:
        return None
    if abs(h_m-.20)<1e-6: return 'L20A-'+direction
    if abs(h_m-.25)<1e-6: return 'L25A-'+direction
    raise ValueError('No hay seccion de catalogo para ese espesor')


def cavity_rectangles(bounds, direction, rib, pitch, border):
    if len(bounds)!=4 or direction not in ('1D','2D'):
        raise ValueError('Contorno o direccion invalida')
    if any(math.isnan(float(v)) or math.isinf(float(v)) for v in list(bounds)+[rib,pitch,border]):
        raise ValueError('Valores no finitos')
    x0,y0,x1,y1=bounds
    if rib<=0 or pitch<=rib or border<rib or min(x1-x0,y1-y0)<=2*border:
        raise ValueError('Modulacion invalida')
    def slots(a,b):
        result=[];start=a+border
        while start < b-border-1e-6:
            end=min(start+pitch-rib,b-border)
            if end-start>0.05:result.append((start,end))
            start+=pitch
            if len(result)>200:raise ValueError('Pano demasiado grande')
        return result
    xs=slots(x0,x1);ys=slots(y0,y1)
    if direction=='1D':
        if x1-x0 <= y1-y0:xs=[(x0+border,x1-border)]
        else:ys=[(y0+border,y1-border)]
    result=[[a,c,b,d] for a,b in xs for c,d in ys]
    if not result or len(result)>400:raise ValueError('Numero de cavidades fuera del limite')
    return result


def new_host_join_ids(previous,current,protected_ids):
    previous=set(previous);current=set(current)
    if not previous.issubset(current):raise ValueError('Se perdio una union previa del host')
    added=current-previous
    if not added.issubset(set(protected_ids)):raise ValueError('Nueva union fuera de vecinos auditados')
    return sorted(added)


def memory_floor_mb(config):
    mode=config.get('memory_mode','normal')
    if mode not in ('normal','bounded'):raise ValueError('Modo de memoria desconocido')
    if mode=='normal':return 1000
    count=len(cavity_rectangles(config['bounds_m'],config['section'],config['rib_m'],config['pitch_m'],config['border_m']))
    return 768 if count<=150 else 1000


def selected_cavity_rectangles(config):
    all_rectangles=cavity_rectangles(config['bounds_m'],config['section'],config['rib_m'],config['pitch_m'],config['border_m'])
    operation=config.get('operation','new')
    if operation=='new':
        if config.get('supplement_rectangles_m') or config.get('expected_void_ids'):
            raise ValueError('Complemento exige operation=supplement')
        return all_rectangles
    if operation!='supplement':raise ValueError('Operacion desconocida')
    requested=config.get('supplement_rectangles_m') or []
    expected=config.get('expected_void_ids') or []
    if not 1<=len(requested)<=25 or not 1<=len(expected)<=10 or len(set(expected))!=len(expected) or any(not isinstance(i,int) or isinstance(i,bool) or i<=0 for i in expected):
        raise ValueError('Complemento exige rectangulos y vacios previos explicitos')
    used=set();result=[]
    for rect in requested:
        if len(rect)!=4 or any(not _finite_rectangle_number(v) for v in rect):raise ValueError('Rectangulo invalido')
        matches=[i for i,r in enumerate(all_rectangles) if all(abs(a-b)<1e-7 for a,b in zip(r,rect))]
        if len(matches)!=1 or matches[0] in used:raise ValueError('Rectangulo duplicado o fuera de la reticula declarada')
        used.add(matches[0]);result.append(all_rectangles[matches[0]])
    return result


def _finite_rectangle_number(value):
    return not math.isnan(float(value)) and not math.isinf(float(value))


def run(doc, uidoc, DB, P):
    owned=[]
    try:return _run(doc,uidoc,DB,P,owned)
    finally:
        for solid in owned:solid.Dispose()


def _run(doc, uidoc, DB, P, owned):
    import clr,System
    from System.Collections.Generic import List
    clr.AddReference('Microsoft.VisualBasic')
    from Microsoft.VisualBasic.Devices import ComputerInfo
    norm=lambda p:os.path.normcase(os.path.realpath(p))
    protected=P.get('protected_paths') or []
    if not protected or norm(doc.PathName)!=norm(P['expected_path']) or norm(doc.PathName) in [norm(p) for p in protected]:
        raise ValueError('Documento no autorizado')
    if int(System.Diagnostics.Process.GetCurrentProcess().Id)!=P['expected_pid']:
        raise ValueError('PID diferente')
    with io.open(P['lock_path'],encoding='utf-8-sig') as stream:
        lock=json.load(stream)
    if lock.get('state')!='active' or lock.get('process_id')!=P['expected_pid'] or not all(P.get('lock_identity',{}).get(k) and P['lock_identity'][k]==lock.get(k) for k in ['owner','session','task']):
        raise ValueError('Turno diferente')
    if P.get('geometry_reference_authorized') is not True or doc.IsModifiable or doc.IsReadOnly or doc.IsWorkshared:
        raise ValueError('Se requiere propuesta autorizada y documento editable')
    memory_floor=memory_floor_mb(P)
    if int(ComputerInfo().AvailablePhysicalMemory/1048576)<memory_floor:
        raise ValueError('RAM libre <%s MB; inspeccion geometrica no iniciada' % memory_floor)
    if os.path.exists(P['receipt_path']):raise ValueError('Ya hay recibo: inspeccionar, no repetir')
    rectangles=selected_cavity_rectangles(P)
    supplement=P.get('operation')=='supplement'
    host=doc.GetElement(DB.ElementId(System.Int64(P['floor_id'])))
    if not isinstance(host,DB.Floor):raise ValueError('Host no es Floor')
    if DB.PartUtils.HasAssociatedParts(doc,host.Id):raise ValueError('Host con Parts: requiere auditoria de sus armados')
    old_voids=set(int(i.Value) for i in DB.InstanceVoidCutUtils.GetCuttingVoidInstances(host))
    if old_voids!=set(P.get('expected_void_ids',[])):
        raise ValueError('Cortes de familia distintos del estado esperado')
    host_data=DB.Structure.RebarHostData.GetRebarHostData(host)
    reinforcement_methods=['GetRebarsInHost','GetAreaReinforcementsInHost','GetPathReinforcementsInHost',
                           'GetFabricAreasInHost','GetFabricSheetsInHost','GetRebarContainersInHost']
    if host_data is not None and any(list(getattr(host_data,method)()) for method in reinforcement_methods):
        raise ValueError('Host con acero existente: requiere adaptar armado antes de retirar hormigon')
    # Some Floors return null HostData. Audit every reinforcement class
    # independently; null is not treated as evidence of no reinforcement.
    reinforcement_classes=[DB.Structure.Rebar,DB.Structure.RebarInSystem,DB.Structure.AreaReinforcement,
        DB.Structure.PathReinforcement,DB.Structure.FabricArea,DB.Structure.FabricSheet,DB.Structure.RebarContainer]
    reinforcement_audit={}
    for cls in reinforcement_classes:
        count=0
        for element in DB.FilteredElementCollector(doc).OfClass(cls):
            count+=1
            host_id=element.GetHostId() if hasattr(element,'GetHostId') else element.HostId
            if host_id==host.Id:raise ValueError('Host con acero o malla existente')
        reinforcement_audit[str(cls)]=count
    hp=host.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)
    h=hp.AsDouble()*.3048
    structural_before=host.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL).AsInteger()
    if abs(h-P['h_m'])>1e-6:raise ValueError('Espesor cambio')
    section=section_for_existing_thickness(h,P['section'])
    if section is None:raise ValueError('No supera umbral 0.16 m')
    if abs(P['topping_m']-.05)>1e-6 or abs(P['pitch_m']-.65)>1e-6 or abs(P['rib_m']-(.15 if h<.21 else .20))>1e-6:
        raise ValueError('Modulacion fuera del catalogo declarado')
    loops=list(doc.GetElement(host.SketchId).Profile)
    if len(loops)!=1 or len(list(loops[0]))!=4 or any(not isinstance(c,DB.Line) for c in loops[0]):
        raise ValueError('Solo perfil rectangular de cuatro lineas')
    points=[c.GetEndPoint(0) for c in loops[0]]
    if any(abs(c.GetEndPoint(1).X-c.GetEndPoint(0).X)>1e-6 and abs(c.GetEndPoint(1).Y-c.GetEndPoint(0).Y)>1e-6 for c in loops[0]):
        raise ValueError('Perfil girado: transformar explicitamente primero')
    b=[min(p.X for p in points)*.3048,min(p.Y for p in points)*.3048,max(p.X for p in points)*.3048,max(p.Y for p in points)*.3048]
    if any(abs(x-y)>1e-6 for x,y in zip(b,P['bounds_m'])):raise ValueError('Contorno cambio')
    editor=host.GetSlabShapeEditor()
    if editor is None or editor.IsEnabled:raise ValueError('Floor con edicion de forma o estado desconocido: no admitido')
    faces=[host.GetGeometryObjectFromReference(r) for r in DB.HostObjectUtils.GetTopFaces(host)]
    if not faces or any(not isinstance(f,DB.PlanarFace) or abs(f.FaceNormal.Z-1)>1e-9 for f in faces):
        raise ValueError('Cara superior no horizontal')
    top=faces[0].Origin.Z
    if any(abs(f.Origin.Z-top)>1e-7 for f in faces):raise ValueError('Caras superiores no coplanares')
    bottom=[host.GetGeometryObjectFromReference(r) for r in DB.HostObjectUtils.GetBottomFaces(host)]
    bottom_levels=[top-h/.3048]+([top-P['topping_m']/.3048] if supplement else [])
    if not bottom or any(not isinstance(f,DB.PlanarFace) or abs(f.FaceNormal.Z+1)>1e-9 or min(abs(f.Origin.Z-z_) for z_ in bottom_levels)>1e-7 for f in bottom):
        raise ValueError('Cara inferior no confirma espesor uniforme')
    z=top-h/.3048;depth=(h-P['topping_m'])/.3048
    warnings_before=set((w.GetDescriptionText(),tuple(sorted(int(i.Value) for i in w.GetFailingElements()))) for w in doc.GetWarnings())
    options=DB.Options();options.DetailLevel=DB.ViewDetailLevel.Fine
    def solids(geo):
        for g in geo:
            if isinstance(g,DB.Solid) and g.Volume>1e-9:yield g
            elif isinstance(g,DB.GeometryInstance):
                for s in solids(g.GetInstanceGeometry()):yield s
    host_solids=list(solids(host.get_Geometry(options)))
    if not host_solids:raise ValueError('Sin solido nativo')
    def element_solids(e):
        geo=e.get_Geometry(options)
        return list(solids(geo)) if geo else []
    def fingerprint(ss):
        rows=[]
        for s in ss:
            pts=sorted(set(tuple(round(float(v),7) for v in (p.X,p.Y,p.Z)) for edge in s.Edges for p in edge.Tessellate()))
            rows.append([round(s.Volume,7),pts,sorted(round(f.Area,7) for f in s.Faces)])
        return hashlib.sha256(json.dumps(sorted(rows),sort_keys=True).encode('utf8')).hexdigest()
    def overlaps(a,b_):
        return a and b_ and all(min(getattr(a.Max,c),getattr(b_.Max,c))-max(getattr(a.Min,c),getattr(b_.Min,c))>1e-8 for c in ('X','Y','Z'))
    # Clone only adjacent structure. Family documents are closed sequentially and
    # the clones are disposed by run(), including on rejection/rollback.
    protected=[];neighbors=[];host_box=host.get_BoundingBox(None)
    joined=set(int(i.Value) for i in DB.JoinGeometryUtils.GetJoinedElements(doc,host))
    join_order_before={i:bool(DB.JoinGeometryUtils.IsCuttingElementInJoin(doc,host,doc.GetElement(DB.ElementId(System.Int64(i))))) for i in joined}
    for bic in (DB.BuiltInCategory.OST_Floors,DB.BuiltInCategory.OST_StructuralFraming,
                DB.BuiltInCategory.OST_StructuralColumns,DB.BuiltInCategory.OST_Walls,
                DB.BuiltInCategory.OST_StructuralFoundation,DB.BuiltInCategory.OST_GenericModel,
                DB.BuiltInCategory.OST_Rebar):
        for e in DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
            if e.Id==host.Id:continue
            eb=e.get_BoundingBox(None)
            contact=host_box and eb and all(min(getattr(host_box.Max,c),getattr(eb.Max,c))-max(getattr(host_box.Min,c),getattr(eb.Min,c))>=-1e-7 for c in ('X','Y','Z'))
            if not contact and int(e.Id.Value) not in joined:continue
            neighbors.append(e)
    if memory_floor<1000 and len(neighbors)>40:
        raise ValueError('Modo acotado admite hasta 40 vecinos; usar modo normal')
    for e in neighbors:
        ss=[]
        for s in element_solids(e):
            clone=DB.SolidUtils.CreateTransformed(s,DB.Transform.Identity)
            owned.append(clone);ss.append(clone)
        protected.append((int(e.Id.Value),ss,fingerprint(ss)))
    def loop(rect, local=False):
        a,c,b_,d=rect;ox=b[0] if local else 0;oy=b[1] if local else 0
        pts=[DB.XYZ((x-ox)/.3048,(y-oy)/.3048,0 if local else z) for x,y in [(a,c),(b_,c),(b_,d),(a,d)]]
        lines=[DB.Line.CreateBound(pts[i],pts[(i+1)%4]) for i in range(4)]
        cl=DB.CurveLoop()
        for line in lines:cl.Append(line)
        return cl
    nearby=[]
    # Only solids whose bounds can overlap this slab; detect foreign physical overlaps.
    for bic in [DB.BuiltInCategory.OST_StructuralFraming,DB.BuiltInCategory.OST_StructuralColumns,DB.BuiltInCategory.OST_Walls]:
        for e in DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
            eb=e.get_BoundingBox(None)
            if eb and eb.Max.Z>z and eb.Min.Z<z+depth and eb.Max.X>b[0]/.3048 and eb.Min.X<b[2]/.3048 and eb.Max.Y>b[1]/.3048 and eb.Min.Y<b[3]/.3048:
                nearby.append((eb,list(solids(e.get_Geometry(options)))))
    accepted=[];excluded=[]
    def intersect_volume(a,b_):
        intersection=DB.BooleanOperationsUtils.ExecuteBooleanOperation(a,b_,DB.BooleanOperationsType.Intersect)
        try:return intersection.Volume
        finally:intersection.Dispose()
    for rect in rectangles:
        cube=DB.GeometryCreationUtilities.CreateExtrusionGeometry(List[DB.CurveLoop]([loop(rect)]),DB.XYZ.BasisZ,depth)
        try:
            volume=cube.Volume
            intersection=sum(intersect_volume(s,cube) for s in host_solids)
            reason=None
            if abs(intersection-volume)>max(1e-7,volume*1e-6):reason='hueco_o_borde_fuera_del_host'
            if reason is None:
                for eb,ss in nearby:
                    if eb.Max.X<=rect[0]/.3048 or eb.Min.X>=rect[2]/.3048 or eb.Max.Y<=rect[1]/.3048 or eb.Min.Y>=rect[3]/.3048:continue
                    if any(intersect_volume(s,cube)>1e-7 for s in ss):
                        reason='interferencia_con_elemento_existente';break
            (excluded if reason else accepted).append({'rect':rect,'reason':reason} if reason else rect)
        finally:cube.Dispose()
    if not accepted:raise ValueError('Ninguna cavidad segura')
    if supplement and excluded:raise ValueError('Complemento incompleto: alguna celda no es segura')
    before=host.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED).AsDouble()
    removed=sum((r[2]-r[0])*(r[3]-r[1])*(h-P['topping_m'])/.3048**3 for r in accepted)
    receipt={'host_id':P['floor_id'],'mark':host.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString(),'section':section,
        'cavities':len(accepted),'excluded':excluded,'before_m3':before*.3048**3,'expected_after_m3':(before-removed)*.3048**3,'status':'inspected',
        'geometry_reference_only':True,'rebar_created':False,'project_instances_per_floor':2}
    receipt['reinforcement_audit']=reinforcement_audit
    receipt['memory_floor_mb']=memory_floor
    receipt['operation']='supplement' if supplement else 'new'
    receipt['previous_void_ids']=sorted(old_voids)
    def write():
        with io.open(P['receipt_path'],'w',encoding='utf8') as f:f.write(text_type(json.dumps(receipt,indent=2)))
    if P.get('inspect_only',True):return receipt
    if int(ComputerInfo().AvailablePhysicalMemory/1048576)<memory_floor:
        raise ValueError('RAM libre <%s MB; lote no iniciado' % memory_floor)
    receipt['status']='started';write()
    failures=[]
    class Reject(DB.IFailuresPreprocessor):
        def PreprocessFailures(self,accessor):
            messages=list(accessor.GetFailureMessages());failures.extend(m.GetDescriptionText() for m in messages)
            return DB.FailureProcessingResult.ProceedWithRollBack if messages else DB.FailureProcessingResult.Continue
    files=[];tx=None;group=None
    try:
        # Close each temporary family immediately. No multiple family documents held.
        for solid in [False,True]:
            name='CDX_ALIG_%s_%s' % (P['floor_id'],'EPS' if solid else 'VOID')
            if supplement:name+='_SUP_'+hashlib.sha256(json.dumps(rectangles).encode('utf8')).hexdigest()[:12]
            path=os.path.join(P['family_dir'],name+'.rfa')
            if os.path.exists(path):raise ValueError('Familia ya existe: inspeccionar antes de reintentar')
            fd=doc.Application.NewFamilyDocument(P['family_template']);ft=None
            try:
                ft=DB.Transaction(fd,'CDX: paquete geometrico');ft.Start()
                ft.SetFailureHandlingOptions(ft.GetFailureHandlingOptions().SetFailuresPreprocessor(Reject()).SetClearAfterRollback(True))
                fd.FamilyManager.NewType('PROPUESTA_'+section)
                autojoin=fd.OwnerFamily.get_Parameter(DB.BuiltInParameter.FAMILY_AUTOJOIN)
                if autojoin is None or autojoin.IsReadOnly:raise ValueError('Plantilla no permite desactivar union automatica')
                autojoin.Set(0)
                if not solid:fd.OwnerFamily.get_Parameter(DB.BuiltInParameter.FAMILY_ALLOW_CUT_WITH_VOIDS).Set(1)
                sp=DB.SketchPlane.Create(fd,DB.Plane.CreateByNormalAndOrigin(DB.XYZ.BasisZ,DB.XYZ.Zero))
                profile=DB.CurveArrArray()
                for rect in accepted:
                    arr=DB.CurveArray()
                    for c in loop(rect,True):arr.Append(c)
                    profile.Append(arr)
                ex=fd.FamilyCreate.NewExtrusion(solid,profile,sp,depth)
                if not solid:ex.get_Parameter(DB.BuiltInParameter.EXTRUSION_START_PARAM).Set(-.001/.3048)
                if solid:
                    material=fd.GetElement(DB.Material.Create(fd,'EPS geometrico - densidad sin validar'));material.Color=DB.Color(220,225,230)
                    ex.get_Parameter(DB.BuiltInParameter.MATERIAL_ID_PARAM).Set(material.Id)
                if ft.Commit()!=DB.TransactionStatus.Committed:raise ValueError('Familia no confirmada')
                save=DB.SaveAsOptions();save.OverwriteExistingFile=False;fd.SaveAs(path,save);files.append((name,path))
            finally:
                cleanup_errors=[]
                try:
                    if ft is not None and ft.GetStatus()==DB.TransactionStatus.Started and ft.RollBack()!=DB.TransactionStatus.RolledBack:
                        cleanup_errors.append('Rollback de familia no confirmado')
                except Exception as cleanup_error:cleanup_errors.append(str(cleanup_error))
                try:
                    if ft is not None:ft.Dispose()
                except Exception as cleanup_error:cleanup_errors.append(str(cleanup_error))
                try:
                    if not fd.Close(False):cleanup_errors.append('Familia no cerrada')
                except Exception as cleanup_error:cleanup_errors.append(str(cleanup_error))
                if cleanup_errors:
                    receipt['family_cleanup_errors']=cleanup_errors
                    raise ValueError('Estado de familia no confirmado: '+'; '.join(cleanup_errors))
        group=DB.TransactionGroup(doc,'CDX: propuesta aligerada acotada');group.Start()
        tx=DB.Transaction(doc,'CDX: familias y corte de un solo host');tx.Start()
        tx.SetFailureHandlingOptions(tx.GetFailureHandlingOptions().SetFailuresPreprocessor(Reject()).SetClearAfterRollback(True))
        instances=[]
        for name,path in files:
            ref=clr.Reference[DB.Family]()
            if not doc.LoadFamily(path,ref):raise ValueError('No se cargo familia')
            symbol=doc.GetElement(list(ref.Value.GetFamilySymbolIds())[0]);symbol.Activate();doc.Regenerate()
            instance=doc.Create.NewFamilyInstance(DB.XYZ(b[0]/.3048,b[1]/.3048,z),symbol,DB.Structure.StructuralType.NonStructural)
            instance.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).Set('CDX:ALIGERADO:PROPUESTA;host=%s;cavidades=%s' % (P['floor_id'],len(accepted)))
            instances.append(instance)
        DB.InstanceVoidCutUtils.AddInstanceVoidCut(doc,host,instances[0])
        original_type_id=host.GetTypeId()
        if not supplement:
            type_name=section+' H=%.2f PROPUESTA host%s' % (h,P['floor_id'])
            floor_type=next((t for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType) if t.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()==type_name),None)
            if floor_type is not None:raise ValueError('Tipo de propuesta ya existe: inspeccionar antes de reutilizar')
            floor_type=doc.GetElement(host.GetTypeId()).Duplicate(type_name)
            host.ChangeTypeId(floor_type.Id)
        receipt['new_families_autojoin_disabled']=True
        cp=host.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        cp.Set((cp.AsString() or '')+(' | CDX COMPLEMENTO %s CELDAS; ARMADO Y PESO POR REVALIDAR' % len(accepted) if supplement else ' | CDX PROPUESTA ALIGERADA >16cm; topping5cm; ARMADO Y PESO POR REVALIDAR'))
        if tx.Commit()!=DB.TransactionStatus.Committed:raise ValueError('Corte no confirmado')
        # Structural floors can auto-join framing/columns during commit. Restore
        # only the newly introduced relations; never remove a pre-existing join.
        added_joins=new_host_join_ids(joined,[int(i.Value) for i in DB.JoinGeometryUtils.GetJoinedElements(doc,host)],
            [i for i,ss,fp in protected])
        receipt['restored_new_host_joins']=added_joins
        if added_joins:
            tx.Dispose();tx=DB.Transaction(doc,'CDX: restaurar relaciones previas del host');tx.Start()
            tx.SetFailureHandlingOptions(tx.GetFailureHandlingOptions().SetFailuresPreprocessor(Reject()).SetClearAfterRollback(True))
            for i in added_joins:DB.JoinGeometryUtils.UnjoinGeometry(doc,host,doc.GetElement(DB.ElementId(System.Int64(i))))
            if tx.Commit()!=DB.TransactionStatus.Committed:raise ValueError('Restauracion de uniones no confirmada')
        if set(int(i.Value) for i in DB.JoinGeometryUtils.GetJoinedElements(doc,host))!=joined:
            raise ValueError('Relaciones del host distintas a las previas')
        if any(bool(DB.JoinGeometryUtils.IsCuttingElementInJoin(doc,host,doc.GetElement(DB.ElementId(System.Int64(i)))))!=cutting for i,cutting in join_order_before.items()):
            raise ValueError('Orden de union previa modificado')
        after=host.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED).AsDouble()
        if abs(after-(before-removed))>max(1e-6,removed*1e-6):raise ValueError('Volumen nativo distinto del esperado')
        if not DB.InstanceVoidCutUtils.InstanceVoidCutExists(host,instances[0]):raise ValueError('Corte ausente')
        if set(int(i.Value) for i in DB.InstanceVoidCutUtils.GetCuttingVoidInstances(host))!=old_voids|{int(instances[0].Id.Value)}:
            raise ValueError('Cortes previos modificados')
        if supplement and host.GetTypeId()!=original_type_id:raise ValueError('Tipo de losa cambiado por complemento')
        receipt['cut_host_ids']=sorted(int(i.Value) for i in DB.InstanceVoidCutUtils.GetElementsBeingCut(instances[0]))
        if receipt['cut_host_ids']!=[P['floor_id']]:raise ValueError('El vacio corta un elemento ajeno')
        if host.get_Parameter(DB.BuiltInParameter.FLOOR_PARAM_IS_STRUCTURAL).AsInteger()!=structural_before:
            raise ValueError('Clasificacion estructural modificada')
        receipt['structural_flag']=structural_before
        receipt['protected_neighbors']=[i for i,ss,fp in protected]
        receipt['protected_geometry_changed']=[]
        receipt['protected_geometry_deltas']=[]
        for i,old,fp in protected:
            e=doc.GetElement(DB.ElementId(System.Int64(i)))
            if e is None:raise ValueError('Vecino eliminado por regeneracion')
            current=element_solids(e)
            if fingerprint(current)==fp:continue
            common=sum(intersect_volume(a_,b_) for a_ in old for b_ in current)
            delta=sum(s.Volume for s in old)+sum(s.Volume for s in current)-2*common
            joined_now=DB.JoinGeometryUtils.AreElementsJoined(doc,host,e)
            receipt['protected_geometry_deltas'].append({'id':i,'delta_m3':delta*.3048**3,'before_m3':sum(s.Volume for s in old)*.3048**3,'after_m3':sum(s.Volume for s in current)*.3048**3,
                'joined_host':bool(joined_now),'host_cuts_neighbor':bool(DB.JoinGeometryUtils.IsCuttingElementInJoin(doc,host,e)) if joined_now else None,
                'cutting_voids':[int(v.Value) for v in DB.InstanceVoidCutUtils.GetCuttingVoidInstances(e)]})
            if abs(delta)>.00000001/.3048**3:receipt['protected_geometry_changed'].append(i)
        if receipt['protected_geometry_changed']:raise ValueError('Corte cambia geometria protegida; revertido')
        eps=element_solids(instances[1]);eps_box=instances[1].get_BoundingBox(None)
        if abs(sum(s.Volume for s in eps)-removed)>max(1e-6,removed*1e-6):raise ValueError('EPS nativo distinto de las cavidades')
        receipt['eps_structure_collisions']=[]
        for bic in (DB.BuiltInCategory.OST_Walls,DB.BuiltInCategory.OST_StructuralFraming,
                    DB.BuiltInCategory.OST_StructuralColumns,DB.BuiltInCategory.OST_Floors,
                    DB.BuiltInCategory.OST_StructuralFoundation):
            for e in DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                if not overlaps(eps_box,e.get_BoundingBox(None)):continue
                volume=sum(intersect_volume(a_,b_) for a_ in eps for b_ in element_solids(e))*.3048**3
                if volume>1e-8:receipt['eps_structure_collisions'].append({'id':int(e.Id.Value),'m3':volume})
        if receipt['eps_structure_collisions']:raise ValueError('EPS invade estructura; revertido')
        warnings_after=set((w.GetDescriptionText(),tuple(sorted(int(i.Value) for i in w.GetFailingElements()))) for w in doc.GetWarnings())
        if warnings_after-warnings_before:raise ValueError('Nuevas advertencias; lote revertido')
        receipt['family_paths']=[p for n,p in files]
        if P.get('simulate_only') is True:
            if group.RollBack()!=DB.TransactionStatus.RolledBack:raise ValueError('Simulacion no revertida')
            receipt.update(status='simulation_passed_rolled_back',after_m3=after*.3048**3);write()
            return receipt
        if group.Assimilate()!=DB.TransactionStatus.Committed:raise ValueError('Grupo no confirmado')
        receipt.update(status='applied',after_m3=after*.3048**3,instance_ids=[int(e.Id.Value) for e in instances],family_paths=[p for n,p in files])
        write()
        doc.Save();receipt['saved']=not doc.IsModified;write()
        return receipt
    except Exception as exc:
        rollback_errors=[]
        for item in (tx,group):
            try:
                if item is not None and item.GetStatus()==DB.TransactionStatus.Started and item.RollBack()!=DB.TransactionStatus.RolledBack:
                    rollback_errors.append('Estado de rollback no confirmado')
            except Exception as rollback_error:rollback_errors.append(str(rollback_error))
        status='rollback_unverified' if rollback_errors or receipt.get('family_cleanup_errors') else 'applied_unsaved' if receipt.get('status')=='applied' else 'error_inspect_before_retry'
        receipt.update(status=status,error=str(exc),failures=failures,rollback_errors=rollback_errors);write();raise
    finally:
        if tx is not None:tx.Dispose()
        if group is not None:group.Dispose()
