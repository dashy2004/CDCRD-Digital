import importlib.util
from pathlib import Path
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "examples/calle_demo/run.py"
spec = importlib.util.spec_from_file_location("calle_demo_run", SCRIPT)
demo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(demo)


def test_plan_does_not_import_bridge_or_write(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert demo.main([]) == 0
    assert '"instancias": 61' in capsys.readouterr().out
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("expected,actual,version,objects", [
    ("DEMO.dwg", "OTHER.dwg", "0.5.19", 0),
    ("DEMO.dwg", "DEMO.dwg", "0.5.18", 0),
    ("DEMO.dwg", "DEMO.dwg", "0.5.19", 1),
    ("DEMO.dwg", "DEMO.dwg", None, 0),
])
def test_preflight_rejects_other_drawing_old_bridge_or_nonempty_model(tmp_path, expected, actual, version, objects):
    with pytest.raises(ValueError):
        demo.preflight(expected, actual, version, objects, tmp_path)


def test_preflight_rejects_previous_uncertain_run(tmp_path):
    (tmp_path / "control.json").write_text("{}")
    with pytest.raises(ValueError, match="vacia"):
        demo.preflight("DEMO.dwg", "DEMO.dwg", "0.5.19", 0, tmp_path)


def test_preflight_accepts_new_empty_output(tmp_path):
    demo.preflight("DEMO.dwg", "DEMO.dwg", "0.5.19", 0, tmp_path / "new")
