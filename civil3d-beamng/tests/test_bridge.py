"""Public fixtures are synthetic. Tests exercise engineering interchange invariants."""

from copy import deepcopy
import json
from pathlib import Path
import xml.etree.ElementTree as ET

import numpy as np
from PIL import Image
import pytest

from cdcrd_beamng import build_package, verify_package
from cdcrd_beamng.package import file_hash
from cdcrd_beamng.sources import read_landxml, read_snapshot
from cdcrd_beamng.geometry import (boundary_intersected_cells, complete_terrain_cells,
                                  intersected_cells, raster_tin)
from cdcrd_beamng.sources import Surface

NS = {"c": "http://www.collada.org/2005/11/COLLADASchema"}


@pytest.fixture
def synthetic():
    terrain = {"name": "Natural terrain", "vertices_abs_m": [
        [1000.0, 2000.0, 100.0], [1063.0, 2000.0, 112.6],
        [1063.0, 2063.0, 118.9], [1000.0, 2063.0, 106.3]],
        "triangles": [[0, 1, 2], [0, 2, 3]]}
    # Cross-section crown, different shoulder elevations, and 81 stations.
    # 405 vertices deliberately exceed the generic API's former 50-item limit.
    xs = [24.0, 28.0, 31.0, 34.0, 38.0]
    elevations = [99.0, 100.25, 100.5, 100.1, 99.2]
    road = {"name": "Complete corridor TIN", "vertices_abs_m": [], "triangles": []}
    for y in np.linspace(0.0, 60.0, 81):
        road["vertices_abs_m"].extend([[1000 + x, 2000 + float(y), z + float(y) * 0.05]
                                     for x, z in zip(xs, elevations)])
    for station in range(80):
        for column in range(4):
            a, b = station * 5 + column, (station + 1) * 5 + column
            road["triangles"].extend([[a, a + 1, b + 1], [a, b + 1, b]])
    return {"schema": "cdcrd.civil3d.snapshot/1", "units": "m",
            "surfaces": {"terrain": terrain, "road": road},
            "alignment": {"name": "Road guide", "nodes_abs_m": [[1031, 2000, 100.5, 6],
                                                                     [1031, 2060, 103.5, 6]],
                          "station_m": [0, 60]}}


def write_json(path, value):
    path.write_text(json.dumps(value, allow_nan=False), encoding="utf-8")
    return path


def build(tmp_path, data, folder="package", **kwargs):
    snapshot = write_json(tmp_path / "snapshot.json", data)
    return build_package(snapshot=snapshot, output=tmp_path / folder, level_id="synthetic_test",
                         size=128, square_size=0.5, margin=0, **kwargs)


def dae_positions(root, geometry_id):
    geometry = root.find(f".//c:geometry[@id='{geometry_id}']", NS)
    prefix = "collision" if geometry_id.startswith("collision") else "road"
    text = geometry.find(f".//c:source[@id='{prefix}-positions']/c:float_array", NS).text
    return np.fromstring(text, sep=" ").reshape(-1, 3)


def dae_faces(root, geometry_id):
    geometry = root.find(f".//c:geometry[@id='{geometry_id}']", NS)
    result = []
    for triangles in geometry.findall("./c:mesh/c:triangles", NS):
        indices = np.fromstring(triangles.find("c:p", NS).text, sep=" ", dtype=int).reshape(-1, 3, 3)
        assert len(indices) == int(triangles.get("count"))
        result.extend(indices[:, :, 0])
    return np.asarray(result)


def test_metric_position_crown_bank_and_collision_are_preserved(tmp_path, synthetic):
    manifest = build(tmp_path, synthetic)
    root = ET.parse(tmp_path / "package/art/shapes/road.dae").getroot()
    original = np.asarray(synthetic["surfaces"]["road"]["vertices_abs_m"])
    expected = original - manifest["origin_abs_m"]
    for identifier in ("road-geometry", "collision-geometry"):
        assert np.allclose(dae_positions(root, identifier), expected, atol=1e-12, rtol=0)
        faces = dae_faces(root, identifier)
        actual_triangles = {tuple(sorted(face)) for face in faces}
        input_triangles = {tuple(sorted(face)) for face in synthetic["surfaces"]["road"]["triangles"]}
        assert actual_triangles == input_triangles
        assert len(faces) == len(input_triangles)
    assert manifest["counts"]["road_vertices"] == 405
    assert manifest["counts"]["road_triangles"] == 640
    assert root.find("./c:asset/c:up_axis", NS).text == "Z_UP"
    assert root.find("./c:asset/c:unit", NS).get("meter") == "1"
    node = root.find(".//c:node[@name='Colmesh-1']", NS)
    assert node.find("c:instance_geometry", NS).get("url") == "#collision-geometry"
    # Crown and bank must survive independently of terrain raster quantization.
    row = dae_positions(root, "collision-geometry")[:5]
    assert row[2, 2] > row[1, 2] > row[0, 2]
    assert row[1, 2] != row[3, 2]


