"""Save, close and reopen only the identified cubicacion QA copy in the existing Civil process.

Compares the contract, thicknesses, surfaces and a fresh volume simulation before and
after the reopen. Never saves any other document; never retries a write.
"""
import argparse, hashlib, json, os, sys, time
from pathlib import Path
import win32com.client
import win32process
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import puente_cliente as bridge
import cubicacion
from humo_cubicacion import guard, receipt


def near(a, b, tol=1e-6):
    if isinstance(a, dict) and isinstance(b, dict): return a.keys() == b.keys() and all(near(a[k], b[k], tol) for k in a)
    if isinstance(a, list) and isinstance(b, list): return len(a) == len(b) and all(near(x, y, tol) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool) and not isinstance(b, bool): return abs(a - b) <= tol * max(1, abs(a), abs(b))
    return a == b


def snapshot(drawing, pid, corridor, terrain):
    read = cubicacion.ejecutar(drawing, pid, accion="leer", corredor=corridor)["result"]
    volumes = cubicacion.ejecutar(drawing, pid, accion="cubicacion", corredor=corridor, terreno=terrain, nombre_volumen="CDCRD QA persistencia", simular=True)["result"]
    return dict(contrato=read["contrato"], ensamblajes=read["ensamblajes"], superficies=read["superficies"], fuera_de_fecha=read["fuera_de_fecha"],
                volumen={k: v for k, v in volumes["volumen"].items() if k != "handle"}, capas=volumes["capas"], estaciones=volumes["estaciones"])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--drawing", required=True); p.add_argument("--pid", type=int, required=True)
    p.add_argument("--corredor", required=True); p.add_argument("--terreno", required=True); p.add_argument("--etiqueta", default="persistencia")
    a = p.parse_args()
    bridge.TIMEOUT = 120
    guard(a.drawing)
    folder = Path(a.drawing).resolve().parent
    dest = receipt(folder, f"cubicacion-{a.etiqueta}.json")
    report = {"ok": False, "checks": []}
    def record(): dest.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    def check(label, condition):
        report["checks"].append({"name": label, "pass": bool(condition)}); record()
        print(("OK " if condition else "FAIL ") + label, flush=True)
        if not condition: raise AssertionError(label)
    app = win32com.client.GetActiveObject("AutoCAD.Application")
    if win32process.GetWindowThreadProcessId(app.HWND)[1] != a.pid: raise RuntimeError("COM connected to another process")
    def active():
        doc = app.ActiveDocument
        if os.path.normcase(doc.FullName) != os.path.normcase(str(Path(a.drawing).resolve())) or not app.GetAcadState().IsQuiescent:
            raise RuntimeError("Wrong document or active command")
        return doc
    before = snapshot(a.drawing, a.pid, a.corredor, a.terreno); report["before"] = before; record()
    check("corredor al dia antes de guardar", not before["fuera_de_fecha"] and all(not s["fuera_de_fecha"] for s in before["superficies"]))
    doc = active(); doc.Save()
    check("guardado nativo DBMOD=0", doc.Saved and doc.GetVariable("DBMOD") == 0)
    def documents():
        # Right after Save the COM server can still be busy: a dynamic property fetch then fails; wait instead of guessing.
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            try: return [app.Documents.Item(i).FullName for i in range(app.Documents.Count)]
            except Exception: time.sleep(.5)
        raise RuntimeError("Civil did not answer the document list; do not repeat Save/Close")
    others = [n for n in documents() if os.path.normcase(n) != os.path.normcase(str(Path(a.drawing).resolve()))]
    doc.Close(True)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            names = documents()
            if names == others: break
        except Exception: pass
        time.sleep(.2)
    else: raise RuntimeError("Civil did not finish closing; do not repeat Close")
    app.Documents.Open(str(Path(a.drawing).resolve()))
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        try:
            if app.GetAcadState().IsQuiescent and os.path.normcase(app.ActiveDocument.FullName) == os.path.normcase(str(Path(a.drawing).resolve())): break
        except Exception: pass
        time.sleep(.2)
    else: raise RuntimeError("Civil still busy after Open; do not repeat")
    guard(a.drawing)
    check("reabierto en mismo PID", win32process.GetWindowThreadProcessId(app.HWND)[1] == a.pid)
    check("reapertura DBMOD=0", active().Saved and active().GetVariable("DBMOD") == 0)
    after = snapshot(a.drawing, a.pid, a.corredor, a.terreno); report["after"] = after; record()
    check("contrato persistido", after["contrato"] == before["contrato"])
    check("espesores persistidos", after["ensamblajes"] == before["ensamblajes"])
    check("superficies persistidas", near(after["superficies"], before["superficies"]))
    check("corredor al dia tras reabrir", not after["fuera_de_fecha"])
    check("volumenes reproducidos tras reabrir", near(after["volumen"], before["volumen"], 1e-6) and near(after["capas"], before["capas"], 1e-6))
    doc = active()
    # The aborted volume simulation of the snapshot leaves only the modified flag (DBMOD=1), no geometry: save once more.
    if not doc.Saved or doc.GetVariable("DBMOD") != 0:
        doc.Save(); report["saved_again_after_snapshot"] = True
    report["native_state"] = dict(Saved=doc.Saved, DBMOD=doc.GetVariable("DBMOD"), CMDNAMES=doc.GetVariable("CMDNAMES"), pid=a.pid)
    check("sin comandos ni cambios pendientes", doc.Saved and doc.GetVariable("DBMOD") == 0 and doc.GetVariable("CMDNAMES") == "")
    report["sha256"] = hashlib.sha256(Path(a.drawing).read_bytes()).hexdigest()
    report["ok"] = True; record()


if __name__ == "__main__":
    main()
