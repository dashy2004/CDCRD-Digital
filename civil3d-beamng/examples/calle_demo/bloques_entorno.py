"""Reusable native 3D blocks, placed using the verified Civil alignment."""
import math
import time
import json
from modelar_escena import *

BASE=[0,0,0]

def box(x,y,z,dx,dy,dz,color):
    return {'tipo':'caja','esquina':[BASE[0]+x,BASE[1]+y,z],'dx':dx,'dy':dy,'dz':dz,'color':color,'capa':'0'}

def cylinder(x,y,z,r,h,color):
    return {'tipo':'cilindro','base':[BASE[0]+x,BASE[1]+y,z],'radio':r,'altura':h,'color':color,'capa':'0'}

def block(name,entities,spheres=None):
    if name in state:
        raise RuntimeError('Definicion ya creada; no se redefine automaticamente.')
    rows = list(entities)
    for x,y,z,r,color in spheres or []:
        rows.append({'tipo':'esfera','centro':[x,y,z],'radio':r,'color':color,'capa':'0'})
    return call('blocks.create', {'nombre':name, 'entidades':rows}, True, name)

def definitions():
    lamp=[cylinder(0,0,0,.20,.3,[100,104,110]),cylinder(0,0,.3,.09,6,[72,77,84]),
          box(-.07,-1.5,6.15,.14,1.6,.12,[72,77,84]),box(-.23,-1.8,6.06,.46,.72,.11,[190,194,180])]
    block('CDX2_LUMINARIA_3D',lamp)
    house=[box(-4.5,0,-.15,9,8,.25,[157,153,141]),box(-4,1,0,8,6,3.3,[210,193,159]),
           box(-4.25,.75,3.3,8.5,6.5,.2,[180,177,165]),box(-4.25,.75,3.5,8.5,.15,.38,[213,202,179]),
           box(-4.25,7.1,3.5,8.5,.15,.38,[213,202,179]),box(-4.25,.75,3.5,.15,6.5,.38,[213,202,179]),
           box(4.1,.75,3.5,.15,6.5,.38,[213,202,179]),box(-.5,.96,0,1, .07,2.2,[87,69,52])]
    for x in [-2.8,1.6]:
        house+=[box(x,.94,1.05,1.4,.09,1.15,[70,106,123]),box(x-.08,.9,.98,1.56,.13,.08,[235,232,218]),
                box(x+.67,.84,1.05,.04,.08,1.15,[223,222,211])]
    house += [box(-1.2,-.6,2.65,2.4,1.65,.16,[199,193,173]),cylinder(-1.05,-.45,0,.07,2.65,[220,214,199]),
              cylinder(1.05,-.45,0,.07,2.65,[220,214,199]),cylinder(2.5,5.8,3.5,.55,.9,[53,59,65])]
    block('CDX2_VIVIENDA_3D',house)
    block('CDX2_ARBOL_3D',[cylinder(0,0,0,.2,3.4,[98,75,50])],
          [(0,0,4.1,1.8,96),(-1.0,.25,3.5,1.25,94),(.9,-.35,3.7,1.35,92),(0,.3,5.1,1.25,96)])
    block('CDX2_SENAL_3D',[cylinder(0,0,0,.04,2.6,[110,116,122]),box(-.36,-.05,1.8,.72,.1,.72,[232,176,43])])
    block('CDX2_BANCO_3D',[box(-.8,-.21,.43,1.6,.42,.09,[137,96,60]),box(-.8,.14,.52,1.6,.08,.43,[137,96,60]),
                          box(-.65,-.17,0,.09,.33,.43,[69,73,76]),box(.56,-.17,0,.09,.33,.43,[69,73,76])])
    grate=[box(-.3,-.4,-.06,.6,.8,.07,[53,61,64])]
    for i in range(7):grate.append(box(-.27,-.36+i*.11,.012,.54,.045,.015,[117,125,126]))
    block('CDX2_IMBORNAL_3D',grate)

def place():
    assert 'instancias' not in state,'Already placed'
    ents=[]; placements=[]
    def insert(name,s,o,zextra=0,scale=1,face_road=True):
        x,y,t=axis(s); point=xyz(s,o,zextra)
        if abs(o)>6.1:
            point[2]=b.llamar('objects.invoke',{'handle':state['terreno_relieve']['handle'],'metodo':'FindElevationAtXY','args':point[:2]})['resultado']
        # Front of the house faces -localY. Right side faces inward toward the road.
        rot=-math.degrees(t)+(-90 if o>0 else 90) if face_road else -math.degrees(t)
        ents.append({'tipo':'bloque','nombre':name,'punto':point,'rotacion':rot,'escala':scale,'capa':'CDX2-ENTORNO'})
        placements.append({'bloque':name,'estacion':s,'offset':o,'xyz':point})
    for s in [23,58,94,132,171,204]:
        for side in [-1,1]:insert('CDX2_LUMINARIA_3D',s,side*5.5,.092)
    for s,side in [(28,-1),(68,-1),(121,-1),(166,-1),(198,-1),(40,1),(83,1),(147,1),(190,1)]:
        insert('CDX2_VIVIENDA_3D',s,side*11)
    for i,(s,side) in enumerate([(16,1),(50,-1),(75,1),(105,-1),(138,1),(158,-1),(181,1),(209,-1)]):
        insert('CDX2_ARBOL_3D',s,side*7.4,scale=.85+.12*(i%3))
    for i in range(22):insert('CDX2_ARBOL_3D',8+i*9.3,(-1 if i%2 else 1)*(23+(i%4)*4),scale=.8+.15*(i%4))
    for s in [93,137]:insert('CDX2_SENAL_3D',s,5.4,.09,face_road=False)
    for s in [54,153]:insert('CDX2_BANCO_3D',s,-5.3,.09)
    for s in [61,126,183]:
        for side in [-1,1]:insert('CDX2_IMBORNAL_3D',s,side*3.65,-.085,face_road=False)
    r=call('entity.create',{'entidades':ents},True,'instancias')
    assert not r['errores'],r['errores']
    (OUT/'BLOQUES_COLOCADOS.json').write_text(json.dumps(placements,indent=2))