def test_heightmap_orientation_precision_and_source_holes(tmp_path, synthetic):
    manifest = build(tmp_path, synthetic)
    terrain = manifest["terrain"]
    raw = (tmp_path / "package/terrain/heightmap.png").read_bytes()
    assert raw[24:26] == bytes((16, 0))
    encoded = np.asarray(Image.open(tmp_path / "package" / terrain["heightmap"]))
    x, y = 12.5, 47.0
    row, column = 127 - int(y / 0.5), int(x / 0.5)
    decoded_abs = encoded[row, column] * terrain["max_height"] / 65536 + manifest["origin_abs_m"][2]
    assert abs(decoded_abs - (100 + 0.2 * x + 0.1 * y)) <= terrain["quantization_m"] / 2 + 1e-12
    assert terrain["row0"] == "maxY" and terrain["flip_y"] is False
    coverage = np.asarray(Image.open(tmp_path / "package" / terrain["coverage"]))
    holes = np.asarray(Image.open(tmp_path / "package" / terrain["holemap"]))
    assert coverage[0, 0] == 0 and holes[0, 0] == 255  # Beyond source extent.
    assert coverage[100, 62] == 255 and holes[100, 62] == 255  # Under road cut.
    assert coverage[100, 20] == 255 and holes[100, 20] == 0  # Natural terrain retained.
    dirt = np.asarray(Image.open(tmp_path / "package" / terrain["material_mask"]))
    assert np.all(dirt == 255)


def test_guide_distinguishes_pavement_and_earth_without_removing_slopes(tmp_path, synthetic):
    manifest = build(tmp_path, synthetic)
    materials = {m["name"]: m for m in manifest["meshes"][0]["materials"]}
    assert materials["road_asphalt"]["ground_type"] == "ASPHALT"
    assert materials["road_earth"]["ground_type"] == "DIRT"
    assert materials["road_asphalt"]["triangles"] == 320
    assert materials["road_earth"]["triangles"] == 320
    root = ET.parse(tmp_path / "package/art/shapes/road.dae").getroot()
    for geometry in root.findall(".//c:geometry", NS):
        assert {face.get("material") for face in geometry.findall("./c:mesh/c:triangles", NS)} == set(materials)
    assert manifest["counts"]["road_triangles"] == 640


def test_no_guide_never_paints_entire_corridor_asphalt(tmp_path, synthetic):
    del synthetic["alignment"]
    manifest = build(tmp_path, synthetic)
    assert manifest["counts"]["asphalt_triangles"] == 0
    assert manifest["counts"]["earth_triangles"] == 640
    assert any("No drivable-width guide" in message for message in manifest["warnings"])
    pavement = build(tmp_path, synthetic, folder="pavement", road_is_drivable=True)
    assert pavement["counts"]["asphalt_triangles"] == 640


def write_xml(path, surface):
    root = ET.Element("LandXML", xmlns="http://www.landxml.org/schema/LandXML-1.2")
    ET.SubElement(ET.SubElement(root, "Units"), "Metric", linearUnit="meter")
    s = ET.SubElement(ET.SubElement(root, "Surfaces"), "Surface", name=surface["name"])
    definition = ET.SubElement(s, "Definition", surfType="TIN")
    points = ET.SubElement(definition, "Pnts")
    # Non-consecutive IDs verify that face references are not treated as offsets.
    for index, (east, north, z) in enumerate(surface["vertices_abs_m"]):
        ET.SubElement(points, "P", id=str(100 + index * 7)).text = f"{north:.17g} {east:.17g} {z:.17g}"
    faces = ET.SubElement(definition, "Faces")
    for face in surface["triangles"]:
        ET.SubElement(faces, "F").text = " ".join(str(100 + index * 7) for index in face)
    ET.SubElement(faces, "F", i="1").text = "100 107 114"
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
    return path


