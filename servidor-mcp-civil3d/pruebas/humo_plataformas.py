"""Native Civil 3D feature line/platform smoke test in an explicitly named disposable copy.

Requires optional native_gm_qa DLL, CDCRD_GM_QA_ROOT = output directory,
bridge 0.5.13 and a CDCRD_GM_RECOVERY_PLATFORM*.dwg copy. No automatic retries.
Leaves the synthetic feature lines and platform for visual review, unsaved.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import puente_cliente as bridge


def run(drawing, output, port):
    out = Path(output)
    report_path = out / 'platform-smoke.json'
    if not out.is_dir() or report_path.exists():
        raise RuntimeError('Output debe existir y platform-smoke.json no debe existir')
    if not Path(drawing).name.startswith('CDCRD_GM_RECOVERY_PLATFORM'):
        raise RuntimeError('Solo copia QA CDCRD_GM_RECOVERY_PLATFORM*.dwg')
    bridge.PUERTO, bridge.TIMEOUT = port, 70
    report = {'ok': False, 'checks': [], 'calls': []}
    def record():
        report_path.write_text(json.dumps(report, indent=2), encoding='utf-8')
    def guard():
        info = bridge.llamar('doc.info', {})
        if not info.get('civil3d') or os.path.normcase(info['dibujo']) != os.path.normcase(str(Path(drawing).resolve())):
            raise RuntimeError('Documento Civil exacto no activo')
        if bridge.llamar('diag.dialogos', {})['modal_abierto'] or bridge.llamar('diag.cola', {})['activas']:
            raise RuntimeError('Documento ocupado; no se reintenta')
    def call(method, params, write=True):
        guard()
        row = {'method': method, 'params': params}; report['calls'].append(row); record()
        try:
            result = (bridge.llamar_con_aprobacion if write else bridge.llamar)(method, params)
            row['result'] = result;record();return result
        except Exception as exc:
            row['error'] = str(exc);record();raise
    def check(name, passed):
        report['checks'].append({'name': name, 'pass': bool(passed)});record()
        print(('OK ' if passed else 'FAIL ') + name, flush=True)
        if not passed:raise AssertionError(name)
    def audit(label):
        dest=out/('platform-'+label+'.json')
        if dest.exists():raise RuntimeError('Audit receipt exists')
        (out/'job.json').write_text(json.dumps({'action':'audit','output':dest.name}),encoding='utf-8')
        call('cmd.run',{'linea':'CDCRDGMRECOVERYQA\n'})
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if dest.exists():
                try: data=json.loads(dest.read_text(encoding='utf-8-sig'));break
                except json.JSONDecodeError:pass
            time.sleep(.1)
        else:raise RuntimeError('No native audit receipt. Inspect before any retry.')
        if not data['ok']:raise RuntimeError(data)
        return data['result']
    def same(a,b):
        # Collection enumeration may reorder; object/geometry values must match.
        def canonical(value):
            if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
            if isinstance(value,list):
                items=[canonical(v) for v in value]
                return sorted(items,key=lambda x:x['handle']) if items and all(isinstance(v,dict) and 'handle' in v for v in items) else items
            return value
        return canonical(a)==canonical(b)
    def rejected(method,params,label):
        before=audit(label+'-before')
        try:call(method,params)
        except bridge.PuenteError as exc:
            check(label+' rechazo explicito',any(text in str(exc) for text in ['elevaciones requiere','Ya existe','cerrada','estrictamente dentro','concavo']))
        else:raise AssertionError('Debia rechazar '+label)
        check(label+' sin residuos',same(before,audit(label+'-after')))
    try:
        guard();report['ping']=bridge.llamar('ping',{});record()
        check('DLL Civil 0.5.13',report['ping']['version']=='0.5.13' and report['ping']['puente']=='cdcrd-civil3d')
        audit('baseline')
        x,y=610000,2100000
        entities=[{'tipo':'polilinea','puntos':[[x,y],[x+48,y],[x+48,y+32],[x,y+32]],'cerrada':True},
                  {'tipo':'polilinea','puntos':[[x+4,y+4],[x+44,y+4],[x+44,y+28],[x+4,y+28]],'cerrada':True},
                  {'tipo':'polilinea','puntos':[[x,y-15],[x+10,y-15],[x+20,y-10]]},
                  {'tipo':'polilinea','puntos':[[x+60,y],[x+70,y],[x+65,y+5],[x+70,y+10],[x+60,y+10]],'cerrada':True}]
        for entity in entities:entity.update(capa='CDX-QA-PLATFORM-SOURCE',color=8)
        fixture=call('entity.create',{'entidades':entities});report['fixture']=fixture;record()
        check('cuatro fuentes creadas',len(fixture['creados'])==4 and not fixture['errores'])
        handles=[v['handle'] for v in fixture['creados']]
        names=['OUTER','INNER','OPEN','CONCAVE'];zs=[[100],[102],[100,101,102],[100]]
        params=[dict(polilinea=h,nombre='CDX QA PLATFORM '+name+' 0513',elevaciones=z,capa='CDX-QA-PLATFORM-LINES') for h,name,z in zip(handles,names,zs)]
        rejected('civil.feature_line',{**params[0],'elevaciones':[100,101]},'numero-cotas')
        before=audit('feature-sim-before')
        simulation=call('civil.feature_line',{**params[0],'simular':True})
        check('feature simulada sin handle',simulation['simulacion'] and simulation['handle'] is None)
        check('feature simulada revierte',same(before,audit('feature-sim-after')))
        features=[call('civil.feature_line',value) for value in params]
        report['features']=features;record()
        check('cuatro feature lines nativas',all(v['fuente_conservada'] and v['sin_sitio'] for v in features))
        check('cotas individuales en orden', [pt[2] for pt in features[2]['puntos']]==[100,101,102])
        rejected('civil.feature_line',params[0],'feature-duplicada')
        surface={'contorno':features[0]['handle'],'linea_interior':features[1]['handle'],'nombre':'CDX QA PLATFORM 0513','capa':'CDX-QA-PLATFORM-TIN'}
        rejected('civil.superficie_feature_lines',{**surface,'contorno':features[2]['handle']},'contorno-abierto')
        rejected('civil.superficie_feature_lines',{**surface,'contorno':features[3]['handle']},'contorno-concavo')
        rejected('civil.superficie_feature_lines',{**surface,'linea_interior':features[0]['handle']},'anillos-contacto')
        rejected('civil.superficie_feature_lines',{**surface,'contorno':features[1]['handle'],'linea_interior':features[0]['handle']},'anillo-fuera')
        before=audit('surface-sim-before')
        flat=call('civil.superficie_feature_lines',{'contorno':features[0]['handle'],'nombre':'CDX QA FLAT 0513','simular':True})
        check('TIN de una sola linea',flat['simulacion'] and abs(flat['area_2d_m2']-1536)<1e-6)
        simulation=call('civil.superficie_feature_lines',{**surface,'simular':True})
        check('TIN simulado area 1536 m2',simulation['handle'] is None and abs(simulation['area_2d_m2']-1536)<1e-6)
        check('TIN simulado revierte',same(before,audit('surface-sim-after')))
        actual=call('civil.superficie_feature_lines',surface);report['surface']=actual;record()
        check('TIN nativo area y tipo',abs(actual['area_2d_m2']-1536)<1e-6 and actual['triangulos']>0 and not actual['grading_nativo'])
        rejected('civil.superficie_feature_lines',surface,'superficie-duplicada')
        final=audit('final')
        source_before={v['handle']:v for v in before['objects'] if v['handle'] in handles}
        check('fuentes conservadas exactamente',source_before=={v['handle']:v for v in final['objects'] if v['handle'] in handles})
        report['ok']=True;record()
    except Exception as exc:
        report['failure']=str(exc);record();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--drawing',required=True);parser.add_argument('--output',required=True);parser.add_argument('--port',type=int,default=8763)
    args=parser.parse_args();run(args.drawing,args.output,args.port)
