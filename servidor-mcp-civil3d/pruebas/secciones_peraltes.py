"""Verify actual connected surface sections against the explicit superelevation table."""
import argparse
import json
import math
from pathlib import Path
from humo_cunetas_bermas import NativeQa, alignment, elevation
from humo_peraltes import expected


def run(drawing, output, smoke):
    data = json.loads(Path(smoke).read_text(encoding="utf-8"))
    if not data.get("native_receipts", {}).get("applied", {}).get("committed"):
        raise ValueError("Confirmed native application receipt required")
    table = data["input_table"]
    q = NativeQa(drawing, output, 8760, "peraltes-sections")
    corridor = data["peraltes"]["corridor"]
    q.call("objects.invoke", {"handle": corridor, "metodo": "Rebuild"})
    params = dict(corredor=corridor, nombre="CDX QA SECCIONES PERALTES 0518",
                  estaciones=[110, 160, 180, 260, 300, 340, 400, 450], semiancho=12,
                  origen=[620350, 2100270, 0], cota_min=98, cota_max=106, capa="CDX-QA-PERALTES-SECTIONS")
    result = q.call("civil.secciones_corredor", params)
    q.report["sections"] = result
    q.check("ocho secciones nativas", len(result["secciones"]) == 8)
    errors = []
    for row in result["secciones"]:
        station = row["estacion"]
        q.check("normal al eje " + str(station), math.dist(row["izquierda"], alignment(station, -12)) < 1e-6 and math.dist(row["derecha"], alignment(station, 12)) < 1e-6)
        raw = row["secciones"][0]["puntos"]
        connected = {i for i, p in enumerate(raw) if p["segment_to"] >= 0} | {p["segment_to"] for p in raw if p["segment_to"] >= 0}
        points = [raw[i] for i in sorted(connected)]
        vertices = [(0, elevation(station))]
        for col, sign, width, berm_slope in [(1, -1, 1.5, -.04), (2, 1, 2, -.03)]:
            edge = elevation(station) + 3.5 * expected(table, station, col)
            offsets = [3.5, 3.5 + width, 4.7 + width, 5.2 + width, 6.1 + width]
            levels = [0, width * berm_slope, width * berm_slope - .6, width * berm_slope - .6, width * berm_slope]
            vertices.extend((sign * offset, edge + dz) for offset, dz in zip(offsets, levels))
        for offset, z in vertices:
            errors.append(min(max(abs(p["offset"] - offset), abs(p["cota"] - z)) for p in points))
        q.check("peralte y cuneta en superficie " + str(station), max(errors) < 1e-6)
    q.report["max_surface_section_error_m"] = max(errors)
    q.report["final"] = q.qa("final")
    group = next(g for g in q.report["final"]["civil"]["groups"] if g["handle"] == result["handle"])
    q.check("vistas sin exageracion H=V", all(v["exaggeration"] == 1 for row in group["lines"] for v in row["views"]))
    q.report["ok"] = True; q.record()
    return q.report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drawing", required=True); parser.add_argument("--output", required=True); parser.add_argument("--smoke", required=True)
    args = parser.parse_args()
    print("PASS", len(run(args.drawing, args.output, args.smoke)["checks"]))
