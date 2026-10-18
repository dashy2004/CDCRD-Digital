"""Pure millimetre geometry checks; curved samples never prove exact cut lengths.

No CAD access, native deserialization, material assumptions or fabrication approval.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from itertools import pairwise
from typing import Any


@dataclass(frozen=True)
class Point:
    x: float
    y: float
    z: float
    on_arc: bool = False

    def __post_init__(self) -> None:
        if any(
            isinstance(v, bool) or not math.isfinite(v)
            for v in (self.x, self.y, self.z)
        ):
            raise ValueError("Coordinates must be finite millimetres")
        if not isinstance(self.on_arc, bool):
            raise TypeError("Arc flag must be boolean")


@dataclass(frozen=True)
class Bar:
    diameter_mm: float
    points: tuple[Point, ...]
    additional_bends: bool = False

    def __post_init__(self) -> None:
        if (
            isinstance(self.diameter_mm, bool)
            or not math.isfinite(self.diameter_mm)
            or self.diameter_mm <= 0
        ):
            raise ValueError("Diameter must be positive finite millimetres")
        if len(self.points) < 2:
            raise ValueError("At least two centreline samples required")


@dataclass(frozen=True)
class WallPlan:
    """Centred wall thickness and finite start/end faces, in global XY millimetres."""

    start: tuple[float, float]
    end: tuple[float, float]
    thickness_mm: float

    def __post_init__(self) -> None:
        values = (*self.start, *self.end, self.thickness_mm)
        if any(isinstance(v, bool) or not math.isfinite(v) for v in values):
            raise ValueError("Wall coordinates must be finite")
        if (
            self.thickness_mm <= 0
            or not math.isfinite(math.dist(self.start, self.end))
            or math.dist(self.start, self.end) <= 0
        ):
            raise ValueError("Wall length and thickness must be positive")

    def covers_at(self, point: Point, diameter_mm: float) -> tuple[float, float]:
        dx, dy = self.end[0] - self.start[0], self.end[1] - self.start[1]
        length = math.hypot(dx, dy)
        px, py = point.x - self.start[0], point.y - self.start[1]
        along = (px * dx + py * dy) / length
        across = (px * -dy + py * dx) / length
        radius = diameter_mm / 2
        return self.thickness_mm / 2 - abs(across) - radius, min(
            along, length - along
        ) - radius


def native_bars(payload: dict[str, Any]) -> tuple[Bar, ...]:
    """Read only whitelisted numeric fields; ignore all native $type metadata."""
    result = []
    records = payload.get("$values")
    if not isinstance(records, list) or not records or len(records) > 10000:
        raise ValueError("Expected a nonempty, bounded native bar array")
    for record in records:
        points = record["PLine"]["Points"]["$values"]
        if not isinstance(points, list) or len(points) > 10000:
            raise ValueError("Invalid point sample array")
        result.append(
            Bar(
                record["Dia"],
                tuple(Point(p["X"], p["Y"], p["Z"], p["OnArc"]) for p in points),
                additional_bends=record.get("StartCode") != "None"
                or record.get("EndCode") != "None",
            )
        )
    return tuple(result)


def audit_bars(
    bars: tuple[Bar, ...], wall: WallPlan, required_cover_mm: float
) -> dict[str, Any]:
    if not bars or not math.isfinite(required_cover_mm) or required_cover_mm < 0:
        raise ValueError("Bars and a finite nonnegative required cover are necessary")
    side = math.inf
    end = math.inf
    straight_total = 0.0
    straight_count = 0
    keys: set[tuple[object, ...]] = set()
    duplicates = 0
    for bar in bars:
        samples = [wall.covers_at(p, bar.diameter_mm) for p in bar.points]
        side = min(side, *(c[0] for c in samples))
        end = min(end, *(c[1] for c in samples))
        # Only exactly represented two-point straight bars have an exact span here.
        if len(bar.points) == 2 and not any(p.on_arc for p in bar.points):
            p, q = bar.points
            straight_total += math.dist((p.x, p.y, p.z), (q.x, q.y, q.z))
            straight_count += 1
        coordinates = tuple((p.x, p.y, p.z, p.on_arc) for p in bar.points)
        key = (bar.diameter_mm, min(coordinates, coordinates[::-1]))
        duplicates += key in keys
        keys.add(key)
    exact = straight_count == len(bars) and not any(b.additional_bends for b in bars)
    failed_sample = min(side, end) < required_cover_mm - 1e-6
    return {
        "bar_count": len(bars),
        "diameters_mm": dict(Counter(bar.diameter_mm for bar in bars)),
        "sampled_side_cover_upper_bound_mm": side,
        "sampled_end_cover_upper_bound_mm": end,
        "required_cover_mm": required_cover_mm,
        "cover_status": "fails_at_sampled_point"
        if failed_sample
        else (
            "straight_envelope_satisfies_minimum"
            if exact
            else "not_proven_between_samples"
        ),
        "exact_straight_span_count": straight_count,
        "exact_straight_span_total_mm": straight_total,
        "curved_cut_lengths_verified": False,
        "duplicate_sample_paths": duplicates,
        "lowest_sample_z_mm": min(p.z for bar in bars for p in bar.points),
        "complete_detailing": False,
        "engineering_approval": False,
    }


def elevation_spacing(bars: tuple[Bar, ...], maximum_mm: float) -> dict[str, Any]:
    """Compare base elevations of shapes; do not confuse local crossover Z with rows."""
    if len(bars) < 2 or not math.isfinite(maximum_mm) or maximum_mm <= 0:
        raise ValueError("At least two shapes and a finite positive limit required")
    elevations = sorted(min(p.z for p in bar.points) for bar in bars)
    gaps = [b - a for a, b in pairwise(elevations)]
    span = elevations[-1] - elevations[0]
    return {
        "base_elevations_mm": elevations,
        "maximum_actual_gap_mm": max(gaps),
        "maximum_allowed_gap_mm": maximum_mm,
        "spacing_passes": max(gaps) <= maximum_mm + 1e-6,
        "minimum_rows_for_same_span": math.ceil(span / maximum_mm) + 1,
        "duplicate_base_elevations": sum(gap <= 1e-6 for gap in gaps),
        "cut_length_verified": False,
    }
