# -*- coding: utf-8 -*-
"""Baja las zapatas aisladas a su cota de proyecto.

EL PROBLEMA
-----------
Las zapatas Z1..Z4 estan modeladas con su cara superior en 0.00 (nivel
CIMIENTOS). Segun la tabla de armado, cada una tiene una profundidad de
desplante Df que deja la cara superior 30 cm por debajo del nivel:

    Z1: h=1.20  Df=1.50  ->  fondo -1.50, tope -0.30
    Z2: h=1.20  Df=1.50  ->  fondo -1.50, tope -0.30
    Z3: h=1.40  Df=1.70  ->  fondo -1.70, tope -0.30
    Z4: h=1.50  Df=1.80  ->  fondo -1.80, tope -0.30

En las cuatro el desplazamiento es **-0.30 m exacto**, que es el relleno que
muestra el detalle SZ5 entre el terreno y la cara superior de la zapata.
Que las cuatro den el mismo numero no es casualidad: es el dato del dibujo.

COMO SE MUEVE
-------------
Por `Height Offset From Level`, no por `MoveElement`: asi la zapata conserva
su relacion con el nivel CIMIENTOS y el cambio es un parametro legible, no un
desplazamiento opaco.

EL ACERO
--------
Las zapatas ya estan armadas. Si las barras tienen constraints al anfitrion,
siguen al host solas. **No se asume**: el script mide la cota del acero ANTES
y DESPUES, y si no se movio, lo mueve. Y lo reporta en las dos direcciones.

QUE NO TOCA
-----------
- `ZC Perimetral 0.80x0.30` (12): su tabla no da Df. Sin dato no se mueve.
- `6" Foundation Slab` (3): el bbox da 1.50 m de espesor para lo que el nombre
  dice que son 6 pulgadas. Hay algo que no cierra ahi y mover a ciegas seria
  peor que no mover.

GUARDAS
-------
- Identifica por TIPO contra una tabla explicita. Lo que no esta, no se toca.
- Pide confirmacion mostrando cuantas y cuanto.
- Verifica RELEYENDO la cota real, no el parametro escrito (E-046).
- Idempotente: si ya esta en la cota correcta, la saltea.
"""
__title__ = "MoverZapatas"
__doc__ = "Baja las zapatas Z1..Z4 a su cota de desplante. Verifica el acero."

import os
import json
import traceback

from pyrevit import revit, script, forms
from pyrevit.api import DB
from System.Collections.Generic import List

doc = revit.doc
M = 0.3048
TOL = 0.005                      # 5 mm

# tipo -> (espesor h, desplante Df) en metros, segun la tabla del proyecto
# y `00_DATOS/zapatas.csv` para las combinadas.
PLAN = {
    "Z1": (1.20, 1.50),
    "Z2": (1.20, 1.50),
    "Z3": (1.40, 1.70),
    "Z4": (1.50, 1.80),
    "Z5": (1.20, 1.50),      # combinada 6.00 x 9.00
    "Z6": (1.20, 1.50),      # combinada 6.00 x 9.00
    "Z7": (1.50, 1.80),      # combinada 17.00 x 10.00
}

# Guarda contra nombres corridos: antes de mover, se comprueba que el espesor
# REAL coincida con el `h` que la tabla atribuye a ese nombre. Ya paso en este
# proyecto que un tipo llamado `Z6` midiera lo que la tabla asigna a `Z7`
# (2026-08-14). Si el espesor no coincide, NO se mueve y se reporta: mover una
# zapata la cota equivocada por confiar en su nombre es peor que no moverla.
TOL_ESPESOR = 0.02               # 2 cm


def _slug(txt):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_"
                   for ch in (txt or "SIN_DOC"))[:60]


BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "mover_zapatas_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "mover_zapatas_%s.json" % _slug(doc.Title))

out = script.get_output()

try:
    if os.path.isfile(TRACE):
        os.remove(TRACE)
except Exception:
    pass


def trace(msg):
    with open(TRACE, "a") as fh:
        fh.write("%s\n" % msg)
        fh.flush()
        os.fsync(fh.fileno())


def eidv(e):
    try:
        return int(e.Value)
    except AttributeError:
        return int(e.IntegerValue)


def element_name(el):
    if el is None:
        return None
    try:
        return el.Name
    except Exception:
        pass
    try:
        return DB.Element.Name.GetValue(el)
    except Exception:
        return None


