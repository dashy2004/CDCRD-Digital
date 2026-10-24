"""Native pay-item acceptance on a fresh protected copy; never launches CAD.

Requires the existing bridge, NativeQa harness and an exclusive session lock.
The DWG must have no pay-item catalog. Refuses existing fixture/receipts.
"""
import argparse
import json
import time
from pathlib import Path
from humo_cunetas_bermas import NativeQa, canonical
import partidas

def run(drawing,output,pid,module,qa_module):
    q=NativeQa(drawing,output,8760,'partidas');q.guard()
    if (q.out/'payitems-fixture.json').exists():raise FileExistsError('Fixture exists; inspect receipts, do not repeat')
    def wait(name):
        dest=q.out/name;deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if dest.exists():return json.loads(dest.read_text())
            time.sleep(.1)
        raise RuntimeError('Native receipt missing; inspect state without retry: '+str(dest))
    def call(action,**args):
        try:r=partidas.ejecutar(q.drawing,pid,accion=action,**args)
        except partidas.PartidasError as e:q.report.setdefault('rejected_receipts',[]).append(e.receipt);q.record();raise
        q.report.setdefault('receipts',[]).append(r);q.record();return r
    for dll in (module,qa_module):
        path=Path(dll).resolve()
        if not path.is_file() or path.suffix.lower()!='.dll':raise ValueError('Existing own DLL required')
        q.call('cmd.run',{'linea':'_.NETLOAD\n"'+path.as_posix()+'"\n'})
    q.check('no previous catalog',not call('estado')['result']['catalog'])
    before=q.qa('before-fixture')
    q.call('cmd.run',{'linea':'CDCRDPARTIDASFIXTURE\n'})
    fixture=wait('payitems-fixture.json');q.check('same process',fixture['pid']==pid)
    items=[dict(codigo='CDX-'+u,descripcion='Ensayo '+u,unidad=u) for u in ('EA','M','M2','M3')]
    plan=call('catalogo',partidas=items)
    q.check('catalog preview no write',not plan['committed'] and not call('estado')['result']['catalog'])
    call('catalogo',partidas=items,simular=False)
    assignments=[dict(handle=e['handle'],partida='CDX-'+e['unit']) for e in fixture['entities']];handles=[a['handle'] for a in assignments]
    snapshot=q.qa('before-assignment')
    call('asignar',asignaciones=assignments)
    q.check('assignment preview no write',all(not e['payitems'] for e in call('leer',handles=handles)['result']))
    (q.out/'partidas-fault.json').write_text(json.dumps(dict(stage='assigned',output='partidas-armed.json',occurrence=3)))
    q.call('cmd.run',{'linea':'CDCRDPARTIDASV3QA\n'});wait('partidas-armed.json')
    try:call('asignar',asignaciones=assignments,simular=False)
    except partidas.PartidasError as e:q.check('fault caught','CDCRD_QA_PARTIDAS_FAILURE' in str(e))
    else:raise AssertionError('Fault not raised')
    q.check('all assignments rolled back',all(not e['payitems'] for e in call('leer',handles=handles)['result']))
    q.check('rollback preserves inventory',canonical(snapshot)==canonical(q.qa('after-fault')))
    call('asignar',asignaciones=assignments,simular=False)
    for label,action,args,error in [
        ('repeat catalog','catalogo',dict(partidas=items),'existe catalogo'),
        ('repeat assignment','asignar',dict(asignaciones=assignments),'ya asignada'),
        ('unknown code','asignar',dict(asignaciones=[dict(handle=handles[0],partida='NO-ITEM')]),'ausente'),
        ('wrong geometry','asignar',dict(asignaciones=[dict(handle=handles[0],partida='CDX-M2')]),'Tipo no soportado')]:
        try:call(action,**args,simular=False)
        except partidas.PartidasError as e:q.check(label,error in str(e))
        else:raise AssertionError(label+' accepted')
    report=call('informe')['result'];expected={'EA':3,'M':35,'M2':200,'M3':24}
    q.check('four native rows',len(report['quantities'])==4)
    for row in report['quantities']:q.check(row['unit'],abs(row['quantity']-expected[row['unit']])<1e-8)
    q.report['quantities']=report['quantities'];q.report['baseline']=before
    for mode in ('table','plan-final','report-final'):
        (q.out/'partidas-evidence-job.json').write_text(json.dumps(dict(mode=mode)))
        q.call('cmd.run',{'linea':'CDCRDPARTIDASEVIDENCEFINAL\n'});wait('payitems-evidence-'+mode+'.json')
        if mode=='table':
            q.call('cmd.run',{'linea':'CDCRDPARTIDASLAYOUT\n'});wait('payitems-layout-final.json')
            q.call('cmd.run',{'linea':'CDCRDPARTIDASGRID\n'});wait('payitems-grid.json')
        else:q.qa('capture-'+mode,'capture',image='partidas-'+mode+'.png')
    q.report['ok']=True;q.record();return q.report

if __name__=='__main__':
    p=argparse.ArgumentParser()
    for a in ('drawing','output','module','qa-module'):p.add_argument('--'+a,required=True)
    p.add_argument('--pid',required=True,type=int);a=p.parse_args()
    run(a.drawing,a.output,a.pid,a.module,a.qa_module)
