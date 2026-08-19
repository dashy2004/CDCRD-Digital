# -*- coding: utf-8 -*-
"""Corrige tipos de zapata: espesor de la 17x10 y creacion del tipo Z3.

DOS CORRECCIONES, DECIDIDAS POR EL OPERADOR (2026-08-14)
--------------------------------------------------------
1. El tipo cuya zapata mide 17.00 x 10.00 m tiene `Foundation Thickness` =
   1.40 m y el plano pide 1.50 m. Se corrige a 1.50.
2. No existe el tipo `Z3` (6.50 x 6.50 x 1.40). Se crea duplicando un tipo de
   `Footing-Rectangular` existente. **Las instancias las coloca el operador**,
   este script solo deja el tipo listo.

NO se renombran tipos. Los nombres del modelo estan corridos respecto del
plano (dos combinadas comparten `Z5`, la de 17x10 se llama `Z6` siendo la Z7),
y se decidio armar por DIMENSIONES, no por nombre. Renombrar afectaria tablas
de planificacion y anotaciones existentes.

CUIDADO CON LOS PARAMETROS DE TIPO
----------------------------------
`Foundation Thickness`, `Length` y `Width` son parametros de TIPO. Cambiar uno
afecta a TODAS las instancias de ese tipo. Antes de tocar el espesor, el script
cuenta cuantas instancias tiene el tipo y lo informa: si fueran mas de las
esperadas, el operador cancela.

GUARDAS (E-039, E-041, E-044, E-046)
------------------------------------
- Antes de duplicar, BUSCA si el tipo ya existe por nombre. Nunca usa un
  `except` generico como fallback de "ya existe" (E-041).
- Verifica ademas la FAMILIA del tipo hallado, no solo el nombre (E-044).
- `Duplicate()` devuelve ElementType: se castea explicitamente (E-039).
- Toda escritura se RELEE y se compara. Discrepancia = error, no aviso (E-046).
"""
__title__ = "TiposZapata"
__doc__ = "Corrige espesor de la zapata 17x10 y crea el tipo Z3. No coloca instancias."

import os
import json
import traceback

from pyrevit import revit, script, forms
from pyrevit.api import DB

doc = revit.doc

FAMILIA = "Footing-Rectangular"
M = 0.3048  # pies -> metros

# --- lo que hay que lograr, en metros ---
ESPESOR_OBJETIVO_17x10 = 1.50
Z3_NOMBRE = "Z3"
Z3_LX, Z3_LY, Z3_H = 6.50, 6.50, 1.40
TOL = 0.005  # 5 mm

BASE = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
LOG_DIR = os.path.join(BASE, "_log")
if not os.path.isdir(LOG_DIR):
    os.makedirs(LOG_DIR)
TRACE = os.path.join(LOG_DIR, "tipos_zapata_trace.log")
OUT_JSON = os.path.join(LOG_DIR, "tipos_zapata.json")

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


def eidv(element_id):
    try:
        return int(element_id.Value)
    except AttributeError:
        return int(element_id.IntegerValue)


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


def par(el, nombre):
    return el.LookupParameter(nombre)


def leer_m(el, nombre):
    p = par(el, nombre)
    return p.AsDouble() * M if p is not None else None


result = {
    "ok": False,
    "phase_reached": "inicio",
    "document": doc.Title,
    "espesor": {"aplicado": False},
    "tipo_z3": {"creado": False},
    "error": None,
}

trace("=== inicio: %s ===" % doc.Title)

