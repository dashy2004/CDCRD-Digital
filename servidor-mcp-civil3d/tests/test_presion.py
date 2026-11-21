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
    t = presion.validar_trazado(trazado())
    assert t["cobertura_m"] == 1.2 and t["codos_automaticos"] is True and t["paso_m"] == 5.0 and "cobertura_min_m" not in t and "polilinea" not in t
    with pytest.raises(ValueError): presion.validar_trazado(trazado(ruta=[[0, 0]]))


def trazado(**over):
    spec = dict(nombre="R", superficie="TN", familia="pipe", diametro_nominal=6, cobertura_m=1.2, ruta=[[0, 0], [10, 0]])
    spec.update(over)
    return spec


def test_trazado_requires_an_explicit_design_cover():
    spec = trazado(); spec.pop("cobertura_m")
    with pytest.raises(ValueError, match="cobertura_m"): presion.validar_trazado(spec)


def test_trazado_takes_vertices_or_a_polyline_handle_never_both():
    spec = trazado(polilinea="1a2f"); spec.pop("ruta")
    out = presion.validar_trazado(spec)
    assert out["polilinea"] == "1A2F" and "ruta" not in out
    with pytest.raises(ValueError, match="una sola"): presion.validar_trazado(trazado(polilinea="1A2F"))
    neither = trazado(); neither.pop("ruta")
    with pytest.raises(ValueError, match="una sola"): presion.validar_trazado(neither)
    bad = trazado(polilinea="no-hex"); bad.pop("ruta")
    with pytest.raises(ValueError, match="handle"): presion.validar_trazado(bad)


def test_trazado_minimum_cover_cannot_exceed_design_cover():
    assert presion.validar_trazado(trazado(cobertura_min_m=1.0))["cobertura_min_m"] == 1.0
    with pytest.raises(ValueError, match="no puede superar"): presion.validar_trazado(trazado(cobertura_min_m=1.5))
    with pytest.raises(ValueError, match="booleano"): presion.validar_trazado(trazado(codos_automaticos="si"))
    with pytest.raises(ValueError, match="punto de la ruta"): presion.validar_trazado(trazado(ruta=[[0, 0], [5]]))


def test_inspeccion_validation_keeps_only_given_options():
    assert presion.validar_inspeccion(dict(red="RED")) == dict(red="RED", paso_m=5.0)
    out = presion.validar_inspeccion(dict(red="RED", superficie="TN", cobertura_min_m=0.9, paso_m=2))
    assert out == dict(red="RED", paso_m=2, superficie="TN", cobertura_min_m=0.9)
    with pytest.raises(ValueError): presion.validar_inspeccion(dict(red=""))
    with pytest.raises(ValueError, match="paso_m"): presion.validar_inspeccion(dict(red="RED", paso_m=0))


def test_request_carries_only_validated_fields(monkeypatch, tmp_path):
    sent = {}
    def llamar(method, params=None):
        return {"doc.info": dict(civil3d=True, dibujo=str(tmp_path / "a.dwg"), insunits=6), "diag.dialogos": dict(modal_abierto=False), "diag.cola": dict(activas=0)}[method]
    def despachar(method, params):
        key = params["linea"].split("\n")[1]
        sent.clear(); sent.update(json.loads((tmp_path / f"cdcrd-presion-{key}.request.json").read_text(encoding="utf-8")))
        (tmp_path / f"cdcrd-presion-{key}.result.json").write_text(json.dumps(dict(id=key, sha256=params["linea"].split("\n")[2], module="cdcrd-presion", version="0.2.1", pid=7, ok=True, committed=False, result={})), encoding="utf-8")
    presion.transporte._versiones.clear()
    monkeypatch.setattr(presion.bridge, "llamar", llamar); monkeypatch.setattr(presion.bridge, "llamar_con_aprobacion", despachar)
    presion.ejecutar(str(tmp_path / "a.dwg"), 7, accion="inspeccionar", red="RED", cobertura_min_m=1.0, basura="x")
    assert sent["accion"] == "inspeccionar" and sent["red"] == "RED" and sent["cobertura_min_m"] == 1.0 and "basura" not in sent and sent["pid"] == 7
    presion.ejecutar(str(tmp_path / "a.dwg"), 7, accion="leer")
    assert sent["accion"] == "leer" and "red" not in sent
    presion.ejecutar(str(tmp_path / "a.dwg"), 7, accion="trazado", **trazado(cobertura_min_m=1.0))
    assert sent["simular"] is True and sent["cobertura_min_m"] == 1.0 and sent["ruta"] == [[0, 0], [10, 0]]


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
    assert set(tools) == {"listar_catalogo_presion", "cotas_superficie", "crear_red_presion", "verificar_red_presion",
                          "leer_redes_presion", "trazar_red_presion", "inspeccionar_red_presion"}
    args = (r"C:\x\a.dwg", 1, "R", "TN", "pipe", 6.0, 1.2)
    assert "confirmar=True" in json.loads(tools["trazar_red_presion"](*args, ruta="[[0,0],[1,0]]"))["error"]
    assert "una sola" in json.loads(tools["trazar_red_presion"](*args, confirmar=True))["error"]
    assert "una sola" in json.loads(tools["trazar_red_presion"](*args, ruta="[[0,0],[1,0]]", polilinea="1A", confirmar=True))["error"]
    assert "error" in json.loads(tools["trazar_red_presion"](*args, ruta="[[", confirmar=True))
    assert "confirmar=True" in json.loads(tools["crear_red_presion"](r"C:\x\a.dwg", 1, "R", "[]", "[]"))["error"]
    assert "error" in json.loads(tools["crear_red_presion"](r"C:\x\a.dwg", 1, "R", "{", "[]", confirmar=True))
    assert "error" in json.loads(tools["cotas_superficie"](r"C:\x\a.dwg", 1, "TN", "no json"))


def test_an_older_loaded_module_is_refused_before_the_write_request(monkeypatch, tmp_path):
    sent = []
    def llamar(method, params=None):
        return {"doc.info": dict(civil3d=True, dibujo=str(tmp_path / "a.dwg"), insunits=6), "diag.dialogos": dict(modal_abierto=False), "diag.cola": dict(activas=0)}[method]
    def despachar(method, params):
        key, digest = params["linea"].split("\n")[1:3]
        sent.append(json.loads((tmp_path / f"cdcrd-presion-{key}.request.json").read_text(encoding="utf-8")))
        (tmp_path / f"cdcrd-presion-{key}.result.json").write_text(json.dumps(dict(id=key, sha256=digest, module="cdcrd-presion", version="0.1.0", pid=7, ok=False, committed=False, error="Accion desconocida")), encoding="utf-8")
    presion.transporte._versiones.clear()
    monkeypatch.setattr(presion.bridge, "llamar", llamar); monkeypatch.setattr(presion.bridge, "llamar_con_aprobacion", despachar)
    with pytest.raises(RuntimeError, match="requiere 0.2.1"):
        presion.ejecutar(str(tmp_path / "a.dwg"), 7, accion="trazado", simular=False, **trazado(cobertura_min_m=1.0))
    assert [r["accion"] for r in sent] == ["version"]
    presion.transporte._versiones.clear()
