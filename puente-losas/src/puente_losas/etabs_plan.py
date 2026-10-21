"""Plan de export a ETABS vía el servidor MCP ``fea`` (servidor-mcp de CDCRD-Digital).

Esta tarea NO toca ETABS vivo: genera un plan JSON —una lista ordenada de
llamadas a tools reales del servidor ``fea``— para que una sesión con el turno
de ETABS reclamado (lock de ``_coordinacion/locks``) lo ejecute paso a paso.

Reglas aplicadas (prompt "Modelar en ETABS desde AutoCAD" de la Ing. Arlette
Ramírez, 14/10/2026):
- Unidades Ton, m, °C.
- Material C210 con sus constantes en tonf/m² (E=2 188 197.76, peso 2.4028).
- TODAS las losas Modeling Type = Shell-Thick (nunca Membrane/Shell-Thin).
- Biblioteca de losas L12/L15/L20 macizas y aligeradas L25A-1D/2D.
- Geometría en múltiplos de 0.05 m (ajuste coherente; se reporta la desviación).
- Sets de carga por uso (acabados Dead + viva), mampostería aparte ya redondeada
  hacia arriba a 0.05; el peso propio lo aporta el patrón Dead (multiplicador 1),
  no se duplica como carga superficial.

Las llamadas sin tool dedicada van por ``call_oapi`` con la instrucción expresa
de confirmar la firma con ``describe_oapi`` antes de ejecutar (los enteros de
los enums de CSI no se dan por sabidos).
"""
from __future__ import annotations

import datetime as _dt
import json

from puente_losas.motor import ResultadoPano

UNIDADES_ETABS = "Ton, m, C"

# Biblioteca de losas de Arlette: h total, topping, ancho de nervio y separación (m).
BIBLIOTECA_LOSAS: dict[str, dict] = {
    "L12": {"tipo": "Slab", "h": 0.12},
    "L15": {"tipo": "Slab", "h": 0.15},
    "L20": {"tipo": "Slab", "h": 0.20},
    "L20A-1D": {"tipo": "Ribbed", "h": 0.20, "topping": 0.05, "ancho_nervio": 0.15, "separacion": 0.65},
    "L20A-2D": {"tipo": "Waffle", "h": 0.20, "topping": 0.05, "ancho_nervio": 0.15, "separacion": 0.65},
    "L25A-1D": {"tipo": "Ribbed", "h": 0.25, "topping": 0.05, "ancho_nervio": 0.20, "separacion": 0.65},
    "L25A-2D": {"tipo": "Waffle", "h": 0.25, "topping": 0.05, "ancho_nervio": 0.20, "separacion": 0.65},
}

C210 = {"name": "C210", "fc": 2100.0, "E": 2188197.76, "poisson": 0.20, "unit_weight": 2.4028}


def ajustar_005(x: float) -> float:
    """Múltiplo de 0.05 más cercano (regla de modelado; no es el redondeo del Excel)."""
    return round(round(x / 0.05) * 0.05, 10)


def _contorno_ajustado(contorno: list[list[float]], z: float) -> tuple[dict, float]:
    xs = [ajustar_005(p[0]) for p in contorno]
    ys = [ajustar_005(p[1]) for p in contorno]
    desv = max((abs(a - b[0]) for a, b in zip(xs, contorno)), default=0.0)
    desv = max(desv, max((abs(a - b[1]) for a, b in zip(ys, contorno)), default=0.0))
    return {"type": "surface", "xs": xs, "ys": ys, "zs": [ajustar_005(z)] * len(xs)}, desv


def _paso(tool: str, args: dict, nota: str = "", verificar: str = "") -> dict:
    paso = {"tool": tool, "args": args}
    if nota:
        paso["nota"] = nota
    if verificar:
        paso["verificar"] = verificar
    return paso


