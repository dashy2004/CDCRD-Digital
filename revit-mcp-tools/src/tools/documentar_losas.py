# -*- coding: utf-8 -*-
"""documentar_losas: documentacion de losas existentes en una copia protegida.

No calcula ni crea acero fisico. Genera vistas, tags, cortes y una tabla nativa.
El armado esquematico se toma exclusivamente de parametros existentes y se
rotula por estado de evidencia. Reutiliza vistas_planta y acero_losas_plano.
Exportar con exportar_pdf despues de componer y comprobar las hojas.

P: expected_path, expected_pid, protected_paths, lock_path, lock_identity,
   action (inspect|views|annotate|schedule|sheets|layout|align|refine), prefix, floor_ids,
   plan_views [{name,bounds_m:[x0,y0,x1,y1],scale,role}],
   sections [{name,origin_m,right,up,direction,bounds_m,scale}],
   trial_ids, inherited_reference_authorized, receipt_path, min_free_mb.
Unidades de configuracion: metros; coordenadas del modelo Revit, sin traslacion.
Vistas nuevas solamente. Una repeticion con contenido existente se rechaza:
la fase inspect permite comprobar y continuar sin borrar elementos.
"""
import hashlib
import io
import json
import math
import os
import re

_PILOT_STATUS = 'CDX_Estado_Armado'


def _pilot_validate(P, path, pid, lock):
    expected = P.get('expected_path')
    protected = P.get('protected_paths') or []
    if not expected or not protected:
        raise ValueError('expected_path y protected_paths son obligatorios')
    normal = lambda p: os.path.normcase(os.path.abspath(p))
    if normal(path) != normal(expected) or normal(path) in [normal(p) for p in protected]:
        raise ValueError('Documento no autorizado o fuente protegida')
    if int(pid) != int(P.get('expected_pid', -1)):
        raise ValueError('PID diferente')
    identity = P.get('lock_identity') or {}
    if lock.get('state') != 'active' or not all(
            identity.get(k) and identity[k] == lock.get(k)
            for k in ('owner', 'session', 'task')):
        raise ValueError('Turno exclusivo no coincide')
    ids = P.get('floor_ids') or []
    if not ids or len(ids) != len(set(ids)):
        raise ValueError('floor_ids vacio o duplicado')
    if not set(P.get('trial_ids') or []).issubset(set(ids)):
        raise ValueError('trial_ids fuera del alcance')
    if len(ids) > len(P.get('trial_ids') or []) and not P.get('inherited_reference_authorized'):
        raise ValueError('Representacion heredada no autorizada')
    if not str(P.get('prefix', '')).startswith('CDX:'):
        raise ValueError('prefix debe empezar por CDX:')
    view_prefix = P.get('view_prefix')
    if not view_prefix or not view_prefix.startswith('CDX '):
        raise ValueError('view_prefix debe empezar por CDX y espacio')
    if int(P.get('min_free_mb', 1000)) < 1000:
        raise ValueError('La guarda de memoria no puede ser menor a 1000 MB')
    for spec in P.get('plan_views', []) + P.get('sections', []):
        if not spec.get('name', '').startswith(view_prefix):
            raise ValueError('Vista fuera del namespace propio')


def _pilot_spacing(raw):
    """Presentacion en cm solo para la sintaxis explicita conocida en metros."""
    raw = raw or ''
    match = re.match(r'^\s*(#[0-9]+)\s*@\s*(0\.[0-9]+)(?:\s*\(PILOTO\))?\s*$', raw)
    if not match:
        return raw or 'SIN DATO'
    return '%s@%g cm' % (match.group(1), float(match.group(2)) * 100)


