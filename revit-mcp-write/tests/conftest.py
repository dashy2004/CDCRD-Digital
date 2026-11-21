# -*- coding: utf-8 -*-
"""Pone revit-mcp-write (carpeta del paquete mep) y tests en sys.path."""
import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parents[1]
for carpeta in (str(RAIZ), str(RAIZ / "tests")):
    if carpeta not in sys.path:
        sys.path.insert(0, carpeta)
