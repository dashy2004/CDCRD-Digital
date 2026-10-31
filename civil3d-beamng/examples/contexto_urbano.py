"""Create two illustrative urban Civil 3D drawings through native APIs.

Dimensions are explicit assumptions, not a survey or a crash reconstruction.
Requires the local Civil bridge, pywin32, and an empty/new owned drawing.
"""
import argparse
import json
import math
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'servidor-mcp-civil3d/src'))
import puente_cliente as bridge


def box(x,y,z,dx,dy,dz,c,layer='CDX-CONTEXTO'):
    return dict(tipo='caja',esquina=[x,y,z],dx=dx,dy=dy,dz=dz,color=c,capa=layer)


def cylinder(x,y,z,r,h,c,layer='CDX-CONTEXTO'):
    return dict(tipo='cilindro',base=[x,y,z],radio=r,altura=h,color=c,capa=layer)


def line(points,c,layer='CDX-CONTEXTO',width=0):
    if width:
        return dict(tipo='polilinea',puntos=points,elevacion=points[0][2],ancho=width,color=c,capa=layer)
    return dict(tipo='polilinea3d',puntos=points,color=c,capa=layer)


def text(value,x,y,size=.65,color=(35,52,69)):
    return dict(tipo='texto',texto=value,punto=[x,y,115],altura=size,color=list(color),capa='CDX-PLANO')