def test_landxml_snapshot_equivalence_and_north_east_order(tmp_path, synthetic):
    expected = build(tmp_path, synthetic)
    terrain = write_xml(tmp_path / "terrain.xml", synthetic["surfaces"]["terrain"])
    road = write_xml(tmp_path / "road.xml", synthetic["surfaces"]["road"])
    guide = write_json(tmp_path / "guide.json", synthetic["alignment"])
    actual = build_package(terrain_landxml=terrain, terrain_surface="Natural terrain",
                           road_landxml=road, road_surface="Complete corridor TIN", road_guide=guide,
                           output=tmp_path / "xml-package", level_id="synthetic_test", size=128,
                           square_size=0.5, margin=0)
    assert expected["sha256s"] == actual["sha256s"]
    assert expected["origin_abs_m"] == actual["origin_abs_m"]
    assert expected["counts"] == actual["counts"]
    assert read_landxml(terrain).vertices[0].tolist() == [1000, 2000, 100]


@pytest.mark.parametrize("mutation", ["units", "index", "degenerate", "duplicate", "bool", "invalid-guide"])
def test_invalid_source_has_no_output_or_partial_build(tmp_path, synthetic, mutation):
    if mutation == "units":
        synthetic["units"] = "ft"
    elif mutation == "index":
        synthetic["surfaces"]["road"]["triangles"][0][0] = 9999
    elif mutation == "degenerate":
        synthetic["surfaces"]["terrain"]["triangles"][0] = [0, 0, 1]
    elif mutation == "duplicate":
        synthetic["surfaces"]["terrain"]["triangles"].append([2, 1, 0])
    elif mutation == "bool":
        synthetic["surfaces"]["terrain"]["vertices_abs_m"][0][0] = True
    else:
        synthetic["alignment"]["station_m"] = [60, 0]
    with pytest.raises(ValueError):
        build(tmp_path, synthetic)
    assert not (tmp_path / "package").exists()
    assert not list(tmp_path.glob(".cdcrd-build-*"))


def test_geometric_duplicate_faces_with_distinct_vertex_ids_are_rejected(tmp_path, synthetic):
    terrain = synthetic["surfaces"]["terrain"]
    offset = len(terrain["vertices_abs_m"])
    terrain["vertices_abs_m"].extend(deepcopy(terrain["vertices_abs_m"]))
    # Duplicate coordinates with new IDs and reversed winding must not cancel
    # boundary edges and hide source voids during terrain-cell classification.
    terrain["triangles"].extend([
        [index + offset for index in reversed(face)] for face in terrain["triangles"]
    ])
    with pytest.raises(ValueError, match="contains duplicate triangles"):
        build(tmp_path, synthetic)
    assert not (tmp_path / "package").exists()
    assert not list(tmp_path.glob(".cdcrd-build-*"))


def test_bad_json_constants_duplicate_fields_and_xml_entities_are_rejected(tmp_path):
    for contents in ('{"units":"m","bad":NaN}', '{"units":"m","units":"ft"}',
                     '{"units":"m","bad":1e999}'):
        path = tmp_path / "bad.json"
        path.write_text(contents)
        with pytest.raises(ValueError):
            read_snapshot(path)
    path = tmp_path / "unsafe.xml"
    path.write_text('<!DOCTYPE LandXML [<!ENTITY source SYSTEM "file:///nonexistent">]>'
                    '<LandXML>&source;</LandXML>')
    from defusedxml.common import DefusedXmlException
    with pytest.raises(DefusedXmlException):
        read_landxml(path)


def test_integrity_refuses_corruption_traversal_and_symlinks(tmp_path, synthetic):
    manifest = build(tmp_path, synthetic)
    folder = tmp_path / "package"
    assert verify_package(folder)["counts"] == manifest["counts"]
    path = folder / "art/shapes/road.dae"
    original = path.read_bytes()
    path.write_bytes(original + b"corruption")
    with pytest.raises(ValueError, match="SHA256 mismatch"):
        verify_package(folder)
    path.write_bytes(original)
    edited = deepcopy(manifest)
    edited["terrain"]["heightmap"] = "../external.png"
    external = tmp_path / "external.png"
    external.write_bytes((folder / "terrain/heightmap.png").read_bytes())
    edited["sha256s"]["../external.png"] = file_hash(external)
    edited["sha256_hex_strings"]["../external.png"] = file_hash(external, hex_string=True)
    write_json(folder / "manifest.json", edited)
    with pytest.raises(ValueError, match="Unsafe package path"):
        verify_package(folder)
    write_json(folder / "manifest.json", manifest)
    path.unlink()
    path.symlink_to(external)
    with pytest.raises(ValueError, match="symlinks"):
        verify_package(folder)


