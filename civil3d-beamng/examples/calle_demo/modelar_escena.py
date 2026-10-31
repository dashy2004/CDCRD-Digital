"""Native TIN finish surfaces and true block references for the R02 demo."""
import json
import math
import time
from construir_base import ROOT, OUT, STATE, state, call, b

L=state['eje']['longitud_m']
A=math.pi/6
ARC=120*A
D=120*(1-math.cos(A))
BS=112.0
BO=1.05

def axis(s):
    if s<=40: return 0,s,0
    if s<=40+ARC:
        t=(s-40)/120
        return 120*(1-math.cos(t)),40+120*math.sin(t),t
    if s<=40+2*ARC:
        u=(s-40-ARC)/120
        t=A-u
        return D+120*(math.cos(t)-math.cos(A)),100+120*(math.sin(A)-math.sin(t)),t
    return 2*D,160+s-40-2*ARC,0

def grade(s):
    pvis=[[0,100],[55,101.1],[125,100],[L,102.3]]
    for i,length in [(1,32),(2,44)]:
        st,z=pvis[i]; start=st-length/2; end=st+length/2
        if start<=s<=end:
            ga=(z-pvis[i-1][1])/(st-pvis[i-1][0]); gb=(pvis[i+1][1]-z)/(pvis[i+1][0]-st)
            u=s-start
            return z-ga*length/2+ga*u+(gb-ga)*u*u/(2*length)
    for (s0,z0),(s1,z1) in zip(pvis,pvis[1:]):
        if s<=s1+1e-8:return z0+(z1-z0)*(s-s0)/(s1-s0)
    raise ValueError(s)

def depression(s,o):
    u=(s-BS)/1.375; v=(o-BO)/.895
    r=math.hypot(u,v); t=math.atan2(v,u)
    edge=.91+.045*math.sin(5*t)+.025*math.cos(9*t)+.018*math.sin(13*t)
    q=r/edge
    if q>=1:return 0
    # Central bottom with a narrower, visibly broken transition at the edge.
    return .0635*(1-q**6)**1.4

def xyz(s,o,dz=0, damaged=False):
    x,y,t=axis(s)
    return [x+o*math.cos(t),y-o*math.sin(t),grade(s)+dz-(depression(s,o) if damaged else 0)]

def bounds(offsets,step=1):
    ss=[min(i*step,L) for i in range(math.ceil(L/step)+1)]
    return [xyz(s,offsets[0]) for s in ss]+[xyz(s,offsets[1]) for s in reversed(ss)]

def invoke(h,method,args=None,path=None):
    p={'handle':h,'metodo':method,'profundidad':0}
    if args is not None:p['args']=args
    if path:p['ruta']=path
    return call('objects.invoke',p,True)

def style(name,color):
    r=call('estilos.crear',{'familia':'SurfaceStyles','nombre':name,'base':'Border Only'},True)
    for view in ['Model', 'Plan']:
        call('estilos.display',{'familia':'SurfaceStyles','estilo':name,'vista':view,'componente':'Triangles','visible':True,'color_rgb':color},True)
        call('estilos.display',{'familia':'SurfaceStyles','estilo':name,'vista':view,'componente':'Boundary','visible':False},True)
    return r

def surface(key,name,layer,pts,style_name,boundary=None,kind='Outer'):
    assert key not in state, key+' already created; resume explicitly'
    r=call('superficie.crear',{'nombre':name,'capa':layer,'estilo':style_name},True,key)
    h=r['handle']
    invoke(h,'AddVertices',[pts])
    if boundary:invoke(h,'AddBoundaries',[boundary,.05,kind,True],'BoundariesDefinition')
    invoke(h,'Rebuild')
    return h

def validate_axis():
    checks=[]
    for s in [0,25,40,55,70,90,102.83185307179588,BS,125,145,170,200,L]:
        r=b.llamar('objects.invoke',{'handle':state['eje']['handle'],'metodo':'PointLocation','args':[s,1.05,None,None]})['resultado']['salidas']
        z=b.llamar('objects.invoke',{'handle':state['rasante']['handle'],'metodo':'ElevationAt','args':[s]})['resultado']
        p=xyz(s,1.05)
        error=max(abs(p[0]-r['easting']),abs(p[1]-r['northing']),abs(p[2]-z))
        assert error<1e-7, (s,error)
        checks.append({'station':s,'error_m':error})
    (OUT/'VERIFICACION_EJE_RASANTE.json').write_text(json.dumps(checks,indent=2))

