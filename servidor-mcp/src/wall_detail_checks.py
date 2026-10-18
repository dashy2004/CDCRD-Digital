"""Bounded geometry checks for synthetic fixtures, not engineering approval.

No COM access, native setters, unit guessing, or conversion of curved cages to BBS.
The development check is deliberately limited to straight, vertical, uncoated,
unbundled Grade-60-or-lower bars in normal-weight concrete. See the fixture README.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from itertools import pairwise

PSI_MPA = 0.006894757293168361
INCH_MM = 25.4


def _positive(name: str, value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive")


def equally_spaced_levels(
    start_mm: float, end_mm: float, maximum_mm: float
) -> list[float]:
    """Include both ends; never use nearest-integer rounding for a maximum gap."""
    _positive("maximum_mm", maximum_mm)
    if not all(math.isfinite(v) for v in (start_mm, end_mm)) or end_mm <= start_mm:
        raise ValueError("Expected finite, increasing endpoints")
    ratio = (end_mm - start_mm) / maximum_mm
    if not math.isfinite(ratio) or ratio > 100_000:
        raise ValueError("Fixture interval budget exceeded")
    count = max(1, math.ceil(ratio))
    levels = [start_mm + (end_mm - start_mm) * i / count for i in range(count)] + [
        end_mm
    ]
    actual = max(b - a for a, b in pairwise(levels))
    if actual > maximum_mm + max(1.0, maximum_mm) * 1e-12:
        raise ValueError("Generated positions exceed the requested maximum")
    if any(b <= a for a, b in pairwise(levels)):
        raise ValueError("Coordinate precision cannot represent distinct levels")
    return levels


def straight_length_mm(points: Sequence[Sequence[float]], *, has_arcs: bool) -> float:
    """Only a two-point straight segment has a supported cut-length geometry."""
    if has_arcs or len(points) != 2 or any(len(p) != 3 for p in points):
        raise ValueError(
            "Curves, bends and multi-point cages need a separate verified contract"
        )
    if not all(math.isfinite(v) for p in points for v in p):
        raise ValueError("Non-finite coordinates")
    length = math.dist(points[0], points[1])
    _positive("straight length", length)
    return length


@dataclass(frozen=True)
class DevelopmentResult:
    calculated_mm: float
    minimum_governed_mm: float
    required_mm: float
    confinement_ratio: float
    yielding_factor: float


def vertical_uncoated_development(
    diameter_mm: float,
    fc_mpa: float,
    fy_mpa: float,
    cb_mm: float,
    *,
    yielding_expected: bool,
) -> DevelopmentResult:
    """ACI 318-19 25.4.2.4a in original US units, converted explicitly to mm.

    Restricted test regime: normal-weight, straight vertical uncoated/unbundled
    bars; Ktr=0, all psi factors=1 (no favorable small-bar reduction), no excess-As
    reduction. Applies 1.25 to the minimum-governed ld when yielding is expected.
    Does not check lap locations, confinement, foundation capacity or bar standards.
    """
    for name, value in (
        ("diameter", diameter_mm),
        ("fc", fc_mpa),
        ("fy", fy_mpa),
        ("cb", cb_mm),
    ):
        _positive(name, value)
    if not isinstance(yielding_expected, bool):
        raise TypeError("Explicit boolean yielding condition required")
    if not (
        6 <= diameter_mm <= 36
        and 17 <= fc_mpa <= 55
        and fy_mpa <= 60000 * PSI_MPA + 1e-8
    ):
        raise ValueError(
            "Outside the tested Grade-60-or-lower, normal-concrete fixture range"
        )
    confinement = min(cb_mm / diameter_mm, 2.5)
    fc_psi, fy_psi, db_in = fc_mpa / PSI_MPA, fy_mpa / PSI_MPA, diameter_mm / INCH_MM
    calculated = (
        (3 / 40) * fy_psi / min(math.sqrt(fc_psi), 100) / confinement * db_in * INCH_MM
    )
    minimum_governed = max(calculated, 12 * INCH_MM)
    factor = 1.25 if yielding_expected else 1.0
    return DevelopmentResult(
        calculated, minimum_governed, factor * minimum_governed, confinement, factor
    )


def anchorage_fixture() -> dict:
    """Documented candidate only: this function never changes an ETABS model."""
    diameter, fc, fy = 16.0, 30.0, 60000 * PSI_MPA
    wall_length, wall_thickness, wall_top = 4000.0, 200.0, 6000.0
    embedment, footing_depth, required_cover = 800.0, 1000.0, 75.0
    # 40 mm to outer 12 mm horizontal bars, then a tangent vertical 16 mm bar.
    # This candidate cover convention is NOT asserted equivalent to ETABS's overwrite.
    vertical_x = wall_thickness / 2 - 40 - 12 - diameter / 2
    ys = equally_spaced_levels(60, wall_length - 60, 250)
    xs = (-vertical_x, vertical_x)
    center_spacing = min(2 * vertical_x, min(b - a for a, b in pairwise(ys)))
    cb = min(wall_thickness / 2 - vertical_x, ys[0], center_spacing / 2)
    development = vertical_uncoated_development(
        diameter, fc, fy, cb, yielding_expected=True
    )
    bars = []
    for face, x in enumerate(xs, 1):
        for index, y in enumerate(ys, 1):
            points = ((x, y, -embedment), (x, y, wall_top - 40))
            bars.append(
                {
                    "mark": f"V{face}-{index:02}",
                    "diameter_mm": diameter,
                    "points_mm": points,
                    "straight_length_mm": straight_length_mm(points, has_arcs=False),
                    "laps": 0,
                    "bends": 0,
                    "status": "synthetic_candidate_not_fabrication_release",
                }
            )
    bottom_cover = footing_depth - embedment
    levels = equally_spaced_levels(76.2, 2923.8, 450)
    return {
        "schema": "cdcrd.synthetic-straight-anchorage.v1",
        "units": "N_mm_C",
        "status": "candidate_not_applied_to_EDB",
        "complete_detailing": False,
        "engineering_approval": False,
        "assumptions": {
            "fc_mpa": fc,
            "fy_mpa": fy,
            "concrete": "normal_weight",
            "steel": "uncoated_unbundled_vertical_straight_Grade60",
            "material_assignment_to_ETABS_design_confirmed": False,
            "yielding_expected": True,
            "ktr_mm": 0,
            "psi_t_e_s_g": [1, 1, 1, 1],
            "footing_bounds_mm": {"x": [-800, 800], "y": [-400, 4400], "z": [-1000, 0]},
            "required_bottom_cover_mm": required_cover,
            "outer_wall_cover_target_mm": 40,
            "cover_semantics_match_checked_section": False,
        },
        "vertical_bars": bars,
        "checks": {
            "bar_count": len(bars),
            "total_straight_length_mm": sum(b["straight_length_mm"] for b in bars),
            "same_face_spacing_mm": ys[1] - ys[0],
            "cross_face_spacing_mm": center_spacing,
            "cb_mm": cb,
            "calculated_ld_mm": development.calculated_mm,
            "minimum_governed_ld_mm": development.minimum_governed_mm,
            "yielding_factor": development.yielding_factor,
            "required_development_mm": development.required_mm,
            "provided_embedment_mm": embedment,
            "development_length_pass": embedment >= development.required_mm,
            "actual_bottom_cover_mm": bottom_cover,
            "bottom_cover_pass": bottom_cover >= required_cover,
            "laps_in_candidate": 0,
            "continuous_through_base": True,
            "native_captured_bars_extend_below_base": False,
        },
        "horizontal_position_regression_only": {
            "captured_diameter_mm": 14,
            "captured_count_per_story": 7,
            "captured_gap_mm": 474.6,
            "declared_maximum_mm": 450,
            "minimum_count_same_range": len(levels),
            "candidate_levels_relative_mm": levels,
            "candidate_gap_mm": levels[1] - levels[0],
            "cuts_verified": False,
            "note": "Position regression only, not a corrected 12 mm cage or complete hoop design.",
        },
        "excluded": [
            "soil_and_foundation_capacity",
            "footing_flexural_and_shear_reinforcement",
            "construction_joint_shear_transfer",
            "wall_section_capacity_with_candidate_bar_positions",
            "horizontal_cuts_bends_hooks_and_confinement",
            "native_detail_persistence",
            "reinforcement_product_compliance_and_construction_tolerances",
        ],
    }