def test_binary_safe_digest_checks_bytes_after_nul(tmp_path, synthetic):
    import hashlib
    binary = tmp_path / "binary.dat"
    binary.write_bytes(b"a\x00b\n\xff")
    expected = hashlib.sha256(b"6100620aff").hexdigest()
    assert file_hash(binary, hex_string=True) == expected
    binary.write_bytes(b"a\x00c\n\xff")
    assert file_hash(binary, hex_string=True) != expected
    manifest = build(tmp_path, synthetic)
    manifest["sha256_hex_strings"]["terrain/heightmap.png"] = "0" * 64
    write_json(tmp_path / "package/manifest.json", manifest)
    with pytest.raises(ValueError, match="Hexadecimal-string SHA256 mismatch"):
        verify_package(tmp_path / "package")


def test_existing_output_is_preserved_and_packages_are_reproducible(tmp_path, synthetic):
    first = build(tmp_path, synthetic)
    existing = (tmp_path / "package/manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        build(tmp_path, synthetic)
    assert (tmp_path / "package/manifest.json").read_bytes() == existing
    second = build(tmp_path, synthetic, folder="package-again")
    assert first == second
    assert (tmp_path / "package-again/manifest.json").read_bytes() == existing


def test_cropping_is_refused_and_negative_heights_are_supported(tmp_path, synthetic):
    with pytest.raises(ValueError, match="does not fit"):
        build_package(snapshot=write_json(tmp_path / "source.json", synthetic), output=tmp_path / "bad",
                      level_id="synthetic", size=128, square_size=0.1)
    for surface in synthetic["surfaces"].values():
        for vertex in surface["vertices_abs_m"]:
            vertex[2] -= 150
    for vertex in synthetic["alignment"]["nodes_abs_m"]:
        vertex[2] -= 150
    result = build(tmp_path, synthetic)
    assert result["origin_abs_m"][2] < 0
    assert result["spawn_local_m"][2] > 0


def test_collada_consumer_can_load_both_render_and_collision_geometry(tmp_path, synthetic):
    collada = pytest.importorskip("collada")
    build(tmp_path, synthetic)
    shape = collada.Collada(str(tmp_path / "package/art/shapes/road.dae"))
    assert len(shape.geometries) == 2
    assert len(list(shape.scene.objects("geometry"))) == 2
    assert not shape.errors


def test_road_between_samples_is_detected_by_cell_intersection_and_coarse_build_refused(tmp_path):
    terrain = {"name": "terrain", "vertices_abs_m": [[0, 0, 0], [50, 0, 0], [50, 50, 0], [0, 50, 0]],
               "triangles": [[0, 1, 2], [0, 2, 3]]}
    road = {"name": "road", "vertices_abs_m": [[2, 2, 1], [8, 2, 1], [8, 32, 1], [2, 32, 1]],
            "triangles": [[0, 1, 2], [0, 2, 3]]}
    surface = Surface.from_dict(road, "road")
    origin = np.array([0, 0, 0])
    samples = raster_tin(surface, origin, 128, 10, coverage_only=True)
    cells = intersected_cells(surface, origin, 128, 10)
    assert samples.sum() == 0
    assert cells.sum() == 4
    assert cells[:4, 0].all()
    assert not cells[:, 1:].any()
    snapshot = write_json(tmp_path / "source.json", {"schema": "cdcrd.civil3d.snapshot/1", "units": "m",
                                                    "surfaces": {"terrain": terrain, "road": road}})
    with pytest.raises(ValueError, match="Road has no heightmap samples"):
        build_package(snapshot=snapshot, output=tmp_path / "bad", level_id="coarse", square_size=10, margin=0)
    assert not (tmp_path / "bad").exists()


def test_hole_boundary_intersections_do_not_depend_on_corner_samples():
    # Offset pavement crosses cells along x=1.2 and x=2.8. The cell corners at
    # x=1 and x=3 lie outside the road, but these cells still must be removed.
    road = Surface.from_dict({"name": "offset", "vertices_abs_m": [[1.2, 1, 1], [2.8, 1, 1],
                                                                   [2.8, 4, 1], [1.2, 4, 1]],
                              "triangles": [[0, 1, 2], [0, 2, 3]]}, "road")
    cells = intersected_cells(road, np.zeros(3), 128, 1)
    assert cells[1:4, 1:3].all()
    assert cells.sum() == 6
    # Boundary-only contact at integer y=1 or y=4 must not cut an extra row.
    assert not cells[0].any() and not cells[4].any()


def test_unknown_corner_cells_cannot_collide_with_zero_filled_heights():
    coverage = np.zeros((128, 128), dtype=bool)
    coverage[:4, :4] = True
    cells = complete_terrain_cells(coverage, np.zeros_like(coverage), np.ones_like(coverage))
    assert cells.sum() == 9
    assert cells[:3, :3].all()
    assert not cells[3, :4].any() and not cells[:4, 3].any()
    assert not cells[-1].any() and not cells[:, -1].any()


def test_guide_rejects_underresolved_hole_boundaries(tmp_path, synthetic):
    snapshot = write_json(tmp_path / "source.json", synthetic)
    with pytest.raises(ValueError, match="fewer than four grid intervals"):
        build_package(snapshot=snapshot, output=tmp_path / "bad", level_id="coarse",
                      square_size=2, margin=0)
    assert not (tmp_path / "bad").exists()


def ring_surface(outer, inner_low, inner_high):
    return {"name": "Natural TIN with an internal void", "vertices_abs_m": [
        [0, 0, 10], [outer, 0, 10], [outer, outer, 10], [0, outer, 10],
        [inner_low, inner_low, 10], [inner_high, inner_low, 10],
        [inner_high, inner_high, 10], [inner_low, inner_high, 10]],
        "triangles": [[0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5],
                      [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]]}


@pytest.mark.parametrize("inner_low,inner_high", [(4, 6), (2, 4)])
def test_internal_tin_hole_between_known_corners_cannot_be_fabricated(tmp_path, inner_low, inner_high):
    terrain_dict = ring_surface(20, inner_low, inner_high)
    terrain = Surface.from_dict(terrain_dict, "terrain")
    origin = np.zeros(3)
    coverage = raster_tin(terrain, origin, 128, 10, coverage_only=True)
    boundary = boundary_intersected_cells(terrain, origin, 128, 10)
    center = raster_tin(terrain, np.array([5, 5, 0]), 128, 10, coverage_only=True)
    assert coverage[:2, :2].all()  # Original four-corner strategy misses the void.
    assert boundary[0, 0]
    if inner_low == 2:
        assert center[0, 0]  # Center-only checks also miss this offset void.
    complete = complete_terrain_cells(coverage, boundary, center)
    assert not complete[0, 0]
    road = {"name": "Separate road", "vertices_abs_m": [[10, 10, 11], [20, 10, 11],
                                                           [20, 20, 11], [10, 20, 11]],
            "triangles": [[0, 1, 2], [0, 2, 3]]}
    source = write_json(tmp_path / "ring.json", {"schema": "cdcrd.civil3d.snapshot/1", "units": "m",
                                               "surfaces": {"terrain": terrain_dict, "road": road}})
    manifest = build_package(snapshot=source, output=tmp_path / "ring-package", level_id="ring",
                             size=128, square_size=10, margin=0)
    holes = np.asarray(Image.open(tmp_path / "ring-package" / manifest["terrain"]["holemap"]))
    assert holes[127, 0] == 255
    assert manifest["counts"]["terrain_boundary_cells"] > 0


def test_grid_aligned_complete_internal_void_is_detected_by_cell_center():
    terrain = Surface.from_dict(ring_surface(30, 10, 20), "terrain")
    coverage = raster_tin(terrain, np.zeros(3), 128, 10, coverage_only=True)
    boundary = boundary_intersected_cells(terrain, np.zeros(3), 128, 10)
    center = raster_tin(terrain, np.array([5, 5, 0]), 128, 10, coverage_only=True)
    assert coverage[1:3, 1:3].all()
    assert not boundary[1, 1]  # Four boundary edges lie exactly on cell edges.
    assert not center[1, 1]
    complete = complete_terrain_cells(coverage, boundary, center)
    assert not complete[1, 1]
    assert complete[0, 0]  # Exact external tangency does not remove valid cells.
