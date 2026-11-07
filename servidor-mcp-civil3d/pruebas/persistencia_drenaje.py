"""Fault injection, committed network, save/reopen and re-verification on the identified copy.

Runs in the existing Civil process. Steps, each leaving a receipt next to the copy:
  1. Arm a one-shot failure at --fallo (default pipes-connected) and expect the simulated
     creation to fail with no residue in the pipe network, layer and corridor inventories.
  2. Create the network for real, verify, save the copy through COM, close it, reopen it
     and verify again from the stored contract.
Never run on a project drawing; the copy name must start with CDCRD_QA_DRENAJE.
"""
import argparse, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pywintypes, win32com.client, win32process
import puente_cliente as bridge
import drenaje
from humo_drenaje import guard, qa_job

COLLECTIONS = ("redes_gravedad", "corredores", "superficies")


def inventory():
    out = {c: bridge.llamar("objects.query", {"coleccion": c, "props": ["Name"], "limite": 1000})["coincidencias"] for c in COLLECTIONS}
    out["capas"] = sorted(r["nombre"] for r in bridge.llamar("layers.query", {})["capas"])
    return out


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--drawing", required=True); p.add_argument("--pid", type=int, required=True)
    p.add_argument("--nodos", required=True); p.add_argument("--nombre", default="CDCRD QA DRENAJE")
    p.add_argument("--familia-tuberia", default="Concrete Pipe"); p.add_argument("--familia-imbornal", required=True); p.add_argument("--familia-pozo", required=True)
    p.add_argument("--diametros", default="[300, 375, 450, 525, 600]"); p.add_argument("--lista-partes", default="")
    p.add_argument("--fallo", default="pipes-connected"); p.add_argument("--comando"); p.add_argument("--qa-comando", default="CDCRDDRENAJEV1QA")
    p.add_argument("--reanudar", action="store_true", help="skip fault and creation: the network already exists")
    p.add_argument("--etiqueta", default="", help="receipt suffix: drenaje-persistencia-<etiqueta>.json")
    a = p.parse_args()
    if a.comando: drenaje.COMMAND = a.comando
    import humo_drenaje; humo_drenaje.QA_COMMAND = a.qa_comando
    bridge.TIMEOUT = 120
    folder = Path(a.drawing).resolve().parent
    dest = folder / ("drenaje-persistencia" + ("-" + a.etiqueta if a.etiqueta else "") + ".json")
    if dest.exists(): raise FileExistsError(dest)
    report = {"ok": False, "steps": []}
    def record(): dest.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    nodes = json.loads(Path(a.nodos).read_text(encoding="utf-8"))
    familias = dict(tuberia=dict(familia=a.familia_tuberia), imbornal=dict(familia=a.familia_imbornal), pozo=dict(familia=a.familia_pozo), salida=dict(familia=a.familia_pozo))
    design, structures, pipes = drenaje.disenar(nodes, familias, diametros_mm=json.loads(a.diametros))
    create = dict(nombre=a.nombre, lista_partes=a.lista_partes or None, estructuras=structures, tuberias=pipes)
    guard(a.drawing)
    if not a.reanudar:
        # 1. injected failure: explicit error and no residue
        before = inventory()
        armed = qa_job(folder, dict(action="fault", stage=a.fallo, output=f"drenaje-fault-{a.fallo}.json"))
        report["steps"].append({"armed": armed}); record()
        try:
            drenaje.ejecutar(a.drawing, a.pid, accion="crear", **create)
            raise AssertionError("Injected failure was not reported")
        except drenaje.DrenajeError as exc:
            if "CDCRD_QA_DRENAJE_FAILURE:" + a.fallo not in str(exc): raise
            after = inventory()
            report["steps"].append({"fault": str(exc), "inventory_before": before, "inventory_after": after}); record()
            assert after == before, "Residue after injected failure"
        # 2. real creation and in-transaction verification
        created = drenaje.ejecutar(a.drawing, a.pid, accion="crear", simular=False, **create)
        assert created["committed"]
        report["steps"].append({"created": {k: v for k, v in created["result"]["verificacion"].items() if not k.startswith("detalle")}, "red": created["result"]["red"]}); record()
        red = created["result"]["red"]
    else:
        red = a.nombre; report["steps"].append({"resumed": True}); record()
    verified = drenaje.ejecutar(a.drawing, a.pid, accion="verificar", red=red)
    report["steps"].append({"verified": verified["result"]}); record()
    app = win32com.client.GetActiveObject("AutoCAD.Application")
    if win32process.GetWindowThreadProcessId(app.HWND)[1] != a.pid: raise RuntimeError("COM connected to another process")
    doc = app.ActiveDocument
    if os.path.normcase(doc.FullName) != os.path.normcase(str(Path(a.drawing).resolve())) or not app.GetAcadState().IsQuiescent:
        raise RuntimeError("Wrong document or active command")
    doc.Save(); doc.Close(False)
    # Civil rejects COM calls for a moment after closing a document: retry the reopen, never the save.
    # The dispatch object can also lose its type info after the close: re-acquire the application each attempt.
    for attempt in range(60):
        try:
            app = win32com.client.GetActiveObject("AutoCAD.Application")
            app.Documents.Open(str(Path(a.drawing).resolve())); break
        except (pywintypes.com_error, AttributeError) as exc:
            if attempt == 59: raise RuntimeError("Civil rejected the reopen for 60 s; inspect the session, do not retry blindly") from exc
            time.sleep(1)
    for _ in range(300):
        try:
            if app.GetAcadState().IsQuiescent and os.path.normcase(app.ActiveDocument.FullName) == os.path.normcase(str(Path(a.drawing).resolve())): break
        except Exception: pass
        time.sleep(1)
    guard(a.drawing)
    reopened = drenaje.ejecutar(a.drawing, a.pid, accion="verificar", red=red)
    report["steps"].append({"reopened": reopened["result"]}); record()
    same = {k: reopened["result"][k] == verified["result"][k] for k in ("estructuras", "tuberias", "detalle_estructuras", "detalle_tuberias")}
    report["persisted"] = same; assert all(same.values()), "Network changed across save/reopen"
    report["ok"] = True; record()
    print(json.dumps({"fault": None if a.reanudar else a.fallo, "verified": {k: v for k, v in verified["result"].items() if not k.startswith("detalle")},
                      "reopened_equal": same}, ensure_ascii=False))


if __name__ == "__main__":
    main()
