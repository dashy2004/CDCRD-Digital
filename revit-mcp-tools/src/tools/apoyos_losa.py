"""Read-only geometric support audit for one horizontal, axis-aligned slab.

Measures solid intersections below the soffit, clear chords, neighboring profiles,
materials and existing voids/rebar. Contact is not proof of moment continuity.
Only StructuralFraming and StructuralColumns are probed; walls are not treated
as supports. No transaction, beam edit or structural approval is performed.
"""
import io
import json
import math
import os


def candidate_grid(bounds, config):
    """Full rectangular EPS cells only; a geometric scenario, never a design."""
    values=list(bounds)+[config[k] for k in ('height_m','topping_m','block_m','rib_m','border_m')]
    if len(bounds)!=4 or any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in values):
        raise ValueError('Invalid candidate geometry')
    x0,y0,x1,y1=bounds
    h,t,b,r,margin=values[4:]
    if not (.16<h<=.60 and .03<=t<h and .20<=b<=1 and .10<=r<=.40 and r<=margin<=1):
        raise ValueError('Candidate geometry out of range')
    def slots(low,high):
        n=int(math.floor((high-low-2*margin+r+1e-9)/(b+r)))
        if n<1 or n>150:
            raise ValueError('Candidate does not fit bounded scope')
        actual=(high-low-(n*b+(n-1)*r))/2
        return [(low+actual+i*(b+r),low+actual+i*(b+r)+b) for i in range(n)],actual
    xs,mx=slots(x0,x1)
    ys,my=slots(y0,y1)
    if len(xs)*len(ys)>150:
        raise ValueError('Candidate exceeds 150 cells')
    return {'rectangles_m':[[a,c,b1,d] for a,b1 in xs for c,d in ys],
            'counts_xy':[len(xs),len(ys)],'actual_border_xy_m':[mx,my],
            'rib_m':r,'block_m':b,'pitch_m':b+r,'height_m':h,'topping_m':t,
            'eps_height_m':h-t,'structural_design_verified':False,'applied':False}


def interval_union(intervals, low, high, tolerance=1e-7):
    if not all(math.isfinite(v) for v in (low, high, tolerance)) or low >= high or tolerance < 0:
        raise ValueError('Invalid interval bounds')
    valid = []
    for a, b in intervals:
        if not math.isfinite(a) or not math.isfinite(b) or a > b:
            raise ValueError('Invalid interval')
        a, b = max(a, low), min(b, high)
        if b > a:
            valid.append((a,b))
    merged = []
    for a,b in sorted(valid):
        if merged and a <= merged[-1][1]+tolerance:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a,b])
    gaps, cursor = [], low
    for a,b in merged:
        if a-cursor > tolerance:
            gaps.append([cursor,a])
        cursor = max(cursor,b)
    if high-cursor > tolerance:
        gaps.append([cursor,high])
    return {'covered_m':sum(b-a for a,b in merged),'intervals_m':merged,'gaps_m':gaps,
            'coverage':sum(b-a for a,b in merged)/(high-low)}


