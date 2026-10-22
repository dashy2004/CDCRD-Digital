"""Offline reports over captured observations; HTML contains no executable data."""

import json
import math
import os
from collections import Counter
from hashlib import sha256
from html import escape
from pathlib import Path

from audit_capture import SCHEMA, model_path
from etabs_procedure import prepare_modeling
from modeling_checks import audit_modeling


def json_bytes(value):
    return (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")


def build_report(profile, project, capture):
    """Reuse the existing profile checker; supplement identity/levels/case status.

    SHA-256 links files and detects later edits. It does not authenticate the
    producer or turn imported JSON into evidence of a native run.
    """
    if not isinstance(capture, dict) or capture.get("schema") != SCHEMA:
        raise ValueError("Esquema de captura no admitido")
    # Reject NaN/Infinity anywhere, before interpreting an imported capture.
    digest = sha256(json_bytes(capture)).hexdigest()
    snapshot = capture.get("snapshot")
    source = capture.get("source")
    observations = capture.get("observations")
    if (
        not isinstance(snapshot, dict)
        or not isinstance(source, dict)
        or not isinstance(observations, list)
    ):
        raise TypeError("Captura sin snapshot, source u observations")
    expected = prepare_modeling(profile, project)
    if model_path(source.get("model_path")) != model_path(
        expected["model_path"]
    ) or model_path(snapshot.get("model_path")) != model_path(expected["model_path"]):
        raise ValueError("Proyecto y captura pertenecen a modelos distintos")
    for item in observations:
        if (
            not isinstance(item, dict)
            or item.get("status") not in ("read", "error", "unavailable", "pending")
            or not isinstance(item.get("id"), str)
        ):
            raise ValueError("Observacion invalida")
    if len({x["id"] for x in observations}) != len(observations):
        raise ValueError("Identificadores de evidencia duplicados")
    audit = audit_modeling(profile, project, snapshot)
    findings = list(audit["findings"])
    for obs in observations:
        if obs["status"] != "read":
            findings.append(
                {
                    "code": "read_" + obs["status"],
                    "object": str(obs.get("object", "")),
                    "status": "error" if obs["status"] == "error" else "pending",
                    "message": str(obs.get("message", "Lectura incompleta")),
                    "evidence_ids": [obs["id"]],
                }
            )
    levels = snapshot.get("stories")
    if isinstance(levels, list):
        if any(
            not isinstance(s, dict) or not isinstance(s.get("name"), str)
            for s in levels
        ):
            raise ValueError("Inventario de niveles invalido")
        index = {s["name"]: s for s in levels}
        if len(index) != len(levels):
            raise ValueError("Niveles duplicados")
        for expected_story in expected["stories"]:
            name = expected_story["name"]
            for key in ("elevation_m", "height_m"):
                value = index.get(name, {}).get(key)
                desired = expected_story["model_height_m" if key == "height_m" else key]
                if type(value) not in (int, float) or not math.isfinite(value):
                    findings.append(
                        {
                            "code": "story_missing",
                            "object": name,
                            "status": "pending",
                            "message": f"Falta {key} del nivel",
                        }
                    )
                elif not math.isclose(value, desired, rel_tol=1e-9, abs_tol=1e-6):
                    findings.append(
                        {
                            "code": "story_geometry",
                            "object": name,
                            "status": "difference",
                            "message": key,
                            "expected": desired,
                            "observed": value,
                            "unit": "m",
                        }
                    )
        for name in index.keys() - {s["name"] for s in expected["stories"]}:
            findings.append(
                {
                    "code": "unexpected_story",
                    "object": name,
                    "status": "difference",
                    "message": "Nivel no incluido en el proyecto de referencia",
                }
            )
    else:
        findings.append(
            {
                "code": "stories_missing",
                "object": "stories",
                "status": "pending",
                "message": "Falta inventario de niveles",
            }
        )
    for area in snapshot.get("unclassified_areas", []):
        findings.append(
            {
                "code": "area_unclassified",
                "object": area["id"],
                "status": "pending",
                "message": "Area no clasificada como Floor/Wall; no se excluye de la cobertura",
            }
        )
    cases = snapshot.get("analysis_status")
    if not cases:
        findings.append(
            {
                "code": "analysis_unknown",
                "object": "analysis",
                "status": "pending",
                "message": "No se acreditaron casos analizados",
            }
        )
    else:
        for case in cases:
            if case["status"] != 4:
                findings.append(
                    {
                        "code": "analysis_not_finished",
                        "object": case["name"],
                        "status": "pending",
                        "message": f"Estado CSI {case['status']}; no Finished",
                    }
                )
    for finding in findings:
        if "evidence_ids" not in finding:
            obj = finding["object"]
            exact = [
                o["id"]
                for o in observations
                if o.get("object") == obj or o.get("field") == obj
            ]
            if finding["code"].startswith("story_") or finding["code"] in (
                "unexpected_story",
                "stories_missing",
            ):
                exact = [o["id"] for o in observations if o.get("section") == "stories"]
            if finding["code"] == "missing_pattern":
                exact = [
                    o["id"] for o in observations if o.get("section") == "LoadPatterns"
                ]
            if not exact:
                exact = [
                    o["id"]
                    for o in observations
                    if obj.startswith(str(o.get("object", "")) + ".")
                ]
            finding["evidence_ids"] = exact
    counts = dict(Counter(f["status"] for f in findings))
    return {
        "schema": "cdcrd-etabs-audit-report/1",
        "capture_id": capture.get("capture_id"),
        "capture_sha256": digest,
        "reference_sha256": sha256(
            json_bytes({"profile": profile, "project": project})
        ).hexdigest(),
        "profile": profile,
        "source": source,
        "summary": {
            "findings": len(findings),
            **{k: counts.get(k, 0) for k in ("difference", "pending", "error")},
        },
        "observations": dict(Counter(o["status"] for o in observations)),
        "findings": findings,
        "snapshot": snapshot,
        "inventory": {
            key: len(snapshot[key]) if isinstance(snapshot.get(key), list) else None
            for key in (
                "stories",
                "joints",
                "frames",
                "slabs",
                "walls",
                "materials",
                "patterns",
            )
        },
        "overall": "incomplete"
        if counts.get("pending") or counts.get("error")
        else (
            "differences" if counts.get("difference") else "matches_checked_criteria"
        ),
        "engineering_approval": False,
        "model_modified": False,
        "analysis_executed": False,
        "limitations": [
            "Criterios del perfil seleccionado; no constituyen certificacion normativa integral.",
            "Resultados historicos o JSON importado no autentican una sesion nativa.",
            "Finished informa estado del caso; no demuestra vigencia frente a todas las ediciones.",
            "No se ejecuta analisis, Check Model, guardado ni correccion automatica.",
        ],
    }


def render_html(report, capture):
    def safe(value):
        return escape(str(value), quote=True)

    def table(headers, rows):
        return (
            "<table><thead><tr>"
            + "".join(f"<th scope='col'>{safe(x)}</th>" for x in headers)
            + "</tr></thead><tbody>"
            + "".join(
                "<tr>" + "".join(f"<td>{safe(x)}</td>" for x in row) + "</tr>"
                for row in rows
            )
            + "</tbody></table>"
        )

    summary = report["summary"]
    states = {
        "difference": "Diferencia",
        "pending": "Pendiente",
        "error": "Error",
        "incomplete": "Revisión incompleta",
        "differences": "Con diferencias",
        "matches_checked_criteria": "Coincide en los criterios comprobados",
    }

    def display_message(finding):
        if finding["code"] == "setting":
            return (
                "Falta lectura para comparar"
                if finding["status"] == "pending"
                else "Difiere del perfil"
            )
        return finding["message"]

    finding_rows = [
        [
            states[f["status"]],
            f["object"],
            f["code"],
            display_message(f),
            f.get("expected", "—"),
            "sin lectura" if f.get("observed", "—") is None else f.get("observed", "—"),
            f.get("unit", ""),
            ", ".join(f["evidence_ids"][:8])
            + (
                f" (+{len(f['evidence_ids']) - 8}; ver JSON)"
                if len(f["evidence_ids"]) > 8
                else ""
            ),
        ]
        for f in report["findings"]
    ]
    labels = {
        "stories": "Niveles",
        "joints": "Nudos",
        "frames": "Barras",
        "slabs": "Losas",
        "walls": "Muros",
        "materials": "Materiales",
        "patterns": "Patrones",
    }
    inventory = " · ".join(
        f"{labels[k]}: {v if v is not None else 'sin lectura'}"
        for k, v in report["inventory"].items()
    )
    evidence_rows = [
        [
            o["id"],
            o["status"],
            o.get("object", ""),
            o.get("field", ""),
            o.get("operation", ""),
            json.dumps(o.get("value", o.get("message", "")), ensure_ascii=False),
        ]
        for o in capture["observations"]
    ]
    snapshot = safe(
        json.dumps(report["snapshot"], ensure_ascii=False, indent=2, allow_nan=False)
    )
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'">
<title>Auditor ETABS · {safe(report["capture_id"])}</title>
<style>body{{font:16px/1.5 system-ui,sans-serif;color:#182b36;background:#f4f6f7;margin:0}}
main{{max-width:1160px;margin:auto;padding:32px;overflow-wrap:anywhere}}h1{{font-size:2rem;margin-bottom:8px}}h2{{margin-top:36px}}
.meta{{color:#435c6a}}.cards{{display:flex;gap:16px;flex-wrap:wrap}}.card{{background:white;border-top:4px solid #25758a;padding:16px;min-width:140px}}
.card strong{{display:block;font-size:2rem}}table{{table-layout:fixed;border-collapse:collapse;width:100%;min-width:1050px;background:white;font-size:.9rem}}
th,td{{border:1px solid #cdd7dc;text-align:left;padding:10px;vertical-align:top;overflow-wrap:anywhere}}
th{{background:#e2edf0;white-space:nowrap}}th:first-child,td:first-child{{white-space:nowrap}}.scroll{{overflow:auto}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;background:white;padding:20px}}
details{{margin-top:24px}}summary{{cursor:pointer;padding:12px;background:#e2edf0}}:focus-visible{{outline:3px solid #ab4b00}}
@media print{{main{{padding:0}}table{{font-size:9pt}}.cards{{break-inside:avoid}}}}</style></head>
<body><main><p class="meta">CDCRD · Revisión de modelo · {safe(report["source"].get("kind", "desconocido"))}</p>
<h1>Auditor de ETABS</h1><p>Estado: <strong>{safe(states[report["overall"]])}</strong>. Perfil {safe(report["profile"])}.</p>
<p class="meta">Modelo: {safe(report["source"]["model_path"])}<br>Captura: {safe(report["capture_id"])}<br>
Fecha: {safe(capture.get("finished_at", "desconocida"))}</p>
<div class="cards"><div class="card"><strong>{summary["difference"]}</strong>Diferencias</div>
<div class="card"><strong>{summary["pending"]}</strong>Pendientes</div><div class="card"><strong>{summary["error"]}</strong>Errores de lectura</div></div>
<p>Una lectura completada no equivale a diseño aprobado. Los datos ausentes permanecen pendientes.</p>
<p>{safe(inventory)}</p>
<h2>Hallazgos</h2><div class="scroll" tabindex="0" aria-label="Tabla desplazable">{table(["Estado", "Elemento", "Código", "Observación", "Esperado", "Leído", "Unidad", "Evidencia"], finding_rows)}</div>
<h2>Alcance</h2><ul>{"".join("<li>" + safe(v) + "</li>" for v in report["limitations"])}</ul>
<details><summary>Datos capturados</summary><pre>{snapshot}</pre></details>
<details><summary>Evidencia por lectura</summary><div class="scroll" tabindex="0" aria-label="Tabla desplazable">{table(["ID", "Estado", "Elemento", "Campo", "Operación", "Valor o diagnóstico"], evidence_rows)}</div></details>
<p class="meta">SHA-256 de captura: {safe(report["capture_sha256"])}</p></main></body></html>"""


def write_report(profile, project, capture, output_directory):
    """Create a new bundle, never overwrite. A failed write leaves INCOMPLETE."""
    target = Path(output_directory)
    if not target.is_absolute():
        raise ValueError("output_directory debe ser absoluto")
    report = build_report(profile, project, capture)
    payloads = {
        "proyecto.json": json_bytes({"profile": profile, "project": project}),
        "captura.json": json_bytes(capture),
        "informe.json": json_bytes(report),
        "informe.html": render_html(report, capture).encode("utf-8"),
    }
    target.mkdir(parents=True, exist_ok=False)
    marker = target / "INCOMPLETE"
    marker.write_text(
        "Publicacion del informe en curso; no usar como entrega completa.\n",
        encoding="utf-8",
    )
    hashes = {}
    for name, content in payloads.items():
        with (target / name).open("xb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        hashes[name] = sha256(content).hexdigest()
    receipt = {
        "schema": "cdcrd-etabs-audit-bundle/1",
        "capture_id": capture.get("capture_id"),
        "status": "complete",
        "files": hashes,
        "engineering_approval": False,
    }
    with (target / "manifest.json").open("xb") as handle:
        handle.write(json_bytes(receipt))
        handle.flush()
        os.fsync(handle.fileno())
    marker.unlink()
    return {
        "output_directory": str(target),
        "summary": report["summary"],
        "overall": report["overall"],
        **receipt,
    }
