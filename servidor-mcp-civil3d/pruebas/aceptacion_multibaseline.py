"""Complete native acceptance after a verified residue-free simulation."""
import argparse,copy,json,math,time
from pathlib import Path
from humo_cunetas_bermas import NativeQa,canonical
from espiral_referencia import Reference
import multibaseline

def run(drawing,output,pid):
 q=NativeQa(drawing,output,8760,'multi-complete');sim=json.loads((q.out/'multi-accepted-smoke.json').read_text());assert sim['ok']
 f=json.loads((q.out/'multi-fixture-smoke.json').read_text());args=sim['request'];q.report['request']=args;q.report['sections']=[];q.record()
 def execute(data):
  try:r=multibaseline.ejecutar(q.drawing,pid,**data)
  except multibaseline.MultiError as e:q.report.setdefault('receipts',[]).append(e.receipt);q.record();raise
  q.report.setdefault('receipts',[]).append(r);q.record();return r
 def rejected(label,data,expected,stage=None,occurrence=1):
  before=q.qa(label+'-before')
  if stage:
   dest=q.out/(q.prefix+'-'+label+'-armed.json')
   if dest.exists():raise FileExistsError(dest)
   (q.out/'multi-fault.json').write_text(json.dumps(dict(stage=stage,occurrence=occurrence,output=dest.name)))
   q.call('cmd.run',dict(linea='CDCRDCORREDORESV4QASAFE\n'))
   deadline=time.monotonic()+15
   while not dest.exists() and time.monotonic()<deadline:time.sleep(.1)
   q.check(label+' armado',dest.exists() and json.loads(dest.read_text()).get('armed')==stage)
  try:execute(data)
  except multibaseline.MultiError as e:q.check(label+' rechazo',expected in str(e) and not e.receipt.get('committed'))
  else:raise AssertionError('Expected rejection '+label)
  q.check(label+' rollback completo',canonical(before)==canonical(q.qa(label+'-after')))
 for label,change,error in [('perfil-ajeno',lambda b:b[1].update(perfil=b[0]['perfil']),'Referencia inexistente'),('eje-duplicado',lambda b:b[1].update(alineamiento=b[0]['alineamiento']),'Alineamiento repetido'),('target-ausente',lambda b:b[0]['regiones'][0].update(superficie_objetivo=None),'requiere superficie'),('fuera-dominio',lambda b:b[1]['regiones'][1].update(fin=999),'fuera del dominio')]:
  a=copy.deepcopy(args);change(a['baselines']);rejected(label,dict(a,simular=False),error)
 for stage,occ in [('baseline-added',2),('region-targets-assigned',3),('corridor-rebuilt',1),('surface-rebuilt',1)]:
  rejected('failure-'+stage,dict(args,simular=False),'CDCRD_QA_MULTI_FAILURE',stage,occ)
 result=execute(dict(args,simular=False));q.check('escritura confirmada',result['committed']);c=result['result'];q.report['corridor']=c;q.record()
 q.check('dos baselines y cuatro regiones persistentes',len(c['baselines'])==2 and all(len(b['regions'])==2 for b in c['baselines']))
 q.check('Top reconstruida y tres contornos separados',not c['out_of_date'] and len(c['triangles'])>1000 and len(c['boundary_loops'])==3)
 errors=dict(xy=0.,z=0.,daylight=0.,width=0.)
 for i,b in enumerate(c['baselines']):
  ref=Reference(f['axes'][i]['geometry']);start,end=f['axes'][i]['start_station'],f['axes'][i]['end_station']
  for region in b['regions']:
   for row in region['applied']:
    s=row['station'];assembly=next(a for a in f['assembly_inputs'] if a['nombre']==next(x['nombre'] for x in f['assemblies'] if x['handle']==row['assembly']))
    grade=101-.5*i+2*(s-start)/(end-start)
    for pt in row['points']:
     xy,_,_=ref.at(s,pt['soe'][1]);errors['xy']=max(errors['xy'],math.dist(xy,pt['xyz'][:2]))
     if 'Daylight' in pt['codes']:errors['daylight']=max(errors['daylight'],abs(pt['xyz'][2]-102))
    for sign,side in [(-1,'izq'),(1,'der')]:
     width=assembly['ancho_'+side];edge=next(p for p in row['points'] if 'ETW' in p['codes'] and p['soe'][1]*sign>0)
     errors['width']=max(errors['width'],abs(edge['soe'][1]-sign*width));errors['z']=max(errors['z'],abs(edge['xyz'][2]-grade-width*assembly['pendiente_'+side]))
 q.report['max_errors']=errors;q.record()
 for k,v in errors.items():q.check('geometria independiente '+k,v<1e-6)
 a1,a2=c['baselines'][0]['regions'];shared=next(r for r in a2['applied'] if r['station']==180)
 q.check('limite compartido identificado sin atribucion falsa',shared['boundary_shared'] and shared['geometry_region']=='A1' and shared['assembly']==a1['assembly'] and shared['assembly']!=a2['assembly'])
 q.check('interiores usan ensamblajes propios',all(row['assembly']==reg['assembly'] for b in c['baselines'] for reg in b['regions'] for row in reg['applied'] if not row['boundary_shared']))
 q.check('Top no une ejes disjuntos',all(all(p[1]<2100075 for p in t) or all(p[1]>2100075 for p in t) for t in c['triangles']))
 def inside(p,t):
  signs=[(t[(j+1)%3][0]-t[j][0])*(p[1]-t[j][1])-(t[(j+1)%3][1]-t[j][1])*(p[0]-t[j][0]) for j in range(3)]
  return all(v>=-1e-8 for v in signs) or all(v<=1e-8 for v in signs)
 gap=Reference(f['axes'][1]['geometry']).at(175,0)[0]
 q.check('Top respeta hueco de veinte metros',not any(inside(gap,t) for t in c['triangles']))
 rejected('duplicado',dict(args,simular=False),'Ya existe')
 sectionbase=dict(accion='secciones',corredor=c['handle'],baseline='A',nombre='CDX QA MULTI SECTIONS A 0520',estaciones=[120,160,179,181,220,260],semiancho=15,origen=[620350,2100400,0],cota_min=98,cota_max=106,capa='CDX-QA-MULTI-SECTIONS',simular=False)
 rejected('seccion-limite',dict(sectionbase,estaciones=[180]),'limite compartido')
 rejected('seccion-hueco',dict(sectionbase,baseline='B',estaciones=[175]),'hueco')
 rejected('seccion-sin-baseline',dict(sectionbase,baseline='C'),'Baseline inexistente')
 rejected('failure-section',sectionbase,'CDCRD_QA_MULTI_FAILURE','section-created',2)
 before=q.qa('sections-simulation-before');sr=execute(dict(sectionbase,simular=True));q.check('secciones simuladas',not sr['committed'] and len(sr['result']['secciones'])==6);q.check('secciones simuladas sin residuos',canonical(before)==canonical(q.qa('sections-simulation-after')))
 for i,label in enumerate(['A','B']):
  data=dict(sectionbase,baseline=label,nombre='CDX QA MULTI SECTIONS '+label+' 0520',estaciones=[120,160,179,181,220,260] if i==0 else [120,150,200,240,260],origen=[620350,2100400-65*i,0])
  sr=execute(data);q.report['sections'].append(sr['result']);q.record();q.check('secciones baseline '+label,sr['committed'] and len(sr['result']['secciones'])==len(data['estaciones']))
  ref=Reference(f['axes'][i]['geometry'])
  for row in sr['result']['secciones']:
   q.check('estacion nativa '+label+str(row['estacion']),abs(row['estacion_nativa']-row['estacion'])<1e-6)
   q.check('seccion normal '+label+str(row['estacion']),math.dist(row['izquierda'],ref.at(row['estacion'],-15)[0])<1e-6 and math.dist(row['derecha'],ref.at(row['estacion'],15)[0])<1e-6)
   native=next(sample for region in c['baselines'][i]['regions'] for sample in region['applied'] if abs(sample['station']-row['estacion'])<1e-6)
   raw=row['secciones'][0]['puntos'];connected={j for j,p in enumerate(raw) if p['segment_to']>=0}|{p['segment_to'] for p in raw if p['segment_to']>=0};pts=[raw[j] for j in connected]
   for pt in native['points']:
    if any(code in pt['codes'] for code in ['ETW','BermaExterior','CunetaFondoInterior','CunetaFondoExterior','CunetaBordeExterior']):
     if min(max(abs(p['offset']-pt['soe'][1]),abs(p['cota']-pt['xyz'][2])) for p in pts)>1e-6:raise AssertionError('Section Top vertex missing '+label+str(row['estacion']))
  q.check('vertices Top cunetas y bermas '+label,True)
 q.report['readback']=execute(dict(accion='leer',corredor=c['handle']))
 q.check('relectura contrato completo',q.report['readback']['ok'] and not q.report['readback']['committed'])
 q.report['ok']=True;q.record()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--pid',type=int,required=True);a=p.parse_args();run(a.drawing,a.output,a.pid)
