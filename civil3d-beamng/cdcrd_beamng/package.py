"""Write new interchange packages transactionally and validate file integrity."""

import hashlib
import json
import math
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

import numpy as np
from PIL import Image

from .collada import write_road_dae
from .geometry import (
    boundary_intersected_cells,
    choose_grid,
    classify_road,
    complete_terrain_cells,
    intersected_cells,
    raster_tin,
    spawn_on_road,
)
from .sources import load_sources, read_json
from .scene import write_scene_meshes

SCHEMA = "cdcrd.beamng.package/1"
LEVEL_ID = re.compile(r"^[a-z][a-z0-9_]{0,47}$")


def file_hash(path, *, hex_string=False):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block.hex().encode("ascii") if hex_string else block)
    return digest.hexdigest()


def relative_file(root, value):
    if not isinstance(value, str) or "\\" in value:
        raise ValueError("Package file paths must be relative POSIX paths")
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(part in ("", ".", "..") for part in value.split("/")):
        raise ValueError(f"Unsafe package path: {value}")
    target = root.joinpath(*path.parts)
    current = root
    for part in path.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f"Package symlinks are not allowed: {value}")
    if not target.is_file() or not target.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Missing or outside package file: {value}")
    return target


def verify_package(folder):
    root = Path(folder)
    if root.is_symlink():
        raise ValueError("Package folder must not be a symlink")
    manifest = read_json(relative_file(root, "manifest.json"))
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or manifest.get("units") != "m":
        raise ValueError(f"Expected {SCHEMA}, units m")
    if not isinstance(manifest.get("level_id"), str) or not LEVEL_ID.fullmatch(manifest["level_id"]):
        raise ValueError("Invalid level_id")
    for name in ("origin_abs_m", "spawn_local_m"):
        vector = manifest.get(name)
        if not isinstance(vector, list) or len(vector) != 3 or any(
            type(value) not in (int, float) or not math.isfinite(value) for value in vector
        ):
            raise ValueError(f"Invalid {name}")
    terrain = manifest.get("terrain")
    if not isinstance(terrain, dict):
        raise ValueError("Missing terrain metadata")
    size = terrain.get("size")
    if type(size) is not int or size < 128 or size > 8192 or size & (size - 1):
        raise ValueError("Invalid terrain size")
    for name in ("square_size", "max_height"):
        value = terrain.get(name)
        if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
            raise ValueError(f"Invalid terrain {name}")
    if terrain.get("row0") != "maxY" or terrain.get("flip_y") is not False:
        raise ValueError("Unsupported terrain orientation")
    if terrain.get("height_scale_divisor") != 65536:
        raise ValueError("Unsupported terrain height scale")
    meshes = manifest.get("meshes")
    if not isinstance(meshes, list) or not meshes or any(not isinstance(mesh, dict) for mesh in meshes):
        raise ValueError("Package requires road meshes")
    representation = terrain.get("representation", "heightmap")
    if representation not in ("heightmap", "mesh"):
        raise ValueError("Unknown terrain representation")
    if representation == "mesh" and not any(
            mesh.get("role") == "terrain" and mesh.get("collision_type") == "Collision Mesh"
            for mesh in meshes):
        raise ValueError("Exact terrain requires a physical terrain mesh")
    references = [terrain.get(name) for name in ("heightmap", "holemap", "coverage", "material_mask")]
    references.extend(mesh.get("file") for mesh in meshes)
    if any(not isinstance(ref, str) for ref in references):
        raise ValueError("Manifest file references must be strings")
    hashes = manifest.get("sha256s")
    if not isinstance(hashes, dict) or not hashes or any(ref not in hashes for ref in references):
        raise ValueError("Manifest file references must all have SHA256 hashes")
    hex_hashes = manifest.get("sha256_hex_strings")
    if not isinstance(hex_hashes, dict) or set(hex_hashes) != set(hashes):
        raise ValueError("Manifest requires binary-safe hexadecimal-string hashes for all assets")
    for name, expected in hashes.items():
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError("Invalid SHA256 value")
        if file_hash(relative_file(root, name)) != expected:
            raise ValueError(f"SHA256 mismatch: {name}")
        hex_expected = hex_hashes[name]
        if not isinstance(hex_expected, str) or not re.fullmatch(r"[0-9a-f]{64}", hex_expected):
            raise ValueError("Invalid hexadecimal-string SHA256 value")
        if file_hash(relative_file(root, name), hex_string=True) != hex_expected:
            raise ValueError(f"Hexadecimal-string SHA256 mismatch: {name}")
    actual = {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}
    if actual != set(hashes) | {"manifest.json"}:
        raise ValueError("Package contains files not covered by its manifest")
    for name in ("heightmap", "holemap", "coverage", "material_mask"):
        with Image.open(relative_file(root, terrain[name])) as image:
            if image.size != (size, size):
                raise ValueError(f"Terrain {name} dimensions do not match size")
    # PNG IHDR distinguishes true 16-bit grayscale from a converted 8-bit image.
    with relative_file(root, terrain["heightmap"]).open("rb") as stream:
        header = stream.read(26)
    if header[:8] != b"\x89PNG\r\n\x1a\n" or header[24:26] != bytes((16, 0)):
        raise ValueError("Terrain heightmap must be a 16-bit grayscale PNG")
    return manifest


