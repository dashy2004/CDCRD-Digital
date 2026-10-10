# -*- coding: utf-8 -*-
"""Inventario MEP de solo lectura por categorias y sistemas observados.
No incluye vinculos. max_details limita detalles, nunca los conteos.
"""


def run(doc, uidoc, DB, P):
    return mep_audit(doc, DB, P, False)
