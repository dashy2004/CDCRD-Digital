import math
import json
from modelar_escena import *

def stripe(key,s0,s1,o0,o1,style_name):
    stations=[s0+(s1-s0)*i/max(1,math.ceil((s1-s0)/.5)) for i in range(max(1,math.ceil((s1-s0)/.5))+1)]
    rows=[xyz(s,o,-.02*abs(o)+.003,True) for s in stations for o in [o0,o1]]
    border=[xyz(s,o0) for s in stations]+[xyz(s,o1) for s in reversed(stations)]
    return surface(key,'CDX2_'+key.upper(),'CDX2-MARCAS',rows,style_name,border)

def markings():
    style('CDX2_PINTURA_BLANCA',[235,232,214]);style('CDX2_PINTURA_AMARILLA',[233,183,49])
    for i,s in enumerate(range(4,211,6)):
        stripe('eje_marca_%02d'%i,s,s+3,-.065,.065,'CDX2_PINTURA_AMARILLA')
    for side,label in [(-1,'izq'),(1,'der')]:
        stripe('borde_'+label,0,L,side*3.35-.055,side*3.35+.055,'CDX2_PINTURA_BLANCA')
    # Two pedestrian crossings away from the pothole, only conceptual placement.
    for s in [19,184]:
        for i in range(8):
            o=-3.15+i*.82
            stripe('paso_%d_%d'%(s,i),s,s+3,o,o+.4,'CDX2_PINTURA_BLANCA')
    # Pathways connect front doors to the sidewalk and follow local grade.
    placements=json.loads((OUT/'BLOQUES_COLOCADOS.json').read_text())
    for i,rec in enumerate(placements):
        if rec['bloque']!='CDX2_VIVIENDA_3D':continue
        s,o=rec['estacion'],rec['offset']; side=1 if o>0 else -1
        pts=[]
        for ds in [-1,1]:
            for off in [side*5.9,side*10.4]:
                p=xyz(s+ds,off)
                p[2]=(grade(s+ds)+.106 if abs(off)<6 else rec['xyz'][2]+.015)
                pts.append(p)
        surface('acceso_%d'%i,'CDX2_ACCESO_%d'%i,'CDX2-ACERAS',pts,'CDX2_HORMIGON')

def terrain_relief():
    # Preserve the native target TIN; rebuild the visible landscape with lateral hills.
    original=json.loads((ROOT/'terreno_puntos.json').read_text())
    centers=[(s,*axis(s)[:2]) for s in [i*.5 for i in range(math.floor(L/.5)+1)]]
    ground=[]
    for x,y,z in original:
        s,xc,yc=min(centers,key=lambda p:(p[1]-x)**2+(p[2]-y)**2)
        _,_,t=axis(s);o=(x-xc)*math.cos(t)-(y-yc)*math.sin(t)
        if 0<y<210 and abs(o)<5.9:continue
        distance=math.hypot(x-xc,y-yc)
        if 0<s<L-.6 and distance<13:
            w=max(0,min(1,(distance-5.9)/7.1));z=(grade(s)+.10)*(1-w)+z*w
        blend=max(0,min(1,(abs(o)-18)/14))
        z+=blend*(7*math.exp(-((x+25)/28)**2-((y-125)/46)**2)+5*math.exp(-((x-75)/30)**2-((y-190)/40)**2))
        ground.append([x,y,z])
    for side in [-1,1]:ground += [xyz(min(i,L),side*5.9,.10) for i in range(math.ceil(L)+1)]
    h=surface('terreno_relieve','CDX2_TERRENO_RELIEVE_FINAL','CDX2-TERRENO',ground,'CDX2_HIERBA',bounds([-5.9,5.9]),'Hide')
    call('objects.update',{'handle':state['terreno_visible']['handle'],'props':{'Visible':False}},True)
    (OUT/'TERRENO_CONTROL.json').write_text(json.dumps({'min_z':min(p[2] for p in ground),'max_z':max(p[2] for p in ground),'puntos':len(ground),'tipo':'relieve sintetico, sin levantamiento topografico'},indent=2))
