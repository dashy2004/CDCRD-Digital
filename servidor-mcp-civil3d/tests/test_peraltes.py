import hashlib
import json

import pytest
import peraltes

TABLE = [[0, -.02, -.02], [50, .06, -.06], [100, -.02, -.02]]


@pytest.mark.parametrize("table", [[], TABLE[:2], [[0, 0, 0], [0, 0, 0], [100, 0, 0]],
    [[0, 0, 0], [50, .13, 0], [100, 0, 0]], [[0, 0, 0], [50, True, 0], [100, 0, 0]],
    [[0, 0, 0], [50, float("nan"), 0], [100, 0, 0]], [[0, 0, 0], [50, 0], [100, 0, 0]]])
def test_invalid_table_rejected_before_cad(table, monkeypatch, tmp_path):
    def forbidden(*a, **k):
        pytest.fail("Invalid input reached CAD")
    monkeypatch.setattr(peraltes.bridge, "llamar", forbidden)
    with pytest.raises((ValueError, TypeError)):
        peraltes.ejecutar(str(tmp_path / "copy.dwg"), 123, "C", table)


def prepare_transport(tmp_path, monkeypatch, mode="success"):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    calls = []
    def read(method):
        return {"doc.info": {"civil3d": True, "dibujo": str(tmp_path / "copy.dwg"), "insunits": 6},
                "diag.dialogos": {"modal_abierto": False}, "diag.cola": {"activas": []}}[method]
    def dispatch(method, payload):
        calls.append((method, payload))
        command, key, digest, tail = payload["linea"].split("\n")
        assert command == "CDCRDPERALTESV1" and tail == ""
        root = tmp_path
        data = (root / ("cdcrd-peraltes-" + key + ".request.json")).read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest
        request = json.loads(data)
        assert request["tabla"] == TABLE and request["pid"] == 123 and request["simular"]
        assert "vence_utc" in request
        if mode == "transport-error":
            raise TimeoutError("socket expired")
        if mode == "missing":
            return
        receipt = dict(id=key if mode != "wrong-id" else "x", sha256=digest, module="cdcrd-peraltes", version="0.1.0", pid=123,
                       ok=mode != "native-error", committed=False, error="rollback" if mode == "native-error" else None, result={"simulation": True})
        (root / ("cdcrd-peraltes-" + key + ".result.json")).write_text(json.dumps(receipt))
    monkeypatch.setattr(peraltes.bridge, "llamar", read)
    monkeypatch.setattr(peraltes.bridge, "llamar_con_aprobacion", dispatch)
    return calls


def test_request_hash_document_pid_and_receipt(tmp_path, monkeypatch):
    calls = prepare_transport(tmp_path, monkeypatch)
    result = peraltes.ejecutar(str(tmp_path / "copy.dwg"), 123, "C", TABLE)
    assert result["ok"] and not result["committed"] and len(calls) == 1


@pytest.mark.parametrize("mode", ["transport-error", "missing", "wrong-id", "native-error"])
def test_failures_preserve_receipt_identity_and_never_retry(tmp_path, monkeypatch, mode):
    calls = prepare_transport(tmp_path, monkeypatch, mode)
    with pytest.raises(peraltes.PeralteError) as raised:
        peraltes.ejecutar(str(tmp_path / "copy.dwg"), 123, "C", TABLE, timeout=.001)
    assert len(calls) == 1 and raised.value.receipt["id"]
    assert len(list(tmp_path.glob("*.request.json"))) == 1


def test_wrong_document_and_modal_do_not_dispatch(tmp_path, monkeypatch):
    calls = prepare_transport(tmp_path, monkeypatch)
    with pytest.raises(ValueError, match="Documento"):
        peraltes.ejecutar(r"C:\other.dwg", 123, "C", TABLE)
    original = peraltes.bridge.llamar
    monkeypatch.setattr(peraltes.bridge, "llamar", lambda method: {"modal_abierto": True} if method == "diag.dialogos" else original(method))
    with pytest.raises(RuntimeError, match="ocupado"):
        peraltes.ejecutar(str(tmp_path / "copy.dwg"), 123, "C", TABLE)
    assert calls == []


def test_tool_requires_confirmation(monkeypatch, tmp_path):
    tools = {}
    class Mcp:
        def tool(self):
            def register(fn):
                tools[fn.__name__] = fn
                return fn
            return register
    peraltes.registrar(Mcp(), json.dumps)
    monkeypatch.setattr(peraltes, "ejecutar", lambda *a, **k: pytest.fail("Not confirmed"))
    assert "confirmar=True" in tools["peraltes_por_tabla"](str(tmp_path / "copy.dwg"), 123, "C", json.dumps(TABLE))
