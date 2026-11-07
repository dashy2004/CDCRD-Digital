"""Native smoke for the drainage module on an identified disposable copy.

Stages (one per invocation, receipts next to the copy; never retries a write):
  cargar     NETLOAD the module and the QA harness in the existing Civil process.
  catalogo   Parts lists, families and sizes of the open drawing.
  cuencas    Gutter feature lines of one corridor and the inlet proposal (rational method).
  red        Simulate (default) or commit the gravity network from a nodes JSON file.
  verificar  Re-read the stored contract of one network.
The copy name must start with CDCRD_QA_DRENAJE; the drawing must be the active document.
"""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import puente_cliente as bridge
import drenaje

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modulo-drenaje/bin/Release/net10.0-windows/Cdcrd.Drenaje.V1.dll"
QA = ROOT / "pruebas/native_drenaje_qa/bin/Release/net10.0-windows/Cdcrd.DrenajeV1Qa.dll"
QA_COMMAND = "CDCRDDRENAJEV1QA"


def guard(drawing):
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or Path(info["dibujo"]).resolve() != Path(drawing).resolve() or info["insunits"] != 6:
        raise RuntimeError("Wrong Civil document or units: " + str(info.get("dibujo")))
    if not Path(drawing).name.startswith("CDCRD_QA_DRENAJE"):
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


def qa_job(folder, job, timeout=120):
    dest = receipt(folder, job["output"])
    (folder / "drenaje-qa.json").write_text(json.dumps(job), encoding="utf-8")
    bridge.llamar_con_aprobacion("cmd.run", {"linea": QA_COMMAND + "\n"})
    return wait(dest, timeout)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--drawing", required=True); p.add_argument("--pid", type=int, required=True)
    p.add_argument("--etapa", required=True, choices=["cargar", "catalogo", "cuencas", "red", "verificar"])
    p.add_argument("--corredor", default=""); p.add_argument("--red", default=""); p.add_argument("--lista-partes", default="")
    p.add_argument("--intensidad", type=float, default=120); p.add_argument("--espaciamiento", type=float, default=60)
    p.add_argument("--ancho", type=float, default=8); p.add_argument("--coeficiente", type=float, default=.9); p.add_argument("--codigo", default="Flowline_Gutter")
    p.add_argument("--nodos", help="JSON file with the design nodes"); p.add_argument("--nombre", default="CDCRD QA DRENAJE")
    p.add_argument("--familia-tuberia", default="Concrete Pipe"); p.add_argument("--familia-imbornal", default=""); p.add_argument("--familia-pozo", default="")
    p.add_argument("--diametros", default="[300, 375, 450, 525, 600]"); p.add_argument("--pendiente-min", type=float, default=.005)
    p.add_argument("--profundidad-min", type=float, default=1.0); p.add_argument("--sumidero", type=float, default=0.0); p.add_argument("--capa", default="CDCRD-DRENAJE")
    p.add_argument("--confirmar", action="store_true"); p.add_argument("--etiqueta", default="")
    p.add_argument("--qa-dll"); p.add_argument("--qa-comando"); p.add_argument("--modulo-dll"); p.add_argument("--comando")
    a = p.parse_args()
    global QA, QA_COMMAND, MODULE
    if a.qa_dll: QA = Path(a.qa_dll)
    if a.modulo_dll: MODULE = Path(a.modulo_dll)
    if a.comando: drenaje.COMMAND = a.comando
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
    dest = receipt(folder, f"drenaje-{label}.json")
    def record(): dest.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    try:
        if a.etapa == "catalogo":
            r = drenaje.ejecutar(a.drawing, a.pid, accion="catalogo", lista_partes=a.lista_partes or None)
            report["results"].append(r); record()
            for pl in r["result"]["listas_partes"]:
                print("lista", pl["nombre"])
                for fam in pl["tuberias"]: print("  tuberia", fam["nombre"], [(s["nombre"], s["diametro_interior_m"]) for s in fam["tamanios"]])
                for fam in pl["estructuras"]: print("  estructura", fam["nombre"], fam["tipo"], [s["nombre"] for s in fam["tamanios"]][:6])
            print("redes", r["result"]["redes"])
        elif a.etapa == "cuencas":
            r = drenaje.proponer(a.drawing, a.pid, a.corredor, intensidad_mm_h=a.intensidad, espaciamiento_max_m=a.espaciamiento, ancho_aporte_m=a.ancho, coeficiente_c=a.coeficiente, codigo=a.codigo)
            report["results"].append(r); record()
            print(json.dumps(dict(lineas=r["lineas"], puntos=r["puntos"], codigos=r["codigos_disponibles"], resumen=r["propuesta"]["resumen"]), ensure_ascii=False))
            for c in r["propuesta"]["cunetas"]:
                print(c["lado"], "L=%.1f" % c["longitud_m"], "crestas", [round(x["estacion"], 1) for x in c["crestas"]], "bajos", [round(x["estacion"], 1) for x in c["puntos_bajos"]],
                      "imbornales", [(i["id"], round(i["estacion"], 1), round(i["q_m3_s"], 4)) for i in c["imbornales"]])
        elif a.etapa == "red":
            nodes = json.loads(Path(a.nodos).read_text(encoding="utf-8"))
            familias = dict(tuberia=dict(familia=a.familia_tuberia), imbornal=dict(familia=a.familia_imbornal), pozo=dict(familia=a.familia_pozo), salida=dict(familia=a.familia_pozo))
            design, structures, pipes = drenaje.disenar(nodes, familias, diametros_mm=json.loads(a.diametros), pendiente_min=a.pendiente_min, profundidad_min_m=a.profundidad_min, sumidero_m=a.sumidero)
            report["design"] = design; record()
            print(json.dumps(design["resumen"], ensure_ascii=False)); print("advertencias", design["advertencias"])
            r = drenaje.ejecutar(a.drawing, a.pid, accion="crear", simular=not a.confirmar, nombre=a.nombre, capa=a.capa, lista_partes=a.lista_partes or None,
                                 pendiente_min=a.pendiente_min, profundidad_min_m=a.profundidad_min, estructuras=structures, tuberias=pipes)
            report["results"].append(r); record()
            v = r["result"]["verificacion"]
            print("committed", r["committed"], json.dumps({k: v[k] for k in v if not k.startswith("detalle")}, ensure_ascii=False))
        else:
            r = drenaje.ejecutar(a.drawing, a.pid, accion="verificar", red=a.red)
            report["results"].append(r); record()
            v = r["result"]; print(json.dumps({k: v[k] for k in v if not k.startswith("detalle")}, ensure_ascii=False))
        report["ok"] = True; record()
    except drenaje.DrenajeError as exc:
        report["error"] = str(exc); report["receipt"] = exc.receipt; record(); raise


if __name__ == "__main__":
    main()
