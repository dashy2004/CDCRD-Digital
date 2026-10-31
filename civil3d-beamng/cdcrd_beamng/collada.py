"""COLLADA 1.4.1 with documented BeamNG static/collision node names.

Reference: https://documentation.beamng.com/modding/levels/export_dae/
The physical mesh preserves every TIN triangle, including bank and crown.
"""

import xml.etree.ElementTree as ET
from copy import deepcopy
import numpy as np

NS = "http://www.collada.org/2005/11/COLLADASchema"
ET.register_namespace("", NS)


def element(parent, tag, text=None, **attributes):
    node = ET.SubElement(parent, f"{{{NS}}}{tag}", {key: str(value) for key, value in attributes.items()})
    if text is not None:
        node.text = str(text)
    return node


def floats(values):
    return " ".join(format(float(value), ".17g") for value in np.asarray(values).flat)


def source(mesh, identifier, values, parameters):
    node = element(mesh, "source", id=identifier)
    element(node, "float_array", floats(values), id=identifier + "-array", count=values.size)
    common = element(node, "technique_common")
    accessor = element(common, "accessor", source="#" + identifier + "-array",
                       count=len(values), stride=len(parameters))
    for name in parameters:
        element(accessor, "param", name=name, type="float")


def write_road_dae(path, road, origin, asphalt, *, material_names=("road_asphalt", "road_earth"), collision=True):
    root = ET.Element(f"{{{NS}}}COLLADA", version="1.4.1")
    asset = element(root, "asset")
    contributor = element(asset, "contributor")
    element(contributor, "authoring_tool", "CDCRD Civil3D BeamNG 0.1")
    # Fixed metadata keeps identical geometry packages byte-for-byte reproducible.
    element(asset, "created", "2000-01-01T00:00:00Z")
    element(asset, "modified", "2000-01-01T00:00:00Z")
    element(asset, "unit", name="meter", meter=1)
    element(asset, "up_axis", "Z_UP")
    effects = element(root, "library_effects")
    materials = element(root, "library_materials")
    names = []
    if asphalt.any():
        names.append(material_names[0])
    if (~asphalt).any():
        names.append(material_names[1])
    for name in names:
        effect = element(effects, "effect", id=name + "-effect")
        profile = element(effect, "profile_COMMON")
        technique = element(profile, "technique", sid="common")
        lambert = element(technique, "lambert")
        diffuse = element(lambert, "diffuse")
        element(diffuse, "color", "0.12 0.13 0.14 1" if name == "road_asphalt" else "0.38 0.28 0.16 1")
        material = element(materials, "material", id=name, name=name)
        element(material, "instance_effect", url="#" + name + "-effect")
    library = element(root, "library_geometries")
    geometry = element(library, "geometry", id="road-geometry", name="cdx_road_a100")
    mesh = element(geometry, "mesh")
    vertices = road.vertices - origin
    points = vertices[road.triangles]
    normals = np.cross(points[:, 1] - points[:, 0], points[:, 2] - points[:, 0])
    normals /= np.linalg.norm(normals, axis=1)[:, None]
    source(mesh, "road-positions", vertices, ("X", "Y", "Z"))
    source(mesh, "road-normals", normals, ("X", "Y", "Z"))
    source(mesh, "road-uv", vertices[:, :2] / 4.0, ("S", "T"))
    vertex_node = element(mesh, "vertices", id="road-vertices")
    element(vertex_node, "input", semantic="POSITION", source="#road-positions")
    for name in names:
        face_indices = np.flatnonzero(asphalt if name == material_names[0] else ~asphalt)
        triangles = element(mesh, "triangles", count=len(face_indices), material=name)
        element(triangles, "input", semantic="VERTEX", source="#road-vertices", offset=0)
        element(triangles, "input", semantic="NORMAL", source="#road-normals", offset=1)
        element(triangles, "input", semantic="TEXCOORD", source="#road-uv", offset=2, set=0)
        indices = np.empty((len(face_indices), 3, 3), dtype=np.int64)
        indices[:, :, 0] = road.triangles[face_indices]
        indices[:, :, 1] = face_indices[:, None]
        indices[:, :, 2] = road.triangles[face_indices]
        element(triangles, "p", " ".join(map(str, indices.flat)))
    # Some shape importers use geometry names for LOD/collision classification,
    # others use node names. Name both and give collision its own geometry.
    collision_geometry = deepcopy(geometry)
    for node in collision_geometry.iter():
        for key, value in tuple(node.attrib.items()):
            if key in ("id", "source") and (value.startswith("road-") or value.startswith("#road-")):
                node.set(key, value.replace("road-", "collision-", 1))
    collision_geometry.set("name", "Colmesh-1")
    if collision:
        library.append(collision_geometry)
    scenes = element(root, "library_visual_scenes")
    visual = element(scenes, "visual_scene", id="Scene", name="Scene")
    base = element(visual, "node", id="base00", name="base00", type="NODE")
    start = element(base, "node", id="start01", name="start01", type="NODE")
    visible = element(start, "node", id="cdx_road_a100", name="cdx_road_a100", type="NODE")
    instances = [(visible, "road-geometry")]
    if collision:
        collision_group = element(base, "node", id="collision-1", name="collision-1", type="NODE")
        collision_node = element(collision_group, "node", id="Colmesh-1", name="Colmesh-1", type="NODE")
        instances.append((collision_node, "collision-geometry"))
    for parent, geometry_id in instances:
        instance = element(parent, "instance_geometry", url="#" + geometry_id)
        binding = element(instance, "bind_material")
        common = element(binding, "technique_common")
        for name in names:
            material = element(common, "instance_material", symbol=name, target="#" + name)
            element(material, "bind_vertex_input", semantic="UVMap", input_semantic="TEXCOORD", input_set=0)
    scene = element(root, "scene")
    element(scene, "instance_visual_scene", url="#Scene")
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
