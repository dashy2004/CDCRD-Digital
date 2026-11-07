"""Native smoke for the cubicacion module on an identified disposable copy.

Stages (one per invocation, receipts next to the copy; never retries a write):
  cargar      NETLOAD the module and the QA harness in the existing Civil process.
  leer        Read assemblies, lanes, thicknesses, surfaces and the stored contract.
  espesores   Simulate (default) or commit the thicknesses on one corridor.
  datum       Simulate (default) or commit the Datum surface of one corridor.
  cubicacion  Simulate (default) or commit terrain/Datum volumes and layer volumes.
  fallo       Arm a one-shot failure at a QaCheckpoint stage, run the action and
              verify the explicit error plus an unchanged inventory (leer before/after).
The copy name must start with CDCRD_QA_CUBICACION; the drawing must be the active document.
"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import puente_cliente as bridge
import cubicacion

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modulo-cubicacion/bin/Release/net10.0-windows/Cdcrd.Cubicacion.V1.dll"
QA = ROOT / "pruebas/native_cubicacion_qa/bin/Release/net10.0-windows/Cdcrd.CubicacionV1Qa.dll"
QA_COMMAND = "CDCRDCUBICACIONV1QA"
THICKNESS = {"Pave1Depth": .075, "Pave2Depth": .05, "BaseDepth": .25, "SubBaseDepth": .35}


def guard(drawing):
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or Path(info["dibujo"]).resolve() != Path(drawing).resolve() or info["insunits"] != 6:
        raise RuntimeError("Wrong Civil document or units: " + str(info.get("dibujo")))
    if not Path(drawing).name.startswith("CDCRD_QA_CUBICACION"):
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


def inventory(drawing, pid, corridor):
    """Read-only snapshot used to prove a rolled-back failure left nothing behind."""
    read = cubicacion.ejecutar(drawing, pid, accion="leer", corredor=corridor)["result"]
    surfaces = bridge.llamar("objects.query", {"coleccion": "superficies", "limite": 500})
    return dict(leer=read, superficies=sorted(r["handle"] for r in surfaces["objetos"]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--drawing", required=True); p.add_argument("--pid", type=int, required=True)
    p.add_argument("--etapa", required=True, choices=["cargar", "leer", "espesores", "datum", "cubicacion", "fallo"])
    p.add_argument("--corredor", default=""); p.add_argument("--terreno", default=""); p.add_argument("--datum", default=""); p.add_argument("--nombre-volumen", default="")
    p.add_argument("--espesores", default=json.dumps(THICKNESS)); p.add_argument("--regiones", default="[]")
    p.add_argument("--tolerancia-m", type=float, default=.001)
    p.add_argument("--confirmar", action="store_true"); p.add_argument("--etiqueta", default="")
    p.add_argument("--fallo-accion", default="espesores"); p.add_argument("--fallo-etapa", default="corridor-rebuilt")
    p.add_argument("--qa-dll"); p.add_argument("--qa-comando"); p.add_argument("--modulo-dll"); p.add_argument("--comando")
    a = p.parse_args()
    global QA, QA_COMMAND, MODULE
    if a.qa_dll: QA = Path(a.qa_dll)
    if a.modulo_dll: MODULE = Path(a.modulo_dll)
    if a.comando: cubicacion.COMMAND = a.comando
    if a.qa_comando: QA_COMMAND = a.qa_comando
    folder = Path(a.drawing).resolve().parent
    bridge.TIMEOUT = 120
    guard(a.drawing)
    label = a.etiqueta or a.etapa
    if a.etapa == "cargar":
        for path in (MODULE, QA):
            # FILEDIA 0 keeps NETLOAD on the command line; a dialog would block the bridge.
            lisp = '(progn (setq cdcrd_fd (getvar "FILEDIA")) (setvar "FILEDIA" 0) (command "_.NETLOAD" "' + str(path).replace("\\", "/") + '") (setvar "FILEDIA" cdcrd_fd) (princ))'
            bridge.llamar_con_aprobacion("cmd.run", {"linea": lisp + "\n"})
        print("NETLOAD enqueued:", MODULE.name, QA.name)
        return
    report = {"ok": False, "stage": a.etapa, "results": []}
    dest = receipt(folder, f"cubicacion-{label}.json")
    def record(): dest.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    def run(action, **extra):
        return cubicacion.ejecutar(a.drawing, a.pid, accion=action, corredor=a.corredor, **extra)
    def args_for(action):
        if action == "espesores": return dict(simular=not a.confirmar, espesores=json.loads(a.espesores), regiones=json.loads(a.regiones), tolerancia_m=a.tolerancia_m)
        if action == "datum": return dict(simular=not a.confirmar)
        if action == "cubicacion": return dict(simular=not a.confirmar, terreno=a.terreno, datum=a.datum or None, nombre_volumen=a.nombre_volumen or None)
        raise ValueError(action)
    try:
        if a.etapa == "leer":
            r = run("leer"); report["results"].append(r); record()
            res = r["result"]
            print(json.dumps({k: v for k, v in res.items() if k != "ensamblajes"}, ensure_ascii=False))
            for asm in res["ensamblajes"]: print("ensamblaje", asm["handle"], asm["nombre"], [(l["nombre"], l["espesores"]) for l in asm["carriles"]])
        elif a.etapa == "fallo":
            before = inventory(a.drawing, a.pid, a.corredor); report["before"] = before; record()
            armed = receipt(folder, f"cubicacion-fallo-armado-{label}.json")
            (folder / "cubicacion-qa.json").write_text(json.dumps(dict(stage=a.fallo_etapa, output=armed.name)), encoding="utf-8")
            bridge.llamar_con_aprobacion("cmd.run", {"linea": QA_COMMAND + "\n"})
            report["armed"] = wait(armed, 60); record()
            try:
                r = run(a.fallo_accion, **dict(args_for(a.fallo_accion), simular=False))
                report["unexpected"] = r; record()
                raise AssertionError("The armed failure did not fire")
            except cubicacion.CubicacionError as exc:
                report["error"] = str(exc); report["receipt"] = exc.receipt; record()
                if "CDCRD_QA_CUBICACION_FAILURE:" + a.fallo_etapa not in str(exc): raise
            after = inventory(a.drawing, a.pid, a.corredor); report["after"] = after; record()
            same = json.dumps(before, sort_keys=True) == json.dumps(after, sort_keys=True)
            report["inventory_unchanged"] = same; record()
            print("fallo inyectado:", report["error"]); print("inventario igual:", same)
            if not same: raise AssertionError("Inventory changed after the rolled-back failure")
        else:
            r = run(a.etapa, **args_for(a.etapa)); report["results"].append(r); record()
            res = r["result"]; print("committed", r["committed"], "reconstruccion", r.get("reconstruccion", {}).get("result", {}).get("fuera_de_fecha"))
            print(json.dumps(res.get("verificacion_tras_confirmar") or res.get("verificacion") or res.get("volumen"), ensure_ascii=False))
            if a.etapa == "cubicacion": print(json.dumps(res["capas"], ensure_ascii=False))
        report["ok"] = True; record()
    except cubicacion.CubicacionError as exc:
        if "error" not in report: report["error"] = str(exc); report["receipt"] = exc.receipt; record()
        raise


if __name__ == "__main__":
    main()
