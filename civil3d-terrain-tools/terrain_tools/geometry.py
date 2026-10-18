"""Piecewise-planar rectangular earthworks; coordinates and slopes are explicit.

No geotechnical or construction suitability is inferred. Corners use intersecting
planes (square offsets), not circular/conical corner grading. Core uses stdlib only.
"""

from dataclasses import dataclass
from math import isfinite
from typing import Sequence

Point = tuple[float, float, float]
Triangle = Sequence[Point]


def area(poly):
    if len(poly) < 3:
        return 0.0
    x, y = poly[0][:2]
    return (
        abs(
            sum(
                (a[0] - x) * (b[1] - y) - (b[0] - x) * (a[1] - y)
                for a, b in zip(poly[1:-1], poly[2:])
            )
        )
        / 2
    )


def clip(poly, function):
    result = []
    if not poly:
        return result
    for a, b in zip(poly, poly[1:] + poly[:1]):
        fa, fb = function(a), function(b)
        if fa >= 0:
            result.append(a)
        if (fa >= 0) != (fb >= 0):
            ratio = fa / (fa - fb)
            result.append(tuple(a[i] + ratio * (b[i] - a[i]) for i in range(3)))
    return result


def split(poly, function):
    """Partition without duplicating a polygon that lies on the split plane."""
    if not poly:
        return [], []
    values = [function(p) for p in poly]
    if max(values) <= 1e-10:
        return [], poly
    if min(values) >= -1e-10:
        return poly, []
    return clip(poly, function), clip(poly, lambda p: -function(p))


@dataclass(frozen=True)
class Platform:
    center_x: float
    center_y: float
    width: float
    length: float
    elevation: float
    horizontal_per_vertical: float
    domain_width: float
    domain_length: float
    mode: str = "cut_fill"

    def validate(self):
        for value in vars(self).values():
            if isinstance(value, (float, int)) and not isfinite(value):
                raise ValueError("All dimensions and coordinates must be finite")
        if min(self.width, self.length, self.horizontal_per_vertical) <= 0:
            raise ValueError("Dimensions and H:V ratio must be positive")
        if self.domain_width <= self.width or self.domain_length <= self.length:
            raise ValueError("Domain must extend beyond the platform")
        if self.mode not in {"cut_only", "fill_only", "cut_fill"}:
            raise ValueError("Unknown earthwork mode")