def fondo_de(el):
    bb = el.get_BoundingBox(None)
    return bb.Min.Z * M if bb is not None else None


result = {
    "ok": False, "phase_reached": "inicio", "document": doc.Title,
    "movidas": [], "ya_ok": [], "no_tocadas": {}, "fallos": [],
    "acero": {"siguio_solo": 0, "hubo_que_mover": 0, "sin_acero": 0},
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: clasificar ----------------------------------------------
    result["phase_reached"] = "fase1_clasificacion"
    acero = {}
    for rb in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_Rebar)
               .WhereElementIsNotElementType()):
        try:
            acero.setdefault(eidv(rb.GetHostId()), []).append(rb)
        except Exception:
            continue

    objetivo = []
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
               .WhereElementIsNotElementType()):
        sym = doc.GetElement(el.GetTypeId())
        tipo = element_name(sym)
        if tipo not in PLAN:
            result["no_tocadas"][tipo] = result["no_tocadas"].get(tipo, 0) + 1
            continue
        h, df = PLAN[tipo]
        bb = el.get_BoundingBox(None)
        if bb is None:
            result["fallos"].append({"id": eidv(el.Id), "motivo": "sin bbox"})
            continue
        fondo = bb.Min.Z * M
        h_real = (bb.Max.Z - bb.Min.Z) * M

        # el nombre dice una cosa, el espesor tiene que confirmarla
        if abs(h_real - h) > TOL_ESPESOR:
            result["fallos"].append({
                "id": eidv(el.Id), "tipo": tipo,
                "motivo": "espesor real %.3f m no coincide con el %.2f m que la "
                          "tabla asigna a '%s'. No se mueve: el nombre puede "
                          "estar corrido." % (h_real, h, tipo)})
            trace("  %d (%s): espesor %.3f != %.2f -> NO se mueve"
                  % (eidv(el.Id), tipo, h_real, h))
            continue

        delta = (-df) - fondo               # cuanto hay que bajar, en metros
        objetivo.append((el, tipo, fondo, -df, delta))

    a_mover = [o for o in objetivo if abs(o[4]) > TOL]
    result["ya_ok"] = [{"id": eidv(o[0].Id), "tipo": o[1], "fondo_m": o[2]}
                       for o in objetivo if abs(o[4]) <= TOL]
    trace("FASE 1 OK: %d objetivo, %d a mover, %d ya bien"
          % (len(objetivo), len(a_mover), len(result["ya_ok"])))

    if not a_mover:
        raise Exception("todas las zapatas Z1..Z4 ya estan en su cota. "
                        "No hay nada que mover.")

    # ---- Fase 2: confirmacion --------------------------------------------
    result["phase_reached"] = "fase2_confirmacion"
    import collections
    resumen = collections.Counter("%s: %+.2f m" % (o[1], o[4]) for o in a_mover)
    msg = ("Se van a bajar %d zapatas:\n\n%s\n\n"
           "Metodo: parametro 'Height Offset From Level'.\n"
           "El acero de cada zapata se verifica despues: si no siguio\n"
           "al anfitrion, se mueve tambien.\n\n"
           "NO se tocan: %s\n\n¿Aplicar?"
           % (len(a_mover),
              "\n".join("  %s  x%d" % (k, v) for k, v in sorted(resumen.items())),
              ", ".join("%s (%d)" % (k, v)
                        for k, v in sorted(result["no_tocadas"].items()))))
    if not forms.alert(msg, title="Bajar zapatas a su desplante",
                       yes=True, no=True, warn_icon=True):
        raise Exception("cancelado por el operador")
    trace("FASE 2 OK: confirmado")

    # ---- Fase 3: mover, una transaccion por zapata ------------------------
    result["phase_reached"] = "fase3_movimiento"
    for el, tipo, fondo_ant, fondo_obj, delta in a_mover:
        zid = eidv(el.Id)
        barras = acero.get(zid, [])
        # cota del acero ANTES, para saber despues si siguio al host
        z_acero_ant = None
        if barras:
            bb = barras[0].get_BoundingBox(None)
            z_acero_ant = bb.Min.Z * M if bb is not None else None
        else:
            result["acero"]["sin_acero"] += 1

        t = DB.Transaction(doc, "MCP: bajar zapata %d" % zid)
        t.Start()
        try:
            p = el.LookupParameter("Height Offset From Level")
            if p is None or p.IsReadOnly:
                raise Exception("'Height Offset From Level' ausente o de solo lectura")
            p.Set(p.AsDouble() + delta / M)
            doc.Regenerate()

            # E-046: releer la COTA REAL, no el parametro que uno escribio
            fondo_new = fondo_de(el)
            if fondo_new is None or abs(fondo_new - fondo_obj) > TOL:
                raise Exception("la zapata no quedo en cota: %s vs %.3f esperado"
                                % (fondo_new, fondo_obj))

            # el acero, ¿siguio?
            movio_acero = False
            if barras and z_acero_ant is not None:
                bb = barras[0].get_BoundingBox(None)
                z_acero_new = bb.Min.Z * M if bb is not None else None
                siguio = (z_acero_new is not None
                          and abs((z_acero_new - z_acero_ant) - delta) < TOL)
                if siguio:
                    result["acero"]["siguio_solo"] += 1
                    trace("  %d: el acero siguio al host" % zid)
                else:
                    ids = List[DB.ElementId]()
                    for rb in barras:
                        ids.Add(rb.Id)
                    DB.ElementTransformUtils.MoveElements(
                        doc, ids, DB.XYZ(0, 0, delta / M))
                    doc.Regenerate()
                    result["acero"]["hubo_que_mover"] += 1
                    movio_acero = True
                    trace("  %d: el acero NO siguio, se movio a mano (%d sets)"
                          % (zid, len(barras)))
            t.Commit()
            result["movidas"].append({
                "id": zid, "tipo": tipo,
                "fondo_antes_m": fondo_ant, "fondo_ahora_m": fondo_new,
                "delta_m": delta, "sets_acero": len(barras),
                "acero_movido_a_mano": movio_acero,
            })
        except Exception as ex:
            t.RollBack()
            result["fallos"].append({"id": zid, "tipo": tipo, "motivo": str(ex)})
            trace("  %d ROLLBACK: %s" % (zid, traceback.format_exc()))

    # ---- Fase 4: verificacion final por relectura -------------------------
    result["phase_reached"] = "fase4_verificacion"
    correctas = 0
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
               .WhereElementIsNotElementType()):
        sym = doc.GetElement(el.GetTypeId())
        tipo = element_name(sym)
        if tipo not in PLAN:
            continue
        f = fondo_de(el)
        if f is not None and abs(f - (-PLAN[tipo][1])) <= TOL:
            correctas += 1
    result["verificacion"] = {
        "zapatas_en_cota": correctas,
        "objetivo": len(objetivo),
        "coincide": correctas == len(objetivo),
    }
    trace("FASE 4 OK: %s" % json.dumps(result["verificacion"]))

    result["phase_reached"] = "completo"
    result["ok"] = not result["fallos"] and result["verificacion"]["coincide"]

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Bajar zapatas a su desplante")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
out.print_md("- Movidas: **%d** | ya estaban en cota: %d"
             % (len(result["movidas"]), len(result["ya_ok"])))
for m in result["movidas"]:
    out.print_md("  - `%s` id %s: fondo %.2f → %.2f m (%+.2f) | %d sets%s"
                 % (m["tipo"], m["id"], m["fondo_antes_m"], m["fondo_ahora_m"],
                    m["delta_m"], m["sets_acero"],
                    " — acero movido a mano" if m["acero_movido_a_mano"] else ""))
a = result["acero"]
out.print_md("- Acero: siguió solo **%d** | hubo que mover **%d** | sin acero %d"
             % (a["siguio_solo"], a["hubo_que_mover"], a["sin_acero"]))
if result["no_tocadas"]:
    out.print_md("- No tocadas: %s"
                 % ", ".join("%s (%d)" % (k, v)
                             for k, v in sorted(result["no_tocadas"].items())))
v = result.get("verificacion")
if v:
    out.print_md("- Verificado: %d de %d en cota | **coincide: %s**"
                 % (v["zapatas_en_cota"], v["objetivo"], v["coincide"]))
if result["fallos"]:
    out.print_md("- ⚠️ **fallos: %d**" % len(result["fallos"]))
out.print_md("- **ok: %s**" % result["ok"])
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
