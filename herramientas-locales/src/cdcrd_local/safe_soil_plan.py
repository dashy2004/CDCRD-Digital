"""Offline Civil TIN + independent geotechnical input -> bounded SAFE write plan."""
import json
import ntpath
import re
from pathlib import Path

from .foundation_exchange import digest, review


def prepare_soil_plan(context, query, samples, geotechnical, config):
    body = dict(context)
    checksum = body.pop("context_sha256", None)
    if context.get("schema") != "cdcrd.safe-soil-context/1" or checksum != digest(body):
        raise ValueError("Contexto SAFE invalido/modificado")
    geometry, snapshot = context["geometry"], context["snapshot"]
    filename = ntpath.basename(geometry["model"])
    if not filename.startswith("SYNTHETIC_") or ntpath.splitext(filename)[1].lower() != ".fdb":
        raise ValueError("Piloto limitado a modelos nuevos SYNTHETIC_*.FDB")
    if (digest(geometry) != context["geometry_sha256"] or context["model_locked"] is not False
            or snapshot["source"]["application"] != "SAFE"
            or query["snapshot_sha256"] != digest(snapshot)
            or query["source"] != snapshot["source"] or query["source_frame"] != snapshot["frame"]):
        raise ValueError("Contexto, snapshot o consulta distintos/bloqueados")
    if (geometry["model"] != snapshot["source"]["model"]
            or geometry["frame"] != snapshot["frame"]
            or geometry["units_enum"] != snapshot["source"]["units_enum"]
            or geometry["points"] != sorted(snapshot["points"], key=lambda p: p["id"])):
        raise ValueError("Geometria y snapshot distintos")
    if type(geometry["units_enum"]) is not int or geometry["units_enum"] not in (6, 9, 10):
        raise ValueError("Unidades SAFE no soportadas por este piloto")
    report = review(query, samples, geotechnical)
    if not report["ok"] or report["geotechnical"] is None:
        raise ValueError("Se requieren cotas TIN completas y geotecnia explicita")
    ids = config["area_ids"]
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 100
            or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids)):
        raise ValueError("Seleccion de areas invalida")
    name = config["property_name"]
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,49}", name):
        raise ValueError("Nombre de resorte invalido")
    if type(config["compression_only"]) is not bool:
        raise ValueError("Declarar compression_only como booleano")
    state = context["soil_state"]
    if name in state["properties"]:
        raise ValueError("Nombre de resorte ya existe")
    areas = {a["id"]: a for a in geometry["areas"]}
    points = {p["id"]: p["xyz"] for p in geometry["points"]}
    sampled = {r["id"] for r in report["rows"]}
    applicable = set(report["geotechnical"]["applicable_point_ids"])
    for aid in ids:
        if aid not in areas or state["assignments"][aid] not in ("", "None"):
            raise ValueError("Area inexistente o con resorte previo")
        area = areas[aid]
        if (area["opening"] or area["section"] in ("", "None") or len(area["matrix"]) != 9
                or any(abs(a-b) > 1e-8 for a, b in zip(area["matrix"][6:9], [0., 0., 1.]))):
            raise ValueError("Area debe ser fisica, horizontal y local 3 hacia +Z")
        vertices = set(area["point_ids"])
        if not vertices.issubset(sampled) or not vertices.issubset(applicable):
            raise ValueError("Alcance geotecnico/cotas no cubre todos los vertices")
        zs = [points[p][2] for p in vertices]
        if max(zs)-min(zs) > 1e-7:
            raise ValueError("Area no horizontal")
    target = {key: geometry[key] for key in ("model", "units_enum", "frame")}
    plan = {"schema": "cdcrd.safe-soil-plan/1", "target": target,
            "geometry_sha256": context["geometry_sha256"], "context_sha256": checksum,
            "query_sha256": query["query_sha256"], "samples_sha256": digest(samples),
            "civil_source": samples["source"], "site_frame": query["site_frame"],
            "vertical_datum": query["vertical_datum"], "terrain_rows": report["rows"],
            "geotechnical": report["geotechnical"],
            "geotechnical_sha256": digest(geotechnical),
            "area_ids": ids, "property_name": name, "compression_only": config["compression_only"],
            "soil_state_before": state, "model_writes": 0, "analysis_run": False,
            "limits": ["qa se registra como metadato; "
                       "no se configura como limite de presion en SAFE.",
                       "k se aporta independientemente; no se deduce de qa ni del TIN.",
                       "Cotas de vertices no son volumen ni fondo de excavacion.",
                       "La cobertura geotecnica de toda el area es declarada por el operador.",
                       "El plan no cambia cotas, geometria, cargas ni ejecuta analisis/diseno."]}
    plan["plan_sha256"] = digest(plan)
    return plan


def run_files(context: Path, query: Path, samples: Path, geotechnical: Path,
              config: Path, output: Path):
    values = [json.loads(path.read_text(encoding="utf-8-sig"))
              for path in (context, query, samples, geotechnical, config)]
    result = prepare_soil_plan(*values)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False, allow_nan=False)
    return result
