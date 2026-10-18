"""Geometric rejection checks for bounded synthetic wall cages, in millimetres.

A nonnegative surface clearance is geometric separation only. It does not prove
code spacing, anchorage, fabrication suitability, capacity or native persistence.
No CSI dependency, model access, unit conversion or inferred curve topology.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

Point = Sequence[float]


def _point(value: Point) -> tuple[float, float, float]:
    if len(value) != 3 or any(
        isinstance(x, bool) or not math.isfinite(x) or abs(x) > 1e7 for x in value
    ):
        raise ValueError("Expected three finite coordinates within the fixture budget")
    return value[0], value[1], value[2]


def _positive(value: float) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or not 0 < value <= 1e4:
        raise ValueError("Expected a finite positive fixture dimension")


def _vertical(start: Point, end: Point) -> tuple[float, float, float, float]:
    a, b = _point(start), _point(end)
    if math.dist(a[:2], b[:2]) > 1e-6 or abs(a[2] - b[2]) <= 1e-6:
        raise ValueError("Expected a nonzero vertical bar axis")
    return a[0], a[1], min(a[2], b[2]), max(a[2], b[2])


def vertical_to_segment_clearance(
    vertical_start: Point,
    vertical_end: Point,
    vertical_diameter: float,
    segment_start: Point,
    segment_end: Point,
    segment_diameter: float,
) -> float:
    """Signed surface gap of a finite vertical axis and a finite straight axis.

    Negative means overlap of the radius envelopes. Bent transitions and end-face
    geometry require their own representation. Do not pass an arc as its chord.
    """
    x, y, lo, hi = _vertical(vertical_start, vertical_end)
    a, b = _point(segment_start), _point(segment_end)
    _positive(vertical_diameter)
    _positive(segment_diameter)
    u = tuple(q - p for p, q in zip(a, b))
    squared = sum(t * t for t in u)
    if squared <= 1e-12:
        raise ValueError("Zero-length straight axis")
    candidates = [0.0, 1.0]
    xy_squared = u[0] ** 2 + u[1] ** 2
    if xy_squared > 0:
        candidates.append(((x - a[0]) * u[0] + (y - a[1]) * u[1]) / xy_squared)
    for z in (lo, hi):
        candidates.append(
            sum((p - q) * v for p, q, v in zip((x, y, z), a, u)) / squared
        )
        if u[2] != 0:
            candidates.append((z - a[2]) / u[2])
    distances = []
    for t in candidates:
        t = min(1.0, max(0.0, t))
        q = tuple(p + t * v for p, v in zip(a, u))
        closest = (x, y, min(hi, max(lo, q[2])))
        distances.append(math.dist(closest, q))
    return min(distances) - (vertical_diameter + segment_diameter) / 2


def vertical_to_horizontal_arc_clearance(
    vertical_start: Point,
    vertical_end: Point,
    vertical_diameter: float,
    arc_start: Point,
    arc_middle: Point,
    arc_end: Point,
    arc_diameter: float,
) -> float:
    """Signed gap to the circular arc through three ordered horizontal points.

    The middle point selects the minor or major sweep. Reject nonhorizontal or
    nearly collinear triples; sampled polylines do not establish this contract.
    """
    x, y, lo, hi = _vertical(vertical_start, vertical_end)
    a, b, c = (_point(p) for p in (arc_start, arc_middle, arc_end))
    _positive(vertical_diameter)
    _positive(arc_diameter)
    if max(a[2], b[2], c[2]) - min(a[2], b[2], c[2]) > 1e-6:
        raise ValueError("Only horizontal circular arcs are supported")
    ux, uy, vx, vy = b[0] - a[0], b[1] - a[1], c[0] - a[0], c[1] - a[1]
    u2, v2 = ux * ux + uy * uy, vx * vx + vy * vy
    cross = ux * vy - uy * vx
    if min(u2, v2) <= 1e-12 or abs(cross) <= 1e-10 * math.sqrt(u2 * v2):
        raise ValueError("Degenerate or numerically unstable circular arc")
    ox = a[0] + (u2 * vy - v2 * uy) / (2 * cross)
    oy = a[1] + (ux * v2 - vx * u2) / (2 * cross)
    radius = math.hypot(a[0] - ox, a[1] - oy)
    if not math.isfinite(radius) or radius > 1e7:
        raise ValueError("Arc exceeds fixture radius budget")
    origin = math.atan2(a[1] - oy, a[0] - ox)
    direction = 1 if cross > 0 else -1

    def angle(px: float, py: float) -> float:
        return (direction * (math.atan2(py - oy, px - ox) - origin)) % math.tau

    middle, end, query = angle(b[0], b[1]), angle(c[0], c[1]), angle(x, y)
    if not 0 < middle < end < math.tau:
        raise ValueError("Cannot resolve circular sweep")
    planar = (
        abs(math.hypot(x - ox, y - oy) - radius)
        if query <= end
        else min(math.hypot(x - a[0], y - a[1]), math.hypot(x - c[0], y - c[1]))
    )
    dz = a[2] - min(hi, max(lo, a[2]))
    return math.hypot(planar, dz) - (vertical_diameter + arc_diameter) / 2


@dataclass(frozen=True)
class LayoutComparison:
    matched: int
    missing_plan_indices: tuple[int, ...]
    unexpected_cage_indices: tuple[int, ...]

    @property
    def agrees(self) -> bool:
        return not self.missing_plan_indices and not self.unexpected_cage_indices


def compare_bar_layouts(
    plan: Sequence[Point], cage: Sequence[Point], *, tolerance_mm: float = 1e-5
) -> LayoutComparison:
    """Match (x, y, diameter) triples irrespective of ordering; reject ambiguity."""
    _positive(tolerance_mm)
    if not 0 < len(plan) <= 512 or not 0 < len(cage) <= 512:
        raise ValueError("Expected nonempty bounded bar inventories")
    left, right = [_point(p) for p in plan], [_point(p) for p in cage]
    for p in left + right:
        _positive(p[2])
    pairs = [
        (i, j)
        for i, a in enumerate(left)
        for j, b in enumerate(right)
        if math.dist(a[:2], b[:2]) <= tolerance_mm and abs(a[2] - b[2]) <= tolerance_mm
    ]
    matched_left, matched_right = {i for i, _ in pairs}, {j for _, j in pairs}
    if len(matched_left) != len(pairs) or len(matched_right) != len(pairs):
        raise ValueError("Duplicate or ambiguous bar correspondence")
    return LayoutComparison(
        len(pairs),
        tuple(i for i in range(len(left)) if i not in matched_left),
        tuple(j for j in range(len(right)) if j not in matched_right),
    )