def _run(doc, uidoc, DB, P, resources):
    if P.get('action','inspect') != 'inspect':
        raise ValueError('Read-only tool')
    import System
    scope = {}
    helper = os.path.join(os.path.dirname(__file__),'dimensiones_losas.py')
    with io.open(helper,encoding='utf-8-sig') as stream:
        exec(compile(stream.read(),helper,'exec'),scope)
    with io.open(P['lock_path'],encoding='utf-8-sig') as stream:
        lock = json.load(stream)
    scope['validate_scope'](P,doc.PathName,System.Diagnostics.Process.GetCurrentProcess().Id,lock)
    if lock.get('process_id') != P['expected_pid'] or len(P['floor_ids']) != 1:
        raise ValueError('Requires one slab and matching lock PID')
    if doc.IsModifiable:
        raise ValueError('Transaction already open')
    modified_before = bool(doc.IsModified)
    floor=doc.GetElement(DB.ElementId(System.Int64(P['floor_ids'][0])))
    if not isinstance(floor,DB.Floor):
        raise ValueError('Target is not a floor')
    eid=lambda e:int(e.Id.Value)
    xyz=lambda p:DB.XYZ(*[v/.3048 for v in p])
    pt=lambda p:[float(p.X)*.3048,float(p.Y)*.3048,float(p.Z)*.3048]
    def bounds(e):
        box=e.get_BoundingBox(None)
        if box is None:
            raise ValueError('Element has no bounding box')
        if not box.Transform.IsIdentity:
            raise ValueError('Unsupported transformed bounding box')
        return [pt(box.Min),pt(box.Max)]
    def profile(e):
        sketch=doc.GetElement(e.SketchId)
        return [[pt(c.GetEndPoint(0)) for c in loop] for loop in sketch.Profile] if sketch else []
    points=profile(floor)
    sketch=doc.GetElement(floor.SketchId)
    if len(points)!=1 or any(not isinstance(c,DB.Line) for c in sketch.Profile[0]):
        raise ValueError('Requires one straight rectangular profile')
    lx,ly=scope['rectangle_lengths'](points[0],0.0)
    box=bounds(floor)
    xmin,ymin,zmin=box[0]
    xmax,ymax,zmax=box[1]
    # Reject shape-edited/variable thickness floors for this bounded audit.
    shape_editor=floor.GetSlabShapeEditor()
    if shape_editor is not None:
        try:
            if shape_editor.IsEnabled:
                raise ValueError('Shape-edited slab not supported')
        finally:
            shape_editor.Dispose()
    h=float(floor.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM).AsDouble())*.3048
    if abs(zmax-zmin-h)>1e-6:
        raise ValueError('Variable/sloped slab not supported')
    options=DB.Options()
    resources.append(options)
    options.DetailLevel=DB.ViewDetailLevel.Fine
    def walk(geometry):
        if geometry is None:
            return
        for item in geometry:
            if isinstance(item,DB.Solid) and item.Volume>1e-9:
                yield item
            elif isinstance(item,DB.GeometryInstance):
                nested = item.GetInstanceGeometry()
                resources.append(nested)
                for solid in walk(nested):
                    yield solid
    def solids_of(e):
        geometry = e.get_Geometry(options)
        if geometry is not None:
            resources.append(geometry)
        return list(walk(geometry))
    def material(mid):
        mat=doc.GetElement(mid)
        data={'id':int(mid.Value),'name':mat.Name if mat else None,'young_mpa':None}
        if isinstance(mat,DB.Material) and mat.StructuralAssetId!=DB.ElementId.InvalidElementId:
            prop=doc.GetElement(mat.StructuralAssetId)
            asset=prop.GetStructuralAsset()
            try:
                data['class']=str(asset.StructuralAssetClass)
                data['young_mpa']=[DB.UnitUtils.ConvertFromInternalUnits(v,DB.UnitTypeId.Megapascals)
                                   for v in (asset.YoungModulus.X,asset.YoungModulus.Y,asset.YoungModulus.Z)]
            finally:
                asset.Dispose()
        return data
    def describe(e):
        d={'id':eid(e),'category':int(e.Category.Id.Value),'box_m':bounds(e)}
        typ=doc.GetElement(e.GetTypeId())
        d['type_name']=typ.get_Parameter(DB.BuiltInParameter.SYMBOL_NAME_PARAM).AsString()
        if hasattr(e.Location,'Curve'):
            d['axis_m']=[pt(e.Location.Curve.GetEndPoint(i)) for i in (0,1)]
        d['type_dimensions']={}
        for par in typ.Parameters:
            if par.StorageType==DB.StorageType.Double and par.Definition.GetDataType()==DB.SpecTypeId.Length:
                d['type_dimensions'][par.Definition.Name]=float(par.AsDouble())*.3048
        mid=(typ.StructuralMaterialId if isinstance(typ,DB.FloorType) else
             e.StructuralMaterialId if isinstance(e,DB.FamilyInstance) else DB.ElementId.InvalidElementId)
        d['material']=material(mid)
        return d
    structures=[]
    for bic in (DB.BuiltInCategory.OST_StructuralFraming,DB.BuiltInCategory.OST_StructuralColumns):
        for e in DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
            b=bounds(e)
            if (b[1][0]>=xmin-.5 and b[0][0]<=xmax+.5 and b[1][1]>=ymin-.5 and b[0][1]<=ymax+.5
                and b[1][2]>=zmin-.002 and b[0][2]<zmin):
                if len(structures)>=80:
                    raise ValueError('Too many nearby supports; narrow the audit')
                structures.append((e,solids_of(e)))
    intersection_options=DB.SolidCurveIntersectionOptions()
    def probe(a,b,axis):
        line=DB.Line.CreateBound(xyz(a),xyz(b))
        intervals=[]
        rows=[]
        try:
            for element,solids in structures:
                parts=[]
                for solid in solids:
                    inter=solid.IntersectWithCurve(line,intersection_options)
                    try:
                        for i in range(inter.SegmentCount):
                            segment=inter.GetCurveSegment(i)
                            try:
                                ends=sorted([pt(segment.GetEndPoint(0))[axis],pt(segment.GetEndPoint(1))[axis]])
                                parts.append(ends)
                                intervals.append(ends)
                            finally:
                                segment.Dispose()
                    finally:
                        inter.Dispose()
                if parts:
                    rows.append({'id':eid(element),'intervals_m':parts})
        finally:
            line.Dispose()
        return dict(interval_union(intervals,a[axis],b[axis]),elements=rows)
    z=zmin-.001
    try:
        edges={'S':probe([xmin,ymin,z],[xmax,ymin,z],0),'N':probe([xmin,ymax,z],[xmax,ymax,z],0),
               'W':probe([xmin,ymin,z],[xmin,ymax,z],1),'E':probe([xmax,ymin,z],[xmax,ymax,z],1)}
        chords=[]
        for frac in (.1,.25,.5,.75,.9):
            y=ymin+frac*(ymax-ymin)
            x=xmin+frac*(xmax-xmin)
            chords.append({'axis':'X','fraction':frac,'probe':probe([xmin,y,z],[xmax,y,z],0)})
            chords.append({'axis':'Y','fraction':frac,'probe':probe([x,ymin,z],[x,ymax,z],1)})
        supports=[describe(e) for e,s in structures]
    finally:
        intersection_options.Dispose()
    neighbors=[]
    for e in DB.FilteredElementCollector(doc).OfClass(DB.Floor):
        b=bounds(e)
        if eid(e)!=eid(floor) and abs(b[1][2]-zmax)<.01 and b[1][0]>=xmin-1 and b[0][0]<=xmax+1 and b[1][1]>=ymin-1 and b[0][1]<=ymax+1:
            neighbors.append({'id':eid(e),'mark':e.get_Parameter(DB.BuiltInParameter.ALL_MODEL_MARK).AsString(),
                              'profile_m':profile(e),'box_m':b,'thickness_m':float(e.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM).AsDouble())*.3048})
    volume=sum(s.Volume for s in solids_of(floor))*.3048**3
    candidate=None
    if P.get('rib_candidate') is not None:
        # Transient solids in memory, not Revit elements or a transaction.
        from System.Collections.Generic import List
        candidate=candidate_grid([xmin,ymin,xmax,ymax],P['rib_candidate'])
        bottom=zmax-candidate['height_m']
        top=zmax-candidate['topping_m']
        obstacles=[]
        for bic in (DB.BuiltInCategory.OST_Walls,DB.BuiltInCategory.OST_StructuralFraming,DB.BuiltInCategory.OST_StructuralColumns):
            for e in DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsNotElementType():
                b=bounds(e)
                if b[0][0]<xmax and b[1][0]>xmin and b[0][1]<ymax and b[1][1]>ymin and b[0][2]<top and b[1][2]>bottom:
                    if len(obstacles)>=80:
                        raise ValueError('Too many candidate obstacles')
                    obstacles.append((e,b,solids_of(e)))
        collisions=[]
        exact_boolean_tests=0
        for index,rect in enumerate(candidate['rectangles_m']):
            a,c,b,d=rect
            matches=[(e,ss) for e,bb,ss in obstacles if bb[0][0]<b and bb[1][0]>a and bb[0][1]<d and bb[1][1]>c]
            if not matches:
                continue
            loop_points=[xyz([xx,yy,bottom]) for xx,yy in ((a,c),(b,c),(b,d),(a,d))]
            loop=DB.CurveLoop()
            lines=[]
            virtual=None
            try:
                for i in range(4):
                    line=DB.Line.CreateBound(loop_points[i],loop_points[(i+1)%4])
                    lines.append(line)
                    loop.Append(line)
                virtual=DB.GeometryCreationUtilities.CreateExtrusionGeometry(List[DB.CurveLoop]([loop]),DB.XYZ.BasisZ,(top-bottom)/.3048)
                for element,ss in matches:
                    intersect_volume=0.0
                    for solid in ss:
                        intersection=DB.BooleanOperationsUtils.ExecuteBooleanOperation(virtual,solid,DB.BooleanOperationsType.Intersect)
                        exact_boolean_tests+=1
                        try:
                            intersect_volume+=float(intersection.Volume)*.3048**3
                        finally:
                            intersection.Dispose()
                    if intersect_volume>1e-9:
                        collisions.append({'cell':index,'obstacle_id':eid(element),'category':int(element.Category.Id.Value),'intersection_sum_m3':intersect_volume})
            finally:
                if virtual is not None:
                    virtual.Dispose()
                loop.Dispose()
                for line in lines:
                    line.Dispose()
        candidate.update(collisions=collisions,obstacle_ids=[eid(e) for e,b,s in obstacles],
                         eps_z_m=[bottom,top],collision_volume_tolerance_m3=1e-9,
                         exact_boolean_tests=exact_boolean_tests,
                         volume_semantics='sum of solid intersections; not union volume',
                         clearance_scope='current walls, framing and columns; linked models and other categories excluded')
    result={'ok':True,'action':'inspect','floor':describe(floor),'profile_m':points[0],'height_m':h,
            'profile_size_m':[lx,ly],'solid_volume_m3':volume,'profile_prism_m3':lx*ly*h,
            'void_cutters':[int(i.Value) for i in DB.InstanceVoidCutUtils.GetCuttingVoidInstances(floor)],
            'rebar_ids':[eid(e) for e in DB.FilteredElementCollector(doc).OfClass(DB.Structure.Rebar) if e.GetHostId()==floor.Id],
            'edges':edges,'chords':chords,'supports':supports,'neighbors':neighbors,
            'probe_z_m':z,'probe_below_soffit_m':.001,'engineering_continuity_verified':False,
            'support_categories':['StructuralFraming','StructuralColumns'],'walls_included':False,
            'gaps_meaning':'between probed framing/column faces, not a complete load path analysis',
            'rib_candidate':candidate,'modified_before':modified_before,
            'warnings':len(list(doc.GetWarnings())),'modified':bool(doc.IsModified)}
    if bool(doc.IsModified)!=modified_before or doc.IsModifiable:
        raise ValueError('Document state changed during read-only audit')
    return result


def run(doc, uidoc, DB, P):
    resources=[]
    try:
        return _run(doc,uidoc,DB,P,resources)
    finally:
        for geometry in reversed(resources):
            geometry.Dispose()