try:
    # ---- Fase 1: mapa de tipos de zapata --------------------------------
    result["phase_reached"] = "fase1_tipos"
    trace("FASE 1: tipos de %s" % FAMILIA)

    tipos = {}
    for sym in (DB.FilteredElementCollector(doc)
                .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
                .WhereElementIsElementType()):
        try:
            fam = sym.Family.Name
        except Exception:
            continue
        if fam != FAMILIA:
            continue
        nom = element_name(sym)
        tipos[nom] = {
            "sym": sym,
            "lx": leer_m(sym, "Length"),
            "ly": leer_m(sym, "Width"),
            "h": leer_m(sym, "Foundation Thickness"),
        }
    trace("FASE 1 OK: %d tipos" % len(tipos))
    if not tipos:
        raise Exception("no hay tipos de la familia '%s'" % FAMILIA)

    # instancias por tipo, para saber a cuantas afecta cada cambio
    inst_por_tipo = {}
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
               .WhereElementIsNotElementType()):
        sym = doc.GetElement(el.GetTypeId())
        nom = element_name(sym)
        inst_por_tipo[nom] = inst_por_tipo.get(nom, 0) + 1

    # ---- Fase 2: el tipo de 17x10 --------------------------------------
    # Se identifica por DIMENSIONES, no por nombre: los nombres estan corridos.
    result["phase_reached"] = "fase2_espesor"
    trace("FASE 2: buscando el tipo de 17.00 x 10.00 por dimensiones")
    objetivo = None
    for nom, t in tipos.items():
        if t["lx"] is None or t["ly"] is None:
            continue
        dims = sorted([round(t["lx"], 2), round(t["ly"], 2)])
        if dims == [10.0, 17.0]:
            objetivo = (nom, t)
            break

    if objetivo is None:
        result["espesor"]["motivo"] = "no se hallo un tipo de 17.00 x 10.00 m"
        trace("FASE 2: NO HALLADO — se salta la correccion de espesor")
    else:
        nom, t = objetivo
        n_inst = inst_por_tipo.get(nom, 0)
        result["espesor"].update({
            "tipo": nom, "h_actual": t["h"], "h_objetivo": ESPESOR_OBJETIVO_17x10,
            "instancias_afectadas": n_inst,
        })
        trace("FASE 2: tipo '%s' h=%.3f -> %.3f | %d instancia(s)"
              % (nom, t["h"] or 0, ESPESOR_OBJETIVO_17x10, n_inst))

        if abs((t["h"] or 0) - ESPESOR_OBJETIVO_17x10) < TOL:
            result["espesor"]["motivo"] = "ya estaba en el valor objetivo"
            trace("FASE 2: ya estaba correcto, no se toca")
        else:
            msg = ("Tipo '%s' (%.2f x %.2f m)\n\n"
                   "  Foundation Thickness: %.3f m  ->  %.3f m\n\n"
                   "Es un parametro de TIPO: afecta a sus %d instancia(s).\n\n"
                   "¿Aplicar?" % (nom, t["lx"], t["ly"], t["h"] or 0,
                                  ESPESOR_OBJETIVO_17x10, n_inst))
            if not forms.alert(msg, title="Corregir espesor", yes=True, no=True):
                trace("FASE 2: operador cancelo")
                result["espesor"]["motivo"] = "cancelado por el operador"
            else:
                tr = DB.Transaction(doc, "MCP: espesor zapata 17x10")
                tr.Start()
                try:
                    p = par(t["sym"], "Foundation Thickness")
                    if p is None or p.IsReadOnly:
                        raise Exception("'Foundation Thickness' ausente o de solo lectura")
                    p.Set(ESPESOR_OBJETIVO_17x10 / M)
                    tr.Commit()
                except Exception as ex:
                    tr.RollBack()
                    raise Exception("no se pudo fijar el espesor: %s" % ex)

                # E-046: releer y comparar. Una escritura que no lanza no es
                # una escritura que aplico.
                leido = leer_m(t["sym"], "Foundation Thickness")
                result["espesor"]["h_releido"] = leido
                if leido is None or abs(leido - ESPESOR_OBJETIVO_17x10) > TOL:
                    raise Exception("el espesor no aplico: releido %s, esperado %.3f"
                                    % (leido, ESPESOR_OBJETIVO_17x10))
                result["espesor"]["aplicado"] = True
                trace("FASE 2 OK: releido %.4f m" % leido)

    # ---- Fase 3: el tipo Z3 ---------------------------------------------
    result["phase_reached"] = "fase3_tipo_z3"
    trace("FASE 3: tipo %s" % Z3_NOMBRE)

    # E-041/E-044: buscar por nombre ANTES de duplicar, y verificar la familia
    # del que se encuentre. Un nombre coincidente no prueba que sea el objeto
    # que uno cree.
    existente = tipos.get(Z3_NOMBRE)
    if existente is not None:
        try:
            fam_ok = existente["sym"].Family.Name == FAMILIA
        except Exception:
            fam_ok = False
        if not fam_ok:
            raise Exception("ya existe un tipo '%s' que NO es de la familia '%s'. "
                            "Abortado para no reutilizar el objeto equivocado."
                            % (Z3_NOMBRE, FAMILIA))
        result["tipo_z3"].update({
            "ya_existia": True, "id": eidv(existente["sym"].Id),
            "lx": existente["lx"], "ly": existente["ly"], "h": existente["h"],
        })
        trace("FASE 3: '%s' ya existe (%.2f x %.2f x %.2f)"
              % (Z3_NOMBRE, existente["lx"] or 0, existente["ly"] or 0,
                 existente["h"] or 0))
    else:
        base_nom, base_t = sorted(tipos.items())[0]
        trace("FASE 3: duplicando '%s' para crear '%s'" % (base_nom, Z3_NOMBRE))
        tr = DB.Transaction(doc, "MCP: crear tipo Z3")
        tr.Start()
        try:
            nuevo = base_t["sym"].Duplicate(Z3_NOMBRE)
            # E-039: Duplicate devuelve ElementType, no el subtipo.
            if not isinstance(nuevo, DB.ElementType):
                raise Exception("Duplicate devolvio %s" % type(nuevo).__name__)
            for nombre_p, valor_m in (("Length", Z3_LX), ("Width", Z3_LY),
                                      ("Foundation Thickness", Z3_H)):
                p = par(nuevo, nombre_p)
                if p is None or p.IsReadOnly:
                    raise Exception("'%s' ausente o de solo lectura" % nombre_p)
                p.Set(valor_m / M)
            tr.Commit()
        except Exception as ex:
            tr.RollBack()
            raise Exception("no se pudo crear el tipo Z3: %s" % ex)

        # Relectura obligatoria de las tres dimensiones
        rel = {"lx": leer_m(nuevo, "Length"), "ly": leer_m(nuevo, "Width"),
               "h": leer_m(nuevo, "Foundation Thickness")}
        esperado = {"lx": Z3_LX, "ly": Z3_LY, "h": Z3_H}
        malas = [k for k in esperado
                 if rel[k] is None or abs(rel[k] - esperado[k]) > TOL]
        result["tipo_z3"].update({
            "creado": True, "id": eidv(nuevo.Id), "duplicado_de": base_nom,
            "releido": rel, "esperado": esperado,
        })
        if malas:
            raise Exception("el tipo Z3 quedo con dimensiones equivocadas en %s: "
                            "releido %s, esperado %s" % (malas, rel, esperado))
        trace("FASE 3 OK: Z3 creado, releido %s" % json.dumps(rel))

    result["phase_reached"] = "completo"
    result["ok"] = True

