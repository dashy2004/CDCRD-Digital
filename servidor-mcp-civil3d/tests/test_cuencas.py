import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import cuencas, transporte

DWG = r"C:\QA\CDCRD_QA_sintetico.dwg"
CUADRO = [[0, 0], [100, 0], [100, 50], [0, 50]]


def cuenca(**over):
    spec = dict(nombre="C-01", grupo="QA", superficie="TN", contorno=[list(p) for p in CUADRO])
    spec.update(over)
    return spec


def test_creation_without_parameters_sends_no_hydrological_value():
    out = cuencas.validar_creacion(cuenca())
    assert out == dict(nombre="C-01", grupo="QA", superficie="TN", contorno=CUADRO)
    assert not set(cuencas.PARAMETROS) & set(out)


def test_boundary_comes_from_vertices_or_a_polyline_handle_never_both():
    spec = cuenca(polilinea="7a1"); spec.pop("contorno")
    assert cuencas.validar_creacion(spec)["polilinea"] == "7A1"
    with pytest.raises(ValueError, match="uno solo"): cuencas.validar_creacion(cuenca(polilinea="7A1"))
    neither = cuenca(); neither.pop("contorno")
    with pytest.raises(ValueError, match="uno solo"): cuencas.validar_creacion(neither)
    with pytest.raises(ValueError, match="3\\.\\."): cuencas.validar_creacion(cuenca(contorno=[[0, 0], [1, 1]]))
    with pytest.raises(ValueError, match="\\[x, y\\]"): cuencas.validar_creacion(cuenca(contorno=[[0, 0, 5], [1, 1, 5], [2, 0, 5]]))


@pytest.mark.parametrize("extra, message", [
    (dict(coeficiente_escorrentia=1.2), "coeficiente_escorrentia"),
    (dict(coeficiente_escorrentia=True), "coeficiente_escorrentia"),
    (dict(numero_curva=75.5), "entero"),
    (dict(metodo_tc="Manning"), "metodo_tc admite"),
    (dict(tc_min=12, metodo_tc="TR55"), "solo es compatible"),
    (dict(tc_min=-1), "tc_min"),
    (dict(trayectoria=[[0, 0]]), "trayectoria"),
    (dict(estructura=7), "estructura"),
])
def test_invalid_parameters_are_rejected(extra, message):
    with pytest.raises(ValueError, match=message):
        cuencas.validar_creacion(cuenca(**extra))


def test_given_parameters_pass_through_unchanged():
    out = cuencas.validar_creacion(cuenca(coeficiente_escorrentia=0.85, tc_min=12.5, trayectoria=[[5, 45], [50, 20, 101.5], [95, 5]], estructura="RED/P-1", numero_curva=90, estilo="Cuenca"))
    assert out["coeficiente_escorrentia"] == 0.85 and out["tc_min"] == 12.5 and "metodo_tc" not in out and out["numero_curva"] == 90
    assert out["trayectoria"] == [[5, 45], [50, 20, 101.5], [95, 5]] and out["estructura"] == "RED/P-1" and out["estilo"] == "Cuenca"
    assert cuencas.validar_creacion(cuenca(metodo_tc="Kirpich"))["metodo_tc"] == "Kirpich"


def test_update_requires_a_catchment_and_at_least_one_change():
    with pytest.raises(ValueError, match="Nada que actualizar"): cuencas.validar_actualizacion(dict(cuenca="C-01"))
    with pytest.raises(ValueError, match="cuenca"): cuencas.validar_actualizacion(dict(coeficiente_escorrentia=0.5))
    assert cuencas.validar_actualizacion(dict(cuenca="C-01", superficie="TN2")) == dict(cuenca="C-01", superficie="TN2")
    assert cuencas.validar_actualizacion(dict(cuenca="C-01", estructura="2F1")) == dict(cuenca="C-01", estructura="2F1")


VERSION = "0.2.0"


def fake_bridge(monkeypatch, tmp_path, dibujo=DWG, version=VERSION):
    sent = {}
    transporte._versiones.clear()
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    def llamar(method, params=None):
        return {"doc.info": dict(civil3d=True, dibujo=dibujo, insunits=6), "diag.dialogos": dict(modal_abierto=False), "diag.cola": dict(activas=0)}[method]
    def despachar(method, params):
        command, key, digest = params["linea"].split("\n")[:3]
        folder = tmp_path / "CdcrdCivil3dBridge" / "cuencas"
        sent.clear(); sent.update(command=command, request=json.loads((folder / f"cdcrd-cuencas-{key}.request.json").read_text(encoding="utf-8")))
        (folder / f"cdcrd-cuencas-{key}.result.json").write_text(json.dumps(dict(id=key, sha256=digest, module="cdcrd-cuencas", version=version, pid=7, ok=True, committed=False, result={})), encoding="utf-8")
    monkeypatch.setattr(cuencas.bridge, "llamar", llamar); monkeypatch.setattr(transporte.bridge, "llamar", llamar)
    monkeypatch.setattr(transporte.bridge, "llamar_con_aprobacion", despachar)
    return sent


