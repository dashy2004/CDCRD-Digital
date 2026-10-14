"""Arnes de Invocar/Coerce/IsSimple de puente/Handlers.cs sin Civil 3D.

Extrae esos tres metodos tal cual estan en Handlers.cs, los compila con el SDK .NET 10
junto a Arnes.cs (fixtures que imitan PointLocation/StationOffset con ref) y corre 8
comprobaciones. Uso: py correr.py  (requiere `dotnet` 10 en el PATH).
"""
import re
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
HANDLERS = AQUI.parents[1] / "puente" / "Handlers.cs"


def metodo(s, firma):
    i = s.index(firma)
    j = s.index("\n        }\n", i) + len("\n        }\n")
    k = s.rfind("\n        private static", 0, i) + 1
    return s[k:j]


def main():
    s = HANDLERS.read_text(encoding="utf-8")
    partes = [metodo(s, "object Invocar(object obj, string nombre"),
              metodo(s, "object Coerce(object json"), metodo(s, "bool IsSimple(Type t)")]
    cuerpo = "\n".join(partes)
    (AQUI / "Extracto.cs").write_text(
        "using System;\nusing System.Collections.Generic;\nusing System.Linq;\nusing System.Reflection;\n"
        "namespace Arnes {\nstatic partial class H {\n" + cuerpo + "\n}}\n", encoding="utf-8")
    dotnet = shutil.which("dotnet")
    if not dotnet:
        print("dotnet no esta en el PATH"); return 2
    r = subprocess.run([dotnet, "build", "-v", "q", "-nologo", str(AQUI)], capture_output=True, text=True)
    print(r.stdout[-1500:], r.stderr[-500:])
    if r.returncode:
        return r.returncode
    r = subprocess.run([dotnet, "run", "--no-build", "--project", str(AQUI)], capture_output=True, text=True)
    print(r.stdout)
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
