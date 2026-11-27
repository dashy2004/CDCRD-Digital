# -*- coding: utf-8 -*-
"""Trazado MEP con conexion verificada para Revit 2027.

Python puro: la API de Revit se inyecta (DB, doc). Cuatro operaciones:
auditar_conectores (lectura), conectar_a_ramal, crear_circuitos y
distribucion_del_tablero (escritura con ensayo por defecto). Contrato en
el README.
"""

from .auditoria import auditar_conectores
from .base import ErrorApi, ErrorEntrada
from .circuitos import crear_circuitos
from .tablero import distribucion_del_tablero
from .trazado import conectar_a_ramal

__all__ = ["auditar_conectores", "conectar_a_ramal", "crear_circuitos",
           "distribucion_del_tablero",
           "ErrorApi", "ErrorEntrada"]
