"""Sección final por paño y payload para reflejar el ESPESOR real en Revit.

Hoy todas las losas del modelo llevan un tipo genérico único (p. ej.
"Generic - 0.25"): la sección decidida en el panel (L12/L15/L20 macizas,
L20A/L25A aligeradas) NO se ve en el modelo. Este módulo resuelve la sección
FINAL de cada paño — la fijada en el parámetro ``Seccion_Losa``, o la regla
del reglamento cuando quedó en "auto" — y empaqueta el payload que consume la
tool ``espesor_losas`` de ``revit-mcp-tools``: un tipo de Floor por sección
(nombre = sección, espesor = h de la biblioteca) y el cambio de tipo por Mark.

La regla "auto" es la misma del puente (``puente_losas.espesor``): espesor
mínimo normativo ACI 318-19 (base CDCRD T05) redondeado hacia arriba a 0.05 →
``seccion_biblioteca``. A propósito NO se usa el espesor actual del modelo
como piso: ese espesor es el placeholder que esta herramienta corrige.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from puente_losas.contrato import PanoLosa, asignar_bordes
from puente_losas.espesor import espesor_de_pano, seccion_biblioteca
from puente_losas.etabs_plan import BIBLIOTECA_LOSAS

PARAM_SECCION = "Seccion_Losa"
SECCION_AUTO = "auto (reglamento)"   # el literal del desplegable del panel


def espesores_de_secciones() -> dict[str, float]:
    """Espesor total (m) de cada sección de la biblioteca (h del catálogo)."""
    return {nombre: d["h"] for nombre, d in BIBLIOTECA_LOSAS.items()}


@dataclass(frozen=True)
class SeccionResuelta:
    mark: str
    seccion: str          # nombre de la biblioteca (= nombre del tipo de Floor)
    espesor_m: float      # h total del catálogo
    origen: str           # "fijada" (del parámetro/panel) | "auto"
    criterio: str         # referencia normativa (auto) o quién la fijó


def _es_auto(valor: str | None) -> bool:
    if not valor:
        return True
    return valor.strip().lower().startswith("auto")


def resolver_secciones(panos: list[PanoLosa],
                       fijadas: dict[str, str] | None = None
                       ) -> dict[str, SeccionResuelta]:
    """Sección final por Mark: la fijada manda; "auto" usa el reglamento.

    ``fijadas`` es el JSON {Mark: seccion} del panel (``secciones.json``); el
    literal "auto (reglamento)" (o vacío) delega en la norma. Una sección fuera
    de la biblioteca —fijada o sugerida por la norma— detiene con instrucción
    de consultar, nunca se inventa.
    """
    fijadas = fijadas or {}
    espesores = espesores_de_secciones()
    con_borde = asignar_bordes(panos)
    out: dict[str, SeccionResuelta] = {}
    for p in con_borde:
        pedida = fijadas.get(p.mark)
        if pedida and not _es_auto(pedida):
            if pedida not in espesores:
                raise ValueError(
                    f"{p.mark}: sección fijada '{pedida}' fuera de la biblioteca "
                    f"{sorted(espesores)}; corregirla en el panel.")
            out[p.mark] = SeccionResuelta(
                mark=p.mark, seccion=pedida, espesor_m=espesores[pedida],
                origen="fijada", criterio="fijada en el panel (Seccion_Losa)")
            continue
        ep = espesor_de_pano(p)
        seccion, nueva = seccion_biblioteca(ep.h_recomendado, p.trabaja_1d)
        if nueva:
            raise ValueError(
                f"{p.mark}: el reglamento pide h={ep.h_recomendado} m, fuera de la "
                f"biblioteca (sugerida {seccion}); definir la sección con el "
                "encargado, no inventarla.")
        out[p.mark] = SeccionResuelta(
            mark=p.mark, seccion=seccion, espesor_m=espesores[seccion],
            origen="auto", criterio=ep.criterio)
    return out


def payload_revit(resueltas: dict[str, SeccionResuelta]) -> dict:
    """El payload que consume la tool ``espesor_losas`` de revit-mcp-tools."""
    usadas = sorted({r.seccion for r in resueltas.values()})
    espesores = espesores_de_secciones()
    return {
        "asignar": {mark: r.seccion for mark, r in sorted(resueltas.items())},
        "tipos_floor": {s: espesores[s] for s in usadas},
    }


def escribir_secciones_json(resueltas: dict[str, SeccionResuelta], ruta: str) -> None:
    datos = {
        "parametro_revit": PARAM_SECCION,
        "regla_auto": "espesor mínimo ACI 318-19 (base CDCRD T05) redondeado "
                      "arriba a 0.05 m → sección de la biblioteca "
                      "(puente_losas.espesor); el espesor del modelo NO es piso",
        "secciones": {mark: asdict(r) for mark, r in sorted(resueltas.items())},
        "asignar_en_revit": payload_revit(resueltas),
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=1, ensure_ascii=False)
