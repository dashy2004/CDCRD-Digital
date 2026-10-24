"""Native SCS acceptance in the identified open copy; no CAD launch or retries."""
import argparse
import json
import math
from pathlib import Path
import time
from humo_cunetas_bermas import NativeQa, canonical
from espiral_referencia import Reference, fixture
import espirales


def verify(q, result, label):
    ref=Reference(result['geometry'])
    errors=[]; angles=[]
    for row in result['samples']:
        for point in row['points']:
            xy,heading,k=ref.at(row['station'],point['offset'])
            errors.append(max(abs(a-b) for a,b in zip(xy,point['xy'])))
        center=next(p['xy'] for p in row['points'] if p['offset']==0)
        right=next(p['xy'] for p in row['points'] if p['offset']==3.5)
        native_heading=math.atan2(right[0]-center[0],center[1]-right[1])
        _,expected,_=ref.at(row['station'])
        angles.append(abs(math.atan2(math.sin(native_heading-expected),math.cos(native_heading-expected))))
    q.check(label+' coordenadas por serie Fresnel',max(errors)<1e-6)
    q.check(label+' orientacion nativa por offsets normales',max(angles)<1e-8)
    q.check(label+' longitud y cinco subentidades',abs(result['length']-ref.length)<1e-6 and [p['type'] for p in result['parts']]==['Line','Spiral','Arc','Spiral','Line'])
    q.check(label+' uniones sin salto',all(math.dist(a['end'],b['start'])<1e-6 and abs(a['end_station']-b['start_station'])<1e-6 for a,b in zip(result['parts'],result['parts'][1:])))
    q.check(label+' parametros A independientes',abs(result['spiral_in_a']-math.sqrt(ref.r*ref.li))<1e-6 and abs(result['spiral_out_a']-math.sqrt(ref.r*ref.lo))<1e-6)
    q.report.setdefault('independent_errors',{})[label]=dict(xy_m=max(errors),heading_rad=max(angles),length_m=abs(result['length']-ref.length),sample_count=len(result['samples']))


def run(drawing,output,pid):
    q=NativeQa(drawing,output,8760,'spirals')
    def create(label,g=None,name='CDX QA ESPIRAL IZQUIERDA 0519',simulate=True):
        q.guard()
        try:
            r=espirales.ejecutar(q.drawing,pid,nombre=name,geometria=g or fixture(),capa='CDX-QA-ESPIRALES',simular=simulate)
        except espirales.SpiralError as exc:
            q.report.setdefault('native_receipts',{})[label]=exc.receipt;q.record();raise
        q.report.setdefault('native_receipts',{})[label]=r;q.record()
        return r['result']
    before=q.qa('baseline');q.report['baseline']=before
    for label,changes,message in [('fit',{'radio':1000},'no cabe'),('collinear',{'fin':[620270,2100020]},'Deflexion'),('no-arc',{'longitud_entrada':100,'longitud_salida':100},'consumen')]:
        g=fixture();g.update(changes)
        try:
            create(label,g,simulate=False);raise AssertionError('Invalid geometry accepted')
        except espirales.SpiralError as exc:
            q.check(label+' rechazo nativo',message in str(exc) and not exc.receipt['committed'])
        q.check(label+' sin residuos',canonical(before)==canonical(q.qa(label+'-after')))
    simulated=create('simulation')
    verify(q,simulated,'simulacion')
    q.check('simulacion sin commit',not q.report['native_receipts']['simulation']['committed'] and simulated['handle'] is None)
    q.check('simulacion revertida',canonical(before)==canonical(q.qa('simulation-after')))
    for stage in ['tangents-created','scs-created','geometry-verified']:
        dest=q.out/('spiral-fault-'+stage+'.json')
        if dest.exists():raise FileExistsError(dest)
        (q.out/'espirales-fault.json').write_text(json.dumps(dict(stage=stage,output=dest.name)))
        q.call('cmd.run',{'linea':'CDCRDESPIRALESV1QA\n'})
        deadline=time.monotonic()+20
        while not dest.exists() and time.monotonic()<deadline:time.sleep(.1)
        if not dest.exists():raise RuntimeError('No arm receipt; inspect state')
        try:
            create(stage,simulate=False);raise AssertionError('Fault did not fire')
        except espirales.SpiralError as exc:
            q.check(stage+' fallo controlado','CDCRD_QA_SPIRAL_FAILURE' in str(exc) and not exc.receipt['committed'])
        q.check(stage+' rollback completo',canonical(before)==canonical(q.qa(stage+'-after')))
    left=create('left',simulate=False)
    right=create('right',fixture(True),'CDX QA ESPIRAL DERECHA 0519',False)
    q.report.update(left=left,right=right)
    for label,result in [('left',left),('right',right)]:
        q.check(label+' commit confirmado',q.report['native_receipts'][label]['committed'])
        verify(q,result,label)
        reread=espirales.ejecutar(q.drawing,pid,alineamiento=result['handle'])
        q.check(label+' relectura contrato Xrecord nativo',canonical(result)==canonical(reread['result']))
    after=q.qa('after')
    try:
        create('duplicate',simulate=False);raise AssertionError('Duplicate accepted')
    except espirales.SpiralError as exc:
        q.check('duplicado rechazado','Ya existe' in str(exc) and not exc.receipt['committed'])
    q.check('duplicado sin residuos',canonical(after)==canonical(q.qa('duplicate-after')))
    q.report['ok']=True;q.record()
    return q.report


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--pid',required=True,type=int)
    a=p.parse_args();print('PASS',len(run(a.drawing,a.output,a.pid)['checks']))
