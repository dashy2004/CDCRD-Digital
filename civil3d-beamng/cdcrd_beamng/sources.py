"""Strict metre-based sources; no source paths are embedded in the package."""

from dataclasses import dataclass
import json
import math
from pathlib import Path

from defusedxml import ElementTree as ET
import numpy as np


def read_json(path):
    def bad_constant(value):
        raise ValueError(f"Non-finite JSON number: {value}")

    def finite_float(value):
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"JSON number exceeds finite range: {value}")
        return number

    def unique_object(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON field: {key}")
            result[key] = value
        return result

    with Path(path).open(encoding="utf-8-sig") as stream:
        return json.load(stream, parse_constant=bad_constant, parse_float=finite_float,
                         object_pairs_hook=unique_object)


def numeric_array(values, columns, label):
    # Reject booleans/strings rather than coercing ambiguous exporter data.
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label} must be a nonempty array")
    if any(not isinstance(row, list) or len(row) != columns for row in values):
        raise ValueError(f"{label} requires {columns} values per row")
    if any(type(value) not in (int, float) for row in values for value in row):
        raise ValueError(f"{label} must contain numbers")
    try:
        array = np.asarray(values, dtype=np.float64)
    except (ValueError, OverflowError) as error:
        raise ValueError(f"{label} contains coordinates outside float64 range") from error
    if not np.isfinite(array).all():
        raise ValueError(f"{label} contains non-finite coordinates")
    return array


@dataclass
class Surface:
    name: str
    vertices: np.ndarray
    triangles: np.ndarray

    @classmethod
    def from_dict(cls, data, role):
        if not isinstance(data, dict):
            raise ValueError(f"Missing {role} surface")
        name = data.get("name", role)
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"{role} surface name must be a nonempty string")
        vertices = numeric_array(data.get("vertices_abs_m"), 3, f"{role} vertices")
        faces = data.get("triangles")
        if not isinstance(faces, list) or not faces:
            raise ValueError(f"{role} requires visible triangles")
        if any(not isinstance(face, list) or len(face) != 3 or
               any(type(index) is not int for index in face) for face in faces):
            raise ValueError(f"{role} triangles require three integer indices")
        if any(index < 0 or index >= len(vertices) for face in faces for index in face):
            raise ValueError(f"{role} triangle index outside vertex array")
        triangles = np.asarray(faces, dtype=np.int64)
        points = vertices[triangles]
        with np.errstate(over="ignore", invalid="ignore"):
            cross = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
        if not np.isfinite(cross).all():
            raise ValueError(f"{role} triangle coordinates overflow numerical precision")
        _, coordinate_ids = np.unique(vertices, axis=0, return_inverse=True)
        canonical = np.sort(coordinate_ids[triangles], axis=1)
        if len(np.unique(canonical, axis=0)) != len(triangles):
            raise ValueError(f"{role} contains duplicate triangles")
        if (np.linalg.norm(cross, axis=1) < 1e-10).any():
            raise ValueError(f"{role} contains a degenerate triangle")
        if (np.abs(cross[:, 2]) < 1e-12).any():
            raise ValueError(f"{role} TIN contains a vertical triangle")
        # Upward winding is necessary for surface normals and physical contact.
        reverse = cross[:, 2] < 0
        triangles[reverse] = triangles[reverse][:, [0, 2, 1]]
        return cls(name, vertices, triangles)


def validate_guide(data):
    if not isinstance(data, dict):
        raise ValueError("Road guide must be an object")
    nodes = numeric_array(data.get("nodes_abs_m"), 4, "Road guide nodes")
    if len(nodes) < 2 or (nodes[:, 3] <= 0).any():
        raise ValueError("Road guide needs two nodes and positive full widths")
    if (np.linalg.norm(np.diff(nodes[:, :2], axis=0), axis=1) < 1e-9).any():
        raise ValueError("Road guide has duplicate consecutive XY nodes")
    stations = data.get("station_m")
    if stations is not None:
        if not isinstance(stations, list) or len(stations) != len(nodes) or any(
            type(value) not in (int, float) for value in stations
        ):
            raise ValueError("Road guide station_m must match node count")
        stations = np.asarray(stations, dtype=np.float64)
        if not np.isfinite(stations).all() or (np.diff(stations) <= 0).any():
            raise ValueError("Road guide stations must be finite and increasing")
    return nodes


def read_snapshot(path):
    data = read_json(path)
    if not isinstance(data, dict) or data.get("schema") != "cdcrd.civil3d.snapshot/1":
        raise ValueError("Expected schema cdcrd.civil3d.snapshot/1")
    if data.get("units") != "m":
        raise ValueError("Snapshot must explicitly declare units: m")
    surfaces = data.get("surfaces")
    if not isinstance(surfaces, dict):
        raise ValueError("Snapshot requires surfaces terrain and road")
    terrain = Surface.from_dict(surfaces.get("terrain"), "terrain")
    road = Surface.from_dict(surfaces.get("road"), "road")
    alignment = data.get("alignment")
    guide = validate_guide(alignment) if alignment is not None else None
    return terrain, road, guide


def local_tag(element):
    return element.tag.rsplit("}", 1)[-1]


def children(element, tag):
    return [child for child in element if local_tag(child) == tag]


def read_landxml(path, surface_name=None):
    root = ET.parse(path).getroot()
    metric = [element for element in root.iter() if local_tag(element) == "Metric"]
    if len(metric) != 1 or metric[0].get("linearUnit") != "meter":
        raise ValueError("LandXML must explicitly declare Metric linearUnit=meter")
    surfaces = [element for element in root.iter() if local_tag(element) == "Surface"]
    matches = [s for s in surfaces if surface_name is None or s.get("name") == surface_name]
    if len(matches) != 1:
        names = ", ".join(s.get("name", "") for s in surfaces)
        raise ValueError(f"Select one LandXML surface by exact name; available: {names}")
    surface = matches[0]
    definitions = children(surface, "Definition")
    if len(definitions) != 1 or definitions[0].get("surfType") != "TIN":
        raise ValueError("LandXML surface requires Definition surfType=TIN")
    definition = definitions[0]
    point_sets, face_sets = children(definition, "Pnts"), children(definition, "Faces")
    if len(point_sets) != 1 or len(face_sets) != 1:
        raise ValueError("LandXML TIN requires one Pnts and one Faces collection")
    indices, vertices = {}, []
    for point in children(point_sets[0], "P"):
        identifier = point.get("id")
        if not identifier or identifier in indices:
            raise ValueError("LandXML point IDs must be unique and nonempty")
        values = (point.text or "").split()
        if len(values) != 3:
            raise ValueError("LandXML points require Northing Easting Elevation")
        north, east, z = map(float, values)
        indices[identifier] = len(vertices)
        vertices.append([east, north, z])
    faces = []
    for face in children(face_sets[0], "F"):
        invisible = face.get("i", "0")
        if invisible not in ("0", "1"):
            raise ValueError("Unsupported LandXML triangle visibility flag")
        if invisible == "1":
            continue
        references = (face.text or "").split()
        if len(references) != 3 or any(identifier not in indices for identifier in references):
            raise ValueError("LandXML face has invalid point references")
        faces.append([indices[identifier] for identifier in references])
    return Surface.from_dict({"name": surface.get("name", "surface"),
                              "vertices_abs_m": vertices, "triangles": faces}, "LandXML")
