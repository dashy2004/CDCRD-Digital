"""Install a verified package into a new BeamNG.drive user level."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cdcrd_beamng.package import verify_package


def read_package(package: Path) -> dict:
    data = verify_package(package)
    for name in data["sha256s"]:
        if PurePosixPath(name).suffix.lower() not in (".png", ".dae"):
            raise ValueError("Packages may contain PNG and DAE assets only, never executable scripts")
    return data


def write_lines(path: Path, objects: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in objects), encoding="utf-8")


def prepare(package: Path, user_folder: Path, game_folder: Path, *, auto_import: bool = False) -> Path:
    package = package.resolve()
    data = read_package(package)
    level_id = data["level_id"]
    target = user_folder / "levels" / level_id
    if target.exists():
        raise FileExistsError(f"Destination already exists: {target}; choose a new revision id")
    template = game_folder / "content" / "levels" / "smallgrid.zip"
    source_extension = Path(__file__).resolve().parents[1] / "beamng/lua/ge/extensions/editor/cdcrdCivilImport.lua"
    if not template.is_file() or not source_extension.is_file():
        raise FileNotFoundError("BeamNG.drive template or importer source is missing")
    # Read the template before creating the new destination. No installed game file is modified.
    with zipfile.ZipFile(template) as archive:
        sky = [json.loads(line) for line in archive.read(
            "levels/smallgrid/main/MissionGroup/Sky/items.level.json").decode("utf-8-sig").splitlines() if line.strip()]
    for obj in sky:
        obj["persistentId"] = str(uuid.uuid4())
    staging = target.parent / ("." + level_id + ".staging-" + uuid.uuid4().hex)
    staging.parent.mkdir(parents=True, exist_ok=True)
    destination_extension = user_folder / "lua/ge/extensions/editor/cdcrdCivilImport.lua"
    previous_extension = destination_extension.read_bytes() if destination_extension.is_file() else None
    extension_replaced = False
    try:
        staging.mkdir()
        for name in ["manifest.json", *data["sha256s"]]:
            destination = staging / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(package / name, destination)
        textures = staging / "art/textures"
        textures.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (32, 32), (95, 80, 55)).save(textures / "road_earth.png")
        Image.new("RGB", (32, 32), (69, 72, 76)).save(textures / "road_asphalt.png")
        materials = {}
        for name, ground in [("road_asphalt", "ASPHALT"), ("road_earth", "DIRT")]:
            tint = [.25, .25, .25, 1] if name == "road_asphalt" else [1, 1, 1, 1]
            materials[name] = {"name": name, "mapTo": name, "class": "Material", "version": 1.5,
                "groundType": ground, "doubleSided": True, "Stages": [{"baseColorFactor": tint,
                "baseColorMap": f"/levels/{level_id}/art/textures/{name}.png", "roughnessFactor": 1, "metallicFactor": 0}]}
        for material in data.get("scene_materials", []):
            name = material["name"]
            if not re.fullmatch(r'cdx_scene_[0-9]{3,}|cdx_terrain', name):
                raise ValueError("Invalid scene material name")
            color = material["color"]
            materials[name] = {"name": name, "mapTo": name, "class": "Material", "version": 1.5,
                "groundType": material["ground_type"], "doubleSided": True,
                "Stages": [{"baseColorFactor": color, "roughnessFactor": 1, "metallicFactor": 0}]}
        (staging / "main.materials.json").write_text(json.dumps(materials, indent=2), encoding="utf-8")
        terrain_name = "cdx_" + level_id + "_dirt"
        terrain_material = {terrain_name: {"name": terrain_name, "class": "TerrainMaterial", "internalName": terrain_name,
            "diffuseMap": f"/levels/{level_id}/art/textures/road_earth.png", "diffuseSize": 100,
            "detailMap": f"/levels/{level_id}/art/textures/road_earth.png", "detailSize": 5,
            "groundmodelName": "DIRT"}}
        terrain_material_path = staging / "art/terrains/main.materials.json"
        terrain_material_path.parent.mkdir(parents=True)
        terrain_material_path.write_text(json.dumps(terrain_material, indent=2), encoding="utf-8")
        write_lines(staging / "main/items.level.json", [{"name":"MissionGroup", "class":"SimGroup"}])
        write_lines(staging / "main/MissionGroup/items.level.json", [
            {"name":"Sky", "class":"SimGroup", "__parent":"MissionGroup"},
            {"name":"PlayerDropPoints", "class":"SimGroup", "__parent":"MissionGroup"}])
        write_lines(staging / "main/MissionGroup/Sky/items.level.json", sky)
        write_lines(staging / "main/MissionGroup/PlayerDropPoints/items.level.json", [{
            "name":"spawn_default", "class":"SpawnSphere", "__parent":"PlayerDropPoints",
            "position":data["spawn_local_m"], "dataBlock":"SpawnSphereMarker", "radius":5,
            "autoplaceOnSpawn":"0"}])
        (staging / "info.json").write_text(json.dumps({"title":"Civil 3D - recorrido importado",
            "description":"Terreno y corredor importados mediante CDCRD. Revision independiente.",
            "authors":"CDCRD", "size":[data["terrain"]["size"] * data["terrain"]["square_size"]]*2,
            "defaultSpawnPointName":"spawn_default", "supportsTraffic":False}, indent=2), encoding="utf-8")
        if auto_import:
            (staging / "mainLevel.lua").write_text(
                'local M = {}\nlocal pending = false\nlocal delay = 0\n'
                'local function onClientPostStartMission() pending = true; delay = 0.5 end\n'
                'local function onUpdate(dtReal)\n'
                '  if not pending then return end\n'
                '  delay = delay - (dtReal or 0)\n  if delay > 0 then return end\n'
                '  pending = false\n'
                "  if scenetree.findObject('cdx_civil_import') then return end\n"
                # The engine can keep mainLevel cached across levels. Resolve the
                # active package at runtime instead of importing the previous id.
                "  local root = '/levels/' .. getCurrentLevelIdentifier() .. '/'\n"
                "  if not FS:fileExists(root .. 'manifest.json') then return end\n"
                '  local ok, err = pcall(function()\n'
                "    extensions.load('editor_cdcrdCivilImport')\n"
                "    editor_cdcrdCivilImport.importPackage(root .. 'manifest.json')\n"
                "    local vehicle = be:getPlayerVehicle(0)\n"
                "    local data = jsonReadFile(root .. 'manifest.json')\n"
                "    if vehicle then spawn.safeTeleport(vehicle, vec3(unpack(data.spawn_local_m)), nil, nil, nil, nil, nil, true) end\n"
                '  end)\n'
                "  if not ok then jsonWriteFile(root .. 'import_failure.json', {error=tostring(err)}, true); log('E','CDCRD',tostring(err)) end\n"
                'end\nM.onClientPostStartMission=onClientPostStartMission\nM.onUpdate=onUpdate\nreturn M\n', encoding="utf-8")
        destination_extension.parent.mkdir(parents=True, exist_ok=True)
        if destination_extension.exists() and destination_extension.read_bytes() != source_extension.read_bytes():
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup = destination_extension.with_name(destination_extension.name + ".backup-" + stamp + "-" + uuid.uuid4().hex[:8])
            with backup.open("xb") as stream:
                stream.write(destination_extension.read_bytes())
        temporary_extension = destination_extension.with_name(destination_extension.name + ".staging-" + uuid.uuid4().hex)
        try:
            shutil.copyfile(source_extension, temporary_extension)
            temporary_extension.replace(destination_extension)
            extension_replaced = True
        finally:
            temporary_extension.unlink(missing_ok=True)
        staging.rename(target)
    except Exception:
        if extension_replaced:
            if previous_extension is None:
                destination_extension.unlink(missing_ok=True)
            else:
                restored = destination_extension.with_name(destination_extension.name + ".restore-" + uuid.uuid4().hex)
                restored.write_bytes(previous_extension)
                restored.replace(destination_extension)
        if staging.exists():
            # Only remove the private temporary folder created by this invocation.
            shutil.rmtree(staging)
        raise
    return target


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--user-folder", required=True, type=Path)
    parser.add_argument("--game-folder", required=True, type=Path)
    parser.add_argument("--auto-import", action="store_true", help="One-shot import on a new level; for integration tests")
    args = parser.parse_args()
    print(prepare(args.package, args.user_folder, args.game_folder, auto_import=args.auto_import))


if __name__ == "__main__":
    main()
