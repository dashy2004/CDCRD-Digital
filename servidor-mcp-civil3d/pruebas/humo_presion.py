"""Native smoke for the pressure module on an identified disposable copy.

Stages (one per invocation, receipts next to the copy; never retries a write):
  cargar     NETLOAD the module in the existing Civil process.
  catalogo   Pressure parts lists, part sizes and existing pressure networks of the open drawing.
  cotas      Surface elevations at points given in a JSON file [[x, y], ...].
  red        Simulate (default) or commit the explicit network from a JSON file {nodos, tuberias}.
  verificar  Re-read the stored contract of one pressure network.
  trazado    Experimental pipe run from a path JSON file [[x, y], ...] with bends added by Civil.
The copy name must start with CDCRD_QA_PRESION; the drawing must be the active document.
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import puente_cliente as bridge
import presion

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT / "modulo-presion/bin/Release/net10.0-windows/Cdcrd.Presion.V1.dll"


def guard(drawing):
    info = bridge.llamar("doc.info")
    if not info.get("civil3d") or Path(info["dibujo"]).resolve() != Path(drawing).resolve() or info["insunits"] != 6:
        raise RuntimeError("Wrong Civil document or units: " + str(info.get("dibujo")))
    if not Path(drawing).name.startswith("CDCRD_QA_PRESION"):
        raise RuntimeError("An identified disposable copy is required")
    if bridge.llamar("diag.dialogos")["modal_abierto"] or bridge.llamar("diag.cola")["activas"]:
        raise RuntimeError("Busy; inspect state before any further write")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--drawing", required=True); p.add_argument("--pid", type=int, required=True)
    p.add_argument("--etapa", required=True, choices=["cargar", "catalogo", "cotas", "red", "verificar", "trazado"])
    p.add_argument("--lista-partes", default=""); p.add_argument("--superficie", default=""); p.add_argument("--puntos"); p.add_argument("--red", default="")
    p.add_argument("--nodos", help="JSON file {nodos, tuberias}"); p.add_argument("--nombre", default="CDCRD QA PRESION"); p.add_argument("--capa", default="CDCRD-PRESION")
    p.add_argument("--sin-conectar", action="store_true"); p.add_argument("--sin-rotar", action="store_true"); p.add_argument("--confirmar", action="store_true")
    p.add_argument("--ruta"); p.add_argument("--familia", default="PVC"); p.add_argument("--diametro", type=float, default=6); p.add_argument("--cobertura", type=float, default=1.0)
    p.add_argument("--etiqueta", default=""); p.add_argument("--modulo-dll"); p.add_argument("--comando")
    a = p.parse_args()
    global MODULE
    if a.modulo_dll: MODULE = Path(a.modulo_dll)
    if a.comando: presion.COMMAND = a.comando
    folder = Path(a.drawing).resolve().parent
    bridge.TIMEOUT = 120
    guard(a.drawing)
    if a.etapa == "cargar":
        # FILEDIA 0 keeps NETLOAD on the command line; a dialog would block the bridge.
        lisp = '(progn (setq cdcrd_fd (getvar "FILEDIA")) (setvar "FILEDIA" 0) (command "_.NETLOAD" "' + str(MODULE).replace("\\", "/") + '") (setvar "FILEDIA" cdcrd_fd) (princ))'
        bridge.llamar_con_aprobacion("cmd.run", {"linea": lisp + "\n"})
        print("NETLOAD enqueued:", MODULE.name); return
    label = a.etiqueta or a.etapa
    dest = folder / f"presion-{label}.json"
    if dest.exists(): raise FileExistsError(dest)
    report = {"ok": False, "stage": a.etapa}
    def record(): dest.write_text(json.dumps(report, indent=1, ensure_ascii=False), encoding="utf-8")
    try:
        if a.etapa == "catalogo":
            r = presion.ejecutar(a.drawing, a.pid, accion="catalogo", lista_partes=a.lista_partes or None)
            report["result"] = r; record()
            for pl in r["result"]["listas_partes"]:
                print("lista", pl["nombre"], "tuberias", len(pl["tuberias"]), "accesorios", len(pl["accesorios"]), "aparatos", len(pl["aparatos"]))
                for s in pl["tuberias"]: print("  TUB", s["descripcion"], s["propiedades"].get("DiameterNominal"), s["propiedades"].get("PipeDiameterOutside"), s["propiedades"].get("IdMaterial"))
                for s in pl["accesorios"]: print("  ACC", s["tipo"], s["descripcion"], "DN", s["propiedades"].get("DiameterNominal"), "ang", s["propiedades"].get("FittingAngle"), "bocas", s["propiedades"].get("ConnectionPointCount"))
                for s in pl["aparatos"]: print("  APA", s["tipo"], s["descripcion"], "DN", s["propiedades"].get("DiameterNominal"), "bocas", s["propiedades"].get("ConnectionPointCount"))
            print("redes", r["result"]["redes"])
        elif a.etapa == "cotas":
            r = presion.ejecutar(a.drawing, a.pid, accion="cotas", superficie=a.superficie, puntos=json.load(open(a.puntos, encoding="utf-8")))
            report["result"] = r; record(); print(json.dumps(r["result"], ensure_ascii=False)[:1500])
        elif a.etapa == "red":
            spec = json.load(open(a.nodos, encoding="utf-8"))
            r = presion.ejecutar(a.drawing, a.pid, accion="crear", simular=not a.confirmar, nombre=a.nombre, capa=a.capa, lista_partes=a.lista_partes or None,
                                 superficie=a.superficie or None, conectar=not a.sin_conectar, rotar=not a.sin_rotar, nodos=spec["nodos"], tuberias=spec["tuberias"], timeout=600)
            report["result"] = r; record()
            v = r["result"]["verificacion"]
            print("committed", r["committed"], json.dumps({k: v[k] for k in v if not k.startswith("detalle")}, ensure_ascii=False))
            for n in v["detalle_nodos"]: print("  nodo", json.dumps(n, ensure_ascii=False)[:400])
            for t in v["detalle_tuberias"]: print("  tub", t["id"], t["inicio"], t["fin"], "L", round(t["longitud_2d_m"], 3), "ext", t["exterior_m"], "piezas", t["inicio_pieza"], t["fin_pieza"])
        elif a.etapa == "verificar":
            r = presion.ejecutar(a.drawing, a.pid, accion="verificar", red=a.red)
            report["result"] = r; record(); v = r["result"]
            print(json.dumps({k: v[k] for k in v if not k.startswith("detalle")}, ensure_ascii=False))
        elif a.etapa == "trazado":
            r = presion.ejecutar(a.drawing, a.pid, accion="trazado", simular=not a.confirmar, nombre=a.nombre, capa=a.capa, lista_partes=a.lista_partes or None,
                                 superficie=a.superficie, cobertura_m=a.cobertura, familia=a.familia, diametro_nominal=a.diametro, ruta=json.load(open(a.ruta, encoding="utf-8")), timeout=600)
            report["result"] = r; record(); print(json.dumps(r["result"], ensure_ascii=False)[:3000])
        report["ok"] = True; record()
    except presion.PresionError as exc:
        report["error"] = str(exc); report["receipt"] = exc.receipt; record(); print("ERROR", str(exc)[:3000]); sys.exit(1)


if __name__ == "__main__":
    main()
