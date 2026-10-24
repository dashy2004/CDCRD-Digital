import copy
import hashlib
import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import qto

VOLUME=dict(nombre='New volume',base='AA',comparacion='BB',factor_corte=1.1,factor_relleno=1.2)
EARTH=dict(nombre='New earthwork',alineamiento='CC',modo='tierras',base='AA',comparacion='BB',estaciones=[100,110,120],semiancho=10)
SHAPES=dict(nombre='New shapes',alineamiento='CC',modo='formas',corredor='DD',baseline='A',region='A1',estaciones=[110,120,130],semiancho=12,codigos=['Pave1','Base'])

@pytest.mark.parametrize('action,args,change',[
 ('volumen',VOLUME,dict(base='')),('volumen',VOLUME,dict(comparacion='aa')),
 *[('volumen',VOLUME,{'factor_corte':v}) for v in [0,-1,11,float('nan'),float('inf'),True,'1']],
 *[('materiales',EARTH,{'estaciones':v}) for v in [[],[1],[110,100],[100,100],[True,110],[100,float('nan')],list(range(201))]],
 *[('materiales',EARTH,{'semiancho':v}) for v in [0,101,float('nan'),True]],
 ('materiales',EARTH,dict(modo='unknown')),('materiales',EARTH,dict(alineamiento='X\nY')),
 *[('materiales',SHAPES,{'codigos':v}) for v in [[],['A','A'],[''],[True],['X\nY'],['a']*21]],
 ('materiales',SHAPES,dict(baseline='')),('materiales',SHAPES,dict(region=False)),
 ('calcular_formas',{'objeto':'AA'},dict(objeto='')),
])
def test_invalid_request_never_reaches_cad(action,args,change,monkeypatch,tmp_path):
    monkeypatch.setattr(qto.bridge,'llamar',lambda *a:pytest.fail('Invalid request reached CAD'))
    with pytest.raises((ValueError,TypeError)):
        qto.ejecutar(str(tmp_path/'copy.dwg'),123,accion=action,**(copy.deepcopy(args)|change))

def prepare(monkeypatch,tmp_path,mode='ok'):
    calls=[]
    def read(method):
        return {'doc.info':dict(civil3d=True,dibujo=str(tmp_path/'copy.dwg'),insunits=6),
                'diag.dialogos':dict(modal_abierto=False),'diag.cola':dict(activas=[])}[method]
    def dispatch(method,payload):
        calls.append((method,payload));cmd,key,digest,tail=payload['linea'].split('\n')
        assert cmd=='CDCRDQTOV8' and not tail
        raw=(tmp_path/f'cdcrd-qto-{key}.request.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==digest
        request=json.loads(raw);assert request['pid']==123 and request['simular']
        if mode=='timeout':raise TimeoutError('dispatch uncertain')
        if mode=='missing':return
        response=dict(id=key,sha256=digest,module='cdcrd-qto',pid=123,ok=mode!='native-error',committed=False,result={},error='rolled back')
        if mode.startswith('wrong-'):response[mode[6:]]='different'
        (tmp_path/f'cdcrd-qto-{key}.result.json').write_text(json.dumps(response),encoding='utf-8')
    monkeypatch.setattr(qto.bridge,'llamar',read);monkeypatch.setattr(qto.bridge,'llamar_con_aprobacion',dispatch)
    return calls

@pytest.mark.parametrize('action,args',[('volumen',VOLUME),('materiales',EARTH),('materiales',SHAPES),('calcular_formas',dict(objeto='DD'))])
def test_request_integrity_and_simulation(action,args,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path)
    assert qto.ejecutar(str(tmp_path/'copy.dwg'),123,accion=action,**args)['ok']
    assert len(calls)==1

@pytest.mark.parametrize('mode',['timeout','missing','native-error','wrong-id','wrong-sha256','wrong-pid','wrong-module'])
def test_uncertain_receipt_never_retries(mode,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path,mode)
    with pytest.raises(qto.QtoError) as e:qto.ejecutar(str(tmp_path/'copy.dwg'),123,accion='volumen',**VOLUME,timeout=.001)
    assert e.value.receipt['id'] and len(calls)==1

@pytest.mark.parametrize('changed',[dict(civil3d=False),dict(insunits=2),dict(dibujo='C:\\other.dwg')])
def test_doc_guard(changed,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path);read=qto.bridge.llamar
    monkeypatch.setattr(qto.bridge,'llamar',lambda m:read(m)|changed if m=='doc.info' else read(m))
    with pytest.raises(ValueError):qto.ejecutar(str(tmp_path/'copy.dwg'),123,accion='volumen',**VOLUME)
    assert not calls

@pytest.mark.parametrize('method,value',[('diag.dialogos',dict(modal_abierto=True)),('diag.cola',dict(activas=[1]))])
def test_busy_guard(method,value,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path);read=qto.bridge.llamar
    monkeypatch.setattr(qto.bridge,'llamar',lambda m:value if m==method else read(m))
    with pytest.raises(RuntimeError):qto.ejecutar(str(tmp_path/'copy.dwg'),123,accion='volumen',**VOLUME)
    assert not calls

def test_confirmation_and_explicit_two_phase_api(monkeypatch):
    registry={}
    class Mcp:
        def tool(self):
            def register(fn):registry[fn.__name__]=fn;return fn
            return register
    qto.registrar(Mcp(),json.dumps)
    monkeypatch.setattr(qto,'ejecutar',lambda *a,**kw:pytest.fail('Unconfirmed'))
    assert 'confirmar=True' in registry['crear_cubicacion_tin']('C:\\copy.dwg',123,'V','A','B')
    assert 'confirmar=True' in registry['crear_materiales_qto']('C:\\copy.dwg',123,'M','A','[1,2]',10,'tierras')
    assert 'confirmar=True' in registry['completar_materiales_qto']('C:\\copy.dwg',123,'G')
    assert len(registry)==4

def test_json_inputs_are_normalized():
    args=dict(SHAPES,estaciones='[110,120,130]',codigos='["Pave1","Base"]')
    qto.validar('materiales',args)
    assert args['estaciones']==SHAPES['estaciones'] and args['codigos']==SHAPES['codigos']
