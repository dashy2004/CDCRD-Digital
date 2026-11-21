"""Native smoke for the session documents module, on disposable drawings only.

One action per invocation; the receipt stays in %LOCALAPPDATA%/CdcrdCivil3dBridge/documentos.
Opening, activating and closing accept only drawings whose name starts with CDCRD_QA, so a
typo can never close someone's working drawing. Never retries.
"""
import argparse, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import documentos
from transporte import ReciboError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--pid", type=int, required=True)
    p.add_argument("--accion", required=True, choices=documentos.ACCIONES)
    p.add_argument("--ruta", default=""); p.add_argument("--solo-lectura", action="store_true")
    p.add_argument("--descartar-cambios", action="store_true"); p.add_argument("--activar-despues", default="")
    p.add_argument("--comando", help="alias of a rebuilt module, e.g. CDCRDDOCUMENTOSV1B")
    a = p.parse_args()
    if a.comando: documentos.COMMAND = a.comando
    if a.accion != "listar" and not Path(a.ruta).name.startswith("CDCRD_QA"):
        raise SystemExit("Only drawings named CDCRD_QA* are opened, activated or closed by this smoke")
    datos = {}
    if a.accion == "abrir": datos = dict(ruta=a.ruta, solo_lectura=a.solo_lectura)
    elif a.accion == "activar": datos = dict(ruta=a.ruta)
    elif a.accion == "cerrar": datos = dict(ruta=a.ruta, descartar_cambios=a.descartar_cambios, activar_despues=a.activar_despues or None)
    try:
        r = documentos.ejecutar(a.pid, accion=a.accion, **datos)
    except ReciboError as exc:
        print("ERROR", str(exc)); print(json.dumps(exc.receipt, ensure_ascii=False)[:2000]); sys.exit(1)
    print(json.dumps(r, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
