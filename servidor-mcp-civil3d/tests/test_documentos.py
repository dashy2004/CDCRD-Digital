import json, sys
from pathlib import Path
import pytest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import documentos, transporte

DWG = r"C:\QA\CDCRD_QA_sintetico.dwg"


def test_listar_sends_no_fields():
    assert documentos.validar("listar", dict(ruta=DWG, basura=1)) == {}


def test_abrir_requires_an_absolute_dwg_and_defaults_to_write_mode():
    assert documentos.validar("abrir", dict(ruta=DWG)) == dict(ruta=DWG, solo_lectura=False)
    assert documentos.validar("abrir", dict(ruta=DWG, solo_lectura=True))["solo_lectura"] is True
    for bad in ("relativo.dwg", r"C:\QA\plantilla.dwt", "", None):
        with pytest.raises(ValueError): documentos.validar("abrir", dict(ruta=bad))
    with pytest.raises(ValueError, match="booleano"): documentos.validar("abrir", dict(ruta=DWG, solo_lectura="si"))


def test_cerrar_never_discards_changes_unless_asked():
    assert documentos.validar("cerrar", dict(ruta=DWG)) == dict(ruta=DWG, descartar_cambios=False)
    out = documentos.validar("cerrar", dict(ruta=DWG, descartar_cambios=True, activar_despues="Drawing1.dwg"))
    assert out == dict(ruta=DWG, descartar_cambios=True, activar_despues="Drawing1.dwg")
    with pytest.raises(ValueError, match="booleano"): documentos.validar("cerrar", dict(ruta=DWG, descartar_cambios=1))
    with pytest.raises(ValueError, match="otro documento"): documentos.validar("cerrar", dict(ruta=DWG, activar_despues=DWG.upper()))


def test_open_documents_are_named_by_full_path_or_by_bare_name():
    assert documentos.validar("activar", dict(ruta="Drawing1.dwg")) == dict(ruta="Drawing1.dwg")
    assert documentos.validar("activar", dict(ruta=DWG)) == dict(ruta=DWG)
    with pytest.raises(ValueError): documentos.validar("activar", dict(ruta=r"carpeta\relativo.dwg"))
    with pytest.raises(ValueError): documentos.validar("guardar", {})


def fake_bridge(monkeypatch, tmp_path, info, receipt=None, modal=False, activas=0):
    sent = {}
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    def llamar(method, params=None):
        return {"doc.info": info, "diag.dialogos": dict(modal_abierto=modal), "diag.cola": dict(activas=activas)}[method]
    def despachar(method, params):
        command, key, digest = params["linea"].split("\n")[:3]
        folder = tmp_path / "CdcrdCivil3dBridge" / "documentos"
        sent.update(command=command, request=json.loads((folder / f"cdcrd-documentos-{key}.request.json").read_text(encoding="utf-8")))
        body = dict(id=key, sha256=digest, module="cdcrd-documentos", pid=7, ok=True, committed=True, activo=DWG, result={})
        body.update(receipt or {})
        (folder / f"cdcrd-documentos-{key}.result.json").write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(documentos.bridge, "llamar", llamar); monkeypatch.setattr(transporte.bridge, "llamar", llamar)
    monkeypatch.setattr(transporte.bridge, "llamar_con_aprobacion", despachar)
    return sent


def test_request_goes_to_the_user_folder_with_pid_and_expiry(monkeypatch, tmp_path):
    sent = fake_bridge(monkeypatch, tmp_path, dict(dibujo=r"C:\otro\abierto.dwg"))
    out = documentos.ejecutar(7, accion="cerrar", ruta=DWG, descartar_cambios=False, basura="x")
    assert out["activo"] == DWG and sent["command"] == "CDCRDDOCUMENTOSV1"
    req = sent["request"]
    assert req["accion"] == "cerrar" and req["ruta"] == DWG and req["descartar_cambios"] is False and req["pid"] == 7 and "vence_utc" in req and "basura" not in req


def test_no_open_drawing_or_busy_session_stops_before_dispatch(monkeypatch, tmp_path):
    fake_bridge(monkeypatch, tmp_path, dict(dibujo=""))
    with pytest.raises(RuntimeError, match="ningun dibujo"): documentos.ejecutar(7, accion="listar")
    fake_bridge(monkeypatch, tmp_path, dict(dibujo=DWG), modal=True)
    with pytest.raises(RuntimeError, match="ocupado"): documentos.ejecutar(7, accion="listar")
    assert not list((tmp_path / "CdcrdCivil3dBridge").glob("**/*.request.json"))


def test_receipt_from_another_process_or_native_refusal_is_an_error(monkeypatch, tmp_path):
    fake_bridge(monkeypatch, tmp_path, dict(dibujo=DWG), receipt=dict(pid=99))
    with pytest.raises(transporte.ReciboError, match="no corresponde"): documentos.ejecutar(7, accion="listar")
    fake_bridge(monkeypatch, tmp_path, dict(dibujo=DWG), receipt=dict(ok=False, error="El documento tiene cambios sin guardar"))
    with pytest.raises(transporte.ReciboError, match="cambios sin guardar"): documentos.ejecutar(7, accion="cerrar", ruta=DWG)
    with pytest.raises(ValueError): documentos.ejecutar(0, accion="listar")


