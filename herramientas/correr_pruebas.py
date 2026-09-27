# -*- coding: utf-8 -*-
"""Descubre y corre los autotests --test de todas las verificaciones.

Solo usa la biblioteca estandar. Se ejecuta con el mismo Python que invoca
este corredor y devuelve codigo distinto de cero ante cualquier falla.
"""

import subprocess
import sys
from pathlib import Path


def main():
    scripts = sorted(Path(__file__).resolve().parent.glob("verificacion_*.py"))
    if not scripts:
        print("ERROR: no se encontraron herramientas verificacion_*.py")
        return 1
    fallos = []
    for script in scripts:
        try:
            proceso = subprocess.run([sys.executable, str(script), "--test"],
                                     capture_output=True, text=True, timeout=60,
                                     cwd=str(script.parent), check=False)
            ok = proceso.returncode == 0
            detalle = (proceso.stdout + proceso.stderr).strip()
        except subprocess.TimeoutExpired:
            ok, detalle = False, "timeout de 60 s"
        print(("OK" if ok else "FALLO") + "  " + script.name)
        if detalle:
            print(detalle)
        if not ok:
            fallos.append(script.name)
    print("Resumen: %d/%d autotests aprobados" % (len(scripts) - len(fallos), len(scripts)))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
