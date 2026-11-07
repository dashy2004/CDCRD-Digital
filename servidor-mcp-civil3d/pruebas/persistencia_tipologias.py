"""Fault injection, committed application, save/reopen and re-verification on the identified copy.

Runs in the existing Civil process. Steps, each leaving a receipt next to the copy:
  1. Arm a one-shot failure at --fallo (default corridor-rebuilt) and expect the
     simulated application to fail with no residue in the Civil collections.
  2. Apply the typology for real on --corredor, verify, save the copy through COM,
     close it, reopen it and verify again from the stored contract.
Never run on a project drawing; the copy name must start with CDCRD_QA_TIPOLOGIAS.
"""
import argparse, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import win32com.client, win32process
import puente_cliente as bridge
import tipologias
from humo_tipologias import guard, qa_job

COLLECTIONS = ("corredores", "ensamblajes", "subensamblajes", "superficies")


def inventory():
    return {c: bridge.llamar("objects.query", {"coleccion": c, "props": ["Name"], "limite": 1000})["coincidencias"] for c in COLLECTIONS}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--drawing", required=True); p.add_argument("--pid", type=int, required=True)
    p.add_argument("--corredor", required=True); p.add_argument("--segmentos", required=True)
    p.add_argument("--terreno", default=""); p.add_argument("--fallo", default="corridor-rebuilt")
    p.add_argument("--comando"); p.add_argument("--qa-comando", default="CDCRDTIPOLOGIASV1QA")
    p.add_argument("--reanudar", action="store_true", help="skip fault and application: the corridor is already applied")
    a = p.parse_args()
    if a.comando: tipologias.COMMAND = a.comando
    import humo_tipologias; humo_tipologias.QA_COMMAND = a.qa_comando
    bridge.TIMEOUT = 120
    folder = Path(a.drawing).resolve().parent
    dest = folder / f"tipologias-persistencia-{a.corredor}.json"
    if dest.exists(): raise FileExistsError(dest)
    report = {"ok": False, "steps": []}
    def record(): dest.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    segments = json.loads(a.segmentos)
    guard(a.drawing)
    if a.reanudar: report["steps"].append({"resumed": True}); record()
    # 1. injected failure: explicit error and no residue
    before = inventory() if not a.reanudar else None
    if not a.reanudar:
        armed = qa_job(folder, dict(action="fault", stage=a.fallo, output=f"tipologias-fault-{a.corredor}-{a.fallo}.json"))
        report["steps"].append({"armed": armed}); record()
        try:
            tipologias.ejecutar(a.drawing, a.pid, accion="aplicar", corredor=a.corredor, segmentos=segments, superficie_terreno=a.terreno)
            raise AssertionError("Injected failure was not reported")
        except tipologias.TipologiaError as exc:
            if "CDCRD_QA_TIPOLOGIA_FAILURE:" + a.fallo not in str(exc): raise
            report["steps"].append({"fault": str(exc), "inventory_before": before, "inventory_after": inventory()}); record()
            assert report["steps"][-1]["inventory_after"] == before, "Residue after injected failure"
        # 2. real application (receipt carries the in-transaction check and the post-commit one), save, reopen, verification
        applied = tipologias.ejecutar(a.drawing, a.pid, accion="aplicar", simular=False, corredor=a.corredor, segmentos=segments, superficie_terreno=a.terreno)
        assert applied["committed"]
        result = applied["result"]
        report["steps"].append({"applied": result["aplicado"]["verificacion"], "after_commit": result["verificacion_tras_confirmar"], "regiones": result["aplicado"]["regiones"]}); record()
    # The command end leaves the corridor flagged out of date; rebuild in a command of its own, then verify.
    settled = tipologias.ejecutar(a.drawing, a.pid, accion="reconstruir", simular=False, corredor=a.corredor)
    report["steps"].append({"settled": settled["result"]}); record()
    verified = tipologias.ejecutar(a.drawing, a.pid, accion="verificar", corredor=a.corredor)
    report["steps"].append({"verified": verified["result"]}); record()
    app = win32com.client.GetActiveObject("AutoCAD.Application")
    if win32process.GetWindowThreadProcessId(app.HWND)[1] != a.pid: raise RuntimeError("COM connected to another process")
    doc = app.ActiveDocument
    if os.path.normcase(doc.FullName) != os.path.normcase(str(Path(a.drawing).resolve())) or not app.GetAcadState().IsQuiescent:
        raise RuntimeError("Wrong document or active command")
    doc.Save(); doc.Close(False)
    time.sleep(2)
    app.Documents.Open(str(Path(a.drawing).resolve()))
    for _ in range(300):
        try:
            if app.GetAcadState().IsQuiescent and os.path.normcase(app.ActiveDocument.FullName) == os.path.normcase(str(Path(a.drawing).resolve())): break
        except Exception: pass
        time.sleep(1)
    guard(a.drawing)
    reopened = tipologias.ejecutar(a.drawing, a.pid, accion="verificar", corredor=a.corredor)
    report["steps"].append({"reopened": reopened["result"]}); record()
    report["ok"] = True; record()
    print(json.dumps({"fault": None if a.reanudar else a.fallo, "verified": verified["result"], "reopened": reopened["result"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
