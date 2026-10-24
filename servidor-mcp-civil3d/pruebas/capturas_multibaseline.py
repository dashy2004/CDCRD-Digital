"""Raw native graphic-area evidence; labels are native drawing entities."""
import argparse,json
from pathlib import Path
from humo_cunetas_bermas import NativeQa
from espiral_referencia import Reference
import puente_cliente as bridge

def run(drawing,output,reuse=None,prefix="multi-captures-verified"):
 q=NativeQa(drawing,output,8760,prefix);f=json.loads((q.out/'multi-fixture-smoke.json').read_text());d=json.loads((q.out/'multi-complete-smoke.json').read_text());d=d if d['ok'] else json.loads((q.out/'multi-final-validation-smoke.json').read_text());assert d['ok']
 c=d['corridor'];layer_before=bridge.llamar('layers.query',{})['capas']
 annotations=[dict(tipo='texto',punto=[620010,2100170,0],texto='CIVIL 3D 2027 - 2 BASELINES / 4 REGIONES',altura=3.5,color=7),dict(tipo='texto',punto=[620010,2100162,0],texto='API .NET - EJEMPLO SINTETICO EN METROS',altura=2.5,color=7),dict(tipo='texto',punto=[620015,2100038,0],texto='A1: carriles 3.5 / 3.5 m',altura=2.5,color=7),dict(tipo='texto',punto=[620115,2099998,0],texto='A2: carriles 4.5 / 3.0 m',altura=2.5,color=7),dict(tipo='texto',punto=[620015,2100128,0],texto='B1: carriles 4.5 / 3.0 m',altura=2.5,color=7),dict(tipo='texto',punto=[620115,2100088,0],texto='B2: carriles 3.5 / 3.5 m',altura=2.5,color=7)]
 for i,station,text,end in [(0,180,'A: CAMBIO EN 0+180',[620077,2099982,0]),(1,175,'B: HUECO 0+165 A 0+185',[620052,2100068,0])]:
  xy=list(Reference(f['axes'][i]['geometry']).at(station,0)[0])+[0]
  annotations += [dict(tipo='circulo',centro=xy,radio=1.2,color=2),dict(tipo='linea',p1=xy,p2=end,color=2),dict(tipo='texto',punto=end,texto=text,altura=2.2,color=2)]
 for a in annotations:a['capa']='CDX-QA-MULTI-ANNOTATIONS'
 made=next(c['result'] for c in json.loads(Path(reuse).read_text())['calls'] if c['method']=='entity.create') if reuse else q.call('entity.create',dict(entidades=annotations));assert not made.get('errores');ann=[r['handle'] for r in made['creados']]
 old=['CDX-QA-CORRIDOR','MCP-QA-CALZADA-CORRIDOR','MCP-QA-CUNETAS-CORRIDOR','CDX-QA-PERALTES-CORRIDOR','CDX-QA-ESPIRALES-CORRIDOR','C-TOPO']
 def capture(label,handles,center,width,height,plan=False):
  hidden=old+([] if plan else ['CDX-QA-MULTI-CORRIDOR']);changed=[r['nombre'] for r in layer_before if r['nombre'] in hidden and not r['congelada']]
  try:
   v=q.call('layers.set',dict(nombres=changed,congelada=True));assert not v['fallidos']
   quoted=' '.join('"'+h+'"' for h in handles)
   q.call('cmd.run',dict(linea='(progn (setq cdxss (ssadd)) (foreach cdxh \'('+quoted+') (ssadd (handent cdxh) cdxss)) (command "_.ISOLATEOBJECTS" cdxss "") (princ))\n'))
   q.call('vista.3d',dict(direccion='PLANTA',objetivo=center,ancho=width,alto=height,estilo_visual='2dWireframe'))
   q.qa(label,'capture',image=prefix+'-'+label+'-0520.png')
  finally:
   try:q.call('cmd.run',dict(linea='_.UNISOLATEOBJECTS\n'))
   finally:q.call('layers.set',dict(nombres=changed,congelada=False))
 capture('planta',ann+[a['handle'] for a in f['axes']]+[c['handle'],c['surface']],[620105,2100073,0],275,230,True)
 for label,indices,base,center in [('region-a1',[2],0,[620434,2100404,0]),('region-a2',[3],0,[620476,2100404,0]),('baseline-b',[0,2],1,[620392,2100339,0])]:
  rows=[d['sections'][base]['secciones'][i] for i in indices];handles=[h for row in rows for h in [row['vista'],row['linea'],row['secciones'][0]['handle']]]+[c['surface']]
  capture(label,handles,center,140 if base else 65,65 if base else 36)
 capture('hueco',ann+[f['axes'][1]['handle'],c['handle'],c['surface']],[620087,2100097,0],120,90,True)
 after={r['nombre']:r for r in bridge.llamar('layers.query',{})['capas']};q.check('capas previas restauradas',all(after[r['nombre']]==r for r in layer_before));q.report['ok']=True;q.record()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--drawing',required=True);p.add_argument('--output',required=True);p.add_argument('--reuse');a=p.parse_args();run(a.drawing,a.output,a.reuse)
