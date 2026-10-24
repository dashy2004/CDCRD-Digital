import copy
import hashlib
import json
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import partidas

CATALOG=dict(partidas=[dict(codigo='CDX-001',descripcion='Ensayo',unidad='M')])
ASSIGN=dict(asignaciones=[dict(handle='AA',partida='CDX-001')])

@pytest.mark.parametrize('action,args',[
 *[('catalogo',dict(partidas=v)) for v in [[],[None],[{}],list(CATALOG['partidas'])*2]],
 *[('catalogo',dict(partidas=[dict(codigo=v,descripcion='X',unidad='M')])) for v in ['', '=1','X/Y','X\nY', True]],
 *[('catalogo',dict(partidas=[dict(codigo='A',descripcion=v,unidad='M')])) for v in ['', '=1+1',' +SUM(1)','@X','X\nY']],
 ('catalogo',dict(partidas=[dict(codigo='A',descripcion='X',unidad='FT')])),
 *[('asignar',dict(asignaciones=v)) for v in [[],[None],[{}],list(ASSIGN['asignaciones'])*2]],
 *[('asignar',dict(asignaciones=[dict(handle=v,partida='A')])) for v in ['',True,'ZZ','A;DROP','A'*17]],
 *[('leer',dict(handles=v)) for v in [[],['ZZ'],[True]]],
])
def test_invalid_never_reaches_cad(action,args,monkeypatch,tmp_path):
    monkeypatch.setattr(partidas.bridge,'llamar',lambda *a:pytest.fail('Invalid reached CAD'))
    with pytest.raises((ValueError,TypeError)):
        partidas.ejecutar(str(tmp_path/'copy.dwg'),123,accion=action,**copy.deepcopy(args))

def prepare(monkeypatch,tmp_path,mode='ok'):
    calls=[]
    def read(method):
        return {'doc.info':dict(civil3d=True,dibujo=str(tmp_path/'copy.dwg'),insunits=6),'diag.dialogos':dict(modal_abierto=False),'diag.cola':dict(activas=[])}[method]
    def dispatch(method,payload):
        calls.append((method,payload));cmd,key,digest,tail=payload['linea'].split('\n')
        assert cmd=='CDCRDPARTIDASV3' and not tail
        raw=(tmp_path/f'cdcrd-partidas-{key}.request.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==digest
        request=json.loads(raw);assert request['pid']==123 and request['simular']
        if mode=='timeout':raise TimeoutError('dispatch uncertain')
        if mode=='missing':return
        response=dict(id=key,sha256=digest,module='cdcrd-partidas',pid=123,ok=mode!='native-error',committed=False,result={},error='rolled back')
        if mode.startswith('wrong-'):response[mode[6:]]='different'
        (tmp_path/f'cdcrd-partidas-{key}.result.json').write_text(json.dumps(response),encoding='utf-8')
    monkeypatch.setattr(partidas.bridge,'llamar',read);monkeypatch.setattr(partidas.bridge,'llamar_con_aprobacion',dispatch)
    return calls

@pytest.mark.parametrize('action,args',[('catalogo',CATALOG),('asignar',ASSIGN),('leer',dict(handles=['AA'])),('informe',{}),('estado',{})])
def test_integrity_and_default_simulation(action,args,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path)
    assert partidas.ejecutar(str(tmp_path/'copy.dwg'),123,accion=action,**args)['ok']
    assert len(calls)==1

@pytest.mark.parametrize('mode',['timeout','missing','native-error','wrong-id','wrong-sha256','wrong-pid','wrong-module'])
def test_uncertain_receipt_never_retries(mode,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path,mode)
    with pytest.raises(partidas.PartidasError) as e:partidas.ejecutar(str(tmp_path/'copy.dwg'),123,accion='catalogo',**CATALOG,timeout=.001)
    assert e.value.receipt['id'] and len(calls)==1

@pytest.mark.parametrize('changed',[dict(civil3d=False),dict(insunits=2),dict(dibujo='C:\\other.dwg')])
def test_doc_guard(changed,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path);read=partidas.bridge.llamar
    monkeypatch.setattr(partidas.bridge,'llamar',lambda m:read(m)|changed if m=='doc.info' else read(m))
    with pytest.raises(ValueError):partidas.ejecutar(str(tmp_path/'copy.dwg'),123,accion='catalogo',**CATALOG)
    assert not calls

@pytest.mark.parametrize('method,value',[('diag.dialogos',dict(modal_abierto=True)),('diag.cola',dict(activas=[1]))])
def test_busy_guard(method,value,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path);read=partidas.bridge.llamar
    monkeypatch.setattr(partidas.bridge,'llamar',lambda m:value if m==method else read(m))
    with pytest.raises(RuntimeError):partidas.ejecutar(str(tmp_path/'copy.dwg'),123,accion='catalogo',**CATALOG)
    assert not calls

def test_confirmation_and_catalog():
    registry={}
    class Mcp:
        def tool(self):
            def register(fn):registry[fn.__name__]=fn;return fn
            return register
    partidas.registrar(Mcp(),json.dumps)
    assert 'confirmar=True' in registry['cargar_catalogo_partidas']('C:\\copy.dwg',123,'[]')
    assert 'confirmar=True' in registry['asignar_partidas_objetos']('C:\\copy.dwg',123,'[]')
    assert len(registry)==5

def test_json_normalization():
    args=dict(partidas=json.dumps(CATALOG['partidas']))
    partidas.validar('catalogo',args)
    assert args==CATALOG
