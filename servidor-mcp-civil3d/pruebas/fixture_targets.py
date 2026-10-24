"""Synthetic width/elevation targets in a protected copy, existing Civil process."""
import argparse,json,math
from pathlib import Path
from humo_cunetas_bermas import NativeQa
import multibaseline

def run(drawing,output,pid):
 q=NativeQa(drawing,output,8760,'targets-fixture');q.guard()
 q.report.update(axes=[],profiles=[],assemblies=[],target_axes=[],target_profiles=[],geometry=[])
 def axis(name,points,start):
  created=q.call('entity.create',dict(entidades=[dict(tipo='polilinea',puntos=points,capa='CDX-QA-TARGETS-SOURCE',color=8)]))
  assert not created['errores'] and len(created['creados'])==1
  handle=created['creados'][0]['handle']
  return q.call('civil.alineamiento_polilinea',dict(polilinea=handle,nombre=name,estacion_inicial=start,capa='CDX-QA-TARGETS-AXIS'))
 def profile(a,name,pvis):
  return q.call('civil.perfil_pvi',dict(alineamiento=a['handle'],nombre=name,pvis=pvis,capa='CDX-QA-TARGETS-PROFILE'))
 for i,label in enumerate(['A','B']):
  x,y=620020,2100160-45*i
  a=axis('CDX QA TARGET BASE '+label+' 0521',[[x,y],[x+160,y]],100)
  p=profile(a,'CDX QA TARGET DESIGN '+label+' 0521',[[100,101.8],[260,102.2]])
  q.report['axes'].append(a);q.report['profiles'].append(p);q.record()
  params=json.loads((Path(__file__).resolve().parents[1]/'docs/PERALTES-0518-fixture.json').read_text())['assembly']
  params.update(nombre='CDX QA TARGET ASSEMBLY '+label+' 0521',origen=[620300,2100520+35*i,0],capa='CDX-QA-TARGETS-ASSEMBLY')
  asm=q.call('civil.ensamblaje_cunetas_bermas',params);q.report['assemblies'].append(asm);q.record()
  target_axes=[];target_profiles=[];geometries=[]
  for side,sign,st in [('L',1,1000),('R',-1,2000)]:
   widths=[3,5,4,6,3.5] if side=='L' else [4,3.2,5.5,4,6]
   pts=[[x+dx,y+sign*w] for dx,w in zip([-10,40,80,120,170],widths)]
   ta=axis('CDX QA TARGET '+label+side+' 0521',pts,st)
   stations=[st]
   for u,v in zip(pts,pts[1:]):stations.append(stations[-1]+math.dist(u,v))
   zs=[101.65,101.8,102.15,102.05,102.35] if side=='L' else [101.9,101.7,102.05,102.3,102.1]
   tp=profile(ta,'CDX QA TARGET Z '+label+side+' 0521',[[s,z] for s,z in zip(stations,zs)])
   target_axes.append(ta);target_profiles.append(tp);geometries.append(dict(points=pts,stations=stations,elevations=zs))
  # Separate profile on the baseline proves elevation-only assignment.
  height=profile(a,'CDX QA TARGET Z BASE '+label+' 0521',[[100,101.7],[180,102.0],[260,102.3]])
  q.report['target_axes'].append(target_axes);q.report['target_profiles'].append(target_profiles+[height]);q.report['geometry'].append(geometries);q.record()
 bases=[]
 for i,label in enumerate(['A','B']):
  intervals=[(100,180),(180,260)] if i==0 else [(100,160),(180,260)]
  regions=[dict(nombre=label+str(j+1),ensamblaje=q.report['assemblies'][i]['handle'],superficie_objetivo='MCP QA TERRENO 0516',inicio=lo,fin=hi,frecuencia=10,estaciones_extra=[s for s in [120,140,150,179,181,200,220,240] if lo<s<hi]) for j,(lo,hi) in enumerate(intervals)]
  bases.append(dict(nombre=label,alineamiento=q.report['axes'][i]['handle'],perfil=q.report['profiles'][i]['handle'],regiones=regions))
 q.report['corridor_request']=dict(accion='crear',nombre='CDX QA TARGET CORRIDOR 0521',baselines=bases,capa='CDX-QA-TARGETS-CORRIDOR')
 q.record();r=multibaseline.ejecutar(q.drawing,pid,**q.report['corridor_request'],simular=False)
 q.report['corridor_receipt']=r;q.report['corridor']=r['result'];q.record()
 q.check('corredor independiente creado',r['committed'] and len(r['result']['baselines'])==2)
 q.report['ok']=True;q.record()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--pid',type=int,required=True);a=p.parse_args();run(a.drawing,a.output,a.pid)
