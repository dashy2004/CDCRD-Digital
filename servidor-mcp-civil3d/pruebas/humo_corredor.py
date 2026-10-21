"""Native corridor QA in an identified disposable copy; no automatic write retries.

Requires bridge 0.5.15 and native_gm_qa loaded with CDCRD_GM_QA_ROOT=output.
Uses the existing synthetic curve axis/profile and leaves assembly, corridor
and sections for review; save/reopen is a separate check.
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
    out=Path(output);report_path=out/'corridor-smoke.json'
    if not out.is_dir() or report_path.exists():raise RuntimeError('Output missing or receipt exists')
    if not Path(drawing).name.startswith('CDCRD_GM_RECOVERY_CORRIDOR'):raise RuntimeError('QA copy required')
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
    def qa(label,action='combined_audit',**kwargs):
        if action=='combined_audit':
            return {'drawing':qa(label+'-drawing','audit'),'corridor':qa(label+'-civil','corridor_audit')}
        dest=out/('corridor-'+label+'.json')
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
        if fault:qa(label+'-arm','corridor_fault',stage=fault)
        try:call(method,params)
        except bridge.PuenteError as e:check(label+' rechazo explicito',expected in str(e))
        else:raise AssertionError(label+' accepted')
        check(label+' sin residuos',canonical(before)==canonical(qa(label+'-after')))
    try:
        guard();report['ping']=bridge.llamar('ping',{});record()
        check('Civil DLL 0.5.15',report['ping']['version']=='0.5.15')
        baseline=qa('baseline')
        assembly=dict(nombre='CDX QA ASSEMBLY 0515',origen=[620300,2100100,0],ancho_izq=3.5,ancho_der=3.5,pendiente_izq=-.02,pendiente_der=-.02,capa='CDX-QA-CORRIDOR-ASSEMBLY')
        rejected('assembly-width','civil.ensamblaje_enlaces',{**assembly,'ancho_izq':-1},'ancho_izq')
        before=qa('assembly-sim-before');sim=call('civil.ensamblaje_enlaces',{**assembly,'simular':True})
        check('ensamblaje simulado',sim['simulacion'] and sim['handle'] is None and len(sim['subensamblajes'])==2)
        check('ensamblaje simulacion sin residuos',canonical(before)==canonical(qa('assembly-sim-after')))
        rejected('assembly-failure','civil.ensamblaje_enlaces',assembly,'CDCRD_QA_CORRIDOR_FAILURE',fault='assembly-part-added')
        built=call('civil.ensamblaje_enlaces',assembly);report['assembly']=built;record()
        check('dos lados y parametros releidos',{s['lado'] for s in built['subensamblajes']}=={'Left','Right'} and all(s['ancho']==3.5 and s['pendiente']==-.02 for s in built['subensamblajes']))
        rejected('assembly-duplicate','civil.ensamblaje_enlaces',assembly,'Ya existe')
        stations=[110,180,200,240,300,330,360,450]
        corridor=dict(nombre='CDX QA CORRIDOR 0515',alineamiento='CDX QA CURVE AXIS 0514',perfil='CDX QA CURVE DESIGN 0514',ensamblaje=built['handle'],inicio=100,fin=340+40*math.pi,frecuencia=10,estaciones_extra=stations,capa='CDX-QA-CORRIDOR')
        other=next(a['profiles'][0]['handle'] for a in baseline['drawing']['alignments'] if a['name']=='CDX QA AXIS 0512')
        rejected('corridor-profile-owner','civil.corredor',{**corridor,'perfil':other},'no pertenece')
        rejected('corridor-region','civil.corredor',{**corridor,'inicio':99},'inicio')
        rejected('corridor-frequency','civil.corredor',{**corridor,'frecuencia':0},'frecuencia')
        rejected('corridor-stations','civil.corredor',{**corridor,'estaciones_extra':[200,180]},'ordenadas')
        before=qa('corridor-sim-before');sim=call('civil.corredor',{**corridor,'simular':True})
        check('corredor simulado con geometria',sim['simulacion'] and sim['handle'] is None and len(sim['aplicados'])>30)
        check('corredor simulacion sin residuos',canonical(before)==canonical(qa('corridor-sim-after')))
        rejected('corridor-failure','civil.corredor',corridor,'CDCRD_QA_CORRIDOR_FAILURE',fault='corridor-rebuilt')
        c=call('civil.corredor',corridor);report['corridor']=c;record()
        check('estaciones explicitas aplicadas',all(any(abs(s-t)<1e-6 for t in c['estaciones']) for s in stations))
        def alignment(s,offset):
            t=s-100
            if t<=80:x,y,h=t,0,0
            elif t<=80+20*math.pi:
                h=(t-80)/40;x,y=80+40*math.sin(h),40-40*math.cos(h)
            elif t<=160+20*math.pi:x,y,h=120,40+t-80-20*math.pi,math.pi/2
            elif t<=160+40*math.pi:
                theta=(t-160-20*math.pi)/40;h=math.pi/2-theta;x,y=160-40*math.cos(theta),120+40*math.sin(theta)
            else:x,y,h=160+t-160-40*math.pi,160,0
            return [620000+x+offset*math.sin(h),2100000+y-offset*math.cos(h)]
        def elevation(s):
            slope=2/(40+40*math.pi)
            if s<=180:return 100+.04*(s-100)
            if s<=220:return 103.2+.04*(s-180)-.08*(s-180)**2/80
            if s<=270:return 104-.04*(s-200)
            if s<=330:return 101.2-.04*(s-270)+(slope+.04)*(s-270)**2/120
            return 100+slope*(s-300)
        max_xy=max_z=0
        for row in c['aplicados']:
            check_offsets=sorted(round(p['soe'][1],5) for p in row['puntos'])
            if not {-3.5,0,3.5}.issubset(set(check_offsets)):raise AssertionError(('wrong offsets',row))
            for point in row['puntos']:
                s,offset,z=point['soe'];xy=alignment(s,offset);expected_z=elevation(s)-abs(offset)*.02
                max_xy=max(max_xy,math.dist(xy,point['xyz'][:2]));max_z=max(max_z,abs(point['xyz'][2]-expected_z))
        report['errors']={'max_xy':max_xy,'max_z':max_z};record()
        check('XYZ corredor contra ecuacion independiente',max_xy<1e-6 and max_z<1e-6)
        call('cmd.run',{'linea':'_.REGENALL\n'})
        qa('materialize','corridor_audit')
        mesh=qa('mesh-ready','audit')
        check('superficie triangulada nativa',any(row['handle']==c['superficie'] and len(row['triangles'])>0 for row in mesh['surfaces']))
        rejected('corridor-duplicate','civil.corredor',corridor,'Ya existe')
        sections=dict(corredor=c['handle'],nombre='CDX QA SECTIONS 0515',estaciones=stations,semiancho=5,origen=[620350,2100100,0],cota_min=99,cota_max=105,capa='CDX-QA-CORRIDOR-SECTIONS')
        rejected('sections-unapplied','civil.secciones_corredor',{**sections,'estaciones':[111.234]},'estaciones aplicadas')
        before=qa('sections-sim-before');sim=call('civil.secciones_corredor',{**sections,'simular':True})
        check('secciones simuladas',sim['simulacion'] and len(sim['secciones'])==8)
        check('secciones simulacion sin residuos',canonical(before)==canonical(qa('sections-sim-after')))
        rejected('sections-failure','civil.secciones_corredor',sections,'CDCRD_QA_CORRIDOR_FAILURE',fault='section-created')
        result=call('civil.secciones_corredor',sections);report['sections']=result;record()
        check('ocho secciones y vistas nativas',len(result['secciones'])==8 and all(r['vista'] and r['linea'] for r in result['secciones']))
        check('lineas siguen normales de eje curvo',all(math.dist(r['izquierda'],alignment(r['estacion'],-5))<1e-6 and math.dist(r['derecha'],alignment(r['estacion'],5))<1e-6 for r in result['secciones']))
        section_errors=[]
        for row in result['secciones']:
            raw=row['secciones'][0]['puntos']
            connected={i for i,p in enumerate(raw) if p['segment_to']>=0}|{p['segment_to'] for p in raw if p['segment_to']>=0}
            points=[raw[i] for i in sorted(connected)]
            check('dos segmentos conectados '+str(row['estacion']),sum(p['segment_to']>=0 for p in raw)==2)
            check('seccion sin extrapolacion '+str(row['estacion']),all(abs(pt['offset'])<=3.500001 for pt in points))
            for offset in [-3.5,0,3.5]:
                nearest=min(points,key=lambda pt:abs(pt['offset']-offset))
                if abs(nearest['offset']-offset)>1e-6:raise AssertionError('borde/centro ausente')
                section_errors.append(abs(nearest['cota']-(elevation(row['estacion'])-abs(offset)*.02)))
        report['errors']['max_section_z']=max(section_errors);record()
        check('cotas de secciones contra formula',max(section_errors)<1e-6)
        rejected('reflection-fatal-protected','objects.invoke',{'handle':result['handle'],'metodo':'GetSectionSources','args':[]},'no es seguro')
        rejected('reflection-route-protected','objects.read',{'handle':result['handle'],'ruta':'GetSectionSources()'},'no es seguro')
        rejected('sections-duplicate','civil.secciones_corredor',sections,'Ya existe')
        report['final']=qa('final');check('estilos H=V con texto dimensionado',all(v['exaggeration']==1 and abs(v['label_height_model']-.6)<1e-8 and abs(v['title_height_model']-.85)<1e-8 for g in report['final']['corridor']['groups'] for l in g['lines'] for v in l['views']));report['ok']=True;record()
        return report
    finally:record()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--drawing',required=True);parser.add_argument('--output',required=True);parser.add_argument('--port',type=int,default=8764);args=parser.parse_args()
    result=run(args.drawing,args.output,args.port);print('PASS',len(result['checks']))
