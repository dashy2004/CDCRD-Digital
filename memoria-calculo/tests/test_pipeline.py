import hashlib
import json

import pytest

from cdcrd_memoria.adapters import import_etabs_capture
from cdcrd_memoria.cli import main
from cdcrd_memoria.contracts import Dossier, coverage
from cdcrd_memoria.pipeline import generate, load_json
from cdcrd_memoria.sources import SourceError


def test_package_reopens_and_preserves_originals(dossier_data, tmp_path):
    source = tmp_path / "inputs" / "data.json"
    before = (source.read_bytes(), source.stat().st_mtime_ns)
    output = tmp_path / "output"
    result = generate(Dossier.model_validate(dossier_data), output, tmp_path)
    assert result["sources_unchanged"] and not (output / "INCOMPLETE").exists()
    assert (source.read_bytes(), source.stat().st_mtime_ns) == before
    portable = Dossier.model_validate(load_json(output / "expediente.json"))
    assert portable.sources[0].path == "fuentes/S1.json"
    manifest = load_json(output / "manifest.json")
    for record in manifest["files"]:
        assert hashlib.sha256((output / record["path"]).read_bytes()).hexdigest() == record["sha256"]
    generate(portable, tmp_path / "second", output, ["html"])
    with pytest.raises(SourceError):
        generate(portable, output, output)


def test_source_change_during_render_leaves_incomplete(dossier_data, tmp_path, monkeypatch):
    from cdcrd_memoria import renderers

    original = renderers.render_html

    def changed(view, path):
        original(view, path)
        (tmp_path / "inputs" / "data.json").write_text("changed", encoding="utf-8")

    monkeypatch.setattr(renderers, "render_html", changed)
    with pytest.raises(SourceError):
        generate(Dossier.model_validate(dossier_data), tmp_path / "output", tmp_path, ["html"])
    assert (tmp_path / "output" / "INCOMPLETE").exists()
    assert not (tmp_path / "output" / "manifest.json").exists()


def test_input_file_protected_even_outside_source_roots(dossier_data, tmp_path):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(dossier_data), encoding="utf-8")
    with pytest.raises(SourceError):
        generate(Dossier.model_validate(dossier_data), path, tmp_path, ["html"], path)
    assert json.loads(path.read_text()) == dossier_data


@pytest.mark.parametrize("content", ['{"a":1,"a":2}', '{"n":NaN}', "[]"])
def test_ambiguous_json_rejected(tmp_path, content):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        load_json(path)


def test_capture_import_is_inventory_only(dossier_data):
    capture = {
        "schema": "cdcrd-etabs-capture/1",
        "snapshot": {"stories": [], "frames": [], "units": "kN_m_C"},
        "source": {"locked": True},
        "finished_at": "2000-01-01",
    }
    imported = import_etabs_capture(capture, Dossier.model_validate(dossier_data), "S1")
    assert imported.results == []
    assert coverage(imported)["analysis_freshness"] == "unverified"
    assert "analysis" in coverage(imported)["pending"]
    assert next(o for o in imported.observations if o.id.endswith("stories")).value == 0
    assert next(o for o in imported.observations if o.id.endswith("walls")).value is None
    with pytest.raises(ValueError):
        import_etabs_capture(capture, imported, "S1")


def test_bounded_json_and_capture_hash(tmp_path):
    path = tmp_path / "capture.json"
    path.write_text('{"schema":"old"}', encoding="utf-8")
    with pytest.raises(SourceError):
        load_json(path, "0" * 64)
    path.write_bytes(b" " * (8 * 1024 * 1024 + 1))
    with pytest.raises(ValueError, match="8 MiB"):
        load_json(path)


def test_cli_exit_and_diagnostics(dossier_data, tmp_path, capsys):
    path = tmp_path / "input.json"
    path.write_text(json.dumps(dossier_data), encoding="utf-8")
    assert main(["validate", str(path)]) == 0
    assert json.loads(capsys.readouterr().out)["source_files_checked"] is False
    assert main(["render", str(path), "--output", str(tmp_path / "output"), "--formats", "html"]) == 0
    capsys.readouterr()
    assert main(["render", str(path), "--output", str(tmp_path / "output")]) == 2
    assert "Error:" in capsys.readouterr().err


def test_cli_json_survives_windows_legacy_stdout(dossier_data, tmp_path, monkeypatch):
    import io

    dossier_data["project"]["name"] = "Ejemplo σ θ"
    path = tmp_path / "input.json"
    path.write_text(json.dumps(dossier_data), encoding="utf-8")
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr("sys.stdout", stream)
    assert main(["prepare", str(path)]) == 0
    stream.flush()
    assert json.loads(buffer.getvalue())["subtitle"] == "Ejemplo σ θ"
