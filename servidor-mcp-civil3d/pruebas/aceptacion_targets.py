"""Native failures, creation and independent numerical reference for width/Z targets."""
import argparse,copy,json,math,time
from pathlib import Path
from humo_cunetas_bermas import NativeQa,canonical
import targets
import multibaseline

def run(drawing,output,pid,resume=False,prefix=None):
 q=NativeQa(drawing,output,8760,prefix or ('targets-final-validation' if resume else 'targets-complete'));q.guard()
 sim=json.loads((q.out/'targets-create-simulation-smoke.json').read_text());assert sim['ok']
 f=json.loads((q.out/'targets-fixture-smoke.json').read_text());args=sim['request'];q.report.update(request=args,receipts=[],sections=[]);q.record()
 def execute(data):
  try:r=targets.ejecutar(q.drawing,pid,**data)
  except targets.TargetError as e:q.report['receipts'].append(e.receipt);q.record();raise
  q.report['receipts'].append(r);q.record();return r
 def rejected(label,data,expected,stage=None,occurrence=1):
  before=q.qa(label+'-before')
  if stage:
   dest=q.out/(q.prefix+'-'+label+'-armed.json');assert not dest.exists()
   (q.out/'targets-fault.json').write_text(json.dumps(dict(stage=stage,occurrence=occurrence,output=dest.name)))
   q.call('cmd.run',dict(linea='CDCRDTARGETSV2QA\n'));deadline=time.monotonic()+15
   while not dest.exists() and time.monotonic()<deadline:time.sleep(.1)
   q.check(label+' armado',dest.exists() and json.loads(dest.read_text()).get('armed')==stage)
  try:execute(data)
  except targets.TargetError as e:q.check(label+' rechazo',expected in str(e) and not e.receipt.get('committed'))
  else:raise AssertionError('Expected rejection '+label)
  q.check(label+' rollback completo',canonical(before)==canonical(q.qa(label+'-after')))
 if resume:
  prior=json.loads((q.out/'targets-complete-smoke.json').read_text());r=prior['receipts'][-1];c=prior['corridor']
  assert r['ok'] and r['committed'] and r['result']==c and not prior['sections']
  current=execute(dict(accion='leer',corredor=c['corredor']))['result']
  q.check('continuacion sobre resultado confirmado',canonical(current)==canonical(c))
  before={key:json.loads((q.out/('targets-complete-create-before-'+key+'.json')).read_text())['result'] for key in ['drawing','civil']}
  q.report['prior_receipt']='targets-complete-smoke.json';q.report['corridor']=c;q.record()
 else:
  for label,change,error in [
   ('perfil-ajeno',lambda b:b[0].update(perfil_cota=f['target_profiles'][1][0]['handle']),'Referencia inexistente'),
   ('target-eje-central',lambda b:b[0].update(alineamiento_ancho=f['axes'][0]['handle']),'eje lateral'),
   ('region-inexistente',lambda b:b[0].update(region='NO-REGION'),'Region inexistente'),
   ('subensamblaje-ajeno',lambda b:b[0].update(subensamblaje=f['assemblies'][1]['subensamblajes'][0]['handle']),'Referencia inexistente')]:
   a=copy.deepcopy(args);change(a['asignaciones']);rejected(label,dict(a,simular=False),error)
  for stage,occ in [('copy-created',1),('targets-assigned',3),('corridor-rebuilt',1),('surface-rebuilt',1),('target-record-written',1)]:
   rejected('failure-'+stage,dict(args,simular=False),'CDCRD_QA_TARGET_FAILURE',stage,occ)
  before=q.qa('create-before');r=execute(dict(args,simular=False));c=r['result'];q.report['corridor']=c;q.record()
 q.check('creacion confirmada',r['committed'] and c['corredor']!=args['corredor_origen'])
 q.check('dos baselines cuatro regiones y Top',len(c['baselines'])==2 and all(len(b['regions'])==2 for b in c['baselines']) and len(c['triangles'])>0 and len(c['boundary_loops'])==3 and not c['out_of_date'])
 after=q.qa('create-after')
 for kind in ['drawing','civil']:
  for collection,old in before[kind].items():
   if isinstance(old,list) and all(isinstance(x,dict) and "handle" in x for x in old):
    current={x['handle']:x for x in after[kind][collection] if isinstance(x,dict) and 'handle' in x}
    q.check('originales '+kind+'/'+collection,all(canonical(current.get(x['handle']))==canonical(x) for x in old))
   else:q.check('originales '+kind+'/'+collection,old==after[kind][collection])
 errors=dict(width=0.,elevation=0.,target_station=0.,xy=0.,daylight=0.)
 for i,b in enumerate(c['baselines']):
  for region in b['regions']:
   for row in region['applied']:
    station=row['station'];x=620020+station-100;y=2100160-45*i;grade=101.8+.4*(station-100)/160
    for lane in row['lanes']:
     j=0 if lane['side']=='Left' else 1;sign=1 if j==0 else -1
     g=f['geometry'][i][j];points=g['points'];k=next(k for k in range(len(points)-1) if points[k][0]-1e-6<=x<=points[k+1][0]+1e-6)
     fraction=(x-points[k][0])/(points[k+1][0]-points[k][0]);width=abs(points[k][1]+fraction*(points[k+1][1]-points[k][1])-y)
     target_station=g['stations'][k]+fraction*(g['stations'][k+1]-g['stations'][k]);z=g['elevations'][k]+fraction*(g['elevations'][k+1]-g['elevations'][k])
     if i==1 and j==0:z=grade-.02*width
     if i==1 and j==1:width=3.5;target_station=station;z=101.7+.6*(station-100)/160
     errors['width']=max(errors['width'],abs(lane['width']-width));errors['elevation']=max(errors['elevation'],abs(lane['elevation']-z));errors['target_station']=max(errors['target_station'],abs(lane['target_station']-target_station));errors['xy']=max(errors['xy'],math.dist(lane['edge'][:2],[x,y+sign*width]))
    for pt in row['points']:
     if 'Daylight' in pt['codes']:errors['daylight']=max(errors['daylight'],abs(pt['xyz'][2]-102))
 q.report['independent_errors']=errors;q.record()
 for key,value in errors.items():q.check('referencia independiente '+key,value<1e-6)
 rejected('duplicado',dict(args,simular=False),'Ya existe')
 for i,label in enumerate(['A','B']):
  stations=[120,140,200,240] if i==0 else [120,150,200,240]
  data=dict(accion='secciones',corredor=c['corredor'],baseline=label,nombre='CDX QA TARGET SECTIONS '+label+' 0521',estaciones=stations,semiancho=16,origen=[620350,2100600-65*i,0],cota_min=98,cota_max=106,capa='CDX-QA-TARGETS-SECTIONS',simular=False)
  try:sr=multibaseline.ejecutar(q.drawing,pid,**data)
  except multibaseline.MultiError as e:q.report['receipts'].append(e.receipt);q.record();raise
  q.report['receipts'].append(sr);q.report['sections'].append(sr['result']);q.record();q.check('cuatro secciones '+label,sr['committed'] and len(sr['result']['secciones'])==4)
  for section in sr['result']['secciones']:
   q.check('estacion seccion '+label+str(section['estacion']),abs(section['estacion_nativa']-section['estacion'])<1e-6)
   row=next(row for region in c['baselines'][i]['regions'] for row in region['applied'] if abs(row['station']-section['estacion'])<1e-6)
   pts=section['secciones'][0]['puntos'];connected={j for j,p in enumerate(pts) if p['segment_to']>=0}|{p['segment_to'] for p in pts if p['segment_to']>=0};pts=[pts[j] for j in connected]
   for lane in row['lanes']:
    offset=(-1 if lane['side']=='Left' else 1)*lane['width']
    if min(max(abs(p['offset']-offset),abs(p['cota']-lane['elevation'])) for p in pts)>1e-6:raise AssertionError('Section ETW differs from target')
  q.check('ETW targets en secciones '+label,True)
 q.report['readback']=execute(dict(accion='leer',corredor=c['corredor']));q.check('relectura targets y geometria',q.report['readback']['ok'])
 q.report['ok']=True;q.record()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--pid',type=int,required=True);p.add_argument('--resume-confirmed',action='store_true');p.add_argument('--prefix');a=p.parse_args();run(a.drawing,a.output,a.pid,a.resume_confirmed,a.prefix)
