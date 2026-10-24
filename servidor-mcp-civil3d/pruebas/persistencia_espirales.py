"""Save/reopen only the identified spiral QA copy in the existing Civil process."""
import argparse
import hashlib
import json
import os
import time
from pathlib import Path

import win32com.client
import win32process
from humo_cunetas_bermas import NativeQa, canonical
from persistencia_cunetas_bermas import near
import espirales
import peraltes


def run(drawing, output, pid, smoke, corridor, baseline, old_peraltes, prefix="spirals-persistence", annotation_scale=None):
    q = NativeQa(drawing, output, 8760, prefix)
    q.guard()
    axes = json.loads(Path(smoke).read_text())
    road = json.loads(Path(corridor).read_text())
    previous = json.loads(Path(old_peraltes).read_text())["native_read"]["result"]
    if not axes["ok"] or not road["ok"]:
        raise ValueError("Successful native receipts required")
    app = win32com.client.GetActiveObject("AutoCAD.Application")
    if win32process.GetWindowThreadProcessId(app.HWND)[1] != pid:
        raise RuntimeError("COM connected to another process")
    original = json.loads(Path(baseline).read_text(encoding="utf-8-sig"))["result"]

    def active():
        doc = app.ActiveDocument
        if os.path.normcase(doc.FullName) != os.path.normcase(q.drawing) or not app.GetAcadState().IsQuiescent:
            raise RuntimeError("Wrong document or active command")
        return doc

    def native():
        return {
            "axes": {key: espirales.ejecutar(q.drawing, pid, alineamiento=axes[key]["handle"])["result"] for key in ("left", "right")},
            "peraltes": peraltes.ejecutar(q.drawing, pid, road["corridor"]["handle"])["result"],
            "previous_peraltes": peraltes.ejecutar(q.drawing, pid, previous["corridor"])["result"],
        }

    # AutoCAD assigns *Paper_Space to the last active paper layout. Native
    # preview capture can change this alias; restore its original owner by
    # selecting that layout, then return to the current tab. No geometry edit.
    paper = next(r["handle"] for r in original["objects"] if r.get("type", "").endswith(".BlockTableRecord") and r.get("name") == "*Paper_Space")
    doc = active()
    tab = doc.GetVariable("CTAB")
    layout = next(l for l in doc.Layouts if l.Block.Handle == paper)
    if layout.Block.Name != "*Paper_Space":
        doc.SetVariable("CTAB", layout.Name)
        doc.SetVariable("CTAB", tab)
        q.report["paper_alias_restored"] = True
    if annotation_scale:
        doc.SetVariable("CANNOSCALE", annotation_scale)
        q.report["annotation_scale_restored"] = annotation_scale
    q.call("cmd.run", {"linea": "_.REGENALL\n"})
    initial = q.qa("initial")
    for c in initial["civil"]["corridors"]:
        if c["out_of_date"]:
            q.call("objects.invoke", {"handle": c["handle"], "metodo": "Rebuild"})
    before = q.qa("before-save")
    native_before = native()
    preserved = {}
    # Primary paper-space viewports resize to the current graphics-area aspect.
    # Verify DXF 69=1 before allowing only their display bounds to differ.
    # Keep each difference explicit. Plotted viewports/model geometry stay strict.
    paper_owners = {r["handle"] for r in original["objects"] if r.get("type", "").endswith(".BlockTableRecord") and r.get("name", "").startswith("*Paper_Space")}
    q.report["paper_viewport_display_bounds"] = []
    def primary_viewport(row):
        handle = row["handle"]
        target = q.out / (q.prefix + "-viewport-" + handle + ".txt")
        if target.exists():
            raise FileExistsError(target)
        q.call("cmd.run", {"linea": f'(progn (setq cdxvf (open "{target.as_posix()}" "w")) (princ (cdr (assoc 69 (entget (handent "{handle}")))) cdxvf) (close cdxvf) (princ))\n'})
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            if target.exists() and target.read_text().strip():
                return target.read_text().strip() == "1"
            time.sleep(.1)
        raise RuntimeError("No native viewport DXF receipt")
    for key, old in original.items():
        if isinstance(old, list):
            current = {r["handle"]: r for r in before["drawing"][key] if isinstance(r, dict) and "handle" in r}
            comparisons = []
            for row in old:
                now = current.get(row["handle"])
                if key == "objects" and now and row.get("type", "").endswith(".Viewport") and row.get("owner") in paper_owners and not near(row.get("extents"), now.get("extents")) and primary_viewport(row):
                    q.report["paper_viewport_display_bounds"].append(dict(handle=row["handle"], dxf_69=1, before=row.get("extents"), after=now.get("extents")))
                    comparisons.append(near({k:v for k,v in row.items() if k != "extents"}, {k:v for k,v in now.items() if k != "extents"}))
                else:
                    comparisons.append(near(now, row))
            preserved[key] = all(comparisons)
        else:
            preserved[key] = before["drawing"][key] == old
    q.report["preserved_by_collection"] = preserved
    q.report["previous_objects"] = len(original["objects"])
    q.check("colecciones originales conservadas", all(preserved.values()))
    q.check("peraltes anteriores conservados", near(previous, native_before["previous_peraltes"]))
    q.check("corredores actualizados antes de guardar", all(not c["out_of_date"] for c in before["civil"]["corridors"]))
    doc = active()
    doc.Save()
    q.check("guardado nativo DBMOD=0", doc.Saved and doc.GetVariable("DBMOD") == 0)
    others = [d.FullName for d in app.Documents if os.path.normcase(d.FullName) != os.path.normcase(q.drawing)]
    doc.Close(True)
    if [d.FullName for d in app.Documents] != others:
        raise RuntimeError("Unexpected documents after closing only QA copy")
    app.Documents.Open(q.drawing)
    q.guard()
    q.check("reabierto en mismo PID", win32process.GetWindowThreadProcessId(app.HWND)[1] == pid)
    q.check("reapertura DBMOD=0", active().Saved and active().GetVariable("DBMOD") == 0)
    after = q.qa("reopened")
    native_after = native()
    q.report["same_by_collection"] = {k: near(canonical(after["drawing"][k]), canonical(v)) for k, v in before["drawing"].items()}
    q.check("inventario persistido", all(q.report["same_by_collection"].values()))
    q.check("geometria Civil persistida", near(canonical(before["civil"]), canonical(after["civil"])))
    q.check("espirales y tablas persistidas", near(native_before, native_after))
    q.check("seis estaciones de peralte en espirales", native_after["peraltes"]["configured"] and len(native_after["peraltes"]["table"]) == 6)
    q.check("corredores actualizados tras reabrir", all(not c["out_of_date"] for c in after["civil"]["corridors"]))
    doc = active()
    if not doc.Saved or doc.GetVariable("DBMOD") != 0:
        doc.Save()
    q.report["native_state"] = dict(Saved=doc.Saved, DBMOD=doc.GetVariable("DBMOD"), CMDNAMES=doc.GetVariable("CMDNAMES"), pid=pid)
    q.check("guardado final sin comandos", doc.Saved and doc.GetVariable("DBMOD") == 0 and doc.GetVariable("CMDNAMES") == "")
    q.report["sha256"] = hashlib.sha256(Path(q.drawing).read_bytes()).hexdigest()
    q.report["native"] = native_after
    q.report["ok"] = True
    q.record()
    return q.report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for arg in ("drawing", "output", "smoke", "corridor", "baseline", "old-peraltes"):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--prefix", default="spirals-persistence")
    p.add_argument("--annotation-scale")
    a = p.parse_args()
    print("PASS", len(run(a.drawing, a.output, a.pid, a.smoke, a.corridor, a.baseline, a.old_peraltes, a.prefix, a.annotation_scale)["checks"]))