def plan_etabs(resultados: list[ResultadoPano], proyecto: str = "Proyecto Ejemplo") -> dict:
    """Compone el plan completo de export para los paños analizados."""
    pasos: list[dict] = [
        _paso("set_units", {"units": UNIDADES_ETABS},
              "Unidades de trabajo del flujo de Arlette; fijar ANTES de crear nada."),
        _paso("define_concrete_material", dict(C210),
              "C210 del prompt (tonf/m²): f'c 2100, E 2 188 197.76, peso 2.4028 tonf/m³."),
        _paso("add_load_pattern", {"name": "Dead", "pattern_type": "muerta", "self_weight_multiplier": 1.0}),
        _paso("add_load_pattern", {"name": "Live", "pattern_type": "viva", "self_weight_multiplier": 0.0}),
    ]
    patrones = {c.cargas.patron_viva for c in resultados}
    if "LiveT" in patrones:
        pasos.append(_paso("add_load_pattern", {"name": "LiveT", "pattern_type": "viva_techo",
                                                "self_weight_multiplier": 0.0}))
    if "LiveP" in patrones:
        pasos.append(_paso("add_load_pattern", {"name": "LiveP", "pattern_type": "viva",
                                                "self_weight_multiplier": 0.0},
                           "Solo porque el proyecto tiene parqueos (regla del §7 de Arlette)."))

    # Secciones de losa usadas, todas Shell-Thick (regla dura de Arlette).
    secciones = {}
    for r in resultados:
        secciones[r.espesor.seccion_etabs] = r.espesor.seccion_nueva
    for nombre in sorted(secciones):
        definicion = BIBLIOTECA_LOSAS.get(nombre)
        if definicion is None:
            pasos.append(_paso("call_oapi", {"path": "PropArea", "method": "SetSlab", "args": []},
                               f"'{nombre}' NO está en la biblioteca: definición nueva según el "
                               "esquema. NO inventar nervios: consultar h/topping/nervios y "
                               "completar args. Shell-Thick obligatorio.",
                               "describe_oapi('PropArea','SetSlab') y los enums eSlabType/eShellType"))
            continue
        args_nombrados = {"Name": nombre, "SlabType": definicion["tipo"],
                          "ShellType": "ShellThick", "MatProp": "C210",
                          "Thickness": definicion["h"]}
        paso = _paso("call_oapi",
                     {"path": "PropArea", "method": "SetSlab",
                      "args_nombrados": args_nombrados},
                     "Convertir los enums a sus enteros reales ANTES de llamar; "
                     "ShellThick es obligatorio para TODAS las losas (nunca Membrane/Thin).",
                     "describe_oapi('PropArea','SetSlab'); enums eSlabType y eShellType")
        pasos.append(paso)
        if definicion["tipo"] in ("Ribbed", "Waffle"):
            metodo = "SetSlabRibbed" if definicion["tipo"] == "Ribbed" else "SetSlabWaffle"
            pasos.append(_paso("call_oapi",
                               {"path": "PropArea", "method": metodo,
                                "args_nombrados": {"Name": nombre, "OverallDepth": definicion["h"],
                                                   "SlabThickness": definicion["topping"],
                                                   "StemWidthTop": definicion["ancho_nervio"],
                                                   "StemWidthBot": definicion["ancho_nervio"],
                                                   "RibSpacing": definicion["separacion"]}},
                               "Nervios de la biblioteca: anchos iguales arriba/abajo, separación "
                               "eje a eje. En Ribbed los nervios siguen el eje local 1: validar "
                               "con Show Slab Rib tras crear.",
                               f"describe_oapi('PropArea','{metodo}')"))

    # Geometría: una superficie por paño, coordenadas en múltiplos de 0.05.
    desv_max = 0.0
    objetos = []
    aberturas = []
    for r in resultados:
        contorno = r.pano.contorno or [[0.0, 0.0], [r.pano.lx, 0.0],
                                       [r.pano.lx, r.pano.ly], [0.0, r.pano.ly]]
        obj, desv = _contorno_ajustado(contorno, r.pano.z_tope)
        obj["ref"] = r.pano.mark
        desv_max = max(desv_max, desv)
        objetos.append(obj)
        for k, hueco in enumerate(r.pano.huecos, start=1):
            hobj, desv_h = _contorno_ajustado(hueco, r.pano.z_tope)
            hobj["ref"] = f"{r.pano.mark}-HUECO{k}"
            desv_max = max(desv_max, desv_h)
            aberturas.append(hobj)
    pasos.append(_paso("create_objects_by_coordinates", {"objects": objetos},
                       "Anotar el nombre de área que devuelve cada 'ref': las "
                       "asignaciones por paño lo necesitan."))
    if aberturas:
        pasos.append(_paso("create_objects_by_coordinates", {"objects": aberturas},
                           "Superficies de los huecos; el paso siguiente las convierte en abertura."))
        for a in aberturas:
            pasos.append(_paso("call_oapi",
                               {"path": "AreaObj", "method": "SetOpening",
                                "args_nombrados": {"Name": f"<área creada para {a['ref']}>", "IsOpening": True}},
                               "Hueco real: queda vacío, sin cargas (ver docs/HUECOS-ETABS-SAFE.md).",
                               "describe_oapi('AreaObj','SetOpening')"))

    # Sección y cargas por paño. assign_area_uniform_load carga por cota TODAS
    # las áreas: solo sirve cuando un nivel es de un único uso; por eso el plan
    # asigna POR PAÑO con call_oapi, usando el nombre devuelto al crear.
    for r in resultados:
        ref = f"<área creada para {r.pano.mark}>"
        pasos.append(_paso("call_oapi",
                           {"path": "AreaObj", "method": "SetProperty",
                            "args_nombrados": {"Name": ref, "PropName": r.espesor.seccion_etabs}},
                           f"{r.pano.mark}: sección {r.espesor.seccion_etabs}.",
                           "describe_oapi('AreaObj','SetProperty')"))
        dead_superficial = round(r.cargas.acabados_dead + r.cargas.mamposteria_asignada, 10)
        viva = r.cargas.viva
        nota_cargas = (f"{r.pano.mark} ({r.pano.uso}): Dead acabados {r.cargas.acabados_dead} + "
                       f"mampostería asignada {r.cargas.mamposteria_asignada} t/m² "
                       f"(calculada {r.cargas.mamposteria_calculada:.3f}, redondeo ↑0.05); "
                       "el peso propio lo pone el patrón Dead, NO duplicarlo.")
        if r.pano.es_vuelo:
            nota_cargas = (f"{r.pano.mark} VUELO: sin mampostería y sin mínimo de 0.10 "
                           "(excepción obligatoria §13.1); solo acabados + viva.")
        for patron, valor in (("Dead", dead_superficial), (r.cargas.patron_viva, viva)):
            pasos.append(_paso("call_oapi",
                               {"path": "AreaObj", "method": "SetLoadUniform",
                                "args_nombrados": {"Name": ref, "LoadPat": patron, "Value": valor,
                                                   "Dir": "Gravity", "Replace": True}},
                               nota_cargas,
                               "describe_oapi('AreaObj','SetLoadUniform'); Dir=Gravity como entero real"))

    return {
        "meta": {
            "proyecto": proyecto,
            "fecha": _dt.date.today().isoformat(),
            "generador": "puente-losas/etabs_plan",
            "unidades": UNIDADES_ETABS,
            "reglas": "Prompt 'Modelar en ETABS desde AutoCAD' — Ing. Arlette Ramírez, 14/10/2026",
            "desviacion_max_ajuste_005_m": round(desv_max, 4),
            "requisitos": [
                "Reclamar el turno/lock de ETABS en _coordinacion/locks antes de ejecutar.",
                "Ejecutar los pasos EN ORDEN; confirmar cada 'verificar' con describe_oapi.",
                "Releer del modelo cada asignación (un ret=0 no prueba que ETABS la conservó).",
                "NO correr el análisis: el flujo se detiene antes de Run (regla §22).",
            ],
        },
        "pasos": pasos,
    }


def escribir_plan(resultados: list[ResultadoPano], ruta: str,
                  proyecto: str = "Proyecto Ejemplo") -> dict:
    plan = plan_etabs(resultados, proyecto)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1, ensure_ascii=False)
    return plan
