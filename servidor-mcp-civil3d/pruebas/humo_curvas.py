"""Native curve QA in an identified disposable copy; no automatic write retries.

Requires bridge 0.5.14 and native_gm_qa loaded with CDCRD_GM_QA_ROOT=output.
Leaves the synthetic axis/profile for review; save/reopen is a separate check.
"""
import argparse
import json
import math
import os
from pathlib import Path
import sys
import time
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import puente_cliente as bridge


def canonical(value):
    if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
    if isinstance(value,list):
        items=[canonical(v) for v in value]
        return sorted(items,key=lambda v:v['handle']) if items and all(isinstance(v,dict) and 'handle' in v for v in items) else items
    return value


def run(drawing,output,port):
    out=Path(output);report_path=out/'curve-smoke.json'
    if not out.is_dir() or report_path.exists():raise RuntimeError('Output missing or receipt exists')
    if not Path(drawing).name.startswith('CDCRD_GM_RECOVERY_CURVES'):raise RuntimeError('QA copy required')
    bridge.PUERTO,bridge.TIMEOUT=port,70
    report={'ok':False,'checks':[],'calls':[]}
    def record():report_path.write_text(json.dumps(report,indent=2),encoding='utf-8')
    def guard():
        info=bridge.llamar('doc.info',{})
        if not info.get('civil3d') or os.path.normcase(info['dibujo'])!=os.path.normcase(str(Path(drawing).resolve())):raise RuntimeError('Wrong Civil document')
        if bridge.llamar('diag.dialogos',{})['modal_abierto'] or bridge.llamar('diag.cola',{})['activas']:raise RuntimeError('Busy; inspect before retry')
    def call(method,params,write=True):
        guard();row={'method':method,'params':params};report['calls'].append(row);record()
        try:r=(bridge.llamar_con_aprobacion if write else bridge.llamar)(method,params)
        except Exception as e:row['error']=str(e);record();raise
        row['result']=r;record();return r
    def check(name,condition):
        report['checks'].append({'name':name,'pass':bool(condition)});record()
        print(('OK ' if condition else 'FAIL ')+name,flush=True)
        if not condition:raise AssertionError(name)
    def qa(label,action='audit',**kwargs):
        dest=out/('curves-'+label+'.json')
        if dest.exists():raise RuntimeError('Receipt exists')
        (out/'job.json').write_text(json.dumps({'action':action,'output':dest.name,**kwargs}),encoding='utf-8')
        call('cmd.run',{'linea':'CDCRDGMRECOVERYQA\n'})
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            if dest.exists():
                try:r=json.loads(dest.read_text(encoding='utf-8-sig'));break
                except json.JSONDecodeError:pass
            time.sleep(.1)
        else:raise RuntimeError('No native receipt; inspect state, no retry')
        if not r['ok']:raise RuntimeError(r)
        return r['result']
    def rejected(label,method,params,expected,fault=None):
        before=qa(label+'-before')
        if fault:qa(label+'-arm','curve_fault',stage=fault)
        try:call(method,params)
        except bridge.PuenteError as e:check(label+' rechazo explicito',expected in str(e))
        else:raise AssertionError(label+' accepted')
        check(label+' sin residuos',canonical(before)==canonical(qa(label+'-after')))
    try:
        guard();report['ping']=bridge.llamar('ping',{});record()
        check('Civil DLL 0.5.14',report['ping']['version']=='0.5.14')
        baseline=qa('baseline')
        fixture=qa('fixture','curve_fixture');report['fixture']=fixture;record()
        fixture_audit=qa('fixture-audit')
        axis={'polilinea':fixture['axis'],'nombre':'CDX QA CURVE AXIS 0514','estacion_inicial':100,'capa':'CDX-QA-CURVE-AXIS'}
        for key,error in [('crossing','autointersectado'),('overlap','superpuestos'),('major','180 grados')]:
            rejected(key,'civil.alineamiento_polilinea',{**axis,'polilinea':fixture[key]},error)
        straight_before=qa('straight-compatibility-before')
        dense=call('entity.create',{'entidades':[{'tipo':'polilinea','puntos':[[621000+i,2100000] for i in range(201)],'capa':'CDX-QA-CURVES-SOURCE'}]})
        check('fuente recta 201 vertices creada',not dense['errores'] and len(dense['creados'])==1)
        dense_handle=dense['creados'][0]['handle']
        dense_result=call('civil.alineamiento_polilinea',{**axis,'nombre':'CDX QA STRAIGHT COMPATIBILITY','polilinea':dense_handle,'simular':True})
        check('compatibilidad eje recto mayor de 200 vertices',abs(dense_result['longitud_m']-200)<1e-6 and not dense_result['geometria']['arcos'])
        call('objects.erase',{'handles':[dense_handle]})
        check('compatibilidad sin residuos',canonical(straight_before)==canonical(qa('straight-compatibility-after')))
        before=qa('axis-simulation-before');sim=call('civil.alineamiento_polilinea',{**axis,'simular':True})
        check('eje simulado con dos arcos',sim['simulacion'] and sim['handle'] is None and len(sim['geometria']['arcos'])==2)
        check('simulacion del eje revierte',canonical(before)==canonical(qa('axis-simulation-after')))
        rejected('axis-failure','civil.alineamiento_polilinea',axis,'CDCRD_QA_CURVE_FAILURE',fault='alignment-created')
        a=call('civil.alineamiento_polilinea',axis);report['alignment']=a;record()
        check('longitud y estacion verificadas',abs(a['longitud_m']-(240+40*math.pi))<1e-6 and abs(a['est_inicio']-100)<1e-7)
        arcs=a['geometria']['arcos']
        check('dos arcos R40 de sentidos opuestos',len(arcs)==2 and all(abs(v['radio_m']-40)<1e-6 for v in arcs) and {v['horario'] for v in arcs}=={True,False})
        check('puntos nativos coinciden con fuente',a['geometria']['max_error_xy_m']<1e-6)
        rejected('axis-duplicate','civil.alineamiento_polilinea',axis,'Ya existe')
        profile={'alineamiento':a['handle'],'nombre':'CDX QA CURVE DESIGN 0514','pvis':[[100,100],[200,104],[300,100],[a['est_fin'],102]],
                 'curvas':[{'pvi':1,'longitud':40},{'pvi':2,'longitud':60}],'capa':'CDX-QA-CURVE-PROFILE'}
        report['profile_input']=profile;record()
        rejected('curve-overlap','civil.perfil_pvi',{**profile,'curvas':[{'pvi':1,'longitud':120},{'pvi':2,'longitud':120}]},'solapadas')
        rejected('curve-endpoint','civil.perfil_pvi',{**profile,'curvas':[{'pvi':0,'longitud':20}]},'interior')
        rejected('curve-tangent-boundary','civil.perfil_pvi',{**profile,'curvas':[{'pvi':1,'longitud':200}]},'tangentes')
        before=qa('profile-simulation-before');sim=call('civil.perfil_pvi',{**profile,'simular':True})
        check('perfil simulado con dos parabolas',sim['simulacion'] and sim['handle'] is None and len(sim['verificacion']['curvas'])==2)
        check('simulacion de perfil revierte',canonical(before)==canonical(qa('profile-simulation-after')))
        rejected('profile-failure','civil.perfil_pvi',profile,'CDCRD_QA_CURVE_FAILURE',fault='profile-curve-added')
        design=call('civil.perfil_pvi',profile);report['profile']=design;record()
        check('PVI de diseno conservados',design['pvis']==profile['pvis'])
        check('parabola convexa y concava nativas',{c['tipo'] for c in design['verificacion']['curvas']}=={'Crest','Sag'})
        check('ecuacion independiente y muestras',design['verificacion']['max_error_z_m']<1e-6 and len(design['verificacion']['muestras'])>=10)
        crest=next(s for s in design['verificacion']['muestras'] if s['estacion']==200)
        check('ordenada convexa 103.6 m',abs(crest['elevacion']-103.6)<1e-8)
        rejected('profile-duplicate','civil.perfil_pvi',profile,'Ya existe')
        call('objects.erase',{'handles':[fixture[k] for k in ['crossing','overlap','major']]})
        final=qa('final');geometry=qa('native-geometry','curve_audit');report['geometry']=geometry
        source_before=next(v for v in fixture_audit['objects'] if v['handle']==fixture['axis'])
        source_after=next(v for v in final['objects'] if v['handle']==fixture['axis'])
        check('fuente con bulges intacta',source_before==source_after)
        old={v['handle']:v for v in baseline['objects']};new={v['handle']:v for v in final['objects']}
        check('todos los objetos previos conservados',all(new.get(h)==v for h,v in old.items()))
        report['prior_objects_preserved']=len(old);report['ok']=True;record()
    except Exception as e:report['failure']=str(e);record();raise


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--drawing',required=True);parser.add_argument('--output',required=True);parser.add_argument('--port',type=int,default=8763)
    args=parser.parse_args();run(args.drawing,args.output,args.port)
