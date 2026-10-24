"""Save/reopen only the identified QA copy; leave every other document open.

Requires pywin32 and the already loaded native harness. No application launch.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import win32com.client
import win32process
from humo_cunetas_bermas import NativeQa, canonical


def near(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool):
        return abs(a - b) <= 1e-6
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(near(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(near(x, y) for x, y in zip(a, b))
    return a == b


def run(drawing, output, port, smoke, pid):
    q = NativeQa(drawing, output, port, "cunetas-persistence")
    q.guard()
    app = win32com.client.GetActiveObject("AutoCAD.Application")
    if win32process.GetWindowThreadProcessId(app.HWND)[1] != pid:
        raise RuntimeError("COM is connected to another process")
    data = json.loads(Path(smoke).read_text(encoding="utf-8"))
    if not data["ok"]:
        raise ValueError("Successful smoke receipt required")
    before = q.qa("before-save")
    original = data["baseline"]["drawing"]
    preserved = {}
    for key, old in original.items():
        if isinstance(old, list):
            current = {r["handle"]: r for r in before["drawing"][key] if isinstance(r, dict) and "handle" in r}
            preserved[key] = all(near(current.get(r["handle"]), r) for r in old)
        else:
            preserved[key] = before["drawing"][key] == old
    q.report["preserved_by_collection"] = preserved
    q.report["previous_objects"] = len(original["objects"])
    q.check("todas las colecciones previas conservadas", all(preserved.values()))
    q.check("corredores actualizados antes de guardar", all(not c["out_of_date"] for c in before["civil"]["corridors"]))

    def active():
        d = app.ActiveDocument
        if os.path.normcase(d.FullName) != os.path.normcase(q.drawing) or not app.GetAcadState().IsQuiescent:
            raise RuntimeError("Wrong COM document or active command")
        return d

    doc = active()
    doc.Save()
    q.check("guardado nativo DBMOD=0", doc.Saved and doc.GetVariable("DBMOD") == 0)
    other_documents = [d.Name for d in app.Documents if os.path.normcase(d.FullName) != os.path.normcase(q.drawing)]
    doc.Close(True)
    if [d.Name for d in app.Documents] != other_documents:
        raise RuntimeError("Unexpected document state after closing the QA copy")
    app.Documents.Open(q.drawing)
    q.guard()
    q.check("reapertura nativa DBMOD=0", active().Saved and active().GetVariable("DBMOD") == 0)
    after = q.qa("reopened")
    q.report["same_by_collection"] = {k: near(canonical(after["drawing"][k]), canonical(v)) for k, v in before["drawing"].items()}
    q.check("colecciones persistidas", all(q.report["same_by_collection"].values()))
    q.check("geometria Civil persistida", near(canonical(before["civil"]), canonical(after["civil"])))
    q.check("corredores actualizados al reabrir", all(not c["out_of_date"] for c in after["civil"]["corridors"]))
    # Native audit getters can mark DBMOD=1 without changing their returned data.
    doc = active()
    if not doc.Saved or doc.GetVariable("DBMOD") != 0:
        doc.Save()
    q.check("estado final guardado sin comandos", doc.Saved and doc.GetVariable("DBMOD") == 0 and doc.GetVariable("CMDNAMES") == "")
    q.report["sha256"] = hashlib.sha256(Path(q.drawing).read_bytes()).hexdigest()
    q.report["native_state"] = {"Saved": doc.Saved, "DBMOD": doc.GetVariable("DBMOD"), "CMDNAMES": doc.GetVariable("CMDNAMES")}
    q.report["ok"] = True
    q.record()
    return q.report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--drawing", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--smoke", required=True)
    parser.add_argument("--pid", required=True, type=int)
    parser.add_argument("--port", type=int, default=8760)
    args = parser.parse_args()
    result = run(args.drawing, args.output, args.port, args.smoke, args.pid)
    print("PASS", len(result["checks"]), result["sha256"])
