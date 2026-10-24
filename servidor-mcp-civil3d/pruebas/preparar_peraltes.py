"""Create an independent peralte fixture in an already open COPY of 0.5.17.

Requires native QA loaded and CDCRDGMQAENTER selected on that copy. No CAD
launch, save, close or automatic retries. Inspect the receipt after a failure.
"""
import argparse
import json
from pathlib import Path
from humo_cunetas_bermas import NativeQa


def run(drawing, output):
    q = NativeQa(drawing, output, 8760, "peraltes-fixture")
    baseline = q.qa("baseline")
    params = json.loads((Path(__file__).resolve().parents[1] / "docs/PERALTES-0518-fixture.json").read_text())
    objects = baseline["drawing"]["objects"]
    if any(o.get("Name", "").startswith("CDX QA PERALTES") for o in objects):
        raise ValueError("Peralte fixture already exists; inspect previous receipt")
    polylines = [o for o in objects if o["type"] == "Autodesk.AutoCAD.DatabaseServices.Polyline" and
                 len(o.get("vertices", [])) == 6 and any(abs(v["bulge"] - .414213562373095) < 1e-9 for v in o["vertices"])]
    if len(polylines) != 1:
        raise ValueError("Expected unique 0.5.17 fixture alignment polyline")
    params["alignment"]["polilinea"] = polylines[0]["handle"]
    axis = q.call("civil.alineamiento_polilinea", params["alignment"])
    params["profile"]["alineamiento"] = axis["handle"]
    profile = q.call("civil.perfil_pvi", params["profile"])
    assembly = q.call("civil.ensamblaje_cunetas_bermas", params["assembly"])
    params["corridor"].update(alineamiento=axis["handle"], perfil=profile["handle"], ensamblaje=assembly["handle"])
    corridor = q.call("civil.corredor_calzada", params["corridor"])
    q.report.update(ok=True, alignment=axis, profile=profile, assembly=assembly, corridor=corridor)
    q.record()
    return q.report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--drawing", required=True); p.add_argument("--output", required=True)
    a = p.parse_args()
    print("Created corridor", run(a.drawing, a.output)["corridor"]["handle"])
