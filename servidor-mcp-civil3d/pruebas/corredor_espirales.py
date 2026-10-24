"""Integrate the validated SCS with profile, roadway, peraltes and native sections."""
import argparse
import json
import math
from pathlib import Path
from humo_cunetas_bermas import NativeQa, canonical
from espiral_referencia import Reference
from humo_peraltes import expected
import peraltes


def run(drawing,output,pid,smoke):
    data=json.loads(Path(smoke).read_text())
    if not data['ok']:raise ValueError('Successful spiral smoke required')
    q=NativeQa(drawing,output,8760,'spirals-corridor')
    axis=data['left'];ref=Reference(axis['geometry']);start,end=axis['start_station'],axis['end_station']
    # Use exact native break stations when passing data back to Civil.
    ts=axis['parts'][1]['start_station'];sc=axis['parts'][2]['start_station']
    cs=axis['parts'][3]['start_station'];st=axis['parts'][4]['start_station']
    stations=[ts-15,ts,(ts+sc)/2,sc,(sc+cs)/2,cs,(cs+st)/2,st+15]
    profile=q.call('civil.perfil_pvi',dict(alineamiento=axis['handle'],nombre='CDX QA ESPIRAL PROFILE 0519',pvis=[[start,101],[end,103]],capa='CDX-QA-ESPIRALES-PROFILE'))
    params=json.loads((Path(__file__).resolve().parents[1]/'docs/PERALTES-0518-fixture.json').read_text())['assembly']
    params.update(nombre='CDX QA ESPIRAL ASSEMBLY 0519',origen=[620300,2100330,0],capa='CDX-QA-ESPIRALES-ASSEMBLY')
    assembly=q.call('civil.ensamblaje_cunetas_bermas',params)
    corridor=q.call('civil.corredor_calzada',dict(nombre='CDX QA ESPIRAL CORRIDOR 0519',alineamiento=axis['handle'],perfil=profile['handle'],ensamblaje=assembly['handle'],
        superficie_objetivo='MCP QA TERRENO 0516',inicio=start,fin=end,frecuencia=5,estaciones_extra=sorted(set(stations+[st])),capa='CDX-QA-ESPIRALES-CORRIDOR'))
    table=[[start,-.02,-.02],[ts,-.02,-.02],[sc,.04,-.04],[cs,.04,-.04],[st,-.02,-.02],[end,-.02,-.02]]
    q.report.update(profile=profile,assembly=assembly,corridor=corridor,input_table=table)
    q.record()
    try:r=peraltes.ejecutar(q.drawing,pid,corridor['handle'],table,False)
    except peraltes.PeralteError as exc:
        q.report['peralte_receipt']=exc.receipt;q.record();raise
    q.report['peralte_receipt']=r;q.record()
    q.check('peraltes aplicados al eje con clotoides',r['committed'] and len(r['result']['table'])==6)
    xy_error=z_error=roadside_error=daylight_error=0
    def grade(s):return 101+2*(s-start)/(end-start)
    for row in r['result']['samples']:
        s=row['station']
        for p in row['points']:
            xy,_,_=ref.at(s,p['soe'][1])
            xy_error=max(xy_error,math.dist(xy,p['xyz'][:2]))
            if 'Daylight' in p['codes']:daylight_error=max(daylight_error,abs(p['xyz'][2]-102))
        for col,sign,width,berm in [(1,-1,1.5,-.04),(2,1,2,-.03)]:
            edge=next(p for p in row['points'] if 'ETW' in p['codes'] and p['soe'][1]*sign>0)
            z_error=max(z_error,abs(edge['xyz'][2]-grade(s)-3.5*expected(table,s,col)))
            for off,dz in [(3.5+width,width*berm),(4.7+width,width*berm-.6),(5.2+width,width*berm-.6),(6.1+width,width*berm)]:
                candidates=[p for p in row['points'] if abs(p['soe'][1]-sign*off)<1e-6]
                if not candidates:raise AssertionError('Missing roadside point')
                roadside_error=max(roadside_error,min(abs(p['xyz'][2]-edge['xyz'][2]-dz) for p in candidates))
    q.check('XY corredor contra Fresnel independiente',xy_error<1e-6)
    q.check('rasante y peraltes independientes',z_error<1e-6)
    q.check('bermas cunetas y encuentro terreno',roadside_error<1e-6 and daylight_error<1e-6)
    q.call('objects.invoke',dict(handle=corridor['handle'],metodo='Rebuild'))
    sections=q.call('civil.secciones_corredor',dict(corredor=corridor['handle'],nombre='CDX QA ESPIRAL SECTIONS 0519',estaciones=stations,
        semiancho=12,origen=[620350,2100330,0],cota_min=98,cota_max=106,capa='CDX-QA-ESPIRALES-SECTIONS'))
    q.report['sections']=sections;q.record()
    q.check('ocho secciones nativas',len(sections['secciones'])==8)
    section_error=0
    for row in sections['secciones']:
        s=row['estacion']
        q.check('normal al eje '+str(s),math.dist(row['izquierda'],ref.at(s,-12)[0])<1e-6 and math.dist(row['derecha'],ref.at(s,12)[0])<1e-6)
        raw=row['secciones'][0]['puntos'];connected={i for i,p in enumerate(raw) if p['segment_to']>=0}|{p['segment_to'] for p in raw if p['segment_to']>=0}
        points=[raw[i] for i in connected];vertices=[(0,grade(s))]
        for col,sign,width,berm in [(1,-1,1.5,-.04),(2,1,2,-.03)]:
            edge=grade(s)+3.5*expected(table,s,col)
            vertices.extend((sign*off,edge+dz) for off,dz in [(3.5,0),(3.5+width,width*berm),(4.7+width,width*berm-.6),(5.2+width,width*berm-.6),(6.1+width,width*berm)])
        for off,z in vertices:section_error=max(section_error,min(max(abs(p['offset']-off),abs(p['cota']-z)) for p in points))
        q.check('vertices Top '+str(s),section_error<1e-6)
    final=q.qa('final');q.report['final']=final
    group=next(g for g in final['civil']['groups'] if g['handle']==sections['handle'])
    q.check('vistas H=V',all(v['exaggeration']==1 for row in group['lines'] for v in row['views']))
    q.report['max_errors']=dict(xy_m=xy_error,z_m=z_error,roadside_m=roadside_error,daylight_m=daylight_error,sections_m=section_error)
    q.report['ok']=True;q.record()
    return q.report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for arg in ['drawing','output','smoke']:p.add_argument('--'+arg,required=True)
    p.add_argument('--pid',type=int,required=True);a=p.parse_args()
    print('PASS',len(run(a.drawing,a.output,a.pid,a.smoke)['checks']))
