import copy,hashlib,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import targets
BINDINGS=[dict(baseline='A',region='A1',subensamblaje='AA',alineamiento_ancho='BB',perfil_cota='CC')]

@pytest.mark.parametrize('change',[lambda a:a.clear(),lambda a:a[0].update(baseline=''),lambda a:a[0].update(region='A\nB'),lambda a:a[0].update(subensamblaje=True),lambda a:a[0].update(perfil_cota=''),lambda a:a[0].update(alineamiento_ancho=None,perfil_cota=None),lambda a:a.append(dict(a[0],baseline='a')),lambda a:a.extend([dict(a[0],region=str(i)) for i in range(100)])])
def test_invalid_bindings_never_reach_cad(change,monkeypatch,tmp_path):
    rows=copy.deepcopy(BINDINGS);change(rows)
    monkeypatch.setattr(targets.bridge,'llamar',lambda *a:pytest.fail('Invalid request reached CAD'))
    with pytest.raises(ValueError):targets.ejecutar(str(tmp_path/'copy.dwg'),123,accion='crear',asignaciones=rows,corredor_origen='DD',nombre='new')

def test_width_and_height_independent():
    assert targets.validar_asignaciones([dict(BINDINGS[0],perfil_cota=None)])[0]['perfil_cota'] is None
    assert targets.validar_asignaciones([dict(BINDINGS[0],alineamiento_ancho=None)])[0]['alineamiento_ancho'] is None

def prepare(monkeypatch,tmp_path,mode='ok'):
    calls=[]
    def read(method):return {'doc.info':dict(civil3d=True,dibujo=str(tmp_path/'copy.dwg'),insunits=6),'diag.dialogos':dict(modal_abierto=False),'diag.cola':dict(activas=[])}[method]
    def dispatch(method,payload):
        calls.append((method,payload));cmd,key,digest,tail=payload['linea'].split('\n');assert cmd=='CDCRDTARGETSV2' and not tail
        raw=(tmp_path/f'cdcrd-targets-{key}.request.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==digest
        request=json.loads(raw);assert request['pid']==123 and request['asignaciones']==BINDINGS and request['simular']
        if mode=='timeout':raise TimeoutError('uncertain dispatch')
        if mode=='missing':return
        response=dict(id=key,sha256=digest,module='cdcrd-targets',pid=123,ok=mode!='native-error',committed=False,result={},error='rolled back')
        if mode=='wrong-hash':response['sha256']='bad'
        if mode=='wrong-pid':response['pid']=999
        if mode=='wrong-module':response['module']='other'
        (tmp_path/f'cdcrd-targets-{key}.result.json').write_text(json.dumps(response))
    monkeypatch.setattr(targets.bridge,'llamar',read);monkeypatch.setattr(targets.bridge,'llamar_con_aprobacion',dispatch);return calls

def test_hash_and_simulation_default(monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path)
    result=targets.ejecutar(str(tmp_path/'copy.dwg'),123,accion='crear',asignaciones=BINDINGS,corredor_origen='DD',nombre='new')
    assert result['ok'] and not result['committed'] and len(calls)==1

@pytest.mark.parametrize('mode',['timeout','missing','native-error','wrong-hash','wrong-pid','wrong-module'])
def test_uncertain_receipt_never_retries(mode,monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path,mode)
    with pytest.raises(targets.TargetError) as raised:targets.ejecutar(str(tmp_path/'copy.dwg'),123,accion='crear',asignaciones=BINDINGS,corredor_origen='DD',nombre='new',timeout=.001)
    assert raised.value.receipt['id'] and len(calls)==1

def test_busy_or_wrong_document_does_not_dispatch(monkeypatch,tmp_path):
    calls=prepare(monkeypatch,tmp_path)
    with pytest.raises(ValueError):targets.ejecutar('C:\\other.dwg',123,accion='crear',asignaciones=BINDINGS,corredor_origen='DD',nombre='new')
    read=targets.bridge.llamar;monkeypatch.setattr(targets.bridge,'llamar',lambda m:dict(activas=[1]) if m=='diag.cola' else read(m))
    with pytest.raises(RuntimeError):targets.ejecutar(str(tmp_path/'copy.dwg'),123,accion='crear',asignaciones=BINDINGS,corredor_origen='DD',nombre='new')
    assert calls==[]

def test_unconfirmed_tool_never_dispatches(monkeypatch):
    registry={}
    class Mcp:
        def tool(self):
            def save(fn):registry[fn.__name__]=fn;return fn
            return save
    targets.registrar(Mcp(),json.dumps);monkeypatch.setattr(targets,'ejecutar',lambda *a,**k:pytest.fail('Not confirmed'))
    assert 'confirmar=True' in registry['crear_corredor_con_targets']('C:\\copy.dwg',123,'DD','new',json.dumps(BINDINGS))
