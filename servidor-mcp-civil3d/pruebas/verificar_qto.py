"""Native regression on a disposable QTO copy with the synthetic fixtures present.
Run humo_qto.py once to create the volume fixture/axis. The shape fixture comes
from the prior targets delivery. This test creates named QTO objects once;
after any interruption inspect its receipt before resuming. Never rerun blindly.
"""
import argparse,json,time
from pathlib import Path
from humo_cunetas_bermas import NativeQa,canonical
import qto

def run(drawing,output,pid,request_file,prefix='qto-acceptance'):
 q=NativeQa(drawing,output,8760,prefix);q.guard()
 requests=json.loads(Path(request_file).read_text(encoding='utf-8'));shape=requests['shape']
 def call(action,**args):
  try:r=qto.ejecutar(q.drawing,pid,accion=action,**args)
  except qto.QtoError as e:q.report['last_error_receipt']=e.receipt;q.record();raise
  q.report.setdefault('receipts',[]).append(r);q.record();return r
 def reject(label,action,args,text,stage=None):
  before=q.qa(label+'-before')
  if stage:
   dest=label+'-armed.json';assert not (q.out/dest).exists()
   (q.out/'qto-fault.json').write_text(json.dumps(dict(stage=stage,output=dest)),encoding='utf-8');q.call('cmd.run',dict(linea='CDCRDQTOV8QA\n'))
   for _ in range(50):
    if (q.out/dest).exists():break
    time.sleep(.1)
   assert (q.out/dest).exists()
  try:call(action,**args)
  except (qto.QtoError,ValueError) as e:q.check(label+' rejected',text in str(e))
  else:raise AssertionError(label+' accepted')
  q.check(label+' unchanged',canonical(before)==canonical(q.qa(label+'-after')))
 def simulate(label,action,args):
  before=q.qa(label+'-before');r=call(action,**args,simular=True);q.check(label+' not committed',not r['committed']);q.check(label+' unchanged',canonical(before)==canonical(q.qa(label+'-after')));return r['result']
 v=simulate('volume','volumen',requests['volume']);q.check('400 cut 400 fill, factors',all(abs(v[k]-expected)<1e-6 for k,expected in [('cut',400),('fill',400),('adjusted_cut',440),('adjusted_fill',480)]))
 e=simulate('earth','materiales',requests['earth']);q.check('earth native 5 stations and 400/400',len(e['quantities'])==5 and abs(e['totals'][-1]['cumulative_cut']-400)<1e-6 and abs(e['totals'][-1]['cumulative_fill']-400)<1e-6)
 simulate('shape-prepare','materiales',shape)
 for label,action,args,text in [
  ('same-surfaces','volumen',{**requests['volume'],'comparacion':requests['volume']['base']},'diferentes'),
  ('missing-surface','volumen',{**requests['volume'],'base':'NOT FOUND'},'inexistente'),
  ('bad-factor','volumen',{**requests['volume'],'factor_corte':0},'rango'),
  ('bad-station-order','materiales',{**requests['earth'],'estaciones':[120,110]},'ordenadas'),
  ('out-of-range','materiales',{**requests['earth'],'estaciones':[99,140]},'fuera'),
  ('incomplete-tin','materiales',{**requests['earth'],'semiancho':15},'cubre'),
  ('gap-or-boundary','materiales',{**shape,'estaciones':[150,180,190]},'interiores'),
  ('wrong-baseline','materiales',{**shape,'baseline':'B'},'Baseline'),
  ('missing-shape','materiales',{**shape,'codigos':['NotACode']},'Forma'),
  ('narrow-swath','materiales',{**shape,'semiancho':1},'Semiancho')]:reject(label,action,args,text)
 for stage,action,args in [('volume-created','volumen',requests['volume']),('group-created','materiales',requests['earth']),('samples-created','materiales',requests['earth']),('materials-created','materiales',requests['earth']),('record-written','materiales',requests['earth'])]:reject('fault-'+stage,action,{**args,'simular':False},'CDCRD_QA_QTO_FAILURE',stage)
 q.report['volume']=call('volumen',**requests['volume'],simular=False)['result'];q.report['earth']=call('materiales',**requests['earth'],simular=False)['result'];q.record()
 prepared=call('materiales',**shape,simular=False)['result'];q.report['shape_prepared']=prepared;q.record();q.check('shape group prepared',prepared['state']=='prepared' and prepared['material_list_count']==0)
 q.call('cmd.run',dict(linea='_.REGENALL\n'))
 s=simulate('shape-calculation','calcular_formas',dict(objeto=prepared['handle']));q.check('shape native four materials',len(s['materials'])==4 and s['max_shape_check_error']<1e-5)
 pending=call('leer_materiales',objeto=prepared['handle'])['result'];q.check('shape simulation reverts list and state',pending['state']=='prepared' and pending['material_list_count']==0)
 for stage in ['materials-created','record-written']:
  reject('shape-fault-'+stage,'calcular_formas',dict(objeto=prepared['handle'],simular=False),'CDCRD_QA_QTO_FAILURE',stage)
  pending=call('leer_materiales',objeto=prepared['handle'])['result'];q.check(stage+' preserves pending group',pending['state']=='prepared' and pending['material_list_count']==0)
 q.report['shape']=call('calcular_formas',objeto=prepared['handle'],simular=False)['result'];q.record()
 reject('repeated-phase','calcular_formas',dict(objeto=prepared['handle'],simular=False),'preparado')
 for name,args,action in [('duplicate-volume',requests['volume'],'volumen'),('duplicate-earth',requests['earth'],'materiales')]:reject(name,action,{**args,'simular':False},'existe')
 q.report['ok']=True;q.record();print('PASS',len(q.report['checks']))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--pid',type=int,required=True);p.add_argument('--requests',required=True);p.add_argument('--prefix',default='qto-acceptance');a=p.parse_args();run(a.drawing,a.output,a.pid,a.requests,a.prefix)
