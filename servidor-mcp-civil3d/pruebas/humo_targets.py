"""Read source catalog and simulate a new corridor with width/elevation targets."""
import argparse,json
from pathlib import Path
from humo_cunetas_bermas import NativeQa,canonical
import targets

def bindings(f):
 result=[]
 for i,label in enumerate(['A','B']):
  for region in [label+'1',label+'2']:
   for j,side in enumerate(['Left','Right']):
    lane=next(x for x in f['assemblies'][i]['subensamblajes'] if x['rol']=='carril' and x['lado']==side)
    result.append(dict(baseline=label,region=region,subensamblaje=lane['handle'],
      alineamiento_ancho=None if i==1 and j==1 else f['target_axes'][i][j]['handle'],
      perfil_cota=None if i==1 and j==0 else f['target_profiles'][i][2 if i==1 else j]['handle']))
 return result

def run(drawing,output,pid,module=None,qa=None):
 q=NativeQa(drawing,output,8760,'targets-create-simulation');q.guard();f=json.loads((q.out/'targets-fixture-smoke.json').read_text());assert f['ok']
 recovery=q.out/'targets-recreate-source-smoke.json'
 if recovery.exists():f['corridor']=json.loads(recovery.read_text())['restored']['result']
 root=Path(__file__).resolve().parents[1]
 for path in [Path(module) if module else root/'modulo-targets/bin/Release/net10.0-windows/Cdcrd.Targets.V2.dll',Path(qa) if qa else root/'pruebas/native_targets_qa/bin/Release/net10.0-windows/Cdcrd.TargetsV2Qa.dll']:
  q.call('cmd.run',dict(linea='_.NETLOAD\n"'+str(path).replace('\\','/')+'"\n'))
 before=q.qa('before');args=dict(accion='crear',corredor_origen=f['corridor']['handle'],nombre='CDX QA TARGETS VARIABLE 0521',asignaciones=bindings(f));q.report['request']=args;q.record()
 q.report['catalog']=targets.ejecutar(q.drawing,pid,accion='catalogo',corredor=args['corredor_origen']);q.record()
 try:result=targets.ejecutar(q.drawing,pid,**args)
 except targets.TargetError as exc:q.report['error_receipt']=exc.receipt;q.record();raise
 q.report['simulation']=result;q.record()
 q.check('simulacion alcanza targets',result['ok'] and not result['committed'] and result['result']['verified_lane_samples']>50)
 q.check('simulacion sin residuos',canonical(before)==canonical(q.qa('after')))
 q.report['ok']=True;q.record()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--pid',type=int,required=True);p.add_argument('--module');p.add_argument('--qa');a=p.parse_args();run(a.drawing,a.output,a.pid,a.module,a.qa)
