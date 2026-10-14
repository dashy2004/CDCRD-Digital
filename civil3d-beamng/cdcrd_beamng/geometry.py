"""TIN interpolation and material selection without altering road geometry."""

import math
import numpy as np


def choose_grid(terrain, road, size=None, square_size=1.0, margin=2.0):
    if type(square_size) not in (int, float) or not math.isfinite(square_size) or square_size <= 0:
        raise ValueError("square_size must be positive and finite")
    if type(margin) not in (int, float) or not math.isfinite(margin) or margin < 0:
        raise ValueError("margin must be finite and nonnegative")
    lower = np.minimum(terrain.vertices.min(axis=0), road.vertices.min(axis=0))
    upper = np.maximum(terrain.vertices.max(axis=0), road.vertices.max(axis=0))
    origin = np.floor(lower)
    origin[:2] -= margin
    needed = int(math.ceil(float(np.max((upper[:2] + margin - origin[:2]) / square_size)))) + 1
    if size is None:
        size = max(128, 1 << max(0, needed - 1).bit_length())
    if type(size) is not int or size < 128 or size > 8192 or size & (size - 1):
        raise ValueError("size must be a power of two between 128 and 8192")
    if needed > size:
        raise ValueError(f"Geometry does not fit size {size}; needs at least {needed} samples. "
                         "Increase size or square_size; geometry is never cropped.")
    return origin, size


def raster_tin(surface, origin, size, square_size, coverage_only=False):
    """Row zero is minY internally. Shared edges must interpolate to the same Z.

    Small row strips bound temporary allocations even for a triangle spanning
    the complete grid. Missing data stays NaN and is explicitly cut with holes.
    """
    grid = np.zeros((size, size), dtype=bool) if coverage_only else np.full((size, size), np.nan)
    vertices = surface.vertices - origin
    for face in surface.triangles:
        tri = vertices[face]
        lo = np.maximum(0, np.ceil(tri[:, :2].min(axis=0) / square_size - 1e-9)).astype(int)
        hi = np.minimum(size - 1, np.floor(tri[:, :2].max(axis=0) / square_size + 1e-9)).astype(int)
        if (lo > hi).any():
            continue
        (ax, ay, az), (bx, by, bz), (cx, cy, cz) = tri
        det = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        x = np.arange(lo[0], hi[0] + 1)[None, :] * square_size
        for row in range(lo[1], hi[1] + 1, 128):
            last = min(row + 128, hi[1] + 1)
            y = np.arange(row, last)[:, None] * square_size
            u = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / det
            v = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / det
            inside = (u >= -1e-9) & (v >= -1e-9) & (u + v <= 1 + 1e-9)
            patch = grid[row:last, lo[0]:hi[0] + 1]
            if coverage_only:
                patch |= inside
            else:
                values = u * az + v * bz + (1 - u - v) * cz
                overlaps = inside & np.isfinite(patch)
                if np.any(np.abs(patch[overlaps] - values[overlaps]) > 1e-5):
                    raise ValueError("Terrain has overlapping XY triangles with inconsistent heights")
                patch[inside] = values[inside]
    if not coverage_only and not np.isfinite(grid).any():
        raise ValueError("Terrain has no samples at this grid spacing; reduce square_size")
    return grid


def intersected_cells(surface, origin, size, square_size):
    """Mask cells with positive-area XY intersection with any TIN triangle.

    BeamNG holes remove whole grid cells, so testing only their sample points
    misses triangles between samples. A separating-axis test uses the three
    triangle edges plus the cell's X/Y axes. Boundary-only contact is excluded
    to avoid deleting an extra cell at an exactly grid-aligned road edge.
    Row zero is minY, as in raster_tin; last row/column have no complete cell.
    """
    cells = np.zeros((size, size), dtype=bool)
    vertices = (surface.vertices[:, :2] - origin[:2]) / square_size
    for face in surface.triangles:
        tri = vertices[face]
        lower = np.maximum(0, np.floor(tri.min(axis=0))).astype(int)
        upper = np.minimum(size - 2, np.ceil(tri.max(axis=0)) - 1).astype(int)
        if (lower > upper).any():
            continue
        x = np.arange(lower[0], upper[0] + 1)[None, :]
        for row in range(lower[1], upper[1] + 1, 128):
            last = min(row + 128, upper[1] + 1)
            y = np.arange(row, last)[:, None]
            intersects = np.ones((last - row, x.shape[1]), dtype=bool)
            for start, end in zip(tri, np.roll(tri, -1, axis=0)):
                dx, dy = end - start
                # Maximum left-of-edge cross product among the cell's corners.
                cross_max = dx * (y - start[1]) - dy * (x - start[0])
                cross_max = cross_max + max(0.0, dx) + max(0.0, -dy)
                intersects &= cross_max > 1e-12
            cells[row:last, lower[0]:upper[0] + 1] |= intersects
    return cells


