# -*- coding: utf-8 -*-
"""Propuesta geometrica acotada: una losa por llamada, dos instancias agrupadas.

P incluye copia/PID/turno, floor_id, h_m, bounds_m, section (1D/2D), topping_m,
rib_m, pitch_m, border_m, family_template, family_dir y receipt_path.
El umbral de 0.16 m es una regla del procedimiento elegido, no un calculo.
No modifica vigas ni arma losas. Rechaza hosts con Rebar o vacios previos.
Omite cavidades que no quepan completamente en el solido real (shafts/uniones).
Conserva una familia de vacios y una de EPS por pano: geometria editable en
familia, sin crear una instancia de proyecto por cada bloque.
"""
import io,json,math,os
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


def run(doc, uidoc, DB, P):
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
    if lock.get('state')!='active' or not all(P.get('lock_identity',{}).get(k) and P['lock_identity'][k]==lock.get(k) for k in ['owner','session','task']):
        raise ValueError('Turno diferente')
    if P.get('geometry_reference_authorized') is not True or doc.IsModifiable or doc.IsReadOnly:
        raise ValueError('Se requiere propuesta autorizada y documento editable')
    if int(ComputerInfo().AvailablePhysicalMemory/1048576)<1000:
        raise ValueError('RAM libre <1000 MB; inspeccion geometrica no iniciada')
    if os.path.exists(P['receipt_path']):raise ValueError('Ya hay recibo: inspeccionar, no repetir')
    host=doc.GetElement(DB.ElementId(System.Int64(P['floor_id'])))
    if not isinstance(host,DB.Floor):raise ValueError('Host no es Floor')
    if DB.PartUtils.HasAssociatedParts(doc,host.Id):raise ValueError('Host con Parts: requiere auditoria de sus armados')
    if list(DB.InstanceVoidCutUtils.GetCuttingVoidInstances(host)):
        raise ValueError('Host ya aligerado o con corte de familia')
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
    if not bottom or any(not isinstance(f,DB.PlanarFace) or abs(f.FaceNormal.Z+1)>1e-9 or abs(f.Origin.Z-(top-h/.3048))>1e-7 for f in bottom):
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
    for rect in cavity_rectangles(b,P['section'],P['rib_m'],P['pitch_m'],P['border_m']):
        cube=DB.GeometryCreationUtilities.CreateExtrusionGeometry(List[DB.CurveLoop]([loop(rect)]),DB.XYZ.BasisZ,depth)
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
        cube.Dispose()
    if not accepted:raise ValueError('Ninguna cavidad segura')
    before=host.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED).AsDouble()
    removed=sum((r[2]-r[0])*(r[3]-r[1])*(h-P['topping_m'])/.3048**3 for r in accepted)
    receipt={'host_id':P['floor_id'],'mark':host.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString(),'section':section,
        'cavities':len(accepted),'excluded':excluded,'before_m3':before*.3048**3,'expected_after_m3':(before-removed)*.3048**3,'status':'inspected',
        'geometry_reference_only':True,'rebar_created':False,'project_instances_per_floor':2}
    receipt['reinforcement_audit']=reinforcement_audit
    def write():
        with io.open(P['receipt_path'],'w',encoding='utf8') as f:f.write(text_type(json.dumps(receipt,indent=2)))
    if P.get('inspect_only',True):return receipt
    if int(ComputerInfo().AvailablePhysicalMemory/1048576)<1000:
        raise ValueError('RAM libre <1000 MB; lote no iniciado')
    receipt['status']='started';write()
    files=[];tx=None;group=None
    try:
        # Close each temporary family immediately. No multiple family documents held.
        for solid in [False,True]:
            name='CDX_ALIG_%s_%s' % (P['floor_id'],'EPS' if solid else 'VOID')
            path=os.path.join(P['family_dir'],name+'.rfa')
            if os.path.exists(path):raise ValueError('Familia ya existe: inspeccionar antes de reintentar')
            fd=doc.Application.NewFamilyDocument(P['family_template']);ft=None
            try:
                ft=DB.Transaction(fd,'CDX: paquete geometrico');ft.Start()
                fd.FamilyManager.NewType('PROPUESTA_'+section)
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
                if ft is not None and ft.GetStatus()==DB.TransactionStatus.Started:ft.RollBack()
                fd.Close(False)
        group=DB.TransactionGroup(doc,'CDX: propuesta aligerada acotada');group.Start()
        tx=DB.Transaction(doc,'CDX: familias y corte de un solo host');tx.Start()
        instances=[]
        for name,path in files:
            ref=clr.Reference[DB.Family]()
            if not doc.LoadFamily(path,ref):raise ValueError('No se cargo familia')
            symbol=doc.GetElement(list(ref.Value.GetFamilySymbolIds())[0]);symbol.Activate();doc.Regenerate()
            instance=doc.Create.NewFamilyInstance(DB.XYZ(b[0]/.3048,b[1]/.3048,z),symbol,DB.Structure.StructuralType.NonStructural)
            instance.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS).Set('CDX:ALIGERADO:PROPUESTA;host=%s;cavidades=%s' % (P['floor_id'],len(accepted)))
            instances.append(instance)
        DB.InstanceVoidCutUtils.AddInstanceVoidCut(doc,host,instances[0])
        type_name=section+' H=%.2f PROPUESTA host%s' % (h,P['floor_id'])
        floor_type=next((t for t in DB.FilteredElementCollector(doc).OfClass(DB.FloorType) if t.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()==type_name),None)
        if floor_type is not None:raise ValueError('Tipo de propuesta ya existe: inspeccionar antes de reutilizar')
        floor_type=doc.GetElement(host.GetTypeId()).Duplicate(type_name)
        host.ChangeTypeId(floor_type.Id)
        cp=host.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        cp.Set((cp.AsString() or '')+' | CDX PROPUESTA ALIGERADA >16cm; topping5cm; ARMADO Y PESO POR REVALIDAR')
        if tx.Commit()!=DB.TransactionStatus.Committed:raise ValueError('Corte no confirmado')
        after=host.get_Parameter(DB.BuiltInParameter.HOST_VOLUME_COMPUTED).AsDouble()
        if abs(after-(before-removed))>max(1e-6,removed*1e-6):raise ValueError('Volumen nativo distinto del esperado')
        if not DB.InstanceVoidCutUtils.InstanceVoidCutExists(host,instances[0]):raise ValueError('Corte ausente')
        warnings_after=set((w.GetDescriptionText(),tuple(sorted(int(i.Value) for i in w.GetFailingElements()))) for w in doc.GetWarnings())
        if warnings_after-warnings_before:raise ValueError('Nuevas advertencias; lote revertido')
        if group.Assimilate()!=DB.TransactionStatus.Committed:raise ValueError('Grupo no confirmado')
        receipt.update(status='applied',after_m3=after*.3048**3,instance_ids=[int(e.Id.Value) for e in instances],family_paths=[p for n,p in files])
        write()
        doc.Save();receipt['saved']=not doc.IsModified;write()
        return receipt
    except Exception as exc:
        if tx is not None and tx.GetStatus()==DB.TransactionStatus.Started:tx.RollBack()
        if group is not None and group.GetStatus()==DB.TransactionStatus.Started:group.RollBack()
        receipt.update(status='error_inspect_before_retry',error=str(exc));write();raise
