"""Consulta textual con procedencia y adaptadores a verificadores existentes."""

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path

from .io import repository

CHECKS = {
    "deriva": "verificacion_deriva.py",
    "escalado_cortante": "verificacion_escalado_cortante_dinamico.py",
    "torsion": "verificacion_irregularidad_torsional.py",
    "irregularidades_verticales": "verificacion_irregularidades_verticales.py",
    "masa_modal": "verificacion_masa_modal.py",
    "zapata": "verificacion_zapata.py",
}


def search(query: str, repo: Path | None = None, limit: int = 5,
           volume: int | None = None) -> dict:
    if not query.strip() or len(query) > 500:
        raise ValueError("La consulta debe tener de 1 a 500 caracteres.")
    if not 1 <= limit <= 50 or (volume is not None and volume not in range(1, 6)):
        raise ValueError("Limite 1..50 y volumen 1..5.")
    root = repository(repo)
    folders = [(1, root / "datos" / "titulos")]
    folders += [(number, root / "datos" / f"vol-{number}") for number in range(2, 6)]
    rows = []
    for number, folder in folders:
        if volume is not None and volume != number:
            continue
        for source in sorted(folder.glob("T*.json")):
            data = json.loads(source.read_text(encoding="utf-8-sig"))
            for occurrence, clause in enumerate(data["clausulas"]):
                rows.append({
                    "id": str(clause["id"]),
                    "volumen": number,
                    "titulo": data["titulo"],
                    "encabezado": clause.get("encabezado", ""),
                    "texto": clause["texto"],
                    "paginas": clause.get("paginas", []),
                    "version_codigo": data.get("version_codigo"),
                    "fuente_pdf": data.get("fuente_pdf"),
                    "source": source.relative_to(root).as_posix(),
                    "ocurrencia": occurrence,
                })
    clean_query = query.strip()
    if re.fullmatch(r"\d+(?:\.\d+)+", clean_query):
        matches = [row for row in rows if row["id"] == clean_query][:limit]
    else:
        terms = re.findall(r"\w+", clean_query, flags=re.UNICODE)
        if not terms or len(terms) > 30:
            raise ValueError("La consulta debe contener entre 1 y 30 terminos.")
        expression = " AND ".join('"' + term.replace('"', '""') + '"' for term in terms)
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE VIRTUAL TABLE corpus USING fts5(id, encabezado, texto)")
            db.executemany("INSERT INTO corpus(rowid,id,encabezado,texto) VALUES (?,?,?,?)",
                           ((index + 1, row["id"], row["encabezado"], row["texto"])
                            for index, row in enumerate(rows)))
            found = db.execute(
                "SELECT rowid FROM corpus WHERE corpus MATCH ? ORDER BY bm25(corpus) LIMIT ?",
                (expression, limit),
            ).fetchall()
            matches = [rows[index - 1] for (index,) in found]
    results = []
    for row in matches:
        entry = dict(row)
        entry["texto"] = row["texto"][:2500]
        entry["texto_truncado"] = len(row["texto"]) > 2500
        results.append(entry)
    return {"query": clean_query, "indexed_clauses": len(rows), "results": results,
            "scope": "Consulta del corpus del repo; no determina el regimen de un expediente."}


def verify(check: str, source: Path, repo: Path | None = None) -> dict:
    if check not in CHECKS:
        raise ValueError(f"Chequeo desconocido. Disponibles: {', '.join(CHECKS)}")
    root = repository(repo)
    source = source.resolve(strict=True)
    data = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("La entrada del verificador debe ser un objeto JSON.")
    script = root / "herramientas" / CHECKS[check]
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    process = subprocess.run([sys.executable, str(script), str(source)], cwd=root,
                             env=env, capture_output=True, text=True, encoding="utf-8",
                             timeout=60, check=False)
    try:
        result = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"El verificador no produjo JSON: {process.stderr[-1000:]}") from exc
    if process.returncode not in (0, 1) or not isinstance(result, dict):
        raise ValueError(f"Error de ejecucion del verificador ({process.returncode}).")
    return {"check": check, "execution_ok": True, "exit_code": process.returncode,
            "script": script.relative_to(root).as_posix(), "result": result,
            "scope": "Alcance y fuentes del verificador existente; no amplifica sus garantias."}
