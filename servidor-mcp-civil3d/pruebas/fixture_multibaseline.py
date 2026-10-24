"""Build only new synthetic inputs in the identified multi-baseline test copy."""
import argparse,json,math
from pathlib import Path
from humo_cunetas_bermas import NativeQa
import espirales

def run(drawing,output,pid):
    q=NativeQa(drawing,output,8760,'multi-fixture');q.guard()
    root=Path(__file__).resolve().parents[1]
    for path in [root/'modulo-corredores/bin/Release/net10.0-windows/Cdcrd.Corredores.V4.dll',root/'pruebas/native_multi_qa/bin/Release/net10.0-windows/Cdcrd.MultiV4QaSafe.dll']:
        q.call('cmd.run',dict(linea='_.NETLOAD\n"'+str(path).replace('\\','/')+'"\n'))
    q.report['axes']=[];q.report['profiles']=[];q.report['assemblies']=[];q.report['assembly_inputs']=[]
    for i,label in enumerate(['A','B']):
        y=2100010+90*i
        g=dict(inicio=[620010,y],pi=[620100,y],fin=[620100+90*math.cos(math.pi/6),y+45],radio=50,longitud_entrada=10,longitud_salida=15,estacion_inicial=100)
        r=espirales.ejecutar(q.drawing,pid,nombre='CDX QA MULTI AXIS '+label+' 0520',geometria=g,capa='CDX-QA-MULTI-AXIS',simular=False)
        axis=r['result'];q.report['axes'].append(axis);q.record()
        profile=q.call('civil.perfil_pvi',dict(alineamiento=axis['handle'],nombre='CDX QA MULTI PROFILE '+label+' 0520',pvis=[[axis['start_station'],101-.5*i],[axis['end_station'],103-.5*i]],capa='CDX-QA-MULTI-PROFILE'))
        q.report['profiles'].append(profile);q.record()
        params=json.loads((root/'docs/PERALTES-0518-fixture.json').read_text())['assembly']
        params.update(nombre='CDX QA MULTI ASSEMBLY '+label+' 0520',origen=[620300,2100400+30*i,0],capa='CDX-QA-MULTI-ASSEMBLY')
        if i:params.update(ancho_izq=4.5,ancho_der=3.0,ancho_berma_izq=2.0,ancho_berma_der=1.5)
        assembly=q.call('civil.ensamblaje_cunetas_bermas',params)
        q.report['assemblies'].append(assembly);q.report['assembly_inputs'].append(params);q.record()
    q.check('dos ejes, perfiles y ensamblajes nuevos',len(q.report['axes'])==len(q.report['profiles'])==len(q.report['assemblies'])==2)
    q.report['ok']=True;q.record()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--pid',type=int,required=True);a=p.parse_args();run(a.drawing,a.output,a.pid)
