"""Four-region synthetic fixture regression; creates A2/B1/B2 once.
Requires successful verificar_qto.py A1 receipt and the prior targets fixture.
Do not rerun after an interruption without inspecting its immutable receipts.
"""
import argparse,json
from pathlib import Path
from humo_cunetas_bermas import NativeQa
import qto
def run(drawing,output,pid,targets_fixture,corridor,acceptance,prefix):
 out=Path(output);q=NativeQa(drawing,out,8760,prefix);q.guard()
 first=json.loads((out/acceptance).read_text(encoding='utf-8'));assert first['ok']
 f=json.loads(Path(targets_fixture).read_text(encoding='utf-8'))
 q.report['groups']=[dict(baseline='A',region='A1',result=first['shape'])];q.record()
 for bi,bn,rn,start,end in [(0,'A','A2',190,250),(1,'B','B1',110,150),(1,'B','B2',190,250)]:
  args=dict(nombre='CDX QA QTO PAVEMENT '+rn+' 0522',alineamiento=f['axes'][bi]['handle'],corredor=corridor,baseline=bn,region=rn,modo='formas',estaciones=list(range(start,end+1,10)),semiancho=12,codigos=['Pave1','Pave2','Base','SubBase'])
  prepared=qto.ejecutar(q.drawing,pid,accion='materiales',**args,simular=False);q.report.setdefault('preparations',[]).append(prepared);q.record()
  q.call('cmd.run',dict(linea='_.REGENALL\n'))
  try:r=qto.ejecutar(q.drawing,pid,accion='calcular_formas',objeto=prepared['result']['handle'],simular=False)
  except qto.QtoError as e:q.report['error_receipt']=e.receipt;q.record();raise
  q.report['groups'].append(dict(baseline=bn,region=rn,result=r['result']));q.record()
 def lerp(x,ys):
  xs=[-10,40,80,120,170]
  for a,c,ya,yc in zip(xs,xs[1:],ys,ys[1:]):
   if a<=x<=c:return ya+(yc-ya)*(x-a)/(c-a)
  raise ValueError(x)
 errors=dict(area=0.,increment=0.,cumulative=0.);totals={};thickness=dict(Pave1=.05,Pave2=.07,Base=.2,SubBase=.3)
 for group in q.report['groups']:
  result=group['result'];q.check(group['region']+' native 4 materials',len(result['materials'])==4 and result['max_shape_check_error']<1e-5)
  cumul={name:0. for name in thickness};prev=None
  for row in result['quantities']:
   st=row['station'];x=st-100;left=lerp(x,[3,5,4,6,3.5]);right=lerp(x,[4,3.2,5.5,4,6]) if group['baseline']=='A' else 3.5
   areas={name:(left+right)*t for name,t in thickness.items()}
   for m in row['materials']:
    name=m['name'];increment=0 if prev is None else (areas[name]+prev[1][name])*(st-prev[0])/2;cumul[name]+=increment
    errors['area']=max(errors['area'],abs(m['area']-areas[name]));errors['increment']=max(errors['increment'],abs(m['volume']-increment));errors['cumulative']=max(errors['cumulative'],abs(m['cumulative']-cumul[name]))
   prev=(st,areas)
  totals[group['region']]=cumul
 for k,e in errors.items():q.check('independent width/thickness '+k,e<1e-5)
 q.report.update(errors=errors,volumes=totals,sampled_length_m=220,shape_station_count=sum(len(g['result']['quantities']) for g in q.report['groups']))
 q.check('4 separated regions with no gap integration',len(totals)==4)
 q.report['ok']=True;q.record();print('PASS',totals,errors)

if __name__=='__main__':
 p=argparse.ArgumentParser()
 for key in ['drawing','output','targets-fixture','corridor','acceptance']:p.add_argument('--'+key,required=True)
 p.add_argument('--pid',type=int,required=True);p.add_argument('--prefix',default='qto-multiple-regions');a=p.parse_args()
 run(a.drawing,a.output,a.pid,a.targets_fixture,a.corridor,a.acceptance,a.prefix)