def finish():
    validate_axis()
    for n,c in [('CDX2_ASFALTO',[69,72,76]),('CDX2_HIERBA',[111,139,85]),('CDX2_HORMIGON',[178,175,161]),('CDX2_BACHE',[90,75,59])]:
        style(n,c)
    # The finished pavement samples the actual native horizontal and vertical design.
    stations=sorted(set([min(i*.5,L) for i in range(math.ceil(L/.5)+1)]+[round(BS-1.7+i*.04,6) for i in range(86)]))
    pts=[]; patch=[]
    for s in stations:
        offsets=[-3.6,-3,-2,-1,0,1,2,3,3.6]
        if abs(s-BS)<=1.7:offsets=sorted(set(offsets+[round(BO-1.1+i*.04,6) for i in range(56)]+[BO]))
        for o in offsets:
            p=xyz(s,o,-.02*abs(o),True);pts.append(p)
            if depression(s,o)>.0001:patch.append([p[0],p[1],p[2]+.0008])
    # Exact center is a mandatory sampled vertex.
    pts.append(xyz(BS,BO,-.02*BO,True))
    surface('pavimento','CDX2_PAVIMENTO_CON_BACHE','CDX2-PAVIMENTO',pts,'CDX2_ASFALTO',bounds([-3.6,3.6]))
    surface('bache_visible','CDX2_FONDO_BACHE','CDX2-BACHE',patch,'CDX2_BACHE')
    # Gutters, raised curb and walk are separate Civil surfaces; offset widths in metres.
    for side,label in [(-1,'IZQ'),(1,'DER')]:
        p=[]
        for s in [min(i*.5,L) for i in range(math.ceil(L/.5)+1)]:
            for o,dz in [(3.6,-.072),(3.92,-.085),(3.94,.065),(4.1,.065),(5.9,.10)]:
                p.append(xyz(s,side*o,dz))
        surface('acera_'+label,'CDX2_ACERA_CONTEN_'+label,'CDX2-ACERAS',p,'CDX2_HORMIGON',bounds(sorted([side*3.6,side*5.9])))
    # Native terrain with an opening for the roadway, preserving the target surface.
    original=json.loads((ROOT/'terreno_puntos.json').read_text())
    # Nearest station projection on the analytically verified axis; blend adjacent verge.
    centers=[(s,*axis(s)[:2]) for s in [i*.5 for i in range(math.floor(L/.5)+1)]]
    ground=[]
    for x,y,z in original:
        s,xc,yc=min(centers,key=lambda p:(p[1]-x)**2+(p[2]-y)**2)
        _,_,t=axis(s); o=(x-xc)*math.cos(t)-(y-yc)*math.sin(t)
        inside=0<y<210 and abs(o)<5.9
        if inside:continue
        distance=math.hypot(x-xc,y-yc)
        if 0<s<L-.6 and distance<13:
            w=max(0,min(1,(distance-5.9)/7.1))
            z=(grade(s)+.10)*(1-w)+z*w
        ground.append([x,y,z])
    for side in [-1,1]:
        ground += [xyz(min(i,L),side*5.9,.10) for i in range(math.ceil(L)+1)]
    surface('terreno_visible','CDX2_TERRENO_ESCENA','CDX2-TERRENO',ground,'CDX2_HIERBA',bounds([-5.9,5.9]),'Hide')
    # Original corridor and target remain available for editing without filling the defect.
    for h in [state['terreno']['handle'],state['corredor']['superficie']]:
        call('objects.update',{'handle':h,'props':{'Layer':'CDX2-AUX'}},True)
    auxiliary = [state[key]['handle'] for key in ['terreno','corredor','eje','rasante','perfil_terreno','ensamblaje']]
    auxiliary += [state['corredor']['superficie']] + [item['handle'] for item in state['ensamblaje']['subensamblajes']]
    for handle in auxiliary:
        call('objects.update', {'handle':handle, 'props':{'Visible':False}}, True)
    # Civil alignment label groups are independent entities on a template layer.
    # This example owns the previously empty drawing; hide their graphics too.
    labels = call('objects.query', {'tipo':'Alignment', 'limite':500})
    if labels.get('truncado'):
        raise RuntimeError('Inspeccione las etiquetas antes de ocultarlas: consulta truncada.')
    for label in labels['objetos']:
        if label['tipo'].endswith('LabelGroup'):
            call('objects.update', {'handle':label['handle'], 'props':{'Visible':False}}, True)
    call('layers.set',{'nombres':['CDX2-AUX','CDX2-EJE','CDX2-RASANTE','CDX2-CORREDOR'],'apagada':True},True)
    call('vista.3d',{'direccion':[1,-1,.8],'objetivo':[15,107,101],'ancho':260,'alto':180,'estilo_visual':'Shaded'},True)
    call('doc.save',{'ruta':str(OUT/'CALLE_REALISTA_R02.dwg')},True)
