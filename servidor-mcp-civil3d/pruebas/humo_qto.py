"""Native QTO fixture, simulation and independent numerical verification."""
import argparse,json,time
from pathlib import Path
from humo_cunetas_bermas import NativeQa,canonical
import qto

def run(drawing,output,pid):
 q=NativeQa(drawing,output,8760,'qto-initial');q.guard()
 root=Path(__file__).resolve().parents[1]
 for path in [root/'modulo-qto/bin/Release/net10.0-windows/Cdcrd.Qto.V8.dll',root/'pruebas/native_qto_qa/bin/Release/net10.0-windows/Cdcrd.QtoV8Qa.dll']:
  q.call('cmd.run',dict(linea='_.NETLOAD\n"'+path.as_posix()+'"\n'))
 q.call('cmd.run',dict(linea='CDCRDQTOFIXTURE\n'))
 dest=q.out/'qto-native-fixture.json'
 for _ in range(100):
  if dest.exists():break
  time.sleep(.1)
 fixture=json.loads(dest.read_text(encoding='utf-8'));assert fixture['ok'],fixture
 pts=q.call('entity.create',dict(entidades=[dict(tipo='polilinea',puntos=[[620500,2100010],[620540,2100010]],capa='CDX-QA-QTO-AXIS',color=2)]))
 assert not pts['errores']
 axis=q.call('civil.alineamiento_polilinea',dict(polilinea=pts['creados'][0]['handle'],nombre='CDX QA QTO AXIS 0522',estacion_inicial=100,capa='CDX-QA-QTO-AXIS'))
 q.report.update(fixture=fixture['result'],axis=axis);q.record()
 args=dict(nombre='CDX QA QTO VOLUME 0522',base=fixture['result']['base_surface'],comparacion=fixture['result']['comparison'],factor_corte=1.1,factor_relleno=1.2)
 q.report['volume_args']=args;q.record()
 before=q.qa('volume-before')
 try:v=qto.ejecutar(q.drawing,pid,accion='volumen',**args)
 except qto.QtoError as e:q.report['error_receipt']=e.receipt;q.record();raise
 q.report['volume_simulation']=v;q.record()
 q.check('TIN cut=400 fill=400',abs(v['result']['cut']-400)<1e-6 and abs(v['result']['fill']-400)<1e-6)
 q.check('TIN simulation no objects',canonical(before)==canonical(q.qa('volume-after')))
 args=dict(nombre='CDX QA QTO EARTHWORK 0522',alineamiento=axis['handle'],estaciones=[100,110,120,130,140],semiancho=10,modo='tierras',base=fixture['result']['base_surface'],comparacion=fixture['result']['comparison'])
 q.report['earth_args']=args;q.record();before=q.qa('earth-before')
 try:r=qto.ejecutar(q.drawing,pid,accion='materiales',**args)
 except qto.QtoError as e:q.report['error_receipt']=e.receipt;q.record();raise
 q.report['earth_simulation']=r;q.record();q.check('QTO simulation no objects',canonical(before)==canonical(q.qa('earth-after')))
 q.report['ok']=True;q.record();return q.report

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--pid',type=int,required=True);a=p.parse_args();run(a.drawing,a.output,a.pid)
