"""Synthetic interchange preflight; no CAD or game process is used."""
import hashlib
import json
import os
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest
from cdcrd_beamng import build_package
from cdcrd_beamng.sources import read_snapshot

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def snapshot(tmp_path):
    surface = {"name": "Synthetic TIN", "vertices_abs_m": [
        [1000, 2000, 10], [1010, 2000, 11], [1010, 2010, 12], [1000, 2010, 11]],
        "triangles": [[0, 1, 2], [0, 2, 3]],
        "boundary_edges": [[0, 1], [1, 2], [2, 3], [3, 0]]}
    data = {"schema": "cdcrd.civil3d.snapshot/1", "units": "m",
            "surfaces": {"terrain": surface, "road": deepcopy(surface)},
            "sources": {"drawing_units": "INSUNITS=6", "civil_drawing_units": "Meters",
                        "coordinate_order": "E,N,Z", "terrain_handle": "A1", "road_handle": "A2"}}
    path = tmp_path / "synthetic.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def change(path, edit):
    data = json.loads(path.read_text())
    edit(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def validate(**options):
    from cdcrd_beamng.validation import validate_interchange
    return validate_interchange(**options)


def test_snapshot_report_is_read_only_and_does_not_claim_consumer_validation(snapshot):
    before = hashlib.sha256(snapshot.read_bytes()).hexdigest()
    files = set(snapshot.parent.iterdir())
    result = validate(snapshot=snapshot)
    assert result["schema"] == "cdcrd.interchange-validation/1"
    assert result["module"] == "beamng" and result["ok"]
    assert result["units"] == "m" and result["coordinate_order"] == "E,N,Z"
    assert result["counts"]["road_triangles"] == 2
    assert result["source_identity_checked"] is True
    assert result["consumer_validation"] == "not_checked"
    assert result["crs"] == "not_verified"
    assert result["bounds_abs_m"]["min"] == [1000, 2000, 10]
    assert str(snapshot) not in json.dumps(result)
    assert hashlib.sha256(snapshot.read_bytes()).hexdigest() == before
    assert set(snapshot.parent.iterdir()) == files


@pytest.mark.parametrize("field,value", [
    ("drawing_units", "INSUNITS=2"), ("civil_drawing_units", "Feet"),
    ("coordinate_order", "N,E,Z"), ("terrain_handle", "a2"),
    ("terrain_handle", "00a2"), ("terrain_handle", "0"),
    ("terrain_handle", "bad id"), ("terrain_handle", 12), ("road_handle", ""),
])
def test_snapshot_rejects_contradictory_metadata_and_object_ids(snapshot, field, value):
    change(snapshot, lambda d: d["sources"].update({field: value}))
    with pytest.raises(ValueError):
        read_snapshot(snapshot)
    assert not validate(snapshot=snapshot)["ok"]


@pytest.mark.parametrize("edges", [
    [[0, 1], [1, 99]], [[True, 1]], [[0, 0]], [[0, 2]],
    [[0, 1], [1, 2], [2, 3]], [[0, 1], [1, 0]], "invalid",
])
def test_boundary_references_must_match_visible_mesh(snapshot, edges):
    change(snapshot, lambda d: d["surfaces"]["road"].update(boundary_edges=edges))
    with pytest.raises(ValueError):
        read_snapshot(snapshot)


def test_optional_legacy_metadata_is_distinguished_from_verified_identity(snapshot):
    change(snapshot, lambda d: d.pop("sources"))
    result = validate(snapshot=snapshot)
    assert result["ok"] and result["source_identity_checked"] is False
    assert result["warnings"]
    change(snapshot, lambda d: d.update(sources={"terrain_handle": "A1"}))
    assert not validate(snapshot=snapshot)["ok"]
    change(snapshot, lambda d: d.update(sources=[]))
    assert not validate(snapshot=snapshot)["ok"]


@pytest.mark.parametrize("edit", [
    lambda d: d.update(units="ft"),
    lambda d: d["surfaces"]["road"]["vertices_abs_m"][0].__setitem__(0, True),
    lambda d: d["surfaces"]["road"]["triangles"][0].__setitem__(0, 99),
    lambda d: d.update(alignment={"nodes_abs_m": [[0, 0, 1, 4], [0, 0, 2, 4]]}),
])
def test_existing_units_coordinates_and_references_are_reused(snapshot, edit):
    change(snapshot, edit)
    result = validate(snapshot=snapshot)
    assert result["ok"] is False and result["errors"]


def test_builder_also_rejects_invalid_metadata_before_creating_output(snapshot):
    change(snapshot, lambda d: d["sources"].update(coordinate_order="N,E,Z"))
    output = snapshot.parent / "package"
    with pytest.raises(ValueError):
        build_package(snapshot=snapshot, output=output, level_id="synthetic_validation")
    assert not output.exists()
    assert not list(snapshot.parent.glob(".cdcrd-build-*"))


def landxml(tmp_path, points=None, face="p1 p2 p3", invisible="0", unit="meter"):
    points = points if points is not None else (
        '<P id="p1">2000 1000 10</P><P id="p2">2000 1010 11</P>'
        '<P id="p3">2010 1000 12</P>')
    path = tmp_path / "synthetic.xml"
    path.write_text(f'<LandXML><Units><Metric linearUnit="{unit}"/></Units><Surfaces>'
        f'<Surface name="Synthetic"><Definition surfType="TIN"><Pnts>{points}</Pnts>'
        f'<Faces><F i="{invisible}">{face}</F></Faces></Definition></Surface>'
        '</Surfaces></LandXML>', encoding="utf-8")
    return path


def test_landxml_reports_en_z_and_scoped_point_ids(tmp_path):
    path = landxml(tmp_path)
    result = validate(terrain_landxml=path, road_landxml=path)
    assert result["ok"] and result["source_identity_checked"] is False
    assert result["bounds_abs_m"]["max"] == [1010, 2010, 12]


@pytest.mark.parametrize("options", [
    {"unit": "foot"}, {"face": "p1 p2 missing"},
    {"face": "p1 p2 missing", "invisible": "1"},
    {"points": '<P id=" ">0 0 0</P>'},
    {"points": '<P id="p1">0 0 0</P><P id="p1">1 1 1</P>'},
    {"points": '<P id="p1">NaN 0 0</P>'},
])
def test_landxml_rejects_units_ids_coordinates_and_hidden_face_references(tmp_path, options):
    path = landxml(tmp_path, **options)
    assert not validate(terrain_landxml=path, road_landxml=path)["ok"]


def test_invalid_files_and_mixed_modes_produce_failed_reports(snapshot):
    for options in ({}, {"snapshot": snapshot.parent / "absent.json"},
                    {"snapshot": snapshot, "road_landxml": snapshot},
                    {"terrain_landxml": snapshot}, {"snapshot": snapshot, "terrain_surface": "x"}):
        assert not validate(**options)["ok"]
    snapshot.write_text('{"units":"m","units":"ft"}')
    assert not validate(snapshot=snapshot)["ok"]
    snapshot.write_text('<!DOCTYPE LandXML [<!ENTITY e SYSTEM "file:///absent">]><LandXML>&e;</LandXML>')
    assert not validate(terrain_landxml=snapshot, road_landxml=snapshot)["ok"]


def cli(module, cwd, *args):
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    env["PYTHONPATH"] = os.pathsep.join([
        str(REPO / "civil3d-beamng"), str(REPO / "herramientas-locales/src")])
    return subprocess.run([sys.executable, "-m", module, *args], cwd=cwd, env=env,
        capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)


@pytest.mark.parametrize("module,command", [
    ("cdcrd_beamng", ["validate"]),
    ("cdcrd_local.cli", ["validar-intercambio", "--modulo", "beamng", "--repo", str(REPO)]),
])
def test_native_and_unified_cli_return_json_and_failure_exit_codes(snapshot, module, command):
    result = cli(module, snapshot.parent, *command, "--snapshot", snapshot.name)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["ok"]
    change(snapshot, lambda d: d.update(units="ft"))
    result = cli(module, snapshot.parent, *command, "--snapshot", snapshot.name)
    assert result.returncode == 1, result.stderr
    assert not json.loads(result.stdout)["ok"]