def test_request_is_bound_to_drawing_and_simulates_by_default(monkeypatch, tmp_path):
    sent = fake_bridge(monkeypatch, tmp_path)
    cuencas.ejecutar(DWG, 7, accion="crear", **cuenca(coeficiente_escorrentia=0.9, basura="x"))
    req = sent["request"]
    assert sent["command"] == "CDCRDCUENCASV1" and req["dibujo"] == DWG and req["pid"] == 7 and req["simular"] is True and req["accion"] == "crear"
    assert req["coeficiente_escorrentia"] == 0.9 and "tc_min" not in req and "basura" not in req
    cuencas.ejecutar(DWG, 7, accion="listar")
    assert "cuenca" not in sent["request"]


def test_wrong_document_stops_before_dispatch(monkeypatch, tmp_path):
    fake_bridge(monkeypatch, tmp_path, dibujo=r"C:\otro\abierto.dwg")
    with pytest.raises(ValueError, match="distintos a lo esperado"): cuencas.ejecutar(DWG, 7, accion="listar")
    with pytest.raises(ValueError): cuencas.ejecutar("relativo.dwg", 7, accion="listar")
    with pytest.raises(ValueError): cuencas.ejecutar(DWG, 7, accion="borrar")
    assert not list(tmp_path.glob("**/*.request.json"))


def test_mcp_tools_require_confirmation_and_treat_negative_as_not_given(monkeypatch, tmp_path):
    sent = fake_bridge(monkeypatch, tmp_path)
    tools = {}
    class Fake:
        def tool(self):
            def deco(fn): tools[fn.__name__] = fn; return fn
            return deco
    cuencas.registrar(Fake(), lambda x: json.dumps(x))
    assert set(tools) == {"listar_cuencas", "crear_cuenca", "actualizar_cuenca"}
    assert "confirmar=True" in json.loads(tools["crear_cuenca"](DWG, 7, "C-01", "QA", "TN", contorno=json.dumps(CUADRO)))["error"]
    assert "uno solo" in json.loads(tools["crear_cuenca"](DWG, 7, "C-01", "QA", "TN", confirmar=True))["error"]
    assert "error" in json.loads(tools["crear_cuenca"](DWG, 7, "C-01", "QA", "TN", contorno="[[", confirmar=True))
    tools["crear_cuenca"](DWG, 7, "C-01", "QA", "TN", contorno=json.dumps(CUADRO), confirmar=True)
    assert not set(cuencas.PARAMETROS) & set(sent["request"]) and sent["request"]["simular"] is True
    tools["actualizar_cuenca"](DWG, 7, "C-01", coeficiente_escorrentia=0.0, tc_min=15, simular=False, confirmar=True)
    assert sent["request"]["coeficiente_escorrentia"] == 0.0 and sent["request"]["tc_min"] == 15 and sent["request"]["simular"] is False
    assert "Nada que actualizar" in json.loads(tools["actualizar_cuenca"](DWG, 7, "C-01", confirmar=True))["error"]


def test_an_older_loaded_module_is_refused_before_any_request_with_data(monkeypatch, tmp_path):
    sent = fake_bridge(monkeypatch, tmp_path, version="0.1.0")
    with pytest.raises(RuntimeError, match="requiere 0.2.0"):
        cuencas.ejecutar(DWG, 7, accion="actualizar", simular=False, cuenca="C-01", tc_min=12)
    assert sent["request"]["accion"] == "version" and "tc_min" not in sent["request"]
    requests = list(tmp_path.glob("**/*.request.json"))
    assert len(requests) == 1


def test_module_version_is_asked_once_per_process(monkeypatch, tmp_path):
    fake_bridge(monkeypatch, tmp_path)
    cuencas.ejecutar(DWG, 7, accion="listar"); cuencas.ejecutar(DWG, 7, accion="listar")
    assert len(list(tmp_path.glob("**/*.request.json"))) == 3
