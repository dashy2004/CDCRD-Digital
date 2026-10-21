"""Native roadway QA in an identified disposable copy; no automatic write retries.

Requires bridge 0.5.16 and native_gm_qa loaded with CDCRD_GM_QA_ROOT=output.
Builds a flat synthetic terrain TIN (z=102), a lane+daylight assembly with four
pavement layers, and a corridor whose surface targets point at that TIN. Every
geometric claim is re-derived with independent formulas (same synthetic axis
and profile as the 0.5.15 run). Save/reopen is a separate check.
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

ANCHO=3.5;PEND=-.02;ESPESORES=[.05,.07,.2,.3];CORTE=3.0;RELLENO=4.0;TERRENO_Z=102.0


def canonical(value):
    if isinstance(value,dict):return {k:canonical(v) for k,v in value.items()}
    if isinstance(value,list):
        items=[canonical(v) for v in value]
        return sorted(items,key=lambda v:v['handle']) if items and all(isinstance(v,dict) and 'handle' in v for v in items) else items
    return value


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


def run(drawing,output,port):
    out=Path(output);report_path=out/'calzada-smoke.json'
    if not out.is_dir() or report_path.exists():raise RuntimeError('Output missing or receipt exists')
    if not Path(drawing).name.startswith('CDCRD_GM_RECOVERY_CALZADA'):raise RuntimeError('QA copy required')
    bridge.PUERTO,bridge.TIMEOUT=port,120
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
        dest=out/('calzada-'+label+'.json')
        if dest.exists():raise RuntimeError('Receipt exists')
        (out/'job.json').write_text(json.dumps({'action':action,'output':dest.name,**kwargs}),encoding='utf-8')
        call('cmd.run',{'linea':'CDCRDGMRECOVERYQA\n'})
        deadline=time.monotonic()+60
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
        check('Civil DLL 0.5.16',report['ping']['version']=='0.5.16')
        qa('baseline')
        # --- synthetic flat terrain TIN for daylight targets ---
        rect=[[619980,2099980],[620260,2099980],[620260,2100200],[619980,2100200]]
        fixture=call('entity.create',{'entidades':[{'tipo':'polilinea','puntos':rect,'cerrada':True,'capa':'MCP-QA-CALZADA-SOURCE','color':8}]})
        check('fuente de terreno creada',len(fixture['creados'])==1 and not fixture['errores'])
        feature=call('civil.feature_line',{'polilinea':fixture['creados'][0]['handle'],'nombre':'MCP QA TERRENO FL 0516','elevaciones':[TERRENO_Z],'capa':'MCP-QA-CALZADA-LINES'})
        check('feature line plana en 102',all(abs(pt[2]-TERRENO_Z)<1e-9 for pt in feature['puntos']))
        terrain=call('civil.superficie_feature_lines',{'contorno':feature['handle'],'nombre':'MCP QA TERRENO 0516','capa':'MCP-QA-CALZADA-TIN'})
        report['terrain']=terrain;record()
        check('TIN de terreno 280x220',abs(terrain['area_2d_m2']-61600)<1e-6 and terrain['triangulos']>0)
        # --- assembly: lane with 4 layers + daylight each side ---
        assembly=dict(nombre='MCP QA CALZADA 0516',origen=[620300,2100200,0],ancho_izq=ANCHO,ancho_der=ANCHO,
            pendiente_izq=PEND,pendiente_der=PEND,espesores=ESPESORES,talud_corte=CORTE,talud_relleno=RELLENO,
            ancho_daylight_max=50,capa='MCP-QA-CALZADA-ASSEMBLY')
        rejected('calzada-ancho-daylight','civil.ensamblaje_calzada',{**assembly,'ancho_daylight_max':0},'ancho_daylight_max')
        rejected('calzada-espesor','civil.ensamblaje_calzada',{**assembly,'espesores':[0,.07,.2,.3]},'espesor')
        rejected('calzada-espesores-cantidad','civil.ensamblaje_calzada',{**assembly,'espesores':[.05,.07,.2]},'espesores')
        rejected('calzada-talud','civil.ensamblaje_calzada',{**assembly,'talud_corte':0},'talud_corte')
        before=qa('calzada-sim-before');sim=call('civil.ensamblaje_calzada',{**assembly,'simular':True})
        check('calzada simulada',sim['simulacion'] and sim['handle'] is None and len(sim['subensamblajes'])==4)
        check('calzada simulacion sin residuos',canonical(before)==canonical(qa('calzada-sim-after')))
        rejected('calzada-failure','civil.ensamblaje_calzada',assembly,'CDCRD_QA_CORRIDOR_FAILURE',fault='calzada-part-added')
        built=call('civil.ensamblaje_calzada',assembly);report['assembly']=built;record()
        lanes=[s for s in built['subensamblajes'] if s['rol']=='carril'];dls=[s for s in built['subensamblajes'] if s['rol']=='daylight']
        check('dos carriles y dos daylight por lado',{s['lado'] for s in lanes}=={'Left','Right'} and {s['lado'] for s in dls}=={'Left','Right'})
        def par(part,key):
            key=key.lower()
            return next(p['valor'] for p in part['parametros'] if p['clave'].replace('-','').lower()==key)
        check('capas releidas por carril',all(abs(par(l,'Pave1Depth')-.05)<1e-9 and abs(par(l,'Pave2Depth')-.07)<1e-9 and abs(par(l,'BaseDepth')-.2)<1e-9 and abs(par(l,'SubBaseDepth')-.3)<1e-9 and abs(par(l,'Width')-ANCHO)<1e-9 for l in lanes))
        check('daylight enganchado al carril de su lado',all(d['engancha_a'] in {l['handle'] for l in lanes if l['lado']==d['lado']} for d in dls))
        report['tipo_talud']=sorted({p['tipo'] for d in dls for p in d['parametros']});record()
        rejected('calzada-duplicada','civil.ensamblaje_calzada',assembly,'Ya existe')
        # --- corridor with surface targets and daylight ---
        stations=[110,180,200,240,300,330,360,450]
        corridor=dict(nombre='MCP QA CORREDOR CALZADA 0516',alineamiento='CDX QA CURVE AXIS 0514',perfil='CDX QA CURVE DESIGN 0514',
            ensamblaje=built['handle'],superficie_objetivo=terrain['handle'],inicio=100,fin=340+40*math.pi,frecuencia=10,
            estaciones_extra=stations,capa='MCP-QA-CALZADA-CORREDOR')
        rejected('corredor-sin-superficie','civil.corredor_calzada',{**corridor,'superficie_objetivo':'NO EXISTE 0516'},'superficie objetivo')
        rejected('corredor-ensamblaje-sin-targets','civil.corredor_calzada',{**corridor,'nombre':'MCP QA CORREDOR ENLACES 0516','ensamblaje':'CDX QA ASSEMBLY 0515'},'no expone targets')
        rejected('corredor-frecuencia','civil.corredor_calzada',{**corridor,'frecuencia':0},'frecuencia')
        rejected('corredor-estaciones','civil.corredor_calzada',{**corridor,'estaciones_extra':[200,180]},'ordenadas')
        before=qa('corredor-sim-before');sim=call('civil.corredor_calzada',{**corridor,'simular':True})
        check('corredor simulado con targets y geometria',sim['simulacion'] and sim['handle'] is None and len(sim['targets'])>=2 and len(sim['aplicados'])>30)
        check('corredor simulacion sin residuos',canonical(before)==canonical(qa('corredor-sim-after')))
        rejected('corredor-failure-targets','civil.corredor_calzada',corridor,'CDCRD_QA_CORRIDOR_FAILURE',fault='targets-assigned')
        rejected('corredor-failure-rebuild','civil.corredor_calzada',corridor,'CDCRD_QA_CORRIDOR_FAILURE',fault='corridor-rebuilt')
        c=call('civil.corredor_calzada',corridor);report['corridor']={k:c[k] for k in c if k!='aplicados'};record()
        check('targets de superficie asignados',len(c['targets'])>=2 and all(t['objetivo']==terrain['handle'] for t in c['targets']))
        check('codigos Top y Daylight',all(code in c['codigos_enlace'] for code in ('Top','Daylight')))
        check('delta daylight de la herramienta',c['delta_daylight_max']<=1e-6)
        check('estaciones explicitas aplicadas',all(any(abs(s-t)<1e-6 for t in c['estaciones']) for s in stations))
        # --- independent geometry: XY, crown/edge elevations, layer stack, daylight on plane ---
        # soe[2] is relative to the baseline profile; xyz[2] is absolute.
        max_xy=max_top=max_stack=max_dl_z=max_abs=0;grados=[];tope=ANCHO*abs(PEND)
        total=[0,ESPESORES[0],ESPESORES[0]+ESPESORES[1],sum(ESPESORES[:3]),sum(ESPESORES)]
        for row in c['aplicados']:
            s=row['estacion'];e=elevation(s)
            for pt in row['puntos']:
                xy=alignment(s,pt['soe'][1]);max_xy=max(max_xy,math.dist(xy,pt['xyz'][:2]))
                max_abs=max(max_abs,abs(pt['soe'][2]+e-pt['xyz'][2]))
            zs={round(pt['soe'][1],6):[] for pt in row['puntos']}
            for pt in row['puntos']:zs[round(pt['soe'][1],6)].append(pt['soe'][2])
            check_center=min(abs(z) for z in zs.get(0.0,[99999]))
            edge=[z for o,v in zs.items() if abs(abs(o)-ANCHO)<1e-6 for z in v]
            max_top=max(max_top,check_center,min(abs(z+tope) for z in edge))
            for depth in total:
                max_stack=max(max_stack,min(abs(z+tope+depth) for z in edge))
            for side in (-1,1):
                dl=[pt for pt in row['puntos'] if 'Daylight' in pt['codigos'] and side*pt['soe'][1]>0]
                if not dl:raise AssertionError(('daylight ausente',s,side))
                far=max(dl,key=lambda pt:abs(pt['soe'][1]))
                max_dl_z=max(max_dl_z,abs(far['xyz'][2]-TERRENO_Z))
                attach_rel=-tope-sum(ESPESORES);run_h=abs(far['soe'][1])-ANCHO
                if run_h>1e-6:
                    grados.append({'estacion':s,'lado':side,'corte':TERRENO_Z>attach_rel+e,'grado':abs((far['soe'][2]-attach_rel)/run_h)})
        report['errors']={'max_xy':max_xy,'max_top_z':max_top,'max_stack_z':max_stack,'max_daylight_z':max_dl_z,'max_abs_vs_perfil':max_abs};record()
        check('XY de todos los puntos contra ecuacion independiente',max_xy<1e-6)
        check('cota absoluta = relativa + perfil independiente',max_abs<1e-6)
        check('cota de centro y borde contra formula',max_top<1e-6)
        check('las cuatro capas apiladas con los espesores exactos',max_stack<1e-6)
        check('daylight sobre el plano z=102',max_dl_z<1e-6)
        # slope interpretation: the observed grade must be consistent per cut/fill with ONE reading of the talud value
        cuts=[g['grado'] for g in grados if g['corte']];fills=[g['grado'] for g in grados if not g['corte']]
        def coherente(vals,talud):
            return all(abs(v-talud)<1e-6 for v in vals) or all(abs(v-1/talud)<1e-6 for v in vals)
        report['taludes_observados']={'corte':[min(cuts),max(cuts)] if cuts else [],'relleno':[min(fills),max(fills)] if fills else [],'lectura':'grado observado dz/dx = valor del parametro'};record()
        check('talud de corte coherente en todas las estaciones',bool(cuts) and coherente(cuts,CORTE))
        check('talud de relleno coherente en todas las estaciones',bool(fills) and coherente(fills,RELLENO))
        call('cmd.run',{'linea':'_.REGENALL\n'})
        mesh=qa('mesh-ready','audit')
        check('superficie de corredor triangulada',any(r['handle']==c['superficie'] and len(r['triangles'])>0 for r in mesh['surfaces']))
        audit=qa('targets-persistidos','corridor_audit')
        cz=[row for row in audit['corridors'] if row['handle']==c['handle']][0]
        check('targets releidos en auditoria nativa',all(t['ids']==[terrain['handle']] for b in cz['baselines'] for r in b['regions'] for t in r['targets'] if t['type']=='Surface') and any(t['type']=='Surface' for b in cz['baselines'] for r in b['regions'] for t in r['targets']))
        check('corredor al dia',not cz['out_of_date'])
        rejected('corredor-duplicado','civil.corredor_calzada',corridor,'Ya existe')
        report['final']=qa('final');report['ok']=True;record()
        return report
    finally:record()

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--drawing',required=True);parser.add_argument('--output',required=True);parser.add_argument('--port',type=int,default=8765);args=parser.parse_args()
    result=run(args.drawing,args.output,args.port);print('PASS',len(result['checks']))
