"""Native transactional tests and numerical proof for multiple baselines/regions."""
import argparse,copy,json,math,time
from pathlib import Path
from humo_cunetas_bermas import NativeQa,canonical
from espiral_referencia import Reference
import multibaseline

def specs(f):
    bases=[]
    for i,label in enumerate(['A','B']):
        a=f['axes'][i];end=a['end_station']
        intervals=[(100,180,0,10,[120,160,179]),(180,end,1,5,[181,220,260])] if i==0 else [(100,165,1,7.5,[120,150]),(185,end,0,10,[200,240,260])]
        regions=[dict(nombre=label+str(j+1),ensamblaje=f['assemblies'][asm]['handle'],superficie_objetivo='MCP QA TERRENO 0516',inicio=lo,fin=hi,frecuencia=freq,estaciones_extra=extra) for j,(lo,hi,asm,freq,extra) in enumerate(intervals)]
        bases.append(dict(nombre=label,alineamiento=a['handle'],perfil=f['profiles'][i]['handle'],regiones=regions))
    return bases

def run(drawing,output,pid):
    q=NativeQa(drawing,output,8760,'multi-accepted');f=json.loads((q.out/'multi-fixture-smoke.json').read_text());assert f['ok']
    args=dict(accion='crear',nombre='CDX QA MULTI CORRIDOR 0520',baselines=specs(f),capa='CDX-QA-MULTI-CORRIDOR')
    q.report['request']=args;q.record()
    before=q.qa('simulation-before')
    try:r=multibaseline.ejecutar(q.drawing,pid,**args)
    except multibaseline.MultiError as exc:q.report['error_receipt']=exc.receipt;q.record();raise
    q.report['simulation']=r;q.record()
    q.check('simulacion con dos baselines y cuatro regiones',not r['committed'] and len(r['result']['baselines'])==2 and all(len(b['regions'])==2 for b in r['result']['baselines']))
    q.check('simulacion sin residuos',canonical(before)==canonical(q.qa('simulation-after')))
    q.report['ok']=True;q.record()
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--pid',type=int,required=True);a=p.parse_args();run(a.drawing,a.output,a.pid)
