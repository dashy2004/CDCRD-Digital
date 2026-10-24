"""Native 0.5.17 QA on a separate copy of the documented 0.5.16 fixture.

No write retries. Requires the bridge and optional native_gm_qa harness loaded,
with the QA root explicitly selected. Does not save or close any drawing.
"""
import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import puente_cliente as bridge
from humo_calzada import alignment, elevation, canonical


class NativeQa:
    def __init__(self, drawing, output, port, prefix="cunetas"):
        self.drawing = str(Path(drawing).resolve())
        self.out = Path(output).resolve()
        self.prefix = prefix
        if not re.fullmatch(r"[a-z0-9-]+", prefix):
            raise ValueError("Receipt prefix must contain only lowercase letters, digits and hyphens")
        if Path(self.drawing).parent != self.out or not Path(self.drawing).name.startswith(("CDCRD_GM_RECOVERY_CUNETAS_BERMAS", "CDCRD_GM_RECOVERY_PERALTES", "CDCRD_GM_RECOVERY_ESPIRALES")):
            raise ValueError("An identified disposable copy in the output directory is required")
        self.receipt = self.out / (prefix + "-smoke.json")
        if self.receipt.exists():
            raise FileExistsError("Receipt exists; inspect the previous run before continuing")
        bridge.PUERTO, bridge.TIMEOUT = port, 120
        self.report = {"ok": False, "checks": [], "calls": []}

    def record(self):
        self.receipt.write_text(json.dumps(self.report, indent=2), encoding="utf-8")

    def guard(self):
        info = bridge.llamar("doc.info", {})
        if not info.get("civil3d") or os.path.normcase(info["dibujo"]) != os.path.normcase(self.drawing) or info["insunits"] != 6:
            raise RuntimeError("Wrong Civil document or units")
        if bridge.llamar("diag.dialogos", {})["modal_abierto"] or bridge.llamar("diag.cola", {})["activas"]:
            raise RuntimeError("Busy; inspect state before any further write")

    def call(self, method, params):
        self.guard()
        row = {"method": method, "params": params}
        self.report["calls"].append(row)
        self.record()
        try:
            result = bridge.llamar_con_aprobacion(method, params)
        except Exception as error:
            row["error"] = str(error)
            self.record()
            raise
        row["result"] = result
        self.record()
        return result

    def check(self, label, condition):
        self.report["checks"].append({"name": label, "pass": bool(condition)})
        self.record()
        print(("OK " if condition else "FAIL ") + label, flush=True)
        if not condition:
            raise AssertionError(label)

    def qa(self, label, action="combined", **kwargs):
        if action == "combined":
            return {"drawing": self.qa(label + "-drawing", "audit"), "civil": self.qa(label + "-civil", "corridor_audit")}
        dest = self.out / (self.prefix + "-" + label + ".json")
        if dest.exists():
            raise FileExistsError(dest)
        (self.out / "job.json").write_text(json.dumps({"action": action, "output": dest.name, **kwargs}), encoding="utf-8")
        self.call("cmd.run", {"linea": "CDCRDGMRECOVERYQA\n"})
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if dest.exists():
                try:
                    result = json.loads(dest.read_text(encoding="utf-8-sig"))
                    break
                except json.JSONDecodeError:
                    pass
            time.sleep(.1)
        else:
            raise RuntimeError("Native receipt missing; inspect queue and command state, do not retry")
        if not result["ok"]:
            raise RuntimeError(result)
        return result["result"]

    def rejected(self, label, method, params, expected, fault=None):
        before = self.qa(label + "-before")
        if fault:
            self.qa(label + "-armed", "corridor_fault", stage=fault)
        try:
            self.call(method, params)
        except bridge.PuenteError as error:
            self.check(label + " rechazo explicito", expected in str(error))
        else:
            raise AssertionError(label + " unexpectedly accepted")
        self.check(label + " sin residuos", canonical(before) == canonical(self.qa(label + "-after")))


