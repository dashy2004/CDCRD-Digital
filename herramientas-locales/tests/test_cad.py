"""CAD tests exercise interoperable geometry rather than screenshots."""

import json
from pathlib import Path

import ezdxf
import pytest

from cdcrd_local import cad
from cdcrd_local.cad import generate_plan, inspect_dxf, preview_dxf


def _source(tmp_path: Path, *, unit="m", factor=1.0, **changes) -> Path:
    data = {
        "name": "Planta CDX",
        "units": unit,
        "outlines": [
            {
                "id": "outline-1",
                "points": [[0, 0], [4 * factor, 0], [4 * factor, 3 * factor], [0, 3 * factor]],
            }
        ],
        "dimensions": [{"p1": [0, 0], "p2": [4 * factor, 0], "offset": -0.5 * factor}],
        "notes": [{"text": "Planta de ejemplo", "position": [0, 3.5 * factor]}],
    }
    data.update(changes)
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.mark.parametrize("unit,factor,insunits", [("m", 1, 6), ("mm", 1000, 4)])
def test_generate_native_dimensions_and_units(tmp_path, unit, factor, insunits):
    source = _source(tmp_path, unit=unit, factor=factor)
    output = tmp_path / "plan.dxf"
    report = generate_plan(source, output)
    assert report["units"] == unit
    assert report["insunits"] == insunits
    assert report["audit"] == {"errors": 0, "repairs": 0}
    assert report["entities"] == {"DIMENSION": 1, "LWPOLYLINE": 1, "TEXT": 1}
    document = ezdxf.readfile(output)
    assert document.dxfversion == "AC1032"
    polyline = document.modelspace().query("LWPOLYLINE").first
    assert polyline.closed
    assert list(polyline.get_points("xy"))[2] == pytest.approx((4 * factor, 3 * factor))
    dimension = document.modelspace().query("DIMENSION").first
    assert dimension.get_measurement() == pytest.approx(4 * factor)
    assert dimension.dxf.geometry in document.blocks
    assert len(list(dimension.virtual_entities())) > 0
    assert document.dimstyles.get("CDX_METRIC").dxf.dimlfac == 1
    assert inspect_dxf(output)["entities"] == report["entities"]


@pytest.mark.parametrize(
    "changes",
    [
        {"units": "feet"},
        {"units": None},
        {"unknown": "field"},
        {"outlines": [{"id": "x", "points": [[0, 0], [2, 2], [0, 2], [2, 0]]}]},
        {"outlines": [{"id": "x", "points": [[0, 0], [1, 0], [2, 0]]}]},
        {"outlines": [{"id": "x", "points": [[0, 0], [float("inf"), 0], [0, 2]]}]},
        {"outlines": [{"id": "x", "points": [[0, 0], ["4", 0], [0, 2]]}]},
        {"outlines": [{"id": "x", "points": [[0, 0], [True, 0], [0, 2]]}]},
        {"dimensions": [{"p1": [0, 0], "p2": [float("nan"), 0], "offset": 1}]},
        {"dimensions": [{"p1": [0, 0], "p2": [0, 0], "offset": 1}]},
        {"outlines": [{"id": "x", "points": [[0, 0], [1, 0], [0, 1]], "layer": "bad:layer"}]},
        {
            "outlines": [
                {"id": "same", "points": [[0, 0], [1, 0], [0, 1]]},
                {"id": "same", "points": [[0, 0], [2, 0], [0, 2]]},
            ]
        },
    ],
)
def test_invalid_plan_never_creates_output(tmp_path, changes):
    source = _source(tmp_path, **changes)
    original = source.read_bytes()
    output = tmp_path / "invalid.dxf"
    with pytest.raises(ValueError):
        generate_plan(source, output)
    assert not output.exists()
    assert source.read_bytes() == original


def test_missing_units_rejected(tmp_path):
    source = _source(tmp_path)
    data = json.loads(source.read_text())
    del data["units"]
    source.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        generate_plan(source, tmp_path / "invalid.dxf")


def test_existing_output_is_preserved(tmp_path):
    source = _source(tmp_path)
    output = tmp_path / "existing.dxf"
    output.write_bytes(b"user drawing")
    with pytest.raises(FileExistsError):
        generate_plan(source, output)
    assert output.read_bytes() == b"user drawing"


@pytest.mark.parametrize(
    "extension,signature", [("svg", b"<svg"), ("png", b"\x89PNG"), ("pdf", b"%PDF")]
)
def test_preview_formats_preserve_source_and_output(tmp_path, extension, signature):
    source = _source(tmp_path)
    dxf = tmp_path / "plan.dxf"
    generate_plan(source, dxf)
    original = dxf.read_bytes()
    output = tmp_path / f"preview.{extension}"
    report = preview_dxf(dxf, output)
    assert report["format"] == extension
    assert signature in output.read_bytes()[:1000]
    preview_bytes = output.read_bytes()
    with pytest.raises(FileExistsError):
        preview_dxf(dxf, output)
    assert output.read_bytes() == preview_bytes
    assert dxf.read_bytes() == original
    assert inspect_dxf(dxf)["entities"]["DIMENSION"] == 1


def test_corrupt_dxf_is_not_accepted(tmp_path):
    source = tmp_path / "broken.dxf"
    source.write_text("not a DXF", encoding="utf-8")
    with pytest.raises(ValueError):
        inspect_dxf(source)
    with pytest.raises(ValueError):
        preview_dxf(source, tmp_path / "preview.svg")
    assert not (tmp_path / "preview.svg").exists()


def test_failure_after_reserved_output_removes_only_new_file(tmp_path, monkeypatch):
    source = _source(tmp_path)
    original = source.read_bytes()
    output = tmp_path / "plan.dxf"

    def fail_readback(*args):
        raise ValueError("simulated DXF readback failure")

    monkeypatch.setattr(cad, "_load_dxf", fail_readback)
    with pytest.raises(ValueError, match="simulated"):
        generate_plan(source, output)
    assert not output.exists()
    assert source.read_bytes() == original