def _pilot_partition(rows, specs):
    """Asignacion por centro para vistas de zonas; nunca decide apoyos/luces."""
    by_role = {}
    result = {}
    for spec in specs:
        bounds = spec['bounds_m']
        if len(bounds) != 4 or bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
            raise ValueError('Limites de planta invalidos')
        selected = [r for r in rows if bounds[0] <= r['cx'] <= bounds[2]
                    and bounds[1] <= r['cy'] <= bounds[3]]
        if not selected:
            raise ValueError('Zona sin losas: ' + spec['name'])
        result[spec['name']] = selected
        if spec['role'] in ('scheme', 'reinforcement'):
            by_role.setdefault(spec['role'], []).extend(r['id'] for r in selected)
    expected = set(r['id'] for r in rows)
    for role in ('scheme', 'reinforcement'):
        ids = by_role.get(role, [])
        if set(ids) != expected or len(ids) != len(expected):
            raise ValueError('Las zonas %s no cubren cada losa exactamente una vez' % role)
    return result


def run(doc, uidoc, DB, P):
    import clr
    clr.AddReference('Microsoft.VisualBasic')
    import System
    from System.Collections.Generic import List
    from Microsoft.VisualBasic.Devices import ComputerInfo
    with io.open(P['lock_path'], encoding='utf-8-sig') as stream:
        lock = json.load(stream)
    _pilot_validate(P, doc.PathName, System.Diagnostics.Process.GetCurrentProcess().Id, lock)
    if doc.IsReadOnly or doc.IsModifiable:
        raise ValueError('Documento bloqueado o transaccion ya abierta')
    action = P.get('action', 'inspect')
    if action not in ('inspect', 'views', 'annotate', 'schedule', 'sheets', 'layout', 'align', 'refine'):
        raise ValueError('action desconocida')
    free_mb = int(ComputerInfo().AvailablePhysicalMemory / 1048576)
    if action != 'inspect' and free_mb < int(P.get('min_free_mb', 1000)):
        raise ValueError('RAM insuficiente antes del lote: %d MB' % free_mb)
    def eid(x): return int(x.Value)
    def get(i): return doc.GetElement(DB.ElementId(System.Int64(i)))
    def xyz_m(p): return DB.XYZ(*[float(x) / 0.3048 for x in p])
    def vec(p): return DB.XYZ(*[float(x) for x in p])
    def ptext(e, name):
        p = e.LookupParameter(name)
        return (p.AsString() or '') if p else ''
    def mark(e):
        p = e.get_Parameter(DB.BuiltInParameter.ALL_MODEL_INSTANCE_COMMENTS)
        if p is not None and not p.IsReadOnly:
            p.Set(P['prefix'])
    def tx(name, fn):
        t = DB.Transaction(doc, P['prefix'] + ' ' + name)
        if t.Start() != DB.TransactionStatus.Started:
            raise RuntimeError('No se inicio transaccion')
        try:
            value = fn()
            if t.Commit() != DB.TransactionStatus.Committed:
                raise RuntimeError('Transaccion no confirmada')
            return value
        except Exception:
            if t.GetStatus() == DB.TransactionStatus.Started:
                t.RollBack()
            raise
    def existing_tool(name, params, overrides=None):
        if name not in ('vistas_planta', 'acero_losas_plano'):
            raise ValueError('Tool no autorizada en orquestador')
        base = os.path.dirname(__file__)
        ns = {'DB': DB, '__file__': os.path.join(base, name + '.py')}
        for file_name in ('_common.py', name + '.py'):
            with io.open(os.path.join(base, file_name), encoding='utf-8') as source:
                exec(compile(source.read(), file_name, 'exec'), ns)
        ns.update(overrides or {})
        result = ns['run'](doc, uidoc, DB, params)
        for key in ('errores', 'excepciones'):
            errors = result.get(key)
            if errors and (not isinstance(errors, dict) or errors.get('n', 0)):
                raise RuntimeError('Error en %s: %s' % (name, result))
        return result
    rows = []
    levels = set()
    trials = set(P.get('trial_ids') or [])
    for i in P['floor_ids']:
        floor = get(i)
        if not isinstance(floor, DB.Floor):
            raise ValueError('Elemento no es Floor: %s' % i)
        b = floor.get_BoundingBox(None)
        if b is None:
            raise ValueError('Floor sin limites')
        levels.add(eid(floor.LevelId))
        rows.append({'id':i, 'uid':floor.UniqueId, 'mark':ptext(floor,'Mark'),
                     'cx':(b.Min.X+b.Max.X)*0.1524,'cy':(b.Min.Y+b.Max.Y)*0.1524,
                     'bounds_m': [[q.X*0.3048,q.Y*0.3048,q.Z*0.3048] for q in (b.Min,b.Max)],
                     'area_m2':floor.get_Parameter(DB.BuiltInParameter.HOST_AREA_COMPUTED).AsDouble()*0.3048**2,
                     'x':ptext(floor,'Acero_X'),'y':ptext(floor,'Acero_Y'),
                     'apoyo':ptext(floor,'Acero_Apoyo'),
                     'status':'ENSAYO PRELIMINAR' if i in trials else 'REF. SIN VERIFICAR'})
    if len(levels) != 1 or len(set(r['mark'] for r in rows)) != len(rows) or any(not r['mark'] for r in rows):
        raise ValueError('Se requiere una planta y marcas no vacias/unicas')
    rows.sort(key=lambda r:r['mark'])
    level = get(list(levels)[0])
    partition = _pilot_partition(rows, P['plan_views'])
    views = {v.Name:v for v in DB.FilteredElementCollector(doc).OfClass(DB.View) if not v.IsTemplate}
    receipt = {'action':action,'path':doc.PathName,'free_mb':free_mb,'level':level.Name,
               'rows':rows,'created':[],'existing_tools':[],'warnings_before':len(list(doc.GetWarnings()))}
    if action == 'inspect':
        receipt['views'] = [{'name':n,'id':eid(v.Id)} for n,v in views.items() if n.startswith(P['view_prefix'])]
    else:
        group = DB.TransactionGroup(doc, P['prefix'] + ' ' + action)
        group.Start()
        try:
            if action == 'views':
                all_names = [s['name'] for s in P['plan_views']] + [s['name'] for s in P['sections']]
                if len(all_names) != len(set(all_names)) or any(n in views for n in all_names):
                    raise ValueError('Nombre existente/duplicado: no se borra ni reemplaza')
                def quiet_view():
                    draft_type=next(t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                                    if t.ViewFamily==DB.ViewFamily.Drafting)
                    v=DB.ViewDrafting.Create(doc,draft_type.Id)
                    v.Name=P['view_prefix']+' CONTROL'
                    return v
                quiet=tx('vista de trabajo',quiet_view)
                uidoc.ActiveView=quiet
                for spec in P['plan_views']:
                    result = existing_tool('vistas_planta', {'levels':[level.Name], 'kind':'piso',
                        'prefix':spec['name']+' - ', 'scale':spec['scale'], 'dry_run':False,
                        'underlay_off':True, 'crop':False, 'replace':False})
                    receipt['existing_tools'].append(result)
                plans = {v.Name:v for v in DB.FilteredElementCollector(doc).OfClass(DB.ViewPlan)}
                def configure():
                    for spec in P['plan_views']:
                        v = plans[spec['name']+' - '+level.Name]
                        v.Name = spec['name']
                        v.ViewTemplateId=DB.ElementId.InvalidElementId
                        v.Discipline=DB.ViewDiscipline.Coordination
                        v.DetailLevel=DB.ViewDetailLevel.Fine
                        v.DisplayStyle=DB.DisplayStyle.HLR
                        v.AreImportCategoriesHidden=True
                        vr=v.GetViewRange()
                        for plane,offset in ((DB.PlanViewPlane.TopClipPlane,0.3),(DB.PlanViewPlane.CutPlane,0.1),
                            (DB.PlanViewPlane.BottomClipPlane,-1.0),(DB.PlanViewPlane.ViewDepthPlane,-1.0)):
                            vr.SetLevelId(plane,level.Id);vr.SetOffset(plane,offset/0.3048)
                        v.SetViewRange(vr)
                        b=v.CropBox; x0,y0,x1,y1=spec['bounds_m']
                        b.Min=DB.XYZ(x0/0.3048,y0/0.3048,b.Min.Z)
                        b.Max=DB.XYZ(x1/0.3048,y1/0.3048,b.Max.Z)
                        v.CropBox=b;v.CropBoxActive=True;v.CropBoxVisible=False
                        for bic in (DB.BuiltInCategory.OST_Levels,DB.BuiltInCategory.OST_Sections,
                                    DB.BuiltInCategory.OST_Elev,DB.BuiltInCategory.OST_Rebar):
                            cid=DB.ElementId(bic)
                            if v.CanCategoryBeHidden(cid):v.SetCategoryHidden(cid,True)
                        colors = [(DB.BuiltInCategory.OST_StructuralFraming,(110,55,150)),
                                  (DB.BuiltInCategory.OST_StructuralColumns,(175,40,45)),
                                  (DB.BuiltInCategory.OST_Walls,(175,40,45)),
                                  (DB.BuiltInCategory.OST_Grids,(170,90,140))]
                        for bic,rgb in colors:
                            og=DB.OverrideGraphicSettings();og.SetProjectionLineColor(DB.Color(*rgb))
                            og.SetCutLineColor(DB.Color(*rgb));v.SetCategoryOverrides(DB.ElementId(bic),og)
                        og=DB.OverrideGraphicSettings();og.SetSurfaceTransparency(75)
                        v.SetCategoryOverrides(DB.ElementId(DB.BuiltInCategory.OST_Floors),og)
                        receipt['created'].append({'kind':'plan','id':eid(v.Id),'name':v.Name})
                    section_type=next(t for t in DB.FilteredElementCollector(doc).OfClass(DB.ViewFamilyType)
                                      if t.ViewFamily==DB.ViewFamily.Section)
                    for spec in P['sections']:
                        tr=DB.Transform.Identity;tr.Origin=xyz_m(spec['origin_m'])
                        tr.BasisX=vec(spec['right']);tr.BasisY=vec(spec['up']);tr.BasisZ=vec(spec['direction'])
                        b=DB.BoundingBoxXYZ();b.Transform=tr
                        b.Min=xyz_m(spec['bounds_m'][0]);b.Max=xyz_m(spec['bounds_m'][1])
                        v=DB.ViewSection.CreateSection(doc,section_type.Id,b)
                        v.Name=spec['name'];v.Scale=spec['scale'];v.DetailLevel=DB.ViewDetailLevel.Fine
                        v.Discipline=DB.ViewDiscipline.Coordination;v.AreImportCategoriesHidden=True
                        v.CropBoxVisible=False
                        receipt['created'].append({'kind':'section','id':eid(v.Id),'name':v.Name})
                tx('configurar vistas y cortes',configure)
            elif action == 'annotate':
                all_existing=[v for v in views.values() if v.Name in partition]
                for v in all_existing:
                    if DB.FilteredElementCollector(doc,v.Id).OfClass(DB.TextNote).GetElementCount():
                        raise ValueError('Vista ya anotada; usar inspect, no recrear')
                def annotate():
                    txt_name=P['view_prefix']+' texto 2mm'
                    types=list(DB.FilteredElementCollector(doc).OfClass(DB.TextNoteType))
                    txt=next((x for x in types if x.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()==txt_name),None)
                    if txt is None:
                        txt=doc.GetElement(doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)).Duplicate(txt_name)
                        txt.get_Parameter(DB.BuiltInParameter.TEXT_SIZE).Set(2.0/304.8)
                    tag_type=next(t for t in DB.FilteredElementCollector(doc).OfCategory(DB.BuiltInCategory.OST_FloorTags).WhereElementIsElementType()
                                  if t.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()==P.get('tag_type','Mark+H'))
                    for spec in P['plan_views']:
                        view=views[spec['name']]
                        for row in partition[spec['name']]:
                            pos=xyz_m([row['cx'],row['cy']+(0.75 if spec['role']=='reinforcement' else 0),level.ProjectElevation*0.3048])
                            tag=DB.IndependentTag.Create(doc,tag_type.Id,view.Id,DB.Reference(get(row['id'])),False,DB.TagOrientation.Horizontal,pos)
                            mark(tag)
                            if spec['role']=='reinforcement':
                                label='ENSAYO' if row['id'] in trials else 'REF.'
                                text='%s\nX: %s\nY: %s\nSUP/AP: %s' % (label,_pilot_spacing(row['x']),_pilot_spacing(row['y']),_pilot_spacing(row['apoyo']))
                                note=DB.TextNote.Create(doc,view.Id,xyz_m([row['cx']-0.7,row['cy']-0.2,level.ProjectElevation*0.3048]),text,txt.Id)
                                mark(note)
                    return eid(txt.Id)
                text_type_id=tx('tags y notas por fuente',annotate)
                # Reuse the existing drawing tool with explicit text type and ownership.
                for spec in P['plan_views']:
                    if spec['role']!='reinforcement':continue
                    plan={'origen_m':[0,0],'losas':[],'apoyos':[]}
                    for row in partition[spec['name']]:
                        x,y=row['cx'],row['cy'];xmin,ymin,z=row['bounds_m'][0];xmax,ymax,_=row['bounds_m'][1]
                        # Graphic direction glyphs only; not bar extents, laps or development.
                        h=min(0.5,(ymax-ymin)*0.15);w=min(0.6,(xmax-xmin)*0.15)
                        plan['losas'].append({'mark':row['mark'],'nivel':level.Name,'trazos':[
                            {'puntos':[[x-w,y+h],[x+w,y+h]],'texto':'','pos_texto':[x,y]},
                            {'puntos':[[x-w,y+h],[x-w,y+2*h]],'texto':'','pos_texto':[x,y]}]})
                    path=os.path.join(os.path.dirname(P['receipt_path']),spec['name'].replace(':','_')+'.plan.json')
                    with io.open(path,'w',encoding='utf-8') as f:f.write(unicode(json.dumps(plan,ensure_ascii=False)))
                    receipt['existing_tools'].append(existing_tool('acero_losas_plano',
                        {'plan':path,'view_name':spec['name'],'limpiar':False,'tabla':False},
                        {'MARCA_DIBUJO':P['prefix']}))
                receipt['text_type_id']=text_type_id
            elif action == 'schedule':
                name=P['view_prefix']+' TABLA LOSAS'
                if name in views:raise ValueError('Tabla existente: no se reemplaza')
                # Binding in its own transaction; reacquire elements after the commit.
                if any(get(i).LookupParameter(_PILOT_STATUS) is None for i in P['floor_ids']):
                    def bind():
                        app=doc.Application;old=app.SharedParametersFilename
                        path=os.path.join(os.path.dirname(P['receipt_path']),'parametros_piloto.txt')
                        if not os.path.exists(path):
                            with io.open(path,'w',encoding='utf-8') as f:f.write(u'')
                        try:
                            app.SharedParametersFilename=path
                            f=app.OpenSharedParameterFile()
                            g=f.Groups.get_Item('CDX Documentacion') or f.Groups.Create('CDX Documentacion')
                            d=g.Definitions.get_Item(_PILOT_STATUS)
                            if d is None:
                                opts=DB.ExternalDefinitionCreationOptions(_PILOT_STATUS,DB.SpecTypeId.String.Text)
                                opts.GUID=System.Guid('e03f325c-2e66-446a-92de-850ea57ce82b')
                                d=g.Definitions.Create(opts)
                            cs=app.Create.NewCategorySet();cs.Insert(doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Floors))
                            if not doc.ParameterBindings.Insert(d,app.Create.NewInstanceBinding(cs),DB.GroupTypeId.Data):
                                raise ValueError('No se pudo crear parametro de evidencia')
                        finally:app.SharedParametersFilename=old
                    tx('parametro de evidencia',bind)
                def schedule():
                    for row in rows:
                        p=get(row['id']).LookupParameter(_PILOT_STATUS)
                        if p is None or p.IsReadOnly:raise ValueError('Parametro de evidencia no editable')
                        p.Set(row['status'])
                    vs=DB.ViewSchedule.CreateSchedule(doc,DB.ElementId(DB.BuiltInCategory.OST_Floors));vs.Name=name
                    d=vs.Definition;d.IsItemized=True;d.ShowGrandTotal=False
                    avail={s.GetName(doc):s for s in d.GetSchedulableFields()}
                    fields=[('Mark','LOSA',15),('Default Thickness','H TIPO (m)',18),('Area','AREA (m2)',25),
                            ('Acero_X','X / HEREDADO',40),('Acero_Y','Y / HEREDADO',40),
                            ('Acero_Apoyo','SUP/AP / HEREDADO',40),(_PILOT_STATUS,'ESTADO',43),('Level','Nivel',15)]
                    for fname,title,width in fields:
                        if fname not in avail:raise ValueError('Campo no disponible: '+fname)
                        f=d.AddField(avail[fname]);f.ColumnHeading=title;f.GridColumnWidth=width/304.8
                        if fname=='Level':
                            d.AddFilter(DB.ScheduleFilter(f.FieldId,DB.ScheduleFilterType.Equal,level.Id));f.IsHidden=True
                        if fname=='Mark':d.AddSortGroupField(DB.ScheduleSortGroupField(f.FieldId))
                    receipt['created'].append({'kind':'schedule','id':eid(vs.Id),'name':name})
                tx('tabla por planta',schedule)
            elif action == 'sheets':
                specs=P.get('sheets') or []
                existing_sheets={s.SheetNumber:s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)}
                if not specs or any(s['number'] in existing_sheets for s in specs):
                    raise ValueError('Hojas vacias o existentes')
                tb=get(P['titleblock_id'])
                def sheets():
                    for spec in specs:
                        sheet=DB.ViewSheet.Create(doc,tb.Id);sheet.SheetNumber=spec['number'];sheet.Name=spec['name']
                        mark(sheet);receipt['created'].append({'kind':'sheet','id':eid(sheet.Id),'number':spec['number']})
                tx('hojas',sheets)
            elif action == 'layout':
                sheets={s.SheetNumber:s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)}
                layout=P.get('layout') or []
                if not layout:raise ValueError('Falta layout')
                for cell in layout:
                    if cell['sheet'] not in sheets or cell['view'] not in views:
                        raise ValueError('Hoja/vista no encontrada')
                    if not cell['view'].startswith(P['view_prefix']):raise ValueError('Vista ajena')
                    if list(sheets[cell['sheet']].GetAllViewports()):
                        raise ValueError('La hoja ya tiene vistas; no duplicar')
                def layout_views():
                    for cell in layout:
                        s=sheets[cell['sheet']];v=views[cell['view']]
                        pos=DB.XYZ(cell['paper_mm'][0]/304.8,cell['paper_mm'][1]/304.8,0)
                        if isinstance(v,DB.ViewSchedule):
                            placed=DB.ScheduleSheetInstance.Create(doc,s.Id,v.Id,pos)
                        else:
                            if 'scale' in cell:v.Scale=int(cell['scale'])
                            if not DB.Viewport.CanAddViewToSheet(doc,s.Id,v.Id):raise ValueError('Vista ya colocada')
                            placed=DB.Viewport.Create(doc,s.Id,v.Id,pos)
                        receipt['created'].append({'kind':'placement','id':eid(placed.Id),'view':v.Name,'sheet':s.SheetNumber})
                tx('colocar vistas',layout_views)
                def notes_and_sections():
                    types=list(DB.FilteredElementCollector(doc).OfClass(DB.TextNoteType))
                    by_size={}
                    for size in (2,2.5,3,4,6):
                        name=P['view_prefix']+' TEXTO '+str(size)
                        typ=next((t for t in types if t.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()==name),None)
                        if typ is None:
                            typ=doc.GetElement(doc.GetDefaultElementTypeId(DB.ElementTypeGroup.TextNoteType)).Duplicate(name)
                            typ.get_Parameter(DB.BuiltInParameter.TEXT_SIZE).Set(size/304.8)
                            typ.get_Parameter(DB.BuiltInParameter.TEXT_FONT).Set('Arial')
                        by_size[size]=typ.Id
                    for spec in P.get('sheet_notes',[]):
                        s=sheets[spec['sheet']];x,y=spec['paper_mm']
                        note=DB.TextNote.Create(doc,s.Id,DB.XYZ(x/304.8,y/304.8,0),
                            float(spec.get('width_mm',700))/304.8,spec['text'],by_size[spec.get('size',3)])
                        mark(note)
                    for sec in P['sections']:
                        v=views[sec['name']]
                        for bic in (DB.BuiltInCategory.OST_Levels,DB.BuiltInCategory.OST_Grids):
                            v.SetCategoryHidden(DB.ElementId(bic),True)
                        for r in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar):
                            if eid(r.GetHostId()) in trials:
                                r.SetUnobscuredInView(v,True)
                                og=DB.OverrideGraphicSettings();og.SetProjectionLineColor(DB.Color(30,80,170))
                                og.SetCutLineColor(DB.Color(30,80,170));og.SetProjectionLineWeight(3);og.SetCutLineWeight(3)
                                v.SetElementOverrides(r.Id,og)
                tx('notas de hoja y visibilidad del ensayo',notes_and_sections)
                # Actual viewport bounds after commits; never force Regenerate on import-heavy models.
                receipt['placement_bounds_mm']=[]
                for created in receipt['created']:
                    item=get(created['id']);s=sheets[created['sheet']]
                    if isinstance(item,DB.Viewport):
                        box=item.GetBoxOutline();a=box.MinimumPoint;b=box.MaximumPoint
                    else:
                        box=item.get_BoundingBox(s);a=box.Min;b=box.Max
                    receipt['placement_bounds_mm'].append({'view':created['view'],'sheet':created['sheet'],
                        'min':[a.X*304.8,a.Y*304.8],'max':[b.X*304.8,b.Y*304.8]})
            elif action == 'align':
                sheets={s.SheetNumber:s for s in DB.FilteredElementCollector(doc).OfClass(DB.ViewSheet)}
                jobs=[]
                for cell in P.get('layout') or []:
                    v=views[cell['view']];s=sheets[cell['sheet']]
                    if not v.Name.startswith(P['view_prefix']):raise ValueError('Vista ajena')
                    if isinstance(v,DB.ViewSchedule):continue
                    vp=next((doc.GetElement(i) for i in s.GetAllViewports() if doc.GetElement(i).ViewId==v.Id),None)
                    if vp is None:raise ValueError('Viewport faltante')
                    wanted=DB.XYZ(cell['paper_mm'][0]/304.8,cell['paper_mm'][1]/304.8,0)
                    actual=vp.GetBoxCenter()
                    if abs(actual.X-wanted.X)>0.00001 or abs(actual.Y-wanted.Y)>0.00001:jobs.append((vp,wanted))
                def align():
                    for vp,wanted in jobs:vp.SetBoxCenter(wanted)
                if jobs:tx('centrar vistas despues del commit',align)
                receipt['aligned']=len(jobs)
            elif action == 'refine':
                # Presentation changes are limited to the new pilot views/sheets.
                def refine():
                    vs=views[P['view_prefix']+' TABLA LOSAS'];d=vs.Definition
                    field=d.GetField(1)
                    native_id=int(DB.BuiltInParameter.FLOOR_ATTR_DEFAULT_THICKNESS_PARAM)
                    if eid(field.ParameterId)!=native_id:
                        d.RemoveField(field.FieldId)
                        sf=next(f for f in d.GetSchedulableFields() if eid(f.ParameterId)==native_id)
                        field=d.InsertField(sf,1)
                    field.ColumnHeading='H TIPO (m)';field.GridColumnWidth=18/304.8
                    fmt=DB.FormatOptions();fmt.UseDefault=False;fmt.SetUnitTypeId(DB.UnitTypeId.Meters);fmt.Accuracy=0.01
                    field.SetFormatOptions(fmt)
                    for cell in P.get('layout') or []:
                        v=views[cell['view']]
                        if isinstance(v,DB.ViewSchedule):continue
                        vp=next(p for p in DB.FilteredElementCollector(doc).OfClass(DB.Viewport) if p.ViewId==v.Id)
                        # Label offsets are relative to the lower-left viewport corner.
                        vp.LabelOffset=DB.XYZ(0,-8/304.8,0)
                        vp.LabelLineLength=(390 if isinstance(v,DB.ViewPlan) else 270)/304.8
                    for spec in P['plan_views']:
                        v=views[spec['name']]
                        if spec['role']!='reinforcement':continue
                        notes=list(DB.FilteredElementCollector(doc,v.Id).OfClass(DB.TextNote))
                        for row in partition[spec['name']]:
                            height=row['bounds_m'][1][1]-row['bounds_m'][0][1]
                            if height>=2.5:continue
                            tagged=[t for t in DB.FilteredElementCollector(doc,v.Id).OfClass(DB.IndependentTag)
                                    if get(row['id']).Id in list(t.GetTaggedLocalElementIds())]
                            for tag in tagged:tag.TagHeadPosition=xyz_m([row['cx'],row['cy'],level.ProjectElevation*0.3048])
                            owned=[n for n in notes if doc.GetElement(n.GetTypeId()).get_Parameter(
                                DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()==P['view_prefix']+' texto 2mm']
                            note=next((n for n in owned if abs(n.Coord.X*0.3048-(row['cx']-0.7))<0.01
                                       and abs(n.Coord.Y*0.3048-(row['cy']-0.2))<0.01),None)
                            if note is not None:
                                note.Text=row['mark']+' - '+note.Text
                                note.Coord=xyz_m([row['cx']-0.7,spec['bounds_m'][1]+1.0,level.ProjectElevation*0.3048])
                    # Alternate crowded native grid bubbles at the other end in pilot views only.
                    for spec in P['plan_views']:
                        v=views[spec['name']]
                        for grid in DB.FilteredElementCollector(doc,v.Id).OfClass(DB.Grid):
                            if not grid.Name.endswith("'"):continue
                            bottom=DB.DatumEnds.End0 if grid.Curve.GetEndPoint(0).Y<grid.Curve.GetEndPoint(1).Y else DB.DatumEnds.End1
                            top=DB.DatumEnds.End1 if bottom==DB.DatumEnds.End0 else DB.DatumEnds.End0
                            grid.HideBubbleInView(top,v);grid.ShowBubbleInView(bottom,v)
                tx('ajustes de presentacion comprobados',refine)
            after=len(list(doc.GetWarnings()))
            if after!=receipt['warnings_before']:raise ValueError('Cambio en advertencias: %s -> %s' % (receipt['warnings_before'],after))
            if group.Assimilate()!=DB.TransactionStatus.Committed:raise RuntimeError('Grupo no confirmado')
            receipt['warnings_after']=after
        except Exception:
            if group.GetStatus()==DB.TransactionStatus.Started:group.RollBack()
            raise
    with io.open(P['receipt_path'],'w',encoding='utf-8') as out:
        out.write(unicode(json.dumps(receipt,ensure_ascii=False,indent=2)))
    return receipt