def run(drawing, output, port, prefix="cunetas"):
    q = NativeQa(drawing, output, port, prefix)
    q.guard()
    q.report["ping"] = bridge.llamar("ping", {})
    q.check("Civil DLL 0.5.17", q.report["ping"]["version"] == "0.5.17" and q.report["ping"]["puente"] == "cdcrd-civil3d")
    baseline = q.qa("baseline")
    q.report["baseline"] = baseline
    terrain = next(s for s in baseline["drawing"]["surfaces"] if s["name"] == "MCP QA TERRENO 0516")
    assembly = dict(nombre="MCP QA CUNETAS BERMAS 0517", origen=[620300, 2100230, 0],
                    ancho_izq=3.5, ancho_der=3.5, pendiente_izq=-.02, pendiente_der=-.02,
                    espesores=[.05, .07, .2, .3], talud_corte=3, talud_relleno=4, ancho_daylight_max=50,
                    ancho_berma_izq=1.5, ancho_berma_der=2, pendiente_berma_izq=-.04, pendiente_berma_der=-.03,
                    profundidad_cuneta=.6, ancho_fondo_cuneta=.5, talud_cuneta_interior_hv=2, talud_cuneta_exterior_hv=1.5,
                    capa="MCP-QA-CUNETAS-ASSEMBLY")
    method = "civil.ensamblaje_cunetas_bermas"
    for field, value in (("ancho_berma_izq", 0), ("pendiente_berma_der", 2), ("profundidad_cuneta", 0),
                         ("ancho_fondo_cuneta", 0), ("talud_cuneta_interior_hv", 0), ("talud_cuneta_exterior_hv", 11)):
        q.rejected("invalid-" + field, method, {**assembly, field: value}, field)
    before = q.qa("simulation-before")
    sim = q.call(method, {**assembly, "simular": True})
    q.check("simulacion de 12 piezas", sim["simulacion"] and sim["handle"] is None and len(sim["subensamblajes"]) == 12)
    q.check("simulacion sin residuos", canonical(before) == canonical(q.qa("simulation-after")))
    q.rejected("failure-berma", method, assembly, "CDCRD_QA_CORRIDOR_FAILURE", fault="berma-cuneta-part-added")
    built = q.call(method, assembly)
    q.report["assembly"] = built
    parts = built["subensamblajes"]
    q.check("12 subensamblajes creados", len(parts) == 12)
    roles = ["carril", "berma", "cuneta_interior", "cuneta_fondo", "cuneta_exterior", "daylight"]
    for side in ("Left", "Right"):
        rows = {s["rol"]: s for s in parts if s["lado"] == side}
        q.check("cadena de enganches " + side, set(rows) == set(roles) and all(rows[b]["engancha_a"] == rows[a]["handle"] for a, b in zip(roles, roles[1:])))
    q.rejected("duplicado", method, assembly, "Ya existe")
    corridor = dict(nombre="MCP QA CORREDOR CUNETAS 0517", alineamiento="CDX QA CURVE AXIS 0514", perfil="CDX QA CURVE DESIGN 0514",
                    ensamblaje=built["handle"], superficie_objetivo=terrain["handle"], inicio=100, fin=340 + 40 * math.pi,
                    frecuencia=10, estaciones_extra=[110, 180, 200, 240, 300, 330, 360, 450], capa="MCP-QA-CUNETAS-CORREDOR")
    before = q.qa("corridor-simulation-before")
    sim = q.call("civil.corredor_calzada", {**corridor, "simular": True})
    q.check("corredor simulado con geometria", sim["simulacion"] and sim["handle"] is None and len(sim["aplicados"]) > 30)
    q.check("corredor simulado sin residuos", canonical(before) == canonical(q.qa("corridor-simulation-after")))
    q.rejected("failure-corridor", "civil.corredor_calzada", corridor, "CDCRD_QA_CORRIDOR_FAILURE", fault="corridor-rebuilt")
    c = q.call("civil.corredor_calzada", corridor)
    q.report["corridor"] = c
    q.check("targets de terreno", len(c["targets"]) >= 2 and all(t["objetivo"] == terrain["handle"] for t in c["targets"]))
    # Independently derive signed offsets, relative heights, world XY and daylight.
    errors = dict(xy=0., profile=0., berm_ditch=0., daylight=0., daylight_grade=0., layers=0.)
    cases = set()
    codes = ("BermaExterior", "CunetaFondoInterior", "CunetaFondoExterior", "CunetaBordeExterior")
    for row in c["aplicados"]:
        station = row["estacion"]
        level = elevation(station)
        for point in row["puntos"]:
            errors["xy"] = max(errors["xy"], math.dist(alignment(station, point["soe"][1]), point["xyz"][:2]))
            errors["profile"] = max(errors["profile"], abs(point["xyz"][2] - level - point["soe"][2]))
        for side, width in ((-1, 1.5), (1, 2.)):
            # Both selected berms drop 0.06 m; 0.6 m ditch with 2:1 and 1.5:1 faces.
            offsets = [3.5 + width, 3.5 + width + 1.2, 3.5 + width + 1.7, 3.5 + width + 2.6]
            levels = [-.13, -.73, -.73, -.13]
            for code, offset, z in zip(codes, offsets, levels):
                points = [p for p in row["puntos"] if code in p["codigos"] and side * p["soe"][1] > 0]
                q_error = max((max(abs(p["soe"][1] - side * offset), abs(p["soe"][2] - z)) for p in points), default=math.inf)
                errors["berm_ditch"] = max(errors["berm_ditch"], q_error)
            for depth in [0., .05, .12, .32, .62]:
                errors["layers"] = max(errors["layers"], min((max(abs(p["soe"][1] - side * 3.5), abs(p["soe"][2] + .07 + depth)) for p in row["puntos"]), default=math.inf))
            dl = [p for p in row["puntos"] if "Daylight" in p["codigos"] and side * p["soe"][1] > 0]
            if not dl:
                raise AssertionError("Daylight missing")
            far = max(dl, key=lambda p: abs(p["soe"][1]))
            errors["daylight"] = max(errors["daylight"], abs(far["xyz"][2] - 102))
            cut = 102 > level - .13
            cases.add("cut" if cut else "fill")
            horizontal = abs(far["soe"][1]) - offsets[-1]
            expected = abs(102 - (level - .13)) / (3 if cut else 4)
            errors["daylight_grade"] = max(errors["daylight_grade"], abs(horizontal - expected))
    q.report["errors"] = errors
    q.report["cut_fill"] = sorted(cases)
    for label, delta in errors.items():
        q.check("ecuacion independiente " + label, delta < 1e-6)
    q.check("corte y relleno ejercitados", cases == {"cut", "fill"})
    q.call("cmd.run", {"linea": "_.REGENALL\n"})
    final = q.qa("final")
    native = next(r for r in final["civil"]["corridors"] if r["handle"] == c["handle"])
    q.check("corredor al dia", not native["out_of_date"])
    q.check("superficie Top triangulada", any(s["handle"] == c["superficie"] and s["triangles"] for s in final["drawing"]["surfaces"]))
    q.check("objetos originales conservados", all(r in final["drawing"]["objects"] for r in baseline["drawing"]["objects"]))
    q.report["final"] = final
    q.report["ok"] = True
    q.record()
    return q.report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drawing", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--port", type=int, default=8760)
    parser.add_argument("--prefix", default="cunetas")
    args = parser.parse_args()
    result = run(args.drawing, args.output, args.port, args.prefix)
    print("PASS", len(result["checks"]))
