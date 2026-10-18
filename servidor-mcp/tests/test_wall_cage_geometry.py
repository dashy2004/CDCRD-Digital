import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from wall_cage_geometry import (
    Bar,
    Point,
    WallPlan,
    audit_bars,
    elevation_spacing,
    native_bars,
)


def bar(x=0, y=50, diameter=16, curved=False):
    return Bar(diameter, (Point(x, y, 0, curved), Point(x, y, 3000, curved)))


def test_straight_cover_and_span_are_exact():
    result = audit_bars((bar(40),), WallPlan((0, 0), (0, 4000), 200), 40)
    assert result["sampled_side_cover_upper_bound_mm"] == 52
    assert result["sampled_end_cover_upper_bound_mm"] == 42
    assert result["exact_straight_span_total_mm"] == 3000
    assert result["cover_status"] == "straight_envelope_satisfies_minimum"
    assert not result["complete_detailing"]


def test_curved_sample_can_disprove_cover_but_cannot_prove_it():
    wall = WallPlan((0, 0), (0, 4000), 200)
    fail = audit_bars((bar(y=38.1, diameter=14, curved=True),), wall, 40)
    assert fail["sampled_end_cover_upper_bound_mm"] == pytest.approx(31.1)
    assert fail["cover_status"] == "fails_at_sampled_point"
    ok_samples = audit_bars((bar(curved=True),), wall, 40)
    assert ok_samples["cover_status"] == "not_proven_between_samples"
    assert ok_samples["exact_straight_span_count"] == 0
    assert not ok_samples["curved_cut_lengths_verified"]


def test_translation_and_rotation_preserve_cover():
    a = audit_bars((bar(40),), WallPlan((0, 0), (0, 4000), 200), 40)
    b = audit_bars(
        (Bar(16, (Point(150, 160, 0), Point(150, 160, 3000))),),
        WallPlan((100, 200), (4100, 200), 200),
        40,
    )
    for key in [
        "sampled_side_cover_upper_bound_mm",
        "sampled_end_cover_upper_bound_mm",
    ]:
        assert a[key] == pytest.approx(b[key])


def test_reversed_path_is_duplicate_but_adjacent_segments_are_not():
    b = bar()
    c = Bar(16, tuple(reversed(b.points)))
    d = Bar(16, (Point(0, 50, 3000), Point(0, 50, 6000)))
    r = audit_bars((b, c, d), WallPlan((0, 0), (0, 4000), 200), 40)
    assert r["duplicate_sample_paths"] == 1
    assert r["bar_count"] == 3  # Never silently deduplicate physical quantities.


def test_crossovers_do_not_become_extra_elevations():
    bars = tuple(
        Bar(12, (Point(0, 100, z), Point(0, 3900, z + 15, True))) for z in [0, 480, 960]
    )
    r = elevation_spacing(bars, 450)
    assert r["maximum_actual_gap_mm"] == 480
    assert r["minimum_rows_for_same_span"] == 4
    assert not r["spacing_passes"]


@pytest.mark.parametrize("value", [float("nan"), float("inf"), True])
def test_nonfinite_and_boolean_coordinates_rejected(value):
    with pytest.raises(ValueError):
        Point(value, 0, 0)


@pytest.mark.parametrize("diameter", [0, -1, float("nan"), float("inf"), True])
def test_invalid_diameters_rejected(diameter):
    with pytest.raises(ValueError):
        bar(diameter=diameter)


def test_negative_cover_means_outside_concrete():
    r = audit_bars((bar(110),), WallPlan((0, 0), (0, 4000), 200), 40)
    assert r["sampled_side_cover_upper_bound_mm"] == -18
    assert r["cover_status"] == "fails_at_sampled_point"


def test_native_parser_ignores_type_and_cached_length():
    p = {
        "$type": "untrusted",
        "\u0024values": [
            {
                "Dia": 16,
                "PLine": {
                    "Length": 999,
                    "Points": {
                        "$values": [
                            {"X": 0, "Y": 50, "Z": 0, "OnArc": False},
                            {"X": 0, "Y": 50, "Z": 3000, "OnArc": False},
                        ]
                    },
                },
            }
        ],
    }
    r = audit_bars(native_bars(p), WallPlan((0, 0), (0, 4000), 200), 40)
    assert r["exact_straight_span_total_mm"] == 3000


@pytest.mark.parametrize(
    "start,end,thickness",
    [((0, 0), (0, 0), 200), ((0, 0), (0, 1), 0), ((0, 0), (math.inf, 0), 200)],
)
def test_invalid_wall_rejected(start, end, thickness):
    with pytest.raises(ValueError):
        WallPlan(start, end, thickness)
