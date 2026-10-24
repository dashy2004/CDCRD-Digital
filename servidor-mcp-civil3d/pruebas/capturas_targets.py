"""Unaltered native graphic-area captures of the synthetic target fixture."""
import argparse,json
from humo_cunetas_bermas import NativeQa
import puente_cliente as bridge

def run(drawing,output,acceptance='targets-complete-smoke.json'):
 q=NativeQa(drawing,output,8760,'targets-captures');q.guard()
 f=json.loads((q.out/'targets-fixture-smoke.json').read_text());d=json.loads((q.out/acceptance).read_text());assert d['ok'];c=d['corridor']
 layers=bridge.llamar('layers.query',{})['capas'];ann=[]
 def label(point,text,height=2.4,color=7):ann.append(dict(tipo='texto',punto=point,texto=text,altura=height,color=color,capa='CDX-QA-TARGETS-ANNOTATIONS'))
 label([620015,2100197,0],'CIVIL 3D 2027 - TARGETS DE ANCHO Y COTA',3.1)
 label([620015,2100190,0],'API .NET / COPIA / EJEMPLO SINTETICO EN METROS',2.1)
 label([620020,2100180,0],'A: ANCHO Y COTA EN AMBOS CARRILES',2.2,2)
 label([620020,2100090,0],'B: IZQ. SOLO ANCHO / DER. SOLO COTA',2.2,2)
 for i,label_name in enumerate(['A','B']):
  for j in [0,2]:
   station=d['sections'][i]['secciones'][j]['estacion'];row=next(row for region in c['baselines'][i]['regions'] for row in region['applied'] if row['station']==station)
   values=' / '.join(lane['side']+': W='+format(lane['width'],'.3f')+' Z='+format(lane['elevation'],'.3f') for lane in row['lanes'])
   label([620350+j*44-30,2100600-65*i+20,0],label_name+' @ '+str(station)+' m - TARGETS API',1.3,2)
   label([620350+j*44-30,2100600-65*i+17,0],values,1.05)
 made=q.call('entity.create',dict(entidades=ann));assert not made['errores'];handles=[r['handle'] for r in made['creados']]
 def capture(name,ids,center,width,height,plan=False):
  old=['CDX-QA-CORRIDOR','MCP-QA-CALZADA-CORRIDOR','MCP-QA-CUNETAS-CORRIDOR','CDX-QA-PERALTES-CORRIDOR','CDX-QA-ESPIRALES-CORRIDOR','CDX-QA-MULTI-CORRIDOR','C-TOPO']+([] if plan else ['CDX-QA-TARGETS-CORRIDOR'])
  changed=[r['nombre'] for r in layers if r['nombre'] in old and not r['congelada']]
  try:
   assert not q.call('layers.set',dict(nombres=changed,congelada=True))['fallidos']
   quoted=' '.join('"'+h+'"' for h in ids)
   q.call('cmd.run',dict(linea='(progn (setq cdxss (ssadd)) (foreach cdxh \'('+quoted+') (ssadd (handent cdxh) cdxss)) (command "_.ISOLATEOBJECTS" cdxss "") (princ))\n'))
   q.call('vista.3d',dict(direccion='PLANTA',objetivo=center,ancho=width,alto=height,estilo_visual='2dWireframe'))
   q.qa(name,'capture',image='targets-'+name+'-0521.png')
  finally:
   try:q.call('cmd.run',dict(linea='_.UNISOLATEOBJECTS\n'))
   finally:q.call('layers.set',dict(nombres=changed,congelada=False))
 capture('planta',handles[:4]+[a['handle'] for a in f['axes']]+[a['handle'] for group in f['target_axes'] for a in group]+[c['corredor'],c['surface']],[620100,2100142,0],235,140,True)
 for i,baseline in enumerate(['a','b']):
  for j in [0,2]:
   row=d['sections'][i]['secciones'][j];index=4+i*4+(0 if j==0 else 2)
   ids=handles[index:index+2]+[row['vista'],row['linea'],row['secciones'][0]['handle'],c['surface']]
   capture(baseline+'-'+str(int(row['estacion'])),ids,[620350+j*44,2100600-65*i+7,0],84,42)
 after={r['nombre']:r for r in bridge.llamar('layers.query',{})['capas']};q.check('capas previas restauradas',all(after[r['nombre']]==r for r in layers));q.report['ok']=True;q.record()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--acceptance',default='targets-complete-smoke.json');a=p.parse_args();run(a.drawing,a.output,a.acceptance)
