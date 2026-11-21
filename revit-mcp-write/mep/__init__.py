# -*- coding: utf-8 -*-
"""Trazado MEP con conexion verificada para Revit 2027.

Python puro: la API de Revit se inyecta (DB, doc). Tres operaciones:
auditar_conectores (lectura), conectar_a_ramal y crear_circuitos
(escritura con ensayo por defecto). Contrato en el README.
"""

from .auditoria import auditar_conectores
from .base import ErrorApi, ErrorEntrada
from .circuitos import crear_circuitos
from .trazado import conectar_a_ramal

__all__ = ["auditar_conectores", "conectar_a_ramal", "crear_circuitos",
           "ErrorApi", "ErrorEntrada"]
