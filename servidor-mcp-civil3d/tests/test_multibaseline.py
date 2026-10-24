import copy
import hashlib
import json
import pytest
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))
import multibaseline

BASELINES = [dict(nombre='A',alineamiento='AA',perfil='BB',regiones=[dict(nombre='A1',ensamblaje='CC',inicio=0,fin=100,frecuencia=5,estaciones_extra=[])])]

@pytest.mark.parametrize('key,value',[('inicio',True),('fin',0),('frecuencia',0),('frecuencia',float('nan')),('estaciones_extra',[101]),('estaciones_extra',[2,1]),('estaciones_extra',[1,1]),('ensamblaje','')])
def test_invalid_input_does_not_reach_cad(key,value,monkeypatch,tmp_path):
    g=copy.deepcopy(BASELINES);g[0]['regiones'][0][key]=value
    monkeypatch.setattr(multibaseline.bridge,'llamar',lambda *args:pytest.fail('Invalid input reached CAD'))
    with pytest.raises(ValueError):
        multibaseline.ejecutar(str(tmp_path/'copy.dwg'),123,accion='crear',nombre='test',baselines=g)


def prepare(monkeypatch, tmp_path, mode='ok'):
    calls=[]
    def read(method):
        return {'doc.info':dict(civil3d=True,dibujo=str(tmp_path/'copy.dwg'),insunits=6),
                'diag.dialogos':dict(modal_abierto=False),'diag.cola':dict(activas=[])}[method]
    def dispatch(method,payload):
        calls.append((method,payload))
        command,key,digest,tail=payload['linea'].split('\n')
        assert command=='CDCRDCORREDORESV4' and not tail
        raw=(tmp_path/f'cdcrd-corredores-{key}.request.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==digest
        request=json.loads(raw)
        assert request['pid']==123 and request['baselines']==BASELINES and request['simular']
        if mode=='timeout':raise TimeoutError('uncertain dispatch')
        if mode=='missing':return
        response=dict(id=key,sha256=digest,module='cdcrd-corredores',pid=123,
                      ok=mode!='native-error',committed=False,result={'simulation':True},error='rolled back')
        if mode=='wrong-hash':response['sha256']='bad'
        if mode=='wrong-module':response['module']='other'
        if mode=='wrong-pid':response['pid']=124
        (tmp_path/f'cdcrd-corredores-{key}.result.json').write_text(json.dumps(response))
    monkeypatch.setattr(multibaseline.bridge,'llamar',read)
    monkeypatch.setattr(multibaseline.bridge,'llamar_con_aprobacion',dispatch)
    return calls


def test_hash_and_simulation_default(monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path)
    result=multibaseline.ejecutar(str(tmp_path/'copy.dwg'),123,accion='crear',nombre='test',baselines=BASELINES)
    assert result['ok'] and not result['committed'] and len(calls)==1


@pytest.mark.parametrize('mode',['timeout','missing','native-error','wrong-hash','wrong-module','wrong-pid'])
def test_uncertain_or_wrong_receipt_never_retries(mode,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path,mode)
    with pytest.raises(multibaseline.MultiError) as raised:
        multibaseline.ejecutar(str(tmp_path/'copy.dwg'),123,accion='crear',nombre='test',baselines=BASELINES,timeout=.001)
    assert len(calls)==1 and raised.value.receipt['id']


def test_busy_queue_and_wrong_document_prevent_dispatch(monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path)
    with pytest.raises(ValueError):
        multibaseline.ejecutar('C:\\other.dwg',123,accion='crear',nombre='test',baselines=BASELINES)
    read=multibaseline.bridge.llamar
    monkeypatch.setattr(multibaseline.bridge,'llamar',lambda method:dict(activas=[1]) if method=='diag.cola' else read(method))
    with pytest.raises(RuntimeError):
        multibaseline.ejecutar(str(tmp_path/'copy.dwg'),123,accion='crear',nombre='test',baselines=BASELINES)
    assert not calls


def test_unconfirmed_tool_does_not_dispatch(monkeypatch,tmp_path):
    registered={}
    class Mcp:
        def tool(self):
            def save(fn):registered[fn.__name__]=fn;return fn
            return save
    multibaseline.registrar(Mcp(),json.dumps)
    monkeypatch.setattr(multibaseline,'ejecutar',lambda *a,**k:pytest.fail('Not confirmed'))
    result=registered['crear_corredor_multibaseline'](str(tmp_path/'copy.dwg'),123,'test',json.dumps(BASELINES))
    assert 'confirmar=True' in result


def test_regions_preserve_gaps_and_contiguity():
    b=copy.deepcopy(BASELINES)
    b[0]['regiones'].append(dict(b[0]['regiones'][0],nombre='A2',inicio=100,fin=150,ensamblaje='DD'))
    assert multibaseline.validar_baselines(b)==b
    b[0]['regiones'][1]['inicio']=110
    assert multibaseline.validar_baselines(b)==b
    b[0]['regiones'][1]['inicio']=99
    with pytest.raises(ValueError):multibaseline.validar_baselines(b)

def test_duplicates_and_combined_budget():
    b=copy.deepcopy(BASELINES);b.append(copy.deepcopy(b[0]))
    with pytest.raises(ValueError):multibaseline.validar_baselines(b)
    b[1]['nombre']='B'
    with pytest.raises(ValueError):multibaseline.validar_baselines(b)