def boundary_intersected_cells(surface, origin, size, square_size):
    """Conservatively cut cells whose open interior contains a TIN boundary.

    Boundary edges belong to one triangle. Segment/slab clipping tests for a
    positive-length segment strictly inside each cell, excluding boundary-only
    tangency. Both external outlines and internal holes are included. Exact
    duplicate vertices are canonicalized for topology only; geometry is intact.
    """
    unique_vertices, remap = np.unique(surface.vertices, axis=0, return_inverse=True)
    triangles = remap[surface.triangles]
    edges = np.concatenate((triangles[:, [0, 1]], triangles[:, [1, 2]], triangles[:, [2, 0]]))
    edges, counts = np.unique(np.sort(edges, axis=1), axis=0, return_counts=True)
    boundary = edges[counts == 1]
    vertices = (unique_vertices[:, :2] - origin[:2]) / square_size
    cells = np.zeros((size, size), dtype=bool)
    for edge in boundary:
        start, end = vertices[edge]
        lower = np.maximum(0, np.floor(np.minimum(start, end))).astype(int)
        upper = np.minimum(size - 2, np.ceil(np.maximum(start, end)) - 1).astype(int)
        if (lower > upper).any():
            continue
        delta = end - start
        x = np.arange(lower[0], upper[0] + 1)[None, :]
        for row in range(lower[1], upper[1] + 1, 128):
            last = min(row + 128, upper[1] + 1)
            y = np.arange(row, last)[:, None]
            shape = (last - row, x.shape[1])
            enter, leave = np.zeros(shape), np.ones(shape)
            intersects = np.ones(shape, dtype=bool)
            for axis, coordinate in enumerate((x, y)):
                if abs(delta[axis]) < 1e-15:
                    intersects &= (start[axis] > coordinate) & (start[axis] < coordinate + 1)
                else:
                    first = (coordinate - start[axis]) / delta[axis]
                    second = (coordinate + 1 - start[axis]) / delta[axis]
                    enter = np.maximum(enter, np.minimum(first, second))
                    leave = np.minimum(leave, np.maximum(first, second))
            intersects &= leave - enter > 1e-12
            cells[row:last, lower[0]:upper[0] + 1] |= intersects
    return cells


def complete_terrain_cells(coverage, boundary_cells, center_coverage):
    """Retain cells known to be entirely inside the source TIN domain.

    Four known corners are insufficient for a small internal hole between
    samples. Boundary edges exclude such cells; center coverage also excludes
    entire holes whose edges coincide with the grid. The final row/column are
    cut rather than fabricating a surface from missing/wrapped samples.
    """
    complete = np.zeros_like(coverage)
    complete[:-1, :-1] = (coverage[:-1, :-1] & coverage[1:, :-1] &
                          coverage[:-1, 1:] & coverage[1:, 1:])
    complete &= ~boundary_cells & center_coverage
    return complete


def classify_road(road, guide=None, road_is_drivable=False):
    """Asphalt classification is advisory; every physical face is retained.

    Centroid membership in an interpolated full-width guide strip avoids
    labelling the entire corridor surface (including cut/fill slopes) asphalt.
    It does not invent Civil 3D corridor codes unavailable in LandXML.
    """
    if guide is None:
        return np.full(len(road.triangles), road_is_drivable, dtype=bool)
    centroids = road.vertices[road.triangles].mean(axis=1)[:, :2]
    asphalt = np.zeros(len(centroids), dtype=bool)
    for start, end in zip(guide[:-1], guide[1:]):
        segment = end[:2] - start[:2]
        parameter = np.clip((centroids - start[:2]) @ segment / (segment @ segment), 0, 1)
        closest = start[:2] + parameter[:, None] * segment
        width = start[3] + parameter * (end[3] - start[3])
        asphalt |= np.sum((centroids - closest) ** 2, axis=1) <= (width / 2) ** 2
    if not asphalt.any():
        raise ValueError("Road guide selects no asphalt triangles; check XY coordinates and full widths")
    return asphalt


def spawn_on_road(road, asphalt, origin, guide=None):
    candidates = np.flatnonzero(asphalt) if asphalt.any() else np.arange(len(road.triangles))
    centers = road.vertices[road.triangles[candidates]].mean(axis=1)
    if guide is not None:
        index = np.argmin(np.sum((centers[:, :2] - guide[0, :2]) ** 2, axis=1))
    else:
        # A large triangle offers a more useful spawn point than a sliver.
        p = road.vertices[road.triangles[candidates]]
        areas = np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
        index = np.argmax(areas)
    spawn = centers[index] - origin
    spawn[2] += 1.0
    return spawn.tolist()
