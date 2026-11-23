import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import geotecnia, transporte

DWG = r"C:\QA\CDCRD_QA_sintetico.dwg"
UBI, LIT = r"C:\QA\qa_ubicaciones.csv", r"C:\QA\qa_litologia.csv"


def test_listar_sends_no_fields():
    assert geotecnia.validar("listar", dict(proyecto_id="X", basura=1)) == {}


def test_every_write_simulates_unless_confirmed():
    assert geotecnia.validar("crear", dict(proyecto_id="QA GM (v1)")) == dict(proyecto_id="QA GM (v1)", confirmar=False)
    assert geotecnia.validar("vincular", dict(proyecto_id="QA", confirmar=True)) == dict(proyecto_id="QA", confirmar=True)
    with pytest.raises(ValueError, match="booleano"): geotecnia.validar("vincular", dict(proyecto_id="QA", confirmar="si"))


def test_project_id_rejects_path_and_control_characters():
    for malo in ("", "a/b", "a\\b", "x;y", "a\nb", "x" * 101, None, 5):
        with pytest.raises(ValueError): geotecnia.validar("crear", dict(proyecto_id=malo))


def test_crear_keeps_only_optional_fields_that_were_given():
    out = geotecnia.validar("crear", dict(proyecto_id="QA", nombre="Proyecto sintetico", ubicacion="", sistema_coord=None, basura=1))
    assert out == dict(proyecto_id="QA", confirmar=False, nombre="Proyecto sintetico")


def test_importar_requires_absolute_csv_paths_and_a_known_delimiter():
    out = geotecnia.validar("importar", dict(proyecto_id="QA", ubicaciones=UBI, litologia=LIT))
    assert out == dict(proyecto_id="QA", confirmar=False, ubicaciones=UBI, litologia=LIT, delimitador=",")
    assert geotecnia.validar("importar", dict(proyecto_id="QA", ubicaciones=UBI, litologia=LIT, orientacion=UBI, delimitador=";"))["orientacion"] == UBI
    for malo in (dict(ubicaciones="qa.csv"), dict(ubicaciones=r"C:\QA\qa.txt"), dict(litologia=""), dict(delimitador="::")):
        with pytest.raises(ValueError): geotecnia.validar("importar", dict(dict(proyecto_id="QA", ubicaciones=UBI, litologia=LIT), **malo))


def fake_bridge(monkeypatch, tmp_path, info, receipt=None, modal=False):
    sent = {}
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    def llamar(method, params=None):
        return {"doc.info": info, "diag.dialogos": dict(modal_abierto=modal), "diag.cola": dict(activas=0)}[method]
    def despachar(method, params):
        command, key, digest = params["linea"].split("\n")[:3]
        folder = tmp_path / "CdcrdCivil3dBridge" / "geotecnia"
        sent.update(command=command, request=json.loads((folder / f"cdcrd-geotecnia-{key}.request.json").read_text(encoding="utf-8")))
        body = dict(id=key, sha256=digest, module="cdcrd-geotecnia", pid=7, ok=True, committed=False, result={})
        body.update(receipt or {})
        (folder / f"cdcrd-geotecnia-{key}.result.json").write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(geotecnia.bridge, "llamar", llamar); monkeypatch.setattr(transporte.bridge, "llamar", llamar)
    monkeypatch.setattr(transporte.bridge, "llamar_con_aprobacion", despachar)
    return sent


def test_request_goes_to_the_user_folder_with_pid_and_expiry(monkeypatch, tmp_path):
    sent = fake_bridge(monkeypatch, tmp_path, dict(dibujo=DWG))
    geotecnia.ejecutar(7, accion="importar", proyecto_id="QA", ubicaciones=UBI, litologia=LIT, basura="x")
    req = sent["request"]
    assert sent["command"] == "CDCRDGEOTECNIAV1" and req["accion"] == "importar" and req["confirmar"] is False
    assert req["pid"] == 7 and "vence_utc" in req and "basura" not in req


def test_no_open_drawing_or_busy_session_stops_before_dispatch(monkeypatch, tmp_path):
    fake_bridge(monkeypatch, tmp_path, dict(dibujo=""))
    with pytest.raises(RuntimeError, match="ningun dibujo"): geotecnia.ejecutar(7, accion="listar")
    fake_bridge(monkeypatch, tmp_path, dict(dibujo=DWG), modal=True)
    with pytest.raises(RuntimeError, match="ocupado"): geotecnia.ejecutar(7, accion="listar")
    assert not list((tmp_path / "CdcrdCivil3dBridge").glob("**/*.request.json"))


def test_native_refusal_is_an_error_with_its_receipt(monkeypatch, tmp_path):
    fake_bridge(monkeypatch, tmp_path, dict(dibujo=DWG), receipt=dict(ok=False, error="Ya existe un proyecto con ese identificador: QA"))
    with pytest.raises(transporte.ReciboError, match="Ya existe"): geotecnia.ejecutar(7, accion="crear", proyecto_id="QA", confirmar=True)


def test_mcp_tools_default_to_simulation(monkeypatch, tmp_path):
    sent = fake_bridge(monkeypatch, tmp_path, dict(dibujo=DWG))
    tools = {}
    class Fake:
        def tool(self):
            def deco(fn): tools[fn.__name__] = fn; return fn
            return deco
    geotecnia.registrar(Fake(), lambda x: json.dumps(x))
    assert set(tools) == {"gm_listar_proyectos", "gm_crear_proyecto", "gm_importar_csv", "gm_vincular_proyecto"}
    tools["gm_crear_proyecto"](7, "QA")
    assert sent["request"]["confirmar"] is False and sent["request"]["accion"] == "crear"
    tools["gm_vincular_proyecto"](7, "QA", confirmar=True)
    assert sent["request"]["confirmar"] is True
    assert "error" in json.loads(tools["gm_importar_csv"](7, "QA", "relativo.csv", LIT))
