"""Raw native graphics-area captures; labels are actual DWG entities."""
import argparse,json,time
from humo_cunetas_bermas import NativeQa
import puente_cliente as bridge

def run(drawing,output,acceptance,regions,prefix='qto-captures',existing_annotations=None):
 q=NativeQa(drawing,output,8760,prefix);q.guard()
 a=json.loads((q.out/acceptance).read_text(encoding='utf-8'));e=json.loads((q.out/regions).read_text(encoding='utf-8'));v=json.loads((q.out/'qto-views-result.json').read_text(encoding='utf-8'))
 assert a['ok'] and e['ok'] and v['ok']
 layers=bridge.llamar('layers.query',{})['capas'];groups=[('tierras',a['earth'])]+[(g['region'].lower(),g['result']) for g in e['groups']]
 previous=[] if not existing_annotations else [c['result']['creados'] for c in json.loads((q.out/existing_annotations).read_text(encoding='utf-8'))['calls'] if c['method']=='entity.create']
 if previous:assert len(previous)==len(groups)
 for index,(label,result) in enumerate(groups):
  views=[x for x in v['result'] if x['group']==result['handle']];assert len(views)==2
  x,y=views[0]['origin'];ann=[]
  def text(dx,dy,value,height=1.2,color=7):ann.append(dict(tipo='texto',punto=[x+dx,y+dy,0],texto=value,altura=height,color=color,capa='CDX-QA-QTO-ANNOTATIONS'))
  text(-13,18,'CIVIL 3D 2027 | QTO POR API | '+label.upper(),2)
  text(-13,14.5,'COPIA SINTETICA EN METROS - SECCIONES Y MATERIALES NATIVOS',1.15)
  for view in views:text(view['origin'][0]-x-10,11,'ESTACION '+format(view['station'],'.0f')+' m',1.3,2)
  if label=='tierras':
   text(-13,-7,'TIN: CORTE 400.000 m3 | RELLENO 400.000 m3 | NETO 0.000 m3',1.1,2)
   text(-13,-10,'QTO: 5 SECCIONES, AREAS MEDIAS | CORTE 400.000 / RELLENO 400.000 m3',1.1)
   text(-13,-13,'FACTORES TIN 1.10 / 1.20: CORTE 440.000 / RELLENO 480.000 m3',1.1)
  else:
   start,end=result['stations'][0],result['stations'][-1]
   text(-13,-7,f'REGION {label.upper()} | TRAMO {start:.0f}-{end:.0f} m | {len(result["stations"])} SECCIONES | SIN INTEGRAR HUECOS',1.1,2)
   qty=result['quantities'][-1]['materials']
   text(-13,-10,'QTO NATIVO (m3): '+' | '.join(m['name']+' '+format(m['cumulative'],'.3f') for m in qty[:2]),1.1)
   text(-13,-13,'                 '+' | '.join(m['name']+' '+format(m['cumulative'],'.3f') for m in qty[2:]),1.1)
  if previous:ids=[r['handle'] for r in previous[index]]
  else:
   created=q.call('entity.create',dict(entidades=ann));assert not created['errores'];ids=[r['handle'] for r in created['creados']]
  for row in views:ids.extend([row['view'],row['line']]+row['sections']+row['material_sections'])
  # Freeze old corridor layers only for the capture, restore all original states.
  frozen=[r['nombre'] for r in layers if ('CORRIDOR' in r['nombre'].upper() or r['nombre']=='C-TOPO') and not r['congelada']]
  try:
   if frozen:assert not q.call('layers.set',dict(nombres=frozen,congelada=True))['fallidos']
   quoted=' '.join('"'+h+'"' for h in ids)
   q.call('cmd.run',dict(linea='(progn (setq cdxss (ssadd)) (foreach cdxh \'('+quoted+') (ssadd (handent cdxh) cdxss)) (command "_.ISOLATEOBJECTS" cdxss "") (princ))\n'))
   q.call('vista.3d',dict(direccion='PLANTA',objetivo=[x+22,y+3,0],ancho=100,alto=50,estilo_visual='2dWireframe'))
   q.call('cmd.run',dict(linea='_.REGENALL\n'))
   time.sleep(1)
   q.guard()
   q.qa(label,'capture',image=prefix+'-'+label+'-0522.png')
  finally:
   try:q.call('cmd.run',dict(linea='_.UNISOLATEOBJECTS\n'))
   finally:
    if frozen:q.call('layers.set',dict(nombres=frozen,congelada=False))
 after={r['nombre']:r for r in bridge.llamar('layers.query',{})['capas']};q.check('previous layers restored',all(after[r['nombre']]==r for r in layers));q.report['ok']=True;q.record()

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--acceptance',default='qto-acceptance-v8-smoke.json');p.add_argument('--regions',default='qto-multiple-regions-smoke.json');p.add_argument('--prefix',default='qto-captures');p.add_argument('--existing-annotations');a=p.parse_args();run(a.drawing,a.output,a.acceptance,a.regions,a.prefix,a.existing_annotations)
