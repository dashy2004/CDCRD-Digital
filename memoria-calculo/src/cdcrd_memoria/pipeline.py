"""Bounded intake and transactional output package. All source access is read-only."""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from . import __version__
from .compose import prepare
from .contracts import Dossier, coverage
from .sources import OutputPackage, SourceError, inspect_sources, verify_sources

MAX_JSON_BYTES = 8 * 1024 * 1024


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Clave JSON duplicada: {key}")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError(f"Número JSON inválido: {value}")


def load_json(path: Path, expected_sha256: str | None = None) -> dict:
    with path.open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("JSON excede 8 MiB")
    if expected_sha256 is not None and hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise SourceError("JSON cambió desde su inspección")
    value = json.loads(
        raw.decode("utf-8-sig"), object_pairs_hook=_unique_pairs, parse_constant=_invalid_constant
    )
    if not isinstance(value, dict):
        raise ValueError("Se requiere un objeto JSON")  # noqa: TRY004 -- stable intake error API
    return value


def parse_dossier(data: dict) -> Dossier:
    if len(json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8")) > MAX_JSON_BYTES:
        raise ValueError("Expediente excede 8 MiB")
    return Dossier.model_validate(data)


def inspect(dossier: Dossier, base_directory: Path, limits: dict | None = None) -> list[dict]:
    return inspect_sources(
        [s.model_dump() for s in dossier.sources], dossier.source_roots, base_directory, limits
    )


def write_json(path: Path, data: dict) -> None:
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, allow_nan=False)
        stream.write("\n")


def generate(
    dossier: Dossier,
    output_directory: Path,
    base_directory: Path,
    formats: list[str] | None = None,
    input_path: Path | None = None,
) -> dict:
    from .renderers import render_docx, render_html, render_pdf

    selected = ["html", "docx", "pdf"] if formats is None else formats
    if not selected or len(set(selected)) != len(selected) or not set(selected) <= {"html", "docx", "pdf"}:
        raise ValueError("Formatos admitidos: html, docx, pdf; sin duplicados")
    records = inspect(dossier, base_directory)
    roots = [(base_directory / root).resolve(strict=True) for root in dossier.source_roots]
    protected = [Path(r["path"]) for r in records]
    if input_path:
        protected.append(input_path.resolve(strict=True))
    view = prepare(dossier)
    pdf_info = None
    with OutputPackage(output_directory, roots, protected) as package:
        evidence_dir = package.path / "fuentes"
        evidence_dir.mkdir()
        staged = {}
        manifest_sources = []
        for record in records:
            source = Path(record["path"])
            target = evidence_dir / (record["id"] + source.suffix.lower())
            digest = hashlib.sha256()
            size = 0
            with source.open("rb") as incoming, target.open("xb") as outgoing:
                while chunk := incoming.read(1024 * 1024):
                    size += len(chunk)
                    if size > record["size"]:
                        raise SourceError("Fuente aumentó durante la copia")
                    digest.update(chunk)
                    outgoing.write(chunk)
            if size != record["size"] or digest.hexdigest() != record["sha256"]:
                raise SourceError("Fuente cambió durante la copia")
            staged[record["id"]] = target
            manifest_sources.append({k: record[k] for k in ("id", "sha256", "size", "kind", "title")})
            manifest_sources[-1]["package_path"] = target.relative_to(package.path).as_posix()
        annex_paths = {}
        for annex in dossier.annexes:
            source = staged[annex.source_id]
            if source.suffix.lower() != ".pdf":
                raise ValueError("Solo PDF como anexo paginado en esta versión")
            annex_paths[annex.source_id] = source
        # A portable dossier points only at immutable copies within this package.
        portable = dossier.model_dump(by_alias=True)
        portable["source_roots"] = ["fuentes"]
        for source in portable["sources"]:
            source["path"] = staged[source["id"]].relative_to(package.path).as_posix()
        write_json(package.path / "expediente.json", portable)
        write_json(package.path / "presentacion.json", view)
        write_json(package.path / "validacion.json", coverage(dossier))
        if "html" in selected:
            render_html(view, package.path / "memoria.html")
        if "docx" in selected:
            render_docx(view, package.path / "memoria.docx")
        if "pdf" in selected:
            pdf_info = render_pdf(view, package.path / "memoria.pdf", annex_paths)
        verify_sources(records)
        outputs = []
        for path in sorted(package.path.rglob("*")):
            if path.is_file() and path.name != "INCOMPLETE":
                outputs.append(
                    {
                        "path": path.relative_to(package.path).as_posix(),
                        "size": path.stat().st_size,
                        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    }
                )
        manifest = {
            "schema": "cdcrd-design-memory-package/1",
            "generator_version": __version__,
            "created_at": datetime.now(UTC).isoformat(),
            "sources": manifest_sources,
            "sources_unchanged": True,
            "files": outputs,
            "pdf": pdf_info,
            "coverage": coverage(dossier),
            "engineering_approval": False,
        }
        write_json(package.path / "manifest.json", manifest)
        package.complete()
    return {
        "output_directory": str(package.path),
        "files": [o["path"] for o in outputs] + ["manifest.json"],
        "coverage": coverage(dossier),
        "pdf": pdf_info,
        "sources_unchanged": True,
    }
