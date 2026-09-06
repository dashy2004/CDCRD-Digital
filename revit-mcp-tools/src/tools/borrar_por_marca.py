# -*- coding: utf-8 -*-
"""borrar_por_marca: borra todo lo que un agente creo con una marca en Comments (y datums por nombre).

Es la mitad que hace idempotente al resto: cada tool de creacion marca lo suyo
(AGENTE:COL, AGENTE:VIGA, AGENTE:LOSA, AGENTE:MURO, AGENTE:ZAP); esta tool lo
encuentra y lo borra sin tocar nada mas. Regla E-044: el script que sabe que
creo, limpia solo; no se le pide al operador que purgue a mano.

Parametros:
  marker:          prefijo de Comments a borrar ("AGENTE:" borra todo lo marcado). Opcional si
                   se dan nombres de datums.
  categorias:      alias a revisar (default columnas, vigas, losas, muros, zapatas, acero, rooms).
  ejes_nombres:    ejes a borrar por nombre (los datums no tienen Comments).
  niveles_nombres: niveles a borrar por nombre. OJO: borrar un nivel arrastra todo lo que
                   hospeda; por eso van al final y solo si se piden explicitamente.
  dry_run:         True solo cuenta (default True).
Devuelve conteo por categoria antes y despues.
"""


def run(doc, uidoc, DB, P):
    marker = P.get("marker")
    ejes = P.get("ejes_nombres") or []
    niveles = P.get("niveles_nombres") or []
    if not marker and not ejes and not niveles:
        raise Exception("falta 'marker' (o ejes_nombres / niveles_nombres)")
    dry = bool(P.get("dry_run", True))
    cats = P.get("categorias") or ["columnas", "vigas", "losas", "muros", "zapatas", "acero", "rooms"]
    E = errs()
    found = {}
    ids = []
    if marker:
        for alias in cats:
            try:
                n = 0
                for e in collector(doc, bic_of(alias)):
                    try:
                        if has_mark(e, marker):
                            ids.append(e.Id)
                            n += 1
                    except Exception as ex:
                        note(E, "mark", ex)
                found[alias] = n
            except Exception as ex:
                note(E, "cat " + alias, ex)
    datum_ids = []
    if ejes:
        gs = dict((g.Name, g) for g in DB.FilteredElementCollector(doc).OfClass(DB.Grid))
        found["ejes"] = [n for n in ejes if n in gs]
        found["ejes_inexistentes"] = [n for n in ejes if n not in gs]
        datum_ids.extend(gs[n].Id for n in found["ejes"])
    if niveles:
        ls = dict((l.Name, l) for l in DB.FilteredElementCollector(doc).OfClass(DB.Level))
        found["niveles"] = [n for n in niveles if n in ls]
        found["niveles_inexistentes"] = [n for n in niveles if n not in ls]
        datum_ids.extend(ls[n].Id for n in found["niveles"])
    out = {"dry_run": dry, "marker": marker, "encontrados": found, "total": len(ids) + len(datum_ids), "excepciones": E}
    if dry or (not ids and not datum_ids):
        return out
    if uidoc is not None and datum_ids:
        # si la vista activa es la planta de un nivel a borrar, salir de ella antes
        try:
            av = uidoc.ActiveView
            if hasattr(av, "GenLevel") and av.GenLevel is not None and av.GenLevel.Id in datum_ids:
                leave_view(doc, uidoc, [av.Id])
        except Exception as ex:
            note(E, "vista activa", ex)

    def work():
        n = 0
        if ids:
            d = doc.Delete(id_list(ids))
            n += len(list(d)) if d is not None else 0
        if datum_ids:
            d = doc.Delete(id_list(datum_ids))
            n += len(list(d)) if d is not None else 0
        return n
    out["borrados_incluyendo_dependientes"] = tx(doc, "tools: borrar por marca", work)
    after = {}
    if marker:
        for alias in cats:
            try:
                after[alias] = sum(1 for e in collector(doc, bic_of(alias)) if has_mark(e, marker))
            except Exception as ex:
                note(E, "after " + alias, ex)
    out["quedan"] = after
    out["ok"] = sum(after.values()) == 0
    return out
