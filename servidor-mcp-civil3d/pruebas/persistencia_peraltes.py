"""Save/reopen the identified QA copy in the same Civil process, then audit it.

Requires the production module and native QA harness already loaded. Never
starts CAD, overwrites an original, or retries a failed write.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

import win32com.client
import win32process
from humo_cunetas_bermas import NativeQa, canonical
from persistencia_cunetas_bermas import near
import peraltes


def run(drawing, output, pid, corridor, baseline):
    q = NativeQa(drawing, output, 8760, "peraltes-persistence")
    q.guard()
    app = win32com.client.GetActiveObject("AutoCAD.Application")
    if win32process.GetWindowThreadProcessId(app.HWND)[1] != pid:
        raise RuntimeError("COM connected to another process")

    def active():
        doc = app.ActiveDocument
        if os.path.normcase(doc.FullName) != os.path.normcase(q.drawing) or not app.GetAcadState().IsQuiescent:
            raise RuntimeError("Wrong document or active command")
        return doc

    q.call("cmd.run", {"linea": "_.REGEN\n"})
    initial = q.qa("initial")
    for c in initial["civil"]["corridors"]:
        if c["out_of_date"]:
            q.call("objects.invoke", {"handle": c["handle"], "metodo": "Rebuild"})
    before = q.qa("before-save")
    native_before = peraltes.ejecutar(q.drawing, pid, corridor)["result"]
    original = json.loads(Path(baseline).read_text(encoding="utf-8-sig"))["result"]
    preserved = {}
    for key, old in original.items():
        if isinstance(old, list):
            current = {r["handle"]: r for r in before["drawing"][key] if isinstance(r, dict) and "handle" in r}
            preserved[key] = all(near(current.get(r["handle"]), r) for r in old)
        else:
            preserved[key] = before["drawing"][key] == old
    q.report["preserved_by_collection"] = preserved
    q.report["previous_objects"] = len(original["objects"])
    q.check("colecciones originales conservadas", all(preserved.values()))
    q.check("corredores actualizados antes de guardar", all(not c["out_of_date"] for c in before["civil"]["corridors"]) and not native_before["out_of_date"])
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
    native_after = peraltes.ejecutar(q.drawing, pid, corridor)["result"]
    q.report["same_by_collection"] = {k: near(canonical(after["drawing"][k]), canonical(v)) for k, v in before["drawing"].items()}
    q.check("inventario persistido", all(q.report["same_by_collection"].values()))
    q.check("geometria Civil persistida", near(canonical(before["civil"]), canonical(after["civil"])))
    q.check("tabla y puntos peraltes persistidos", near(native_before, native_after))
    q.check("nueve estaciones configuradas", native_after["configured"] and len(native_after["table"]) == 9)
    q.check("corredores actualizados tras reabrir", all(not c["out_of_date"] for c in after["civil"]["corridors"]) and not native_after["out_of_date"])
    doc = active()
    if not doc.Saved or doc.GetVariable("DBMOD") != 0:
        doc.Save()
    q.report["native_state"] = dict(Saved=doc.Saved, DBMOD=doc.GetVariable("DBMOD"), CMDNAMES=doc.GetVariable("CMDNAMES"), pid=pid)
    q.check("guardado final sin comandos", doc.Saved and doc.GetVariable("DBMOD") == 0 and doc.GetVariable("CMDNAMES") == "")
    q.report["sha256"] = hashlib.sha256(Path(q.drawing).read_bytes()).hexdigest()
    q.report["native_peraltes"] = native_after
    q.report["ok"] = True
    q.record()
    return q.report


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    for arg in ("drawing", "output", "corridor", "baseline"):
        p.add_argument("--" + arg, required=True)
    p.add_argument("--pid", type=int, required=True)
    a = p.parse_args()
    print("PASS", len(run(a.drawing, a.output, a.pid, a.corridor, a.baseline)["checks"]))
