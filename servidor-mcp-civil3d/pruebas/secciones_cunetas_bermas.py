"""Sample the saved smoke run's new corridor and verify its ditch surface."""
import argparse
import json
import math
from pathlib import Path
from humo_cunetas_bermas import NativeQa, canonical, alignment, elevation


def run(drawing, output, port, smoke):
    data = json.loads(Path(smoke).read_text(encoding="utf-8"))
    if not data["ok"]:
        raise ValueError("Successful native smoke receipt required")
    q = NativeQa(drawing, output, port, "cunetas-sections")
    params = dict(corredor=data["corridor"]["handle"], nombre="MCP QA SECCIONES CUNETAS 0517",
                  estaciones=[110, 180, 200, 240, 300, 330, 360, 450], semiancho=12,
                  origen=[620350, 2100230, 0], cota_min=98, cota_max=106, capa="MCP-QA-CUNETAS-SECTIONS")
    before = q.qa("simulation-before")
    sim = q.call("civil.secciones_corredor", {**params, "simular": True})
    q.check("ocho secciones simuladas", sim["simulacion"] and len(sim["secciones"]) == 8)
    q.check("simulacion sin residuos", canonical(before) == canonical(q.qa("simulation-after")))
    result = q.call("civil.secciones_corredor", params)
    q.report["sections"] = result
    q.check("ocho vistas y lineas nativas", len(result["secciones"]) == 8 and all(r["linea"] and r["vista"] for r in result["secciones"]))
    errors = []
    for row in result["secciones"]:
        station = row["estacion"]
        q.check("normal al eje " + str(station), math.dist(row["izquierda"], alignment(station, -12)) < 1e-6 and math.dist(row["derecha"], alignment(station, 12)) < 1e-6)
        raw = row["secciones"][0]["puntos"]
        connected = {i for i, p in enumerate(raw) if p["segment_to"] >= 0} | {p["segment_to"] for p in raw if p["segment_to"] >= 0}
        points = [raw[i] for i in sorted(connected)]
        expected = [(0, elevation(station))]
        for side, width in ((-1, 1.5), (1, 2)):
            offsets = [3.5, 3.5 + width, 3.5 + width + 1.2, 3.5 + width + 1.7, 3.5 + width + 2.6]
            levels = [-.07, -.13, -.73, -.73, -.13]
            expected.extend((side * offset, elevation(station) + z) for offset, z in zip(offsets, levels))
        for offset, z in expected:
            errors.append(min(max(abs(p["offset"] - offset), abs(p["cota"] - z)) for p in points))
        q.check("vertices de cuneta presentes " + str(station), max(errors) < 1e-6)
    q.report["max_surface_section_error"] = max(errors)
    q.report["final"] = q.qa("final")
    group = next(g for g in q.report["final"]["civil"]["groups"] if g["handle"] == result["handle"])
    q.check("vistas H=V", all(v["exaggeration"] == 1 for row in group["lines"] for v in row["views"]))
    q.report["ok"] = True
    q.record()
    return q.report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drawing", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--smoke", required=True)
    parser.add_argument("--port", type=int, default=8760)
    args = parser.parse_args()
    result = run(args.drawing, args.output, args.port, args.smoke)
    print("PASS", len(result["checks"]))
