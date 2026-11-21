"""Native smoke for the catchments module on an identified disposable copy.

One stage per invocation; receipts stay in %LOCALAPPDATA%/CdcrdCivil3dBridge/cuencas. Never retries a write.
  listar      Every catchment, or one (--cuenca).
  crear       Simulate (default) or commit a catchment from --contorno (JSON file) or --polilinea (handle).
  actualizar  Simulate (default) or commit parameter changes on --cuenca.
The drawing name must start with CDCRD_QA and be the active document.
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import puente_cliente as bridge
import cuencas
from transporte import ReciboError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--drawing", required=True); p.add_argument("--pid", type=int, required=True)
    p.add_argument("--etapa", required=True, choices=cuencas.ACCIONES)
    p.add_argument("--cuenca", default=""); p.add_argument("--nombre", default="QA-C1"); p.add_argument("--grupo", default="QA"); p.add_argument("--superficie", default="")
    p.add_argument("--contorno"); p.add_argument("--polilinea", default=""); p.add_argument("--estilo", default="")
    p.add_argument("--coeficiente", type=float); p.add_argument("--tc", type=float); p.add_argument("--metodo-tc", default=""); p.add_argument("--numero-curva", type=int)
    p.add_argument("--trayectoria", help="JSON file [[x, y], ...]"); p.add_argument("--estructura", default="")
    p.add_argument("--confirmar", action="store_true"); p.add_argument("--comando")
    a = p.parse_args()
    if a.comando: cuencas.COMMAND = a.comando
    if not Path(a.drawing).name.startswith("CDCRD_QA"): raise SystemExit("An identified disposable copy is required")
    if Path(bridge.llamar("doc.info")["dibujo"]).resolve() != Path(a.drawing).resolve(): raise SystemExit("The disposable copy is not the active document")
    extra = dict(coeficiente_escorrentia=a.coeficiente, tc_min=a.tc, metodo_tc=a.metodo_tc or None, numero_curva=a.numero_curva, estructura=a.estructura or None,
                 trayectoria=json.load(open(a.trayectoria, encoding="utf-8")) if a.trayectoria else None)
    try:
        if a.etapa == "listar":
            r = cuencas.ejecutar(a.drawing, a.pid, accion="listar", cuenca=a.cuenca or None)
        elif a.etapa == "crear":
            r = cuencas.ejecutar(a.drawing, a.pid, accion="crear", simular=not a.confirmar, nombre=a.nombre, grupo=a.grupo, superficie=a.superficie, estilo=a.estilo or None,
                                 contorno=json.load(open(a.contorno, encoding="utf-8")) if a.contorno else None, polilinea=a.polilinea or None, **extra)
        else:
            r = cuencas.ejecutar(a.drawing, a.pid, accion="actualizar", simular=not a.confirmar, cuenca=a.cuenca, superficie=a.superficie or None, **extra)
    except ReciboError as exc:
        print("ERROR", str(exc)[:3000]); sys.exit(1)
    print("committed", r["committed"]); print(json.dumps(r["result"], indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