except Exception:
    result["error"] = traceback.format_exc()
    trace("EXCEPCION GLOBAL:\n%s" % result["error"])

with open(OUT_JSON, "w") as fh:
    json.dump(result, fh, indent=2)
    fh.flush()
    os.fsync(fh.fileno())

trace("=== fin: phase=%s ok=%s ===" % (result["phase_reached"], result["ok"]))

out.print_md("### Tipos de zapata")
out.print_md("- Fase alcanzada: `%s`" % result["phase_reached"])
e = result["espesor"]
if e.get("tipo"):
    out.print_md("- Espesor `%s`: %.3f -> %.3f m | aplicado: **%s** %s"
                 % (e["tipo"], e.get("h_actual") or 0, e.get("h_objetivo") or 0,
                    e["aplicado"], "(%s)" % e["motivo"] if e.get("motivo") else ""))
else:
    out.print_md("- Espesor: %s" % e.get("motivo", "no evaluado"))
z = result["tipo_z3"]
if z.get("ya_existia"):
    out.print_md("- Tipo `Z3`: **ya existia** (%.2f x %.2f x %.2f m)"
                 % (z.get("lx") or 0, z.get("ly") or 0, z.get("h") or 0))
elif z.get("creado"):
    r = z["releido"]
    out.print_md("- Tipo `Z3`: **creado** — %.2f x %.2f x %.2f m (releido)"
                 % (r["lx"], r["ly"], r["h"]))
    out.print_md("  - Coloca las 2 instancias en Revit; despues las armo")
out.print_md("- **ok: %s**" % result["ok"])
out.print_md("- JSON: `%s`" % OUT_JSON)
if result["error"]:
    out.print_md("- ❌ **ERROR** — ver trace")
