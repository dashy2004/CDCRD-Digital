"""Localización del corpus del repositorio."""
from pathlib import Path


def repository(path: Path | None = None) -> Path:
    candidate = path or Path(__file__).resolve().parents[3]
    candidate = candidate.resolve()
    if not (candidate / "datos" / "titulos").is_dir():
        raise ValueError("No se encontro el corpus del repo. Indique --repo o CDCRD_REPO_ROOT.")
    return candidate
