"""Analytical geometry regressions, independent of native drawing implementations."""

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from wall_cage_checks import (
    compare_bar_layouts,
)
from wall_cage_checks import (
    vertical_to_horizontal_arc_clearance as arc_gap,
)
from wall_cage_checks import (
    vertical_to_segment_clearance as line_gap,
)


def test_eight_mm_cage_overlap_is_not_plan_tangency():
    assert line_gap(
        (42, 500, 0), (42, 500, 3000), 16, (48, 100, 100), (48, 3900, 100), 12
    ) == pytest.approx(-8)
    assert line_gap(
        (34, 500, 0), (34, 500, 3000), 16, (48, 100, 100), (48, 3900, 100), 12
    ) == pytest.approx(0)


def test_finite_bar_end_and_sloping_crossing():
    assert line_gap(
        (0, 0, 0), (0, 0, 10), 2, (-10, 0, 20), (10, 0, 20), 2
    ) == pytest.approx(8)
    assert line_gap(
        (0, 0, 0), (0, 0, 10), 2, (-10, 0, 0), (10, 0, 10), 2
    ) == pytest.approx(-2)


@pytest.mark.parametrize("reversed_ends", [False, True])
def test_parallel_vertical_segment(reversed_ends):
    a, b = (4, 0, 5), (4, 0, 20)
    if reversed_ends:
        a, b = b, a
    assert line_gap((0, 0, 0), (0, 0, 10), 2, a, b, 2) == pytest.approx(2)


@pytest.mark.parametrize("sweep", [90, 135, 270])
@pytest.mark.parametrize("direction", [1, -1])
def test_arc_radial_minimum_and_major_sweep(sweep, direction):
    pts = [
        (
            10 * math.cos(math.radians(t * direction)),
            10 * math.sin(math.radians(t * direction)),
            5,
        )
        for t in [0, sweep / 2, sweep]
    ]
    t = math.radians(sweep * 0.4 * direction)
    q = (12 * math.cos(t), 12 * math.sin(t))
    assert arc_gap((*q, 0), (*q, 10), 2, *pts, 2) == pytest.approx(0, abs=1e-10)


def test_arc_endpoint_is_nearest_when_polar_angle_outside_sweep():
    s = math.sqrt(50)
    assert arc_gap(
        (12, -3, 0), (12, -3, 10), 2, (10, 0, 5), (s, s, 5), (0, 10, 5), 2
    ) == pytest.approx(math.sqrt(13) - 2)


def test_arc_vertical_disjoint_and_translation():
    pts = [(10, 0, 20), (math.sqrt(50), math.sqrt(50), 20), (0, 10, 20)]
    q = (12 / math.sqrt(2), 12 / math.sqrt(2))
    expected = math.sqrt(104) - 2
    assert arc_gap((*q, 0), (*q, 10), 2, *pts, 2) == pytest.approx(expected)
    shift = lambda p: (p[0] + 100000, p[1] - 200000, p[2] + 300)
    assert arc_gap(
        shift((*q, 0)), shift((*q, 10)), 2, *[shift(p) for p in pts], 2
    ) == pytest.approx(expected, abs=1e-8)


@pytest.mark.parametrize(
    "points",
    [
        ((0, 0, 0), (1, 1, 0), (2, 2, 0)),
        ((0, 0, 0), (0, 0, 0), (1, 0, 0)),
        ((1, 0, 0), (0, 1, 1), (-1, 0, 0)),
    ],
)
def test_unknown_or_unstable_arc_is_rejected(points):
    with pytest.raises(ValueError):
        arc_gap((0, 0, 0), (0, 0, 10), 2, *points, 2)


@pytest.mark.parametrize(
    "args",
    [
        ((0, 0, 0), (1, 0, 10), 2, (0, 0, 2), (1, 1, 2), 2),
        ((0, 0, 0), (0, 0, 0), 2, (0, 0, 2), (1, 1, 2), 2),
        ((0, 0, 0), (0, 0, 10), 2, (1, 1, 2), (1, 1, 2), 2),
        ((0, 0, 0), (0, 0, 10), 0, (0, 0, 2), (1, 1, 2), 2),
        ((math.nan, 0, 0), (0, 0, 10), 2, (0, 0, 2), (1, 1, 2), 2),
        ((False, 0, 0), (0, 0, 10), 2, (0, 0, 2), (1, 1, 2), 2),
    ],
)
def test_invalid_straight_inputs_rejected(args):
    with pytest.raises(ValueError):
        line_gap(*args)


def test_layout_order_independence_and_displaced_bar_rejection():
    plan = [(1, 2, 16), (3, 4, 16)]
    assert compare_bar_layouts(plan, list(reversed(plan))).agrees
    result = compare_bar_layouts(plan, [(1, 2, 16), (11, 4, 16)])
    assert (
        result.matched == 1
        and result.missing_plan_indices == (1,)
        and result.unexpected_cage_indices == (1,)
    )
    assert not result.agrees


@pytest.mark.parametrize(
    "plan,cage",
    [
        ([], [(1, 2, 16)]),
        ([(1, 2, 16)], []),
        ([(1, 2, 16), (1, 2, 16)], [(1, 2, 16)]),
        ([(1, 2, 16)], [(1, 2, 16), (1, 2, 16)]),
        ([(1, 2, 0)], [(1, 2, 16)]),
        ([(1, 2, 16)], [(math.inf, 2, 16)]),
    ],
)
def test_invalid_or_ambiguous_layout_rejected(plan, cage):
    with pytest.raises(ValueError):
        compare_bar_layouts(plan, cage)
