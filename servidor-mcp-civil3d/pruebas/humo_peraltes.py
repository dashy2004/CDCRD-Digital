"""Native superelevation checks on the separately prepared 0.5.18 copy.

Requires the optional production module and QA hooks already NETLOADed in the
same Civil process. Never starts Civil, retries a write, saves or closes a DWG.
"""
import argparse
import json
from pathlib import Path
import time

from humo_cunetas_bermas import NativeQa
from humo_calzada import canonical, elevation, alignment
import peraltes


def expected(rows, station, col):
    for before, after in zip(rows, rows[1:]):
        if station <= after[0] + 1e-7:
            return before[col] + (after[col] - before[col]) * (station - before[0]) / (after[0] - before[0])
    return rows[-1][col]


def run(drawing, output, pid, corridor, end, prefix="peraltes"):
    q = NativeQa(drawing, output, 8760, prefix)
    table = [[100, -.02, -.02], [140, -.02, -.02], [180, .06, -.06], [240, .06, -.06],
             [280, -.02, -.02], [320, -.05, .05], [380, -.05, .05], [420, -.02, -.02], [end, -.02, -.02]]
    q.report["input_table"] = table
    q.report["pid"] = pid
    def call(label, rows=None, simulate=True):
        q.guard()
        try:
            receipt = peraltes.ejecutar(str(Path(drawing).resolve()), pid, corridor, rows, simulate)
        except peraltes.PeralteError as exc:
            q.report.setdefault("native_receipts", {})[label] = exc.receipt
            q.record()
            raise
        q.report.setdefault("native_receipts", {})[label] = receipt
        q.record()
        return receipt["result"]
    def snapshot(label):
        return {"inventory": q.qa(label), "peraltes": call(label)}
    before = snapshot("before")
    q.check("sin peraltes iniciales validos", not before["peraltes"]["configured"] and len(before["peraltes"]["table"]) <= 2)
    invalid = [r[:] for r in table]; invalid[0][0] = 101
    try:
        call("invalid-range", invalid, False)
        raise AssertionError("Invalid range accepted")
    except peraltes.PeralteError as exc:
        q.check("rechazo nativo de rango", "exactamente" in str(exc) and not exc.receipt["committed"])
    q.check("rango invalido sin residuos", canonical(before) == canonical(snapshot("invalid-range-after")))
    sim = call("simulation", table)
    q.check("simulacion nueve estaciones sin duplicados", sim["simulation"] and len(sim["table"]) == len(table) and len({r["station"] for r in sim["table"]}) == len(table))
    q.check("simulacion revertida tabla parametros geometria", canonical(before) == canonical(snapshot("simulation-after")))
    for stage in ["table-written", "corridor-rebuilt"]:
        dest = q.out / (prefix + "-fault-" + stage + ".json")
        if dest.exists():
            raise FileExistsError(dest)
        (q.out / "peraltes-fault.json").write_text(json.dumps({"stage": stage, "output": dest.name}), encoding="utf-8")
        q.call("cmd.run", {"linea": "CDCRDPERALTESV1QA\n"})
        deadline = time.monotonic() + 20
        while not dest.exists() and time.monotonic() < deadline:
            time.sleep(.1)
        if not dest.exists():
            raise RuntimeError("QA fault not armed; inspect state, do not retry")
        try:
            call("fault-" + stage, table, False)
            raise AssertionError("Fault did not fire")
        except peraltes.PeralteError as exc:
            q.check(stage + " fallo inyectado", "CDCRD_QA_PERALTE_FAILURE" in str(exc) and not exc.receipt["committed"])
        q.check(stage + " rollback completo", canonical(before) == canonical(snapshot(stage + "-after")))
    result = call("applied", table, False)
    q.report["peraltes"] = result
    q.check("aplicacion confirmada", q.report["native_receipts"]["applied"]["committed"] and not result["simulation"])
    q.check("frecuencia critica activa corredor actualizado", result["critical_frequency"] and not result["out_of_date"])
    q.check("seleccion explicita de carril exterior", {r["side"]: r["use"] for r in result["lanes"]} == {"Left": 0, "Right": 2})
    q.check("tabla releida igual a solicitada", all(abs(r["station"] - p[0]) < 1e-7 and abs(r["left"] - p[1]) < 1e-12 and abs(r["right"] - p[2]) < 1e-12 for r, p in zip(result["table"], table)))
    max_xyz = max_slope = max_daylight = max_roadside = 0
    for row in result["samples"]:
        station = row["station"]
        for col, sign, berm_width, berm_slope in [(1, -1, 1.5, -.04), (2, 1, 2, -.03)]:
            slope = expected(table, station, col)
            max_slope = max(max_slope, abs(row["slopes"][col - 1] - slope))
            edge = [p for p in row["points"] if "ETW" in p["codes"] and p["soe"][1] * sign > 0]
            assert len(edge) == 1
            p = edge[0]; xy = alignment(station, sign * 3.5)
            max_xyz = max(max_xyz, abs(p["xyz"][0] - xy[0]), abs(p["xyz"][1] - xy[1]), abs(p["xyz"][2] - elevation(station) - 3.5 * slope))
            # Native roadside points: geometry follows ETW but its own slopes stay fixed.
            offsets = [3.5 + berm_width, 3.5 + berm_width + 1.2, 3.5 + berm_width + 1.7, 3.5 + berm_width + 2.6]
            heights = [berm_width * berm_slope, berm_width * berm_slope - .6, berm_width * berm_slope - .6, berm_width * berm_slope]
            for offset, dz in zip(offsets, heights):
                candidates = [point for point in row["points"] if abs(point["soe"][1] - sign * offset) < 1e-6 and any("CDCRD" in c for c in point["codes"])]
                if not candidates:
                    # Codes are namespaced by role in the 0.5.17 assembly.
                    candidates = [point for point in row["points"] if abs(point["soe"][1] - sign * offset) < 1e-6]
                assert candidates
                max_roadside = max(max_roadside, min(abs(point["xyz"][2] - (p["xyz"][2] + dz)) for point in candidates))
        for p in row["points"]:
            if "Daylight" in p["codes"]:
                max_daylight = max(max_daylight, abs(p["xyz"][2] - 102))
    q.report["max_errors"] = dict(xyz_m=max_xyz, slope=max_slope, roadside_m=max_roadside, daylight_m=max_daylight)
    q.check("44 o mas estaciones con formulas independientes", len(result["samples"]) >= 44 and max_xyz < 1e-6 and max_slope < 1e-9)
    q.check("bermas cunetas y daylight conservan geometria", max_roadside < 1e-6 and max_daylight < 1e-6)
    after = snapshot("applied-after")
    q.check("lectura independiente de geometria y tabla coincide", canonical({k:v for k,v in result.items() if k != "out_of_date"}) == canonical({k:v for k,v in after["peraltes"].items() if k != "out_of_date"}))
    # A later Civil display update may invalidate the corridor after commit.
    # Preserve this observed state; persistence QA explicitly rebuilds and rereads.
    q.report["out_of_date_after_commit"] = after["peraltes"]["out_of_date"]
    try:
        call("duplicate", table, False)
        raise AssertionError("Existing table overwritten")
    except peraltes.PeralteError as exc:
        q.check("rechaza reemplazo implicito", "Ya existen peraltes" in str(exc) and not exc.receipt["committed"])
    q.check("rechazo duplicado sin cambios", canonical(after) == canonical(snapshot("duplicate-after")))
    q.report["ok"] = True
    q.record()
    return q.report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drawing", required=True); parser.add_argument("--output", required=True)
    parser.add_argument("--pid", type=int, required=True); parser.add_argument("--corridor", required=True)
    parser.add_argument("--end", type=float, required=True); parser.add_argument("--prefix", default="peraltes")
    a = parser.parse_args()
    run(a.drawing, a.output, a.pid, a.corridor, a.end, a.prefix)
