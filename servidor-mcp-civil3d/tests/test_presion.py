import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import presion


def red(**over):
    spec = dict(nombre="RED", nodos=[
        dict(id="A", tipo="libre", xyz=[0, 0, 10]),
        dict(id="B", tipo="codo", xyz=[20, 0, 10], familia="elbow", diametro_nominal=6, angulo=90),
        dict(id="C", tipo="te", xyz=[20, 20, 10], familia="tee", diametro_nominal=6, diametro_nominal_2=4),
        dict(id="D", tipo="libre", xyz=[40, 20, 10]),
        dict(id="E", tipo="libre", xyz=[20, 40, 10])],
        tuberias=[dict(id="T1", desde="A", hasta="B", familia="pipe", diametro_nominal=6),
                  dict(id="T2", desde="B", hasta="C", familia="pipe", diametro_nominal=6),
                  dict(id="T3", desde="C", hasta="D", familia="pipe", diametro_nominal=4),
                  dict(id="T4", desde="C", hasta="E", familia="pipe", diametro_nominal=6)])
    spec.update(over)
    return spec


def test_valid_network_keeps_defaults_and_optional_fields():
    out = presion.validar_creacion(red(superficie="TN", lista_partes="Standard"))
    assert out["capa"] == "CDCRD-PRESION" and out["conectar"] is True and out["rotar"] is True
    assert out["tolerancia_conexion_m"] == 1.0 and out["superficie"] == "TN" and out["lista_partes"] == "Standard"
    assert [n["id"] for n in out["nodos"]] == ["A", "B", "C", "D", "E"]
    assert out["nodos"][2]["diametro_nominal_2"] == 4 and "familia" not in out["nodos"][0]


@pytest.mark.parametrize("mutate, message", [
    (lambda s: s["nodos"].append(dict(id="A", tipo="libre", xyz=[1, 1, 1])), "Nodo duplicado"),
    (lambda s: s["nodos"][1].update(tipo="pozo"), "tipo de nodo invalido"),
    (lambda s: s["nodos"][1].pop("familia"), "familia de B"),
    (lambda s: s["tuberias"].append(dict(id="T5", desde="B", hasta="D", familia="pipe", diametro_nominal=6)), "requiere 2 tuberias"),
    (lambda s: s["nodos"].append(dict(id="F", tipo="libre", xyz=[9, 9, 9])), "no tiene tuberias"),
    (lambda s: s["tuberias"][0].update(hasta="A"), "dos nodos distintos"),
    (lambda s: s["tuberias"][0].update(diametro_nominal=0), "diametro_nominal de T1"),
    (lambda s: s.update(conectar="si"), "booleanos"),
    (lambda s: s["nodos"][0].update(xyz=[0, 0]), "requiere XYZ"),
])
def test_invalid_networks_are_rejected(mutate, message):
    spec = red(); mutate(spec)
    with pytest.raises(ValueError, match=message):
        presion.validar_creacion(spec)


def test_cotas_and_trazado_validation():
    out = presion.validar_cotas(dict(superficie="TN", puntos=[[1, 2], [3, 4]]))
    assert out["puntos"] == [[1, 2], [3, 4]]
    with pytest.raises(ValueError): presion.validar_cotas(dict(superficie="TN", puntos=[]))
    t = presion.validar_trazado(dict(nombre="R", superficie="TN", familia="pipe", diametro_nominal=6, ruta=[[0, 0], [10, 0]]))
    assert t["cobertura_m"] == 1.0 and t["codos_automaticos"] is True
    with pytest.raises(ValueError): presion.validar_trazado(dict(nombre="R", superficie="TN", familia="pipe", diametro_nominal=6, ruta=[[0, 0]]))


def test_ejecutar_rejects_bad_arguments_before_touching_the_bridge():
    with pytest.raises(ValueError): presion.ejecutar("relativo.dwg", 1, accion="catalogo")
    with pytest.raises(ValueError): presion.ejecutar(r"C:\x\a.dwg", 0, accion="catalogo")
    with pytest.raises(ValueError): presion.ejecutar(r"C:\x\a.dwg", 1, accion="borrar")
    with pytest.raises(ValueError): presion.ejecutar(r"C:\x\a.dwg", 1, accion="verificar", red="")


def test_mcp_tools_require_confirmation_and_parse_json():
    tools = {}
    class Fake:
        def tool(self):
            def deco(fn): tools[fn.__name__] = fn; return fn
            return deco
    presion.registrar(Fake(), lambda x: json.dumps(x))
    assert set(tools) == {"listar_catalogo_presion", "cotas_superficie", "crear_red_presion", "verificar_red_presion"}
    assert "confirmar=True" in json.loads(tools["crear_red_presion"](r"C:\x\a.dwg", 1, "R", "[]", "[]"))["error"]
    assert "error" in json.loads(tools["crear_red_presion"](r"C:\x\a.dwg", 1, "R", "{", "[]", confirmar=True))
    assert "error" in json.loads(tools["cotas_superficie"](r"C:\x\a.dwg", 1, "TN", "no json"))
