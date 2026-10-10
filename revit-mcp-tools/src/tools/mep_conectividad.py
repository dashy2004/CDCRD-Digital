# -*- coding: utf-8 -*-
"""Audita conectores MEP fisicos abiertos y disponibilidad de sistemas.
Hallazgos para revision, no incumplimientos normativos. Solo lectura.
"""


def run(doc, uidoc, DB, P):
    return mep_audit(doc, DB, P, True)
