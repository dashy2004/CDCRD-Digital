"""No passing geometry check may authorize a fabrication schedule."""

import math
import sys
from itertools import pairwise
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from wall_detail_checks import (
    PSI_MPA,
    anchorage_fixture,
    equally_spaced_levels,
    straight_length_mm,
    vertical_uncoated_development,
)


def test_native_rounding_regression():
    levels = equally_spaced_levels(76.2, 2923.8, 450)
    assert len(levels) == 8
    assert levels[0] == 76.2 and levels[-1] == 2923.8
    assert max(b - a for a, b in pairwise(levels)) == pytest.approx(406.8)


@pytest.mark.parametrize("span", [1, 450, 450.000001, 900, 2847.6])
def test_maximum_is_a_bound_not_a_target(span):
    levels = equally_spaced_levels(-800, -800 + span, 450)
    assert max(b - a for a, b in pairwise(levels)) <= 450 + 1e-9
    assert len(levels) == math.ceil(span / 450) + 1


@pytest.mark.parametrize(
    "args",
    [(0, 0, 1), (2, 1, 1), (0, 1, 0), (0, 1, math.nan), (math.inf, 1, 1), (0, 1e12, 1)],
)
def test_invalid_intervals_fail(args):
    with pytest.raises(ValueError):
        equally_spaced_levels(*args)


def test_development_independent_us_unit_reference():
    result = vertical_uncoated_development(
        25.4, 4000 * PSI_MPA, 60000 * PSI_MPA, 63.5, yielding_expected=False
    )
    expected_in = 0.075 * 60000 / math.sqrt(4000) / 2.5
    assert result.required_mm == pytest.approx(expected_in * 25.4)


def test_confinement_cap_and_yielding_factor():
    a = vertical_uncoated_development(
        16, 30, 60000 * PSI_MPA, 40, yielding_expected=True
    )
    b = vertical_uncoated_development(
        16, 30, 60000 * PSI_MPA, 400, yielding_expected=False
    )
    assert a.required_mm == pytest.approx(b.required_mm * 1.25)
    assert a.confinement_ratio == 2.5


def test_minimum_is_not_multiplied_before_comparison():
    r = vertical_uncoated_development(6, 55, 200, 40, yielding_expected=True)
    assert r.minimum_governed_mm == pytest.approx(304.8)
    assert r.required_mm == pytest.approx(381)


@pytest.mark.parametrize(
    "args",
    [
        (0, 30, 400, 40),
        (16, 0, 400, 40),
        (16, 30, 500, 40),
        (16, 60, 400, 40),
        (16, 30, 400, 0),
        (16, 30, math.nan, 40),
    ],
)
def test_unsupported_materials_fail(args):
    with pytest.raises(ValueError):
        vertical_uncoated_development(*args, yielding_expected=True)


def test_curved_cage_cannot_be_labeled_a_straight_cut():
    with pytest.raises(ValueError):
        straight_length_mm(((0, 0, 0), (1, 1, 1)), has_arcs=True)
    with pytest.raises(ValueError):
        straight_length_mm(((0, 0, 0), (1, 1, 1), (2, 2, 2)), has_arcs=False)
    with pytest.raises(ValueError):
        straight_length_mm(((0, 0, 0), (0, 0, 0)), has_arcs=False)


def test_fixture_is_continuous_bounded_and_explicitly_incomplete():
    fixture = anchorage_fixture()
    check = fixture["checks"]
    assert check["bar_count"] == 34
    assert check["total_straight_length_mm"] == pytest.approx(34 * 6760)
    assert check["same_face_spacing_mm"] == 242.5
    assert check["cb_mm"] == 40
    assert check["required_development_mm"] == pytest.approx(545.7596234509224)
    assert check["development_length_pass"] and check["bottom_cover_pass"]
    assert check["laps_in_candidate"] == 0
    assert len({tuple(b["points_mm"][0]) for b in fixture["vertical_bars"]}) == 34
    assert all(
        b["points_mm"][0][2] < 0 < b["points_mm"][1][2]
        for b in fixture["vertical_bars"]
    )
    assert not check["native_captured_bars_extend_below_base"]
    assert fixture["status"] == "candidate_not_applied_to_EDB"
    assert not fixture["complete_detailing"] and not fixture["engineering_approval"]
    assert not fixture["assumptions"]["cover_semantics_match_checked_section"]
