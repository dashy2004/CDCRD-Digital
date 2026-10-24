import copy
import hashlib
import json
import pytest
import espirales

GEOMETRY = dict(inicio=[0,0], pi=[130,0], fin=[195,112.583302491977], radio=50,
                longitud_entrada=25, longitud_salida=35, estacion_inicial=100)


@pytest.mark.parametrize('key,value', [('inicio',[0]),('pi',[0,False]),('fin',[0,float('nan')]),
    ('radio',0),('radio',float('inf')),('longitud_entrada',-.1),('longitud_salida',10001),('estacion_inicial',True)])
def test_invalid_input_does_not_reach_cad(key, value, monkeypatch, tmp_path):
    g=copy.deepcopy(GEOMETRY);g[key]=value
    monkeypatch.setattr(espirales.bridge,'llamar',lambda *args:pytest.fail('Invalid input reached CAD'))
    with pytest.raises(ValueError):
        espirales.ejecutar(str(tmp_path/'copy.dwg'),123,nombre='test',geometria=g)


def prepare(monkeypatch, tmp_path, mode='ok'):
    calls=[]
    def read(method):
        return {'doc.info':dict(civil3d=True,dibujo=str(tmp_path/'copy.dwg'),insunits=6),
                'diag.dialogos':dict(modal_abierto=False),'diag.cola':dict(activas=[])}[method]
    def dispatch(method,payload):
        calls.append((method,payload))
        command,key,digest,tail=payload['linea'].split('\n')
        assert command=='CDCRDESPIRALESV1' and not tail
        raw=(tmp_path/f'cdcrd-espirales-{key}.request.json').read_bytes()
        assert hashlib.sha256(raw).hexdigest()==digest
        request=json.loads(raw)
        assert request['pid']==123 and request['geometria']==GEOMETRY and request['simular']
        if mode=='timeout':raise TimeoutError('uncertain dispatch')
        if mode=='missing':return
        response=dict(id=key,sha256=digest,module='cdcrd-espirales',pid=123,
                      ok=mode!='native-error',committed=False,result={'simulation':True},error='rolled back')
        if mode=='wrong-hash':response['sha256']='bad'
        if mode=='wrong-module':response['module']='other'
        if mode=='wrong-pid':response['pid']=124
        (tmp_path/f'cdcrd-espirales-{key}.result.json').write_text(json.dumps(response))
    monkeypatch.setattr(espirales.bridge,'llamar',read)
    monkeypatch.setattr(espirales.bridge,'llamar_con_aprobacion',dispatch)
    return calls


def test_hash_and_simulation_default(monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path)
    result=espirales.ejecutar(str(tmp_path/'copy.dwg'),123,nombre='test',geometria=GEOMETRY)
    assert result['ok'] and not result['committed'] and len(calls)==1


@pytest.mark.parametrize('mode',['timeout','missing','native-error','wrong-hash','wrong-module','wrong-pid'])
def test_uncertain_or_wrong_receipt_never_retries(mode,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path,mode)
    with pytest.raises(espirales.SpiralError) as raised:
        espirales.ejecutar(str(tmp_path/'copy.dwg'),123,nombre='test',geometria=GEOMETRY,timeout=.001)
    assert len(calls)==1 and raised.value.receipt['id']


def test_busy_queue_and_wrong_document_prevent_dispatch(monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path)
    with pytest.raises(ValueError):
        espirales.ejecutar('C:\\other.dwg',123,nombre='test',geometria=GEOMETRY)
    read=espirales.bridge.llamar
    monkeypatch.setattr(espirales.bridge,'llamar',lambda method:dict(activas=[1]) if method=='diag.cola' else read(method))
    with pytest.raises(RuntimeError):
        espirales.ejecutar(str(tmp_path/'copy.dwg'),123,nombre='test',geometria=GEOMETRY)
    assert not calls


def test_unconfirmed_tool_does_not_dispatch(monkeypatch,tmp_path):
    registered={}
    class Mcp:
        def tool(self):
            def save(fn):registered[fn.__name__]=fn;return fn
            return save
    espirales.registrar(Mcp(),json.dumps)
    monkeypatch.setattr(espirales,'ejecutar',lambda *a,**k:pytest.fail('Not confirmed'))
    result=registered['crear_alineamiento_espirales'](str(tmp_path/'copy.dwg'),123,'test',json.dumps(GEOMETRY))
    assert 'confirmar=True' in result
