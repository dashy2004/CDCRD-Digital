"""Build a synthetic, reproducible native Civil 3D street demonstration."""
import json
import math
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO / 'servidor-mcp-civil3d' / 'src'))
import puente_cliente as b

ROOT = OUT = STATE = None
EXPECTED_DRAWING = None
state = {}

def configure(output, expected_drawing):
    global ROOT, OUT, STATE, EXPECTED_DRAWING
    OUT = Path(output).resolve()
    ROOT = OUT / 'control'
    STATE = ROOT / 'estado.json'
    EXPECTED_DRAWING = expected_drawing
    ROOT.mkdir(parents=True)

def call(method, params, write=False, key=None):
    if ROOT is None:
        raise RuntimeError('Use run.py para comprobar dibujo, version y directorio de salida.')
    if write:
        current = b.llamar('doc.info', {})['dibujo']
        if current != EXPECTED_DRAWING:
            raise RuntimeError('Cambio el dibujo activo. Operacion detenida antes de escribir.')
    pending = ROOT / 'ultima_operacion.json'
    pending.write_text(json.dumps({'method': method, 'key': key, 'estado': 'pendiente'}), encoding='utf-8')
    result = (b.llamar_con_aprobacion if write else b.llamar)(method, params)
    entry = {'method': method, 'key': key, 'estado': 'respondida', 'result': result}
    pending.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding='utf-8')
    with (ROOT / 'operaciones.jsonl').open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    if result.get('errores') or result.get('fallidos'):
        raise RuntimeError(f'{method}: resultado parcial; inspeccione el registro antes de continuar')
    if key:
        state[key] = result
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    print(method, key or '', flush=True)
    return result

def stage1():
    assert not state, 'Stage 1 already started; inspect state before resuming.'
    call('doc.save', {'ruta': str(OUT / 'CALLE_REALISTA_R02.dwg')}, True)
    layers = {'TERRENO':[109,133,85], 'EJE':[240,180,40], 'RASANTE':[230,150,60],
              'CORREDOR':[78,80,82], 'PAVIMENTO':[76,78,80], 'ACERAS':[181,177,161],
              'CONTENES':[210,206,190], 'DRENAJE':[110,116,123], 'MARCAS':[245,241,206],
              'ENTORNO':[120,150,80], 'BACHE':[84,73,61], 'AUX':[100,100,100]}
    call('entity.create', {'entidades':[{'tipo':'capa','nombre':'CDX2-'+n,'color':c} for n,c in layers.items()]}, True, 'capas')
    d = 120*(1-math.cos(math.pi/6))
    points = [[0,0],[0,40],[d,100],[2*d,160],[2*d,210]]
    r=call('entity.create', {'entidades':[{'tipo':'polilinea','puntos':points,'capa':'CDX2-AUX'}]}, True, 'eje_fuente')
    h=r['creados'][0]['handle']
    for index, bulge in [(1,-math.tan(math.pi/24)),(2,math.tan(math.pi/24))]:
        call('objects.invoke', {'handle':h,'metodo':'SetBulgeAt','args':[index,bulge]},True)
    call('civil.alineamiento_polilinea', {'polilinea':h,'nombre':'CDX2_EJE_CALLE','estacion_inicial':0,'capa':'CDX2-EJE'},True,'eje')

def stage2():
    # Native alignment length is read back before defining the grade.
    length=call('objects.read',{'handle':state['eje']['handle'],'ruta':'Length'})['valor']
    pvis=[[0,100],[55,101.1],[125,100.0],[length,102.3]]
    call('civil.perfil_pvi',{'alineamiento':'CDX2_EJE_CALLE','nombre':'CDX2_RASANTE','pvis':pvis,
                           'curvas':[{'pvi':1,'longitud':32},{'pvi':2,'longitud':44}],'capa':'CDX2-RASANTE'},True,'rasante')
    pts=[]
    for y in range(-30,246,4):
        for x in range(-56,93,4):
            xc=32/(1+math.exp(-(y-103)/26))
            z=100+.008*y+.6*math.sin(y/35)+.018*(x-xc)
            z+=2.4*math.exp(-((x+28)/22)**2-((y-110)/48)**2)
            z-=1.15*math.exp(-((x-66)/20)**2-((y-65)/40)**2)
            z+=.22*math.sin(x/12+y/23)
            pts.append([x,y,z])
    (ROOT/'terreno_puntos.json').write_text(json.dumps(pts))
    r=call('superficie.crear',{'nombre':'CDX2_TERRENO_ONDULADO','capa':'CDX2-TERRENO','estilo':'Border Only'},True,'terreno')
    call('objects.invoke',{'handle':r['handle'],'metodo':'AddVertices','args':[pts],'profundidad':0},True)
    call('objects.invoke',{'handle':r['handle'],'metodo':'Rebuild'},True)
    call('civil.perfil_superficie',{'alineamiento':'CDX2_EJE_CALLE','superficie':'CDX2_TERRENO_ONDULADO','nombre':'CDX2_PERFIL_TERRENO','capa':'CDX2-RASANTE'},True,'perfil_terreno')
    call('civil.ensamblaje_calzada',{'nombre':'CDX2_SECCION_CALLE','origen':[-80,0,100],
         'ancho_izq':3.6,'ancho_der':3.6,'pendiente_izq':-.02,'pendiente_der':-.02,
         'espesores':[.05,.07,.20,.25],'talud_corte':1.5,'talud_relleno':2,
         'ancho_daylight_max':18,'capa':'CDX2-CORREDOR'},True,'ensamblaje')
    call('civil.corredor_calzada',{'alineamiento':'CDX2_EJE_CALLE','perfil':'CDX2_RASANTE','ensamblaje':'CDX2_SECCION_CALLE',
         'nombre':'CDX2_CORREDOR_CALLE','superficie_objetivo':'CDX2_TERRENO_ONDULADO',
         'inicio':0,'fin':length,'frecuencia':2,'estaciones_extra':[110], 'capa':'CDX2-CORREDOR'},True,'corredor')
    call('doc.save',{'ruta':str(OUT/'CALLE_REALISTA_R02.dwg')},True)
