"""Installation failure tests using a synthetic package and a tiny fake game archive."""
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

from cdcrd_beamng.package import build_package

_spec = importlib.util.spec_from_file_location("prepare_drive", Path(__file__).with_name("prepare_drive.py"))
prepare_drive = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prepare_drive)


@pytest.fixture
def installed_inputs(tmp_path):
    surface = {"vertices_abs_m": [[0,0,10],[16,0,10],[16,16,10],[0,16,10]],
               "triangles": [[0,1,2],[0,2,3]]}
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps({"schema":"cdcrd.civil3d.snapshot/1", "units":"m",
        "surfaces":{"terrain":surface, "road":surface}}))
    package = tmp_path / "package"
    build_package(snapshot=snapshot, output=package, level_id="a", road_is_drivable=True)
    game = tmp_path / "game"
    (game / "content/levels").mkdir(parents=True)
    with zipfile.ZipFile(game / "content/levels/smallgrid.zip", "w") as archive:
        archive.writestr("levels/smallgrid/main/MissionGroup/Sky/items.level.json",
                         '{"name":"sky","class":"ScatterSky","__parent":"Sky"}\n')
    user = tmp_path / "user"
    return package, user, game


def test_success_and_existing_level_are_preserved(installed_inputs):
    package, user, game = installed_inputs
    level = prepare_drive.prepare(package, user, game)
    before = (level / "info.json").read_bytes()
    with pytest.raises(FileExistsError):
        prepare_drive.prepare(package, user, game)
    assert (level / "info.json").read_bytes() == before
    assert (user / "lua/ge/extensions/editor/cdcrdCivilImport.lua").is_file()


def test_manifest_missing_asset_is_rejected_before_install(installed_inputs):
    package, user, game = installed_inputs
    path = package / "manifest.json"
    data = json.loads(path.read_text())
    data["terrain"]["heightmap"] = "terrain/missing.png"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        prepare_drive.prepare(package, user, game)
    assert not user.exists()


def test_failed_commit_restores_previous_extension(installed_inputs, monkeypatch):
    package, user, game = installed_inputs
    extension = user / "lua/ge/extensions/editor/cdcrdCivilImport.lua"
    extension.parent.mkdir(parents=True)
    extension.write_bytes(b"previous importer")
    original_rename = Path.rename

    def reject_level_commit(self, destination):
        if ".staging-" in self.name:
            raise PermissionError("synthetic level commit failure")
        return original_rename(self, destination)

    monkeypatch.setattr(Path, "rename", reject_level_commit)
    with pytest.raises(PermissionError):
        prepare_drive.prepare(package, user, game)
    assert not (user / "levels/a").exists()
    assert extension.read_bytes() == b"previous importer"
    assert list(extension.parent.glob("*.backup-*"))


def test_failed_commit_removes_only_new_extension(installed_inputs, monkeypatch):
    package, user, game = installed_inputs
    monkeypatch.setattr(Path, "rename", lambda *args: (_ for _ in ()).throw(PermissionError("commit")))
    with pytest.raises(PermissionError):
        prepare_drive.prepare(package, user, game)
    assert not (user / "levels/a").exists()
    assert not (user / "lua/ge/extensions/editor/cdcrdCivilImport.lua").exists()
