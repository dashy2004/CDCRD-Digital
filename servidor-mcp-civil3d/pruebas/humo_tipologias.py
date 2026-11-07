"""Native smoke for the typology module on an identified disposable copy.

Stages (one per invocation, receipts next to the copy; never retries a write):
  cargar     NETLOAD the module and the QA harness in the existing Civil process.
  avisos     Reproduce an operation while counting "Add param returned null!"
             first-chance exceptions (modes side_describe, live_describe, run_parts, rebuild).
  clasificar Classify the edges of the given corridors; optionally compare with a
             reference JSON [{handle, segments:[[from,to,kind],...]}].
  aplicar    Simulate (default) or commit the typology on one corridor.
  verificar  Re-read the stored contract of one corridor.
The copy name must start with CDCRD_QA_TIPOLOGIAS; the drawing must be the active document.
"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import puente_cliente as bridge
import tipologias

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modulo-tipologias/bin/Release/net10.0-windows/Cdcrd.Tipologias.V1.dll"
QA = ROOT / "pruebas/native_tipologias_qa/bin/Release/net10.0-windows/Cdcrd.TipologiasV1Qa.dll"
QA_COMMAND = "CDCRDTIPOLOGIASV1QA"


def guard(drawing):
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or Path(info["dibujo"]).resolve() != Path(drawing).resolve() or info["insunits"] != 6:
        raise RuntimeError("Wrong Civil document or units: " + str(info.get("dibujo")))
    if not Path(drawing).name.startswith("CDCRD_QA_TIPOLOGIAS"):
        raise RuntimeError("An identified disposable copy is required")
    if bridge.llamar("diag.dialogos")["modal_abierto"] or bridge.llamar("diag.cola")["activas"]:
        raise RuntimeError("Busy; inspect state before any further write")


def receipt(folder, name):
    dest = folder / name
    if dest.exists(): raise FileExistsError(dest)
    return dest


def wait(dest, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if dest.exists():
            try: return json.loads(dest.read_text(encoding="utf-8-sig"))
            except json.JSONDecodeError: pass
        time.sleep(.2)
    raise RuntimeError("Native receipt missing; inspect queue and command state, do not retry")


def qa_job(folder, job, timeout=600):
    dest = receipt(folder, job["output"])
    (folder / "tipologias-qa.json").write_text(json.dumps(job), encoding="utf-8")
    bridge.llamar_con_aprobacion("cmd.run", {"linea": QA_COMMAND + "\n"})
    return wait(dest, timeout)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--drawing", required=True); p.add_argument("--pid", type=int, required=True)
    p.add_argument("--etapa", required=True, choices=["cargar", "avisos", "clasificar", "aplicar", "reconstruir", "verificar"])
    p.add_argument("--modo", default="side_describe"); p.add_argument("--corredores", default="[]")
    p.add_argument("--pavimento", default="[]"); p.add_argument("--excluidas", default="[]")
    p.add_argument("--sonda", type=float, default=1.0); p.add_argument("--referencia")
    p.add_argument("--segmentos"); p.add_argument("--terreno", default=""); p.add_argument("--origen", default="")
    p.add_argument("--confirmar", action="store_true"); p.add_argument("--etiqueta", default="")
    p.add_argument("--qa-dll"); p.add_argument("--qa-comando"); p.add_argument("--modulo-dll"); p.add_argument("--comando")
    a = p.parse_args()
    global QA, QA_COMMAND, MODULE
    if a.qa_dll: QA = Path(a.qa_dll)
    if a.modulo_dll: MODULE = Path(a.modulo_dll)
    if a.comando: tipologias.COMMAND = a.comando
    if a.qa_comando: QA_COMMAND = a.qa_comando
    folder = Path(a.drawing).resolve().parent
    bridge.TIMEOUT = 120
    guard(a.drawing)
    corridors = json.loads(a.corredores)
    label = a.etiqueta or a.etapa
    if a.etapa == "cargar":
        for path in (MODULE, QA):
            # FILEDIA 0 keeps NETLOAD on the command line; a dialog would block the bridge.
            lisp = '(progn (setq cdcrd_fd (getvar "FILEDIA")) (setvar "FILEDIA" 0) (command "_.NETLOAD" "' + str(path).replace("\\", "/") + '") (setvar "FILEDIA" cdcrd_fd) (princ))'
            bridge.llamar_con_aprobacion("cmd.run", {"linea": lisp + "\n"})
        print("NETLOAD enqueued:", MODULE.name, QA.name)
        return
    if a.etapa == "avisos":
        out = qa_job(folder, dict(action="avisos", mode=a.modo, corridors=corridors, output=f"tipologias-avisos-{a.modo}{label}.json"))
        print(json.dumps({k: v for k, v in out.items() if k != "samples"}, ensure_ascii=False))
        for s in out.get("samples", []): print("--- sample", s["part"], s["type"]); print(s["stack"])
        return
    report = {"ok": False, "stage": a.etapa, "results": []}
    dest = receipt(folder, f"tipologias-{label}.json")
    def record(): dest.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    try:
        if a.etapa == "clasificar":
            reference = {r["handle"].upper(): r["segments"] for r in json.load(open(a.referencia, encoding="utf-8"))} if a.referencia else {}
            for h in corridors:
                r = tipologias.ejecutar(a.drawing, a.pid, accion="clasificar", corredor=h, sonda_m=a.sonda,
                                        superficies_pavimento=json.loads(a.pavimento), superficies_excluidas=json.loads(a.excluidas))
                res = r["result"]; row = dict(handle=h, nombre=res["nombre"], codigo=res["codigo_borde"], segmentos=res["segmentos"], lados=res["lados"])
                if h.upper() in reference:
                    ref = reference[h.upper()]
                    row["referencia"] = ref
                    row["coincide"] = [[round(x, 2) if isinstance(x, float) else x for x in s] for s in res["segmentos"]] == [[round(x, 2) if isinstance(x, float) else x for x in s] for s in ref]
                report["results"].append(row); record()
                print(h, res["nombre"], "segmentos", res["segmentos"], "coincide", row.get("coincide"))
        elif a.etapa == "aplicar":
            r = tipologias.ejecutar(a.drawing, a.pid, accion="aplicar", simular=not a.confirmar, corredor=corridors[0],
                                    segmentos=json.loads(a.segmentos), superficie_terreno=a.terreno, origen=a.origen or None)
            report["results"].append(r); record()
            res = r["result"]; print("committed", r["committed"])
            print(json.dumps(res.get("verificacion_tras_confirmar") or res["verificacion"], ensure_ascii=False))
        else:
            r = tipologias.ejecutar(a.drawing, a.pid, accion=a.etapa, corredor=corridors[0], simular=False)
            report["results"].append(r); record(); print(json.dumps(r["result"], ensure_ascii=False))
        report["ok"] = True; record()
    except tipologias.TipologiaError as exc:
        report["error"] = str(exc); report["receipt"] = exc.receipt; record(); raise


if __name__ == "__main__":
    main()