def _publish_new(staging, destination):
    """Exclusive directory claim; manifest is moved last so consumers fail closed.

    Never replace a pre-existing folder. On failure remove only files moved by
    this build, preserving any unexpected concurrent files in the new folder.
    """
    destination.mkdir()
    moved = []
    try:
        for source in sorted(staging.iterdir(), key=lambda path: path.name == "manifest.json"):
            target = destination / source.name
            source.rename(target)
            moved.append(target)
    except BaseException:
        for target in reversed(moved):
            if target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink(missing_ok=True)
        try:
            destination.rmdir()
        except OSError:
            pass
        raise


def build_package(*, output, level_id, snapshot=None, terrain_landxml=None,
                  terrain_surface=None, road_landxml=None, road_surface=None,
                  road_guide=None, road_is_drivable=False, size=None,
                  square_size=1.0, margin=2.0, scene_visual_layers=(), exact_terrain=False):
    """Build a new package; road coordinates/faces never pass through a raster."""
    if not isinstance(level_id, str) or not LEVEL_ID.fullmatch(level_id):
        raise ValueError("level_id must start with a lowercase letter and contain only a-z, 0-9, _ (max 48)")
    destination = Path(output).absolute()
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"Output already exists; choose a new folder: {destination}")
    sources = load_sources(snapshot=snapshot, terrain_landxml=terrain_landxml,
                           terrain_surface=terrain_surface, road_landxml=road_landxml,
                           road_surface=road_surface, road_guide=road_guide)
    terrain, road, guide = sources.terrain, sources.road, sources.guide
    source_schema = sources.schema
    if road_is_drivable and guide is not None:
        raise ValueError("--road-is-drivable and a road guide are mutually exclusive")
    origin, size = choose_grid(terrain, road, size, square_size, margin)
    if guide is not None and float(guide[:, 3].min()) / square_size < 4:
        limit = float(guide[:, 3].min()) / 4
        raise ValueError(f"Road width has fewer than four grid intervals; reduce square_size to {limit:g} m or less. "
                         "The holemap has insufficient road-boundary resolution at this spacing.")
    asphalt = classify_road(road, guide, road_is_drivable)
    warnings = ["Consumer validation pending: terrain orientation, wheel contact, ground models and level reload."]
    if guide is not None:
        warnings.append("Asphalt/earth boundaries are approximated by triangle-centroid membership in the guide strip; physical TIN is unchanged.")
    elif not road_is_drivable:
        warnings.append("No drivable-width guide provided: the complete road TIN is assigned DIRT. Supply --road-guide, or --road-is-drivable only for a verified pavement-only surface.")
    if int(asphalt.sum()) and int((~asphalt).sum()):
        warnings.append("Dedicated collision geometry retains the complete corridor TIN including earth slopes; this mesh is not simplified.")
    grid = raster_tin(terrain, origin, size, square_size)
    coverage = np.isfinite(grid)
    road_coverage = raster_tin(road, origin, size, square_size, coverage_only=True)
    road_cells = intersected_cells(road, origin, size, square_size)
    if not road_coverage.any():
        raise ValueError("Road has no heightmap samples at this spacing; reduce square_size. "
                         "A road between grid samples would leave an unresolved hole boundary.")
    # Holes outside known terrain prevent fabrication of driveable extrapolation.
    # Holes underneath the complete corridor avoid terrain contact in cut sections.
    terrain_boundary_cells = boundary_intersected_cells(terrain, origin, size, square_size)
    center_origin = origin.copy()
    center_origin[:2] += square_size / 2
    terrain_center_coverage = raster_tin(terrain, center_origin, size, square_size, coverage_only=True)
    terrain_cells = complete_terrain_cells(coverage, terrain_boundary_cells, terrain_center_coverage)
    holes = (~terrain_cells) | road_cells
    if not exact_terrain:
        warnings.append(f"Terrain holes remove complete cells intersecting the road TIN; the hole edge can extend up to "
                        f"{math.sqrt(2) * square_size:.6g} m beyond its mesh. Road/terrain seams require live validation.")
    z_top = float(max(terrain.vertices[:, 2].max(), road.vertices[:, 2].max()) - origin[2])
    max_height = max(1.0, z_top) * 65536 / 65535
    encoded = np.rint(np.where(coverage, grid, 0.0) * 65536 / max_height)
    if encoded.min() < 0 or encoded.max() > 65535:
        raise ValueError("Terrain height is outside the representable range")
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".cdcrd-build-", dir=destination.parent))
    try:
        (staging / "terrain").mkdir()
        (staging / "art" / "shapes").mkdir(parents=True)
        Image.fromarray(encoded[::-1].astype("<u2")).save(staging / "terrain/heightmap.png")
        Image.fromarray(holes[::-1].astype("uint8") * 255).save(staging / "terrain/holemap.png")
        Image.fromarray(coverage[::-1].astype("uint8") * 255).save(staging / "terrain/coverage.png")
        Image.fromarray(np.full((size, size), 255, dtype="uint8")).save(staging / "terrain/dirt.png")
        write_road_dae(staging / "art/shapes/road.dae", road, origin, asphalt)
        materials = []
        for name, ground, count in (("road_asphalt", "ASPHALT", int(asphalt.sum())),
                                   ("road_earth", "DIRT", int((~asphalt).sum()))):
            if count:
                materials.append({"name": name, "ground_type": ground, "triangles": count})
        mesh = {"file": "art/shapes/road.dae", "role": "road", "name": "cdx_road",
                "ground_type": materials[0]["ground_type"] if len(materials) == 1 else "MIXED",
                "materials": materials, "collision": "Colmesh-1", "collision_type": "Collision Mesh"}
        if len(materials) == 1:
            mesh["material"] = materials[0]["name"]
        snapshot_data = read_json(snapshot) if snapshot else {}
        scene_meshes, scene_materials, degenerate = write_scene_meshes(
            staging, snapshot_data.get("scene_meshes", []), origin, scene_visual_layers)
        if exact_terrain:
            # Use only when the source terrain already excludes the pavement:
            # unlike a heightmap, this preserves its exact native boundaries.
            write_road_dae(staging / "art/shapes/terrain.dae", terrain, origin,
                           np.ones(len(terrain.triangles), dtype=bool),
                           material_names=("cdx_terrain", "cdx_terrain_unused"))
            scene_meshes.append({"file": "art/shapes/terrain.dae", "role": "terrain",
                                 "name": "cdx_terrain", "material": "cdx_terrain",
                                 "collision_type": "Collision Mesh"})
            scene_materials.append({"name": "cdx_terrain", "color": [.29, .39, .17, 1],
                                    "ground_type": "DIRT"})
            warnings.append("Exact terrain TIN enabled: source must already exclude the road and sidewalks; check overlap in the consumer.")
        if degenerate:
            warnings.append(f"Scene meshes omitted {degenerate} zero-area triangles; road TIN unchanged.")
        if snapshot_data.get("scene_skipped"):
            warnings.append(f"Native scene export skipped {len(snapshot_data['scene_skipped'])} unsupported entities; see snapshot.")
        manifest = {
            "schema": SCHEMA, "units": "m", "level_id": level_id,
            "origin_abs_m": origin.tolist(),
            "terrain": {"heightmap": "terrain/heightmap.png", "holemap": "terrain/holemap.png",
                        "representation": "mesh" if exact_terrain else "heightmap",
                        "coverage": "terrain/coverage.png", "material_mask": "terrain/dirt.png",
                        "size": size, "square_size": square_size, "max_height": max_height,
                        "row0": "maxY", "flip_y": False, "height_scale_divisor": 65536,
                        "quantization_m": max_height / 65536,
                        "hole_strategy": "unknown-corners-or-center-TIN-boundary-crossing-and-road-TIN-cell-intersection",
                        "hole_boundary_uncertainty_m": math.sqrt(2) * square_size},
            "meshes": [mesh, *scene_meshes], "scene_materials": scene_materials,
            "spawn_local_m": spawn_on_road(road, asphalt, origin, guide),
            "counts": {"terrain_vertices": len(terrain.vertices), "terrain_triangles": len(terrain.triangles),
                       "road_vertices": len(road.vertices), "road_triangles": len(road.triangles),
                       "asphalt_triangles": int(asphalt.sum()), "earth_triangles": int((~asphalt).sum()),
                       "terrain_covered_samples": int(coverage.sum()), "road_covered_samples": int(road_coverage.sum()),
                       "terrain_complete_cells": int(terrain_cells.sum()), "road_intersected_cells": int(road_cells.sum()),
                       "terrain_boundary_cells": int(terrain_boundary_cells.sum()),
                       "hole_samples": int(holes.sum()), "guide_nodes": len(guide) if guide is not None else 0},
            "source": {"schema": source_schema, "terrain_surface": terrain.name, "road_surface": road.name},
            "warnings": warnings,
            "sha256s": {path.relative_to(staging).as_posix(): file_hash(path)
                        for path in sorted(staging.rglob("*")) if path.is_file()},
            # BeamNG's hashStringSHA256 accepts a C string and truncates at NUL.
            # Hash lowercase hexadecimal text in Lua, retaining raw SHA256 above.
            "sha256_hex_strings": {path.relative_to(staging).as_posix(): file_hash(path, hex_string=True)
                        for path in sorted(staging.rglob("*")) if path.is_file()},
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")
        verify_package(staging)
        _publish_new(staging, destination)
        return manifest
    finally:
        shutil.rmtree(staging)