def test_mcp_tools_require_confirmation_except_listing(monkeypatch, tmp_path):
    fake_bridge(monkeypatch, tmp_path, dict(dibujo=DWG))
    tools = {}
    class Fake:
        def tool(self):
            def deco(fn): tools[fn.__name__] = fn; return fn
            return deco
    documentos.registrar(Fake(), lambda x: json.dumps(x))
    assert set(tools) == {"listar_documentos", "abrir_documento", "activar_documento", "cerrar_documento", "guardar_como"}
    assert "confirmar=True" in json.loads(tools["guardar_como"](7, DWG, r"C:\QA\otro.dwg"))["error"]
    for name in ("abrir_documento", "activar_documento", "cerrar_documento"):
        assert "confirmar=True" in json.loads(tools[name](7, DWG))["error"]
    assert json.loads(tools["listar_documentos"](7))["ok"] is True
    assert "error" in json.loads(tools["abrir_documento"](7, "relativo.dwg", confirmar=True))
    assert json.loads(tools["cerrar_documento"](7, DWG, confirmar=True))["committed"] is True

def guion(monkeypatch, respuestas):
    """Sustituye ejecutar por una lista de respuestas (dict = recibo, excepcion = fallo) y anota las llamadas."""
    llamadas = []
    def ejecutar(pid, *, accion, **datos):
        llamadas.append(dict(datos, accion=accion))
        r = respuestas.pop(0)
        if isinstance(r, Exception): raise r
        return r
    monkeypatch.setattr(documentos, "ejecutar", ejecutar)
    return llamadas


def ocupado(activo):
    return transporte.ReciboError("Drawing is busy.", dict(ok=False, error="Drawing is busy.", activo=activo))


def test_cerrar_activates_a_busy_inactive_drawing_and_retries_once(monkeypatch):
    otro = r"C:\QA\otro.dwg"
    llamadas = guion(monkeypatch, [ocupado(otro), dict(ok=True), dict(ok=True, abiertos=1)])
    recibo = documentos.cerrar(7, ruta=DWG)
    assert [c["accion"] for c in llamadas] == ["cerrar", "activar", "cerrar"]
    assert llamadas[1]["ruta"] == DWG and llamadas[2]["activar_despues"] == otro
    assert recibo["abiertos"] == 1 and "busy" in recibo["reintento"]


def test_cerrar_retry_keeps_the_requested_next_document_and_never_points_to_itself(monkeypatch):
    pedido = r"C:\QA\pedido.dwg"
    llamadas = guion(monkeypatch, [ocupado(r"C:\QA\otro.dwg"), dict(ok=True), dict(ok=True)])
    documentos.cerrar(7, ruta=DWG, activar_despues=pedido)
    assert llamadas[2]["activar_despues"] == pedido
    llamadas = guion(monkeypatch, [ocupado(DWG.upper()), dict(ok=True), dict(ok=True)])
    documentos.cerrar(7, ruta=DWG)
    assert llamadas[2]["activar_despues"] is None


def test_cerrar_does_not_retry_other_refusals_and_reports_a_second_busy(monkeypatch):
    llamadas = guion(monkeypatch, [transporte.ReciboError("El documento tiene cambios sin guardar", dict(ok=False))])
    with pytest.raises(transporte.ReciboError, match="cambios sin guardar"):
        documentos.cerrar(7, ruta=DWG)
    assert len(llamadas) == 1
    llamadas = guion(monkeypatch, [ocupado(r"C:\QA\otro.dwg"), dict(ok=True), ocupado(DWG)])
    with pytest.raises(transporte.ReciboError, match="busy"):
        documentos.cerrar(7, ruta=DWG, descartar_cambios=False)
    assert len(llamadas) == 3 and all(c.get("descartar_cambios", False) is False for c in llamadas)


def test_guardar_como_names_the_document_and_an_absolute_dwg_destination():
    out = documentos.validar("guardar_como", dict(ruta="Drawing1.dwg", destino=r"C:\QA\nuevo.dwg", basura=1))
    assert out == dict(ruta="Drawing1.dwg", destino=r"C:\QA\nuevo.dwg", sobrescribir=False)
    assert documentos.validar("guardar_como", dict(ruta=DWG, destino=DWG, sobrescribir=True))["sobrescribir"] is True
    for malo in (dict(destino="nuevo.dwg"), dict(destino=r"C:\QA\nuevo.dxf"), dict(destino=""), dict(sobrescribir="si"), dict(ruta=r"sub\x.dwg")):
        with pytest.raises(ValueError): documentos.validar("guardar_como", dict(dict(ruta=DWG, destino=r"C:\QA\nuevo.dwg"), **malo))