class Scene:
    def __init__(self, output, template, case, resume_empty=False):
        self.output=Path(output).resolve()/case
        self.output.mkdir(parents=True,exist_ok=resume_empty)
        self.case=case
        self.receipt={'case':case,'illustrative':True,'surveyed':False,'operations':[],'views':{}}
        creation=self.output/'creation.json'
        if resume_empty:
            new=json.loads(creation.read_text())
        else:
            new=bridge.llamar_con_aprobacion('doc.new',{'plantilla':str(Path(template).resolve())})
            creation.write_text(json.dumps(new))
        self.expected=new['dibujo']
        info=bridge.llamar('doc.info',{})
        if info['dibujo']!=self.expected or not info.get('civil3d'):
            raise RuntimeError('New Civil drawing not confirmed')
        if bridge.llamar('objects.query',{'limite':1})['coincidencias']:
            raise RuntimeError('Template has model objects; refusing to change it')
        import win32com.client
        self.app=win32com.client.GetActiveObject('AutoCAD.Application.26')
        self.doc=self.app.ActiveDocument
        self.guard()
        if self.doc.Name!=Path(self.expected).name:
            raise RuntimeError('COM and bridge active drawings differ')
        self.doc.SetVariable('INSUNITS',6)
        self.doc.SetVariable('GRIDMODE',0)
        self.doc.SetVariable('UCSICON',0)
        self.doc.SetVariable('FACETRES',5)
        self.doc.TextStyles.Item('Standard').SetFont('Arial',False,False,0,34)
        self.call('entity.create',{'entidades':[dict(tipo='capa',nombre=n,color=c) for n,c in [
            ('CDX-CONTEXTO',[170,160,148]),('CDX-CALZADA',[99,102,104]),
            ('CDX-VEHICULOS',[45,100,170]),('CDX-BACHE',[95,76,57]),
            ('CDX-PLANO',[30,55,73]),('CDX-TRAYECTORIAS',[237,138,40]),
            ('CDX-INGENIERIA',[120,130,140])]]})

    def guard(self):
        if bridge.llamar('doc.info',{})['dibujo']!=self.expected:
            raise RuntimeError('Active drawing changed; stopped before write')

    def call(self,method,params,write=True):
        if write:self.guard()
        pending=self.output/'pending.json'
        pending.write_text(json.dumps({'method':method,'state':'pending'}))
        result=(bridge.llamar_con_aprobacion if write else bridge.llamar)(method,params)
        if isinstance(result,dict) and (result.get('errores') or result.get('fallidos')):
            raise RuntimeError(str(result))
        entry={'method':method,'result':result}
        with (self.output/'operations.jsonl').open('a',encoding='utf-8') as stream:
            stream.write(json.dumps(entry,ensure_ascii=False)+'\n')
        pending.write_text(json.dumps({'method':method,'state':'responded'}))
        print(method,flush=True)
        return result

    def entities(self,rows):
        handles=[]
        for start in range(0,len(rows),180):
            handles+=self.call('entity.create',{'entidades':rows[start:start+180]})['creados']
        return handles

    def surface(self,name,points,color,boundary=None):
        style='CDX_'+name+'_STYLE'
        self.call('estilos.crear',dict(familia='SurfaceStyles',nombre=style,base='Border Only'))
        for view in ['Plan','Model']:
            for component,visible in [('Triangles',True),('Boundary',False)]:
                self.call('estilos.display',dict(familia='SurfaceStyles',estilo=style,vista=view,
                    componente=component,visible=visible,color_rgb=color))
        handle=self.call('superficie.crear',dict(nombre='CDX_'+name,capa='CDX-CALZADA',estilo=style))['handle']
        self.call('objects.invoke',dict(handle=handle,metodo='AddVertices',args=[points],profundidad=0))
        if boundary:
            self.call('objects.invoke',dict(handle=handle,ruta='BoundariesDefinition',metodo='AddBoundaries',
                args=[boundary,.05,'Outer',True],profundidad=0))
        self.call('objects.invoke',dict(handle=handle,metodo='Rebuild',profundidad=0))
        return handle

    def block(self,name,rows,rotations=()):
        result=self.call('blocks.create',dict(nombre=name,entidades=rows))
        # Native AutoCAD ActiveX rotates wheel solids within our new definition.
        # It avoids screen commands and preserves independent block references.
        import pythoncom
        from win32com.client import VARIANT
        def pt(values):return VARIANT(pythoncom.VT_ARRAY|pythoncom.VT_R8,values)
        for index,center in rotations:
            self.guard()
            solid=self.doc.HandleToObject(result['entidades'][index])
            solid.Rotate3D(pt(center),pt([center[0],center[1]+1,center[2]]),math.pi/2)
        return name

    def definitions(self):
        dark=[33,36,39];metal=[170,177,182];blue=[37,91,161]
        wheels=[];rot=[]
        for y in [-.72,.72]:
            for radius,width,c in [(.31,.14,dark),(.21,.145,metal),(.07,.15,dark)]:
                rot.append((len(wheels),[0,y,.32]))
                wheels.append(cylinder(0,y,.32-width/2,radius,width,c))
        bike=wheels+[box(-.12,-.6,.59,.24,.87,.13,dark),box(-.15,-.12,.53,.3,.47,.3,blue),
            box(-.12,-.48,.32,.24,.5,.25,metal),box(-.34,.5,1,.68,.055,.05,dark),
            box(-.16,.69,.74,.32,.1,.22,[231,222,178])]
        for x in [-.08,.08]:
            bike+=[line([[x,.72,.32],[x,.38,.96]],metal),line([[x,-.72,.32],[x,-.28,.63]],metal)]
        for x in [-.34,.34]:bike+=[line([[x,.5,1],[x,.51,1.25]],metal),box(x-.07,.49,1.23,.14,.04,.08,dark)]
        self.block('CDX_MOTO',bike,rot)
        self.block('CDX_ARBOL',[cylinder(0,0,0,.14,3.1,[107,87,63])]+[
            dict(tipo='esfera',centro=[x,y,z],radio=r,color=c) for x,y,z,r,c in [
            (0,0,4,1.7,[76,113,63]),(1,.2,3.5,1.1,[92,132,72]),(-.8,.3,4.6,1.1,[66,108,60])]])
        car=[box(-.85,-2,.4,1.7,4,.65,[139,149,153]),box(-.79,-.8,1.05,1.58,1.8,.8,[139,149,153]),
            box(-.75,1.02,1.15,1.5,.025,.55,[56,77,90]),box(-.80,-.65,1.2,.02,1.5,.5,[56,77,90]),
            box(.78,-.65,1.2,.02,1.5,.5,[56,77,90]),box(-.75,-.82,1.2,1.5,.02,.5,[56,77,90])]
        carrot=[]
        for x in [-.84,.84]:
            for y in [-1.3,1.3]:
                carrot.append((len(car),[x,y,.4]));car.append(cylinder(x,y,.29,.36,.22,dark))
        self.block('CDX_SUV',car,carrot)
        van=[box(-.92,-2.25,.45,1.84,4.5,1.9,[230,228,215]),
             box(-.8,2.255,1.3,1.6,.02,.8,[49,72,89])]
        vanrot=[]
        for x in [-.92,.92]:
            for y in [-1.5,1.5]:vanrot.append((len(van),[x,y,.4]));van.append(cylinder(x,y,.29,.36,.22,dark))
        self.block('CDX_VAN',van,vanrot)

    def insert(self,name,x,y,rotation=0,z=100,scale=1):
        return dict(tipo='bloque',nombre=name,punto=[x,y,z],rotacion=rotation,escala=scale,capa='CDX-VEHICULOS')

    def house(self,x,y,w,d,c,second=False,shop=False):
        # Front faces south; geometric details remain editable native solids.
        h=6.1 if second else 3.2
        rows=[box(x,y,100,w,d,h,c),box(x-.15,y-.18,100+h,w+.3,d+.3,.18,[183,180,169])]
        for j in range(2):
            xx=x+.6+j*(w-2.2)
            rows +=[box(xx,y-.04,101.1,1.15,.08,1.25,[63,88,99])]
            for k in range(5):rows.append(box(xx+k*.25,y-.09,101.08,.025,.04,1.3,[220,215,201]))
        rows.append(box(x+w/2-.5,y-.08,100,1,.09,2.2,[77,71,65]))
        if second:
            rows +=[box(x+.5,y-.1,104,1.25,.1,1.25,[57,83,98]),box(x+w-1.9,y-.1,104,1.25,.1,1.25,[57,83,98]),
                    box(x-.05,y-.65,103.1,w+.1,.75,.14,[210,207,192])]
        if shop:
            rows +=[box(x+.35,y-.15,100.1,w-.7,.15,2.5,[79,77,73]),box(x-.1,y-.8,102.9,w+.2,1,.12,c)]
            for k in range(12):rows.append(box(x+.35,y-.17,100.15+k*.2,w-.7,.025,.025,[158,154,141]))
        return rows

    def build(self):
        self.definitions()
        case_a=self.case=='A_CALLE_BACHE'
        xmin,xmax=(-40,40);half=3.25 if case_a else 3.6
        self.receipt['assumptions']={'road_width_m':2*half,'length_m':80,'pothole_depth_m':.0635 if case_a else None,
            'horizontal_unreferenced':True,'elevation_datum_arbitrary_m':100,'slope':0}
        rows=[box(-43,-16,99.5,86,54 if not case_a else 32,.26,[151,144,126])]
        points=[];patch=[]
        for i in range(161):
            x=xmin+i*.5
            ys=[-half+j*(half*2)/20 for j in range(21)]
            if case_a and -2<x<2:ys=sorted(set(ys+[-1.8+j*.08 for j in range(20)]))
            for y in ys:
                q=math.hypot(x/1.3,(y+1.05)/.85)
                dep=.0635*max(0,1-q**6)**1.4 if case_a and q<1 else 0
                p=[x,y,100-dep];points.append(p)
                if dep>.001:patch.append([x,y,100-dep+.001])
        if case_a:points.append([0,-1.05,100-.0635])
        road=self.surface('CALZADA',points,[103,106,107])
        if patch:self.surface('FONDO_BACHE',patch,[83,68,50])
        if not case_a:
            side=[[x,y,100] for x in [-3.2,-1.6,0,1.6,3.2] for y in [3.6+i*.5 for i in range(70)]]
            self.surface('CALLE_LATERAL',side,[108,110,110])
        for side in [-1,1]:
            for i in range(20):
                x=-40+i*4
                if not case_a and side==1 and -8<=x<=4:continue
                yy=side*(half+1.0)-.75
                rows.append(box(x,yy,100,3.95,1.5,.14,[185,177,159]))
                if not (case_a and side==-1 and x in [-4,0]):
                    rows.append(box(x,side*(half+.1)-.09,99.98,3.95,.18,.18,[195,189,174]))
        # Broken edge and gravel remain a separate native detail, with no implied survey.
        rng=random.Random(41)
        if case_a:
            rows +=[box(-3,-4.35,99.97,6,.7,.055,[123,105,82])]
            rows +=[box(x,-3.44,99.97,w,.18,h,[187,177,156]) for x,w,h in
                    [(-4,.7,.18),(-2.8,.4,.1),(-1.5,.25,.07),(.5,.45,.09),(2,.6,.16),(3.3,.65,.18)]]
            for _ in range(100):
                x=rng.uniform(-3,3);y=rng.uniform(-4.5,-3.5)
                rows.append(box(x,y,100,rng.uniform(.03,.13),rng.uniform(.03,.15),rng.uniform(.02,.08),[155,146,126]))
        palette=[[176,57,52],[215,162,167],[207,194,161],[204,169,80],[166,192,181],[163,167,164]]
        for i,x in enumerate(range(-39,40,10)):
            if not case_a and -10<=x<=4:continue
            rows+=self.house(x,5.3 if case_a else 5.6,8.8,7,palette[i%len(palette)],second=(i%3==0),shop=(i%3==1))
        # South edge is kept sparse enough to see the road from the reference-camera side.
        for i,x in enumerate([-35,-22,17,30]):
            rows+=self.house(x,-14,8.7,7,palette[(i+2)%len(palette)],shop=(i==1))
        if not case_a:
            rows+=self.house(5.5,16,8,8,[205,167,72],True)
            rows+=self.house(-15,20,9,9,[174,61,62])
            for side in [-1,1]:rows.append(box(side*4.4-.6,8,100,1.2,29,.14,[185,177,159]))
            # Rounded corner represented by an arc of curb solids via native block references.
            curb=self.block('CDX_CURVA_CONTEN',[box(-.3,-.1,0,.6,.2,.18,[195,189,174])])
            for side in [-1,1]:
                for j in range(10):
                    a=math.pi+j*math.pi/18 if side==1 else -math.pi/2+j*math.pi/18
                    cx=6.2 if side==1 else -6.2
                    rows.append(self.insert(curb,cx+3*math.cos(a),6.6+3*math.sin(a),math.degrees(a)+90))
        for x in [-33,-12,12,34]:
            rows +=[cylinder(x,4.8,100,.14,7,[150,145,132]),box(x-.8,4.72,106.7,1.6,.16,.13,[108,99,84])]
            rows +=[self.insert('CDX_ARBOL',x+3,13,scale=1.1)]
        for y,z in [(4.8,106.7),(4.5,106.4),(5.1,106.5)]:
            rows.append(line([[x,y,z-.5*math.sin(math.pi*(x+33)/21)**2] for x in range(-33,35)], [57,60,59]))
        if case_a:
            rows +=[self.insert('CDX_SUV',-8,-3.5,-90),self.insert('CDX_VAN',-25,-1.6,-90),
                    self.insert('CDX_MOTO',10,1.6,90),self.insert('CDX_MOTO',27,-1.5,-90)]
        else:
            rows +=[self.insert('CDX_SUV',16,-1.7,-90),self.insert('CDX_MOTO',-.9,14,180)]
            rows +=[self.insert('CDX_MOTO',-17+i*1.3,-5.2,-35) for i in range(8)]
        self.entities(rows)
        axis=self.entities([dict(tipo='polilinea',puntos=[[-40,0],[40,0]],capa='CDX-INGENIERIA')])[0]['handle']
        alignment=self.call('civil.alineamiento_polilinea',dict(polilinea=axis,nombre='CDX_EJE_APROX',estacion_inicial=0,capa='CDX-INGENIERIA'))
        self.call('civil.perfil_pvi',dict(alineamiento='CDX_EJE_APROX',nombre='CDX_RASANTE_SUPUESTA',pvis=[[0,100],[80,100]],capa='CDX-INGENIERIA'))
        # The empty template is ours; hide automatically generated alignment labels for the views.
        labels=self.call('objects.query',dict(tipo='Alignment',limite=500),False)
        if labels.get('truncado'):raise RuntimeError('Label query truncated')
        for obj in labels['objetos']:
            if obj['tipo'].endswith('LabelGroup'):self.call('objects.update',dict(handle=obj['handle'],props={'Visible':False}))
        self.call('layers.set',dict(nombres=['CDX-INGENIERIA'],apagada=True))
        self.receipt['native_road_surface']=road
        self.receipt['alignment']=alignment
        z=self.call('objects.invoke',dict(handle=road,metodo='FindElevationAtXY',args=[0,-1.05]),False)['resultado']
        self.receipt['pothole_elevation_readback']=z
        # Plan annotations and trajectories are explanatory overlays on separate native layers.
        title='01 / CALLE Y BORDE DETERIORADO' if case_a else '02 / ESQUINA Y CIRCULACION DE MOTOS'
        anno=[text(title,-37,25 if case_a else 41,1.2),text('APROXIMACION VISUAL | CIVIL 3D | NO ES UN LEVANTAMIENTO',-37,22.8 if case_a else 39.2,.55),
              text('Dimensiones supuestas. Trayectorias ilustrativas; no reconstruyen un accidente real.',-37,-20,.55),
              text('Calzada supuesta: '+str(2*half)+' m',-37,-18,.6),
              text('Escala del modelo (m)',24,-18,.55)]
        anno +=[line([[24,-19,115],[34,-19,115]],[36,61,74],'CDX-PLANO',.08),text('0',24,-20,.45),text('10',33.5,-20,.45)]
        if case_a:
            path=[[-25,-1.6,114],[-10,-1.6,114],[-4,1.1,114],[6,1.4,114],[16,-1.6,114]]
            anno +=[text('Bache de prueba: 6.35 cm',-7,-10,.7),text('Borde roto / grava',-7,-12,.6),
                line([[0,-8.8,115],[0,-1.05,115]],[194,90,45],'CDX-PLANO',.08),
                text('Esquiva hipotetica',-34,-9,.65)]
        else:
            path=[[-1,28,114],[-1,10,114],[-1,2,114],[4,-1.5,114],[17,-1.5,114]]
            anno +=[text('Cruce hipotetico',8,17,.7),text('Motos estacionadas',-29,-11,.65),
                line([[-19,-9.5,115],[-13,-5.2,115]],[36,61,74],'CDX-PLANO',.08)]
        anno.append(line(path,[230,125,34],'CDX-TRAYECTORIAS',.22))
        x,y,z=path[-1];anno.append(line([[x-1.5,y+.8,z],[x,y,z],[x-1.5,y-.8,z]],[230,125,34],'CDX-TRAYECTORIAS',.22))
        self.entities(anno)
        self.save()

    def save(self):
        self.guard()
        target=self.output/(self.case+'.dwg')
        self.doc.SaveAs(str(target))
        self.expected=bridge.llamar('doc.info',{})['dibujo']
        self.receipt['drawing']=str(target)
        (self.output/'scene.json').write_text(json.dumps(self.receipt,ensure_ascii=False,indent=2),encoding='utf-8')

    def export(self):
        case_a=self.case=='A_CALLE_BACHE'
        views=[('PLANO',[0,0,1],[0,2 if case_a else 10,100],116 if not case_a else 87,65.25 if not case_a else 49,True),
               ('GENERAL',[.65,-1,1.25],[0,1,101],83,46.7,False),
               ('CALLE',[-.7,-1,.42],[0,2,101],43,24.2,False),
               ('DETALLE',[.4,-1,.65],[0,-1.2,100] if case_a else [-9,-3,100],12 if case_a else 30,6.75 if case_a else 16.875,False)]
        for name,direction,target,width,height,annotations in views:
            self.call('layers.set',dict(nombres=['CDX-PLANO','CDX-TRAYECTORIAS'],apagada=not annotations))
            params=dict(direccion=direction,objetivo=target,ancho=width,alto=height,estilo_visual='Shaded')
            self.call('vista.3d',params)
            self.call('vista.guardada',dict(nombre='CDX_'+name))
            self.receipt['views'][name]=params
            self.call('vista.exportar',dict(ruta=str(self.output/(name+'.png')),dispositivo='PublishToWeb PNG.pc3',
                papel='FHD_(1920.00_x_1080.00_Pixels)',nombre_vista='CDX_'+name,sombreado='AsDisplayed',rotacion='0'))
            if name=='PLANO':
                self.call('vista.exportar',dict(ruta=str(self.output/'PLANO.pdf'),dispositivo='DWG To PDF.pc3',
                    papel='ISO_full_bleed_A3_(420.00_x_297.00_MM)',nombre_vista='CDX_'+name,sombreado='AsDisplayed',rotacion='0'))
        view=self.call('vista.guardada',dict(nombre='CDX_PERSPECTIVA',direccion=[-22,-7,1],
            objetivo=[2,0,101.65],ancho=18,alto=10.125,estilo_visual='Shaded'))
        # Set the actual camera distance after the generic view helper normalizes direction.
        self.call('objects.update',dict(handle=view['handle'],props={'PerspectiveEnabled':True,
            'ViewDirection':[-22,-7,1],'Target':[2,0,101.65],'Width':18.0,'Height':10.125,'LensLength':35.0}))
        self.call('vista.activar',dict(nombre='CDX_PERSPECTIVA'))
        self.call('vista.exportar',dict(ruta=str(self.output/'PERSPECTIVA.png'),dispositivo='PublishToWeb PNG.pc3',
            papel='FHD_(1920.00_x_1080.00_Pixels)',nombre_vista='CDX_PERSPECTIVA',sombreado='AsDisplayed',rotacion='0'))
        self.receipt['views']['PERSPECTIVA']={'direction':[-22,-7,1],'target':[2,0,101.65],'lens_mm':35}
        self.call('vista.activar',dict(nombre='CDX_GENERAL'))
        self.save()


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    parser.add_argument('--template',required=True,type=Path)
    parser.add_argument('--case',choices=['A_CALLE_BACHE','B_ESQUINA_MOTOS'],required=True)
    parser.add_argument('--resume-empty',action='store_true',help='Only after confirming a saved creation receipt and empty drawing')
    args=parser.parse_args()
    scene=Scene(args.output,args.template,args.case,args.resume_empty)
    scene.build()
    scene.export()