def prepare_platform(triangles: Sequence[Triangle], spec: Platform):
    """Return a conforming design mesh, separate volumes and affected areas.

    All terrain triangles must represent a non-overlapping, continuous TIN.
    Complete domain coverage and zero earthwork at every domain edge are required.
    The input surface must be independently checked for topology and units.
    """
    spec.validate()
    if not triangles:
        raise ValueError("Empty terrain")
    cx, cy = spec.center_x, spec.center_y
    w, h = spec.width / 2, spec.length / 2
    dw, dh = spec.domain_width / 2, spec.domain_length / 2
    forms = [
        (0.0, 0.0, 0.0),
        (1.0, 0.0, -w),
        (-1.0, 0.0, -w),
        (0.0, 1.0, -h),
        (0.0, -1.0, -h),
    ]
    vertices, faces, vertex_by_xy = [], [], {}
    totals = dict(
        cut_m3=0.0, fill_m3=0.0, cut_area_m2=0.0, fill_area_m2=0.0, domain_area_m2=0.0
    )
    edge_change = 0.0

    def add_polygon(poly, grade, category):
        nonlocal edge_change
        if area(poly) < 1e-10:
            return
        ids = []
        for p in poly:
            z = grade(p)
            if abs(abs(p[0]) - dw) < 1e-7 or abs(abs(p[1]) - dh) < 1e-7:
                edge_change = max(edge_change, abs(z - p[2]))
            xy = (round(p[0], 8), round(p[1], 8))
            if xy in vertex_by_xy:
                idx = vertex_by_xy[xy]
                if abs(vertices[idx][2] - z) > 1e-6:
                    raise ValueError("Discontinuous mesh at shared XY")
            else:
                idx = len(vertices)
                vertices.append([xy[0] + cx, xy[1] + cy, round(z, 9)])
                vertex_by_xy[xy] = idx
            if not ids or idx != ids[-1]:
                ids.append(idx)
        if len(ids) > 1 and ids[0] == ids[-1]:
            ids.pop()
        for i in range(1, len(ids) - 1):
            face = [ids[0], ids[i], ids[i + 1]]
            if area([vertices[j] for j in face]) > 1e-10:
                faces.append(face)
        for i in range(1, len(poly) - 1):
            tri = [poly[0], poly[i], poly[i + 1]]
            a = area(tri)
            totals["domain_area_m2"] += a
            if category != "unchanged":
                delta = sum(p[2] - grade(p) for p in tri) / 3
                totals[category + "_m3"] += a * abs(delta)
                totals[category + "_area_m2"] += a

    for source in triangles:
        if len(source) != 3 or any(
            len(p) != 3 or not all(isfinite(v) for v in p) for p in source
        ):
            raise ValueError("Each input triangle needs three finite XYZ vertices")
        local = [tuple([p[0] - cx, p[1] - cy, p[2]]) for p in source]
        for f in [
            lambda p: p[0] + dw,
            lambda p: dw - p[0],
            lambda p: p[1] + dh,
            lambda p: dh - p[1],
        ]:
            local = clip(local, f)
        for form in forms:
            poly = local
            for other in forms:
                poly = clip(
                    poly,
                    lambda p, a=form, b=other: (a[0] - b[0]) * p[0]
                    + (a[1] - b[1]) * p[1]
                    + a[2]
                    - b[2],
                )
            if area(poly) < 1e-10:
                continue
            distance = lambda p, a=form: a[0] * p[0] + a[1] * p[1] + a[2]
            upper = (
                lambda p: spec.elevation + distance(p) / spec.horizontal_per_vertical
            )
            lower = (
                lambda p: spec.elevation - distance(p) / spec.horizontal_per_vertical
            )
            remainder = poly
            if spec.mode != "fill_only":
                cut, remainder = split(remainder, lambda p: p[2] - upper(p))
                add_polygon(cut, upper, "cut")
            if spec.mode != "cut_only":
                fill, remainder = split(remainder, lambda p: lower(p) - p[2])
                add_polygon(fill, lower, "fill")
            add_polygon(remainder, lambda p: p[2], "unchanged")
    expected = spec.domain_width * spec.domain_length
    if abs(totals["domain_area_m2"] - expected) > max(1e-5, expected * 1e-8):
        raise ValueError("Terrain does not completely and uniquely cover the domain")
    if edge_change > 1e-7:
        raise ValueError(
            "Daylight reaches domain edge: enlarge domain or change parameters"
        )
    totals["net_fill_minus_cut_m3"] = totals["fill_m3"] - totals["cut_m3"]
    totals["max_boundary_change_m"] = edge_change
    return {
        "vertices": vertices,
        "faces": faces,
        "expected": totals,
        "parameters": vars(spec),
    }


def profile_at_x(triangles, x):
    """Intersect TIN edges with a transverse vertical plane x=constant."""
    points = {}
    for tri in triangles:
        for a, b in zip(tri, tri[1:] + tri[:1]):
            if abs(a[0] - x) < 1e-8:
                points[round(a[1], 8)] = a[2]
            if (a[0] - x) * (b[0] - x) < 0:
                f = (x - a[0]) / (b[0] - a[0])
                y = a[1] + f * (b[1] - a[1])
                z = a[2] + f * (b[2] - a[2])
                key = round(y, 8)
                if key in points and abs(points[key] - z) > 1e-6:
                    raise ValueError("Conflicting profile elevations")
                points[key] = z
    return sorted(points.items())


def section_areas(base, design, ymin, ymax):
    """Exact linear-profile integration, splitting every cut/fill crossing."""
    from bisect import bisect_right

    def elevation(profile, y):
        if y < profile[0][0] - 1e-7 or y > profile[-1][0] + 1e-7:
            raise ValueError("Profile coverage gap")
        i = max(0, min(len(profile) - 2, bisect_right([p[0] for p in profile], y) - 1))
        a, b = profile[i : i + 2]
        return a[1] + (y - a[0]) * (b[1] - a[1]) / (b[0] - a[0])

    breaks = sorted({ymin, ymax} | {p[0] for p in base + design if ymin < p[0] < ymax})
    cut = fill = 0.0
    for a, b in zip(breaks, breaks[1:]):
        u = elevation(base, a) - elevation(design, a)
        v = elevation(base, b) - elevation(design, b)
        if u * v < 0:
            ratio = abs(u) / (abs(u) + abs(v))
            pieces = [((b - a) * ratio, u, 0), ((b - a) * (1 - ratio), 0, v)]
        else:
            pieces = [(b - a, u, v)]
        for length, left, right in pieces:
            value = length * (left + right) / 2
            if value >= 0:
                cut += value
            else:
                fill -= value
    return {"cut_m2": cut, "fill_m2": fill}
