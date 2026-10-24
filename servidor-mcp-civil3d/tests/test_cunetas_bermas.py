import json
import pytest
import corredores


def tool_and_calls():
    tools, calls = {}, []
    class Mcp:
        def tool(self):
            def register(fn):
                tools[fn.__name__] = fn
                return fn
            return register
    corredores.registrar(Mcp(), lambda *a, **k: calls.append((a, k)), json.dumps)
    return tools["crear_ensamblaje_cunetas_bermas"], calls


def args():
    return dict(nombre="QA", origen="[0,0,0]", ancho_izq=3.5, ancho_der=3.5,
                pendiente_izq=-.02, pendiente_der=-.02, espesores="[0.05,0.07,0.2,0.3]",
                ancho_berma_izq=1.5, ancho_berma_der=2, pendiente_berma_izq=-.04,
                pendiente_berma_der=-.03, profundidad_cuneta=.6, ancho_fondo_cuneta=.5,
                talud_cuneta_interior_hv=2, talud_cuneta_exterior_hv=1.5,
                talud_corte=3, talud_relleno=4, ancho_daylight_max=50)


def test_confirmation_and_exact_serializable_payload():
    tool, calls = tool_and_calls()
    assert "confirmar=True" in tool(**args())
    assert not calls
    tool(**args(), confirmar=True, simular=True)
    (method, payload), options = calls[0]
    assert method == "civil.ensamblaje_cunetas_bermas"
    assert options == {"escribe": True}
    expected = args() | {"origen": [0, 0, 0], "espesores": [.05, .07, .2, .3], "simular": True}
    assert payload == expected
    json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize("key,value", [("origen", "[0,1]"), ("origen", "[true,0,0]"), ("espesores", "[0.1]"), ("espesores", "[1e999,0.1,0.2,0.3]")])
def test_invalid_lists_never_send_write(key, value):
    tool, calls = tool_and_calls()
    assert "error" in tool(**(args() | {key: value}), confirmar=True)
    assert not calls
