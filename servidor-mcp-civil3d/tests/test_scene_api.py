import json
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import creacion
import vistas


def registry(module):
    methods, calls = {}, []
    class MCP:
        def tool(self):
            def register(fn):
                methods[fn.__name__] = fn
                return fn
            return register
    module.registrar(MCP(), lambda *args, **kw: calls.append((args, kw)) or "{}",
                     json.dumps)
    return methods, calls


@pytest.mark.parametrize("rotation", ["0", "90", "180", "270"])
def test_export_rotation_reaches_native_without_screen(rotation):
    methods, calls = registry(vistas)
    methods["exportar_vista"]("demo.png", dispositivo="PublishToWeb PNG.pc3",
                              nombre_vista="DEMO", rotacion=rotation, confirmar=True)
    assert calls[0][0][1]["rotacion"] == rotation
    assert calls[0][0][0] == "vista.exportar"
    assert calls[0][1]["escribe"] is True


@pytest.mark.parametrize("rotation", ["45", "-90", "360", "90.0", "NaN", True])
def test_invalid_rotation_never_reaches_bridge(rotation):
    methods, calls = registry(vistas)
    result = methods["exportar_vista"]("existing.png", rotacion=rotation, confirmar=True)
    assert "error" in json.loads(result)
    assert calls == []


def test_omitted_rotation_preserves_previous_contract():
    methods, calls = registry(vistas)
    methods["exportar_vista"]("demo.png", confirmar=True)
    assert "rotacion" not in calls[0][0][1]


def test_block_needs_confirmation_then_uses_atomic_native_api():
    methods, calls = registry(creacion)
    entities = '[{"tipo":"esfera","centro":[0,0,4.1],"radio":1.8}]'
    result = methods["crear_bloque_3d"]("DEMO_TREE", entities)
    assert "confirmar" in json.loads(result)["error"]
    assert calls == []
    methods["crear_bloque_3d"]("DEMO_TREE", entities, confirmar=True)
    assert calls == [(("blocks.create", {"nombre": "DEMO_TREE",
                       "entidades": json.loads(entities)}), {"escribe": True})]


def test_block_rejects_empty_definition_without_native_call():
    methods, calls = registry(creacion)
    assert "error" in json.loads(methods["crear_bloque_3d"]("DEMO", "[]", confirmar=True))
    assert calls == []


def test_new_drawing_requires_confirmation_and_uses_native_document_api():
    methods, calls = registry(creacion)
    assert 'error' in json.loads(methods['crear_dibujo']('C:/Templates/metric.dwt'))
    assert calls == []
    methods['crear_dibujo']('C:/Templates/metric.dwt', confirmar=True)
    assert calls == [(('doc.new', {'plantilla': 'C:/Templates/metric.dwt'}), {'escribe': True})]
