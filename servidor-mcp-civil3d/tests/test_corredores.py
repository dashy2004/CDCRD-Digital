import json
import pytest
import corredores

@pytest.mark.parametrize("value", ["[true]", "[null]", "[1e999]", "{}", "[\"x\"]", [float("nan")], list(range(501))])
def test_invalid_numbers(value):
    with pytest.raises((ValueError, TypeError)):
        corredores.numeros(value)

def test_exact_origin():
    assert corredores.numeros("[1,2,3]", 3) == [1, 2, 3]
    with pytest.raises(ValueError):
        corredores.numeros("[1,2]", 3)

@pytest.mark.parametrize("name,args,method", [
    ("crear_ensamblaje_enlaces", dict(nombre="A", origen="[0,0,0]", ancho_izq=3.5, ancho_der=3.5, pendiente_izq=-.02, pendiente_der=-.02), "civil.ensamblaje_enlaces"),
    ("crear_corredor", dict(alineamiento="A", perfil="P", ensamblaje="S", nombre="C", inicio=100, fin=200, frecuencia=10, estaciones_extra="[120,150]"), "civil.corredor"),
    ("crear_ensamblaje_calzada", dict(nombre="A", origen="[0,0,0]", ancho_izq=3.5, ancho_der=3.5, pendiente_izq=-.02, pendiente_der=-.02, espesores="[0.05,0.07,0.2,0.3]", talud_corte=3, talud_relleno=4, ancho_daylight_max=50), "civil.ensamblaje_calzada"),
    ("crear_corredor_calzada", dict(alineamiento="A", perfil="P", ensamblaje="S", nombre="C", superficie_objetivo="T", inicio=100, fin=200, frecuencia=10, estaciones_extra="[120,150]"), "civil.corredor_calzada"),
    ("crear_secciones_corredor", dict(corredor="C", nombre="G", estaciones="[120,150]", semiancho=5, origen="[0,0,0]", cota_min=90, cota_max=110), "civil.secciones_corredor")])
def test_confirmation_and_payload(name, args, method):
    tools, calls = {}, []
    class Mcp:
        def tool(self):
            def register(fn):
                tools[fn.__name__] = fn
                return fn
            return register
    corredores.registrar(Mcp(), lambda *a, **k: calls.append((a, k)), json.dumps)
    assert "confirmar=True" in tools[name](**args)
    assert not calls
    tools[name](**args, confirmar=True, simular=True)
    assert calls[0][0][0] == method
    assert calls[0][1] == {"escribe": True}
    assert calls[0][0][1]["simular"] is True
    assert "capa" not in calls[0][0][1]
