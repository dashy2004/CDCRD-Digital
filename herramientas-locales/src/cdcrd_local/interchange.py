"""Adapter to the existing BeamNG package, using this interpreter and no shell."""
import json
import os
import subprocess
import sys
from pathlib import Path

from .io import repository

SOURCE_OPTIONS = ("snapshot", "terrain_landxml", "terrain_surface",
                  "road_landxml", "road_surface", "road_guide")
PATH_OPTIONS = {"snapshot", "terrain_landxml", "road_landxml", "road_guide"}


def validate_beamng(repo: Path | None = None, *, receipt: Path | None = None,
                    evidence: list[Path] | None = None, **sources) -> dict:
    root = repository(repo)
    folder = (root / "civil3d-beamng").resolve()
    if not folder.is_relative_to(root) or not (folder / "cdcrd_beamng/validation.py").is_file():
        raise ValueError("No se encontro el validador Civil3D-BeamNG en el repositorio.")
    command = [sys.executable, "-m", "cdcrd_beamng", "validate"]
    if evidence and receipt is None:
        raise ValueError("--evidencia requiere --recibo.")
    if receipt is not None:
        command.extend(["--receipt", str(receipt.resolve())])
    for path in evidence or []:
        command.extend(["--evidence", str(path.resolve())])
    for option, value in sources.items():
        if option not in SOURCE_OPTIONS:
            raise ValueError(f"Opcion de intercambio desconocida: {option}")
        if value is not None:
            argument = str(Path(value).resolve()) if option in PATH_OPTIONS else str(value)
            command.extend(["--" + option.replace("_", "-"), argument])
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    env.pop("PYTHONPATH", None)
    process = subprocess.run(command, cwd=folder, env=env, capture_output=True,
                             text=True, encoding="utf-8", timeout=60, check=False)
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "El validador BeamNG no produjo JSON; compruebe sus dependencias."
        ) from error
    schema = "cdcrd.operation-receipt/1" if receipt is not None else "cdcrd.interchange-validation/1"
    if (not isinstance(result, dict) or result.get("schema") != schema
            or type(result.get("ok")) is not bool
            or process.returncode != (0 if result["ok"] else 1)):
        raise RuntimeError("Respuesta o codigo de salida inesperado del validador BeamNG.")
    return result
