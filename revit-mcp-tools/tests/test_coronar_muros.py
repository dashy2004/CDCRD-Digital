"""Offline contracts; native geometry/rollback must also be verified in Revit."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    "caps", Path(__file__).parents[1] / "src/tools/coronar_muros.py"
)
caps = importlib.util.module_from_spec(spec)
spec.loader.exec_module(caps)


def test_slab_underside_does_not_drop_entire_wall_to_deeper_local_beam():
    assert caps.select_top([5.15, 5.2], [4.5372]) == 5.15


def test_beam_underside_used_when_no_slab():
    assert caps.select_top([], [10.5372]) == 10.5372


@pytest.mark.parametrize("values", [[], [float("nan")], [float("inf")]])
def test_missing_or_invalid_structure_rejected(values):
    with pytest.raises(ValueError):
        caps.select_top(values, [])


def test_apply_rejects_new_join_or_new_column_not_in_trial():
    plan = {"expected_column_floor_joins": [[10, 20]], "expected_changed_columns": [10]}
    caps.validate_apply_plan(plan, [[10, 20]], [10])
    with pytest.raises(ValueError, match="Uniones"):
        caps.validate_apply_plan(plan, [[10, 21]], [10])
    with pytest.raises(ValueError, match="Columnas"):
        caps.validate_apply_plan(plan, [[10, 20]], [10, 11])


def test_equivalent_numeric_parameters_tolerate_only_roundoff():
    assert caps.close_values({"length": [1., "Double"]}, {"length": [1.+1e-10, "Double"]})
    assert not caps.close_values({"length": 1.}, {"length": 1.001})
    assert not caps.close_values({"type": 123}, {"type": 124})
    assert not caps.close_values({"mark": "A"}, {"mark": "B"})
    assert not caps.close_values({"offset": 0.}, {"offset": None})


def test_owned_geometry_is_disposed_when_preflight_fails(monkeypatch):
    disposed = []

    class Solid:
        def Dispose(self):
            disposed.append(True)

    def fail(doc, uidoc, db, config, owned):
        owned.append(Solid())
        raise ValueError("preflight")

    monkeypatch.setattr(caps, "_run", fail)
    with pytest.raises(ValueError, match="preflight"):
        caps.run(None, None, None, {})
    assert disposed == [True]


@pytest.mark.parametrize("slope,normals,heights,valid", [
    (0., [-1., 1., 0.], [10., 12., 10.], True),
    (.1, [-1., 1.], [10., 12.], False),
    (0., [-.8, 1.], [10., 12.], False),
    (0., [-1., -1.], [10., 11.], False),
])
def test_beam_reference_requires_horizontal_uniform_underside(slope, normals, heights, valid):
    class Line:
        Direction = SimpleNamespace(Z=slope)

    class Face:
        def __init__(self, normal, height):
            self.FaceNormal = SimpleNamespace(Z=normal)
            self.Origin = SimpleNamespace(Z=height)

    class Solid:
        Volume = 1.
        Faces = [Face(n, h) for n, h in zip(normals, heights)]

    db = SimpleNamespace(Line=Line, PlanarFace=Face, Solid=Solid,
                         GeometryInstance=type("Instance", (), {}),
                         Options=SimpleNamespace, ViewDetailLevel=SimpleNamespace(Fine=1))
    beam = SimpleNamespace(Location=SimpleNamespace(Curve=Line()), get_Geometry=lambda opts: [Solid()])
    if valid:
        assert caps.horizontal_beam_bottom(beam, db) == pytest.approx(3.048)
    else:
        with pytest.raises(ValueError):
            caps.horizontal_beam_bottom(beam, db)
