"""Native Civil 3D site smoke test in an explicitly named disposable copy.

Requires optional native_gm_qa DLL, CDCRD_GM_QA_ROOT = output directory,
bridge 0.5.12 and a CDCRD_GM_RECOVERY_SITE*.dwg copy. No automatic retries.
Leaves the synthetic parcel/alignment/profile for visual review, unsaved.
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
    report_path = out / 'site-smoke.json'
    if not out.is_dir() or report_path.exists():
        raise RuntimeError('Output debe existir y site-smoke.json no debe existir')
    if not Path(drawing).name.startswith('CDCRD_GM_RECOVERY_SITE'):
        raise RuntimeError('Solo copia QA CDCRD_GM_RECOVERY_SITE*.dwg')
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
        dest=out/('site-'+label+'.json')
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
            check(label+' rechazo explicito',any(text in str(exc) for text in ['autointersectada','ya existe','Ya existe','PVI fuera']))
        else:raise AssertionError('Debia rechazar '+label)
        check(label+' sin residuos',same(before,audit(label+'-after')))
    try:
        guard();report['ping']=bridge.llamar('ping',{});record()
        check('DLL Civil 0.5.12',report['ping']['version']=='0.5.12' and report['ping']['puente']=='cdcrd-civil3d')
        report['baseline']=str(out/'site-baseline.json');audit('baseline')
        x,y=600000,2100000
        entities=[{'tipo':'polilinea','puntos':[[x,y],[x+80,y],[x+80,y+50],[x,y+50]],'cerrada':True,'capa':'CDX-QA-SITE-SOURCE','color':8},
                  {'tipo':'polilinea','puntos':[[x,y-35],[x+80,y-35],[x+120,y-15],[x+160,y-15]],'capa':'CDX-QA-SITE-SOURCE','color':8},
                  {'tipo':'polilinea','puntos':[[x+100,y],[x+140,y+40],[x+100,y+40],[x+140,y]],'cerrada':True,'capa':'CDX-QA-SITE-INVALID'}]
        fixture=call('entity.create',{'entidades':entities});report['fixture']=fixture;record()
        check('tres fuentes creadas',len(fixture['creados'])==3 and not fixture['errores'])
        poly,axis,bad=[v['handle'] for v in fixture['creados']]
        parcel={'polilinea':poly,'nombre':'CDX QA LOT 4000 m2','sitio_nuevo':'CDX QA SITE 0512','capa':'CDX-QA-SITE-PARCEL'}
        rejected('civil.parcela_polilinea',{**parcel,'polilinea':bad},'poligono-cruzado')
        before=audit('parcel-sim-before');simulation=call('civil.parcela_polilinea',{**parcel,'simular':True})
        check('parcela simulada 4000 m2',simulation['simulacion'] and simulation['handle'] is None and abs(simulation['area_m2']-4000)<1e-6)
        check('parcela COM y sitio revierten',same(before,audit('parcel-sim-after')))
        actual=call('civil.parcela_polilinea',parcel);report['parcel']=actual;record()
        check('parcela nativa 4000 m2',abs(actual['area_m2']-4000)<1e-6 and actual['fuente_conservada'])
        rejected('civil.parcela_polilinea',parcel,'sitio-duplicado')
        alignment={'polilinea':axis,'nombre':'CDX QA AXIS 0512','estacion_inicial':100,'capa':'CDX-QA-SITE-AXIS'}
        before=audit('axis-sim-before');call('civil.alineamiento_polilinea',{**alignment,'simular':True})
        check('eje simulado revierte',same(before,audit('axis-sim-after')))
        actual=call('civil.alineamiento_polilinea',alignment);report['alignment']=actual;record()
        check('eje longitud y estacion',abs(actual['longitud_m']-(120+math.sqrt(2000)))<1e-6 and abs(actual['est_inicio']-100)<1e-7)
        rejected('civil.alineamiento_polilinea',alignment,'eje-duplicado')
        profile={'alineamiento':actual['handle'],'nombre':'CDX QA DESIGN 0512','pvis':[[100,100],[150,101],[200,99],[actual['est_fin'],100]],'capa':'CDX-QA-SITE-PROFILE'}
        rejected('civil.perfil_pvi',{**profile,'pvis':[[100,100],[300,101]]},'PVI-fuera')
        rejected('civil.perfil_pvi',{**profile,'pvis':[[150,100],[100,101]]},'PVI-desorden')
        before=audit('profile-sim-before');call('civil.perfil_pvi',{**profile,'simular':True})
        check('perfil simulado revierte',same(before,audit('profile-sim-after')))
        actual=call('civil.perfil_pvi',profile);report['profile']=actual;record()
        check('cuatro PVI y pendientes',actual['pvis']==profile['pvis'] and abs(actual['pendientes'][0]-.02)<1e-9 and abs(actual['pendientes'][1]+.04)<1e-9)
        rejected('civil.perfil_pvi',profile,'perfil-duplicado')
        call('objects.erase',{'handles':[bad]})
        final=audit('final');report['final_audit']=str(out/'site-final.json')
        check('fuentes validas conservadas',all(any(v['handle']==h for v in final['objects']) for h in [poly,axis]))
        report['ok']=True;record()
    except Exception as exc:
        report['failure']=str(exc);record();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--drawing',required=True);parser.add_argument('--output',required=True);parser.add_argument('--port',type=int,default=8763)
    args=parser.parse_args();run(args.drawing,args.output,args.port)
