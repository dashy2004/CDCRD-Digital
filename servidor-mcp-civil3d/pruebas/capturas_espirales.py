"""Native graphic-area captures with native DWG annotations, never image edits."""
import argparse
import json
from pathlib import Path
from humo_cunetas_bermas import NativeQa
import puente_cliente as bridge


def run(drawing,output,smoke,corridor,prefix='spirals-captures',reuse_annotations=None):
    data=json.loads(Path(smoke).read_text());road=json.loads(Path(corridor).read_text())
    if not data['ok'] or not road['ok']:raise ValueError('Successful native receipts required')
    q=NativeQa(drawing,output,8760,prefix)
    previous = json.loads(Path(reuse_annotations).read_text()) if reuse_annotations else None
    created = [c['result'] for c in previous['calls'] if c['method']=='entity.create'] if previous else []
    layer_before=bridge.llamar('layers.query',{})['capas']
    old_layers=['CDX-QA-CORRIDOR','MCP-QA-CALZADA-CORREDOR','MCP-QA-CUNETAS-CORREDOR','CDX-QA-PERALTES-CORRIDOR','C-TOPO']
    new_layer='CDX-QA-ESPIRALES-CORRIDOR'
    def capture(label,handles,center,width,height):
        quoted=' '.join('"'+h+'"' for h in handles)
        hidden=old_layers+([new_layer] if label!='left' else [])
        changed=[r['nombre'] for r in layer_before if r['nombre'] in hidden and not r['congelada']]
        try:
            result=q.call('layers.set',{'nombres':changed,'congelada':True})
            if result['fallidos']:raise RuntimeError(result['fallidos'])
            q.call('cmd.run',{'linea':'(progn (setq cdxss (ssadd)) (foreach cdxh \'('+quoted+') (ssadd (handent cdxh) cdxss)) (command "_.ISOLATEOBJECTS" cdxss "") (princ))\n'})
            q.call('vista.3d',dict(direccion='PLANTA',objetivo=center,ancho=width,alto=height,estilo_visual='2dWireframe'))
            q.qa(label,'capture',image=prefix+'-'+label+'-0519.png')
        finally:
            try:q.call('cmd.run',{'linea':'_.UNISOLATEOBJECTS\n'})
            finally:
                result=q.call('layers.set',{'nombres':changed,'congelada':False})
                if result['fallidos']:raise RuntimeError(result['fallidos'])
    for number,(key,caption) in enumerate([('left','GIRO IZQUIERDO'),('right','GIRO DERECHO')]):
        axis=data[key];g=axis['geometry'];ys=[g[k][1] for k in ['inicio','pi','fin']]
        top=max(ys)+34
        annotations=[dict(tipo='texto',punto=[g['inicio'][0],top,0],texto='CLOTOIDES NATIVAS - '+caption,altura=3.5,color=7),
                     dict(tipo='texto',punto=[g['inicio'][0],top-7,0],texto='R=50 m   L entrada=25 m   L salida=35 m',altura=2.5,color=7)]
        # Leader ends and labels are native entities, placed from native endpoints.
        points=[axis['parts'][1]['start'],axis['parts'][2]['start'],axis['parts'][3]['start'],axis['parts'][4]['start']]
        shifts=[(-25,-16),(-16,-30),(7,-27),(15,-10)] if key=='left' else [(-25,16),(-16,30),(7,27),(15,10)]
        for tag,xy,(dx,dy) in zip(['TS','SC','CS','ST'],points,shifts):
            end=[xy[0]+dx,xy[1]+dy,0]
            annotations.extend([dict(tipo='linea',p1=xy,p2=end,color=2),dict(tipo='circulo',centro=xy,radio=.8,color=2),
                                dict(tipo='texto',punto=end,texto=tag,altura=2.5,color=2)])
        for obj in annotations:obj['capa']='CDX-QA-ESPIRALES-ANNOTATIONS'
        result=created[number] if previous else q.call('entity.create',dict(entidades=annotations))
        if result.get('errores'):raise RuntimeError(result['errores'])
        handles=[r['handle'] for r in result['creados']]+[axis['handle']]
        if key=='left':handles += [road['corridor']['handle'],road['corridor']['superficie']]
        capture(key,handles,[g['inicio'][0]+105,(min(ys)+top)/2,0],285,210)
    for index,label in [(2,'transicion'),(4,'arco')]:
        row=road['sections']['secciones'][index]
        handles=[row['vista'],row['linea'],row['secciones'][0]['handle'],road['corridor']['superficie']]
        capture(label,handles,[620350+(index%4)*36,2100334-(index//4)*18,0],52,36)
    q.check('estado de capas restaurado',layer_before==bridge.llamar('layers.query',{})['capas'])
    q.report['ok']=True;q.record()
    return q.report


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for arg in ['drawing','output','smoke','corridor']:p.add_argument('--'+arg,required=True)
    p.add_argument('--prefix',default='spirals-captures')
    p.add_argument('--reuse-annotations')
    a=p.parse_args();run(a.drawing,a.output,a.smoke,a.corridor,a.prefix,a.reuse_annotations)
