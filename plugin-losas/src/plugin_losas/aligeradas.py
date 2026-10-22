"""Lógica paramétrica de losas aligeradas: nervios, ejes locales y conexiones.

El catálogo es la biblioteca del flujo Excel/ETABS de la Ing. Arlette Ramírez
(``puente_losas.etabs_plan.BIBLIOTECA_LOSAS``): L20A-1D/2D y L25A-1D/2D con su
topping, ancho de nervio y separación. Este módulo convierte cada paño en un
plan geométrico explícito (cuántos nervios, dónde, en qué dirección, con qué
ángulo de eje local 1) y resuelve las conexiones entre paños, de modo que la
sesión que modela (Cowork) solo coloque el tipo: no decide geometría.

Reglas normativas aplicadas (CDCRD Tomo 1, Título 5 — losas nervadas):
- topping mínimo 50 mm;
- distancia libre entre nervios ≤ 12 × espesor del topping.
Fuente: ``datos/titulos/T05.json`` (definición LOSAS NERVADAS).

Convención de dirección: los nervios de una losa 1D salvan la **luz corta**
(trabajan como viguetas en esa dirección) y se reparten a lo largo de la luz
larga. En ETABS los nervios de una sección Ribbed siguen el **eje local 1**
del área: el plan entrega el ángulo (0° = nervios según X del modelo).
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

from puente_losas.contrato import PanoLosa, lados_continuos
from puente_losas.espesor import seccion_biblioteca
from puente_losas.etabs_plan import BIBLIOTECA_LOSAS

TOPPING_MINIMO_M = 0.05        # CDCRD T05: topping >= 50 mm
FACTOR_LUZ_LIBRE = 12.0        # CDCRD T05: luz libre entre nervios <= 12*topping

CREDITO_CATALOGO = ("Biblioteca de losas del flujo AutoCAD↔Excel/ETABS de la "
                    "Ing. Arlette Ramírez (L20A/L25A, topping 0.05, nervios 0.15/0.20 @0.65)")


@dataclass(frozen=True)
class FamiliaNervios:
    """Los nervios de una dirección: eje a lo largo del nervio y reparto."""
    direccion: str                     # "X" | "Y": eje a lo largo del nervio
    n: int
    separacion_m: float                # eje a eje
    ancho_m: float
    luz_m: float                       # luz que salva cada nervio
    posiciones_m: tuple[float, ...]    # eje de cada nervio, desde el borde del bbox


@dataclass(frozen=True)
class PlanPano:
    mark: str
    seccion: str                       # L20A-1D, L25A-2D, L20, ...
    tipo: str                          # "Ribbed" | "Waffle" | "Maciza"
    h_m: float
    topping_m: float | None
    angulo_eje_local_1: float | None   # 0 = nervios según X; 90 = según Y; None = maciza/waffle
    nervios: tuple[FamiliaNervios, ...]
    chequeos: dict
    notas: tuple[str, ...]


@dataclass(frozen=True)
class Conexion:
    """Un borde compartido entre dos paños y cómo se conectan los nervios."""
    losa_i: str
    losa_j: str
    lado_de_i: str                     # izq/der/inf/sup (visto desde losa_i)
    borde: str                         # "vertical" | "horizontal"
    nervios_cruzan_i: bool
    nervios_cruzan_j: bool
    continuidad: str                   # "momento" | "parcial" | "solo topping"
    topping_igual: bool | None         # None si alguno es macizo
    nota: str = ""


def _reparto(ancho_total: float, separacion: float, ancho_nervio: float
             ) -> tuple[int, tuple[float, ...]]:
    """Cuántos nervios caben en ``ancho_total`` a ``separacion`` eje a eje, centrados."""
    if ancho_total <= ancho_nervio:
        return 1, (ancho_total / 2.0,)
    n = int(math.floor((ancho_total - ancho_nervio) / separacion + 1e-9)) + 1
    margen = (ancho_total - (n - 1) * separacion) / 2.0
    return n, tuple(round(margen + i * separacion, 4) for i in range(n))


def _chequeos(definicion: dict) -> dict:
    topping = definicion["topping"]
    luz_libre = definicion["separacion"] - definicion["ancho_nervio"]
    limite = FACTOR_LUZ_LIBRE * topping
    return {
        "topping_m": topping,
        "topping_minimo_m": TOPPING_MINIMO_M,
        "topping_ok": topping + 1e-9 >= TOPPING_MINIMO_M,
        "luz_libre_nervios_m": round(luz_libre, 4),
        "limite_12_topping_m": round(limite, 4),
        "luz_libre_ok": luz_libre <= limite + 1e-9,
        "fuente": "CDCRD T05, losas nervadas (topping>=50 mm; libre<=12*topping)",
    }


def seccion_de_pano(p: PanoLosa) -> str:
    """La sección de la biblioteca para el paño (misma regla que el puente)."""
    seccion, nueva = seccion_biblioteca(p.espesor, p.trabaja_1d)
    if nueva:
        raise ValueError(
            f"{p.mark}: espesor {p.espesor} m fuera de la biblioteca "
            f"(sugerida {seccion}); definir la sección con el encargado, no inventar nervios.")
    return seccion


def plan_pano(p: PanoLosa, seccion: str | None = None) -> PlanPano:
    """El plan paramétrico de un paño: tipo, nervios, eje local y chequeos."""
    seccion = seccion or seccion_de_pano(p)
    notas: list[str] = []

    if seccion not in BIBLIOTECA_LOSAS:
        raise ValueError(f"{p.mark}: sección '{seccion}' fuera de la biblioteca "
                         f"{sorted(BIBLIOTECA_LOSAS)}.")
    definicion = BIBLIOTECA_LOSAS[seccion]
    if definicion["tipo"] == "Slab":
        return PlanPano(p.mark, seccion, "Maciza", definicion["h"], None, None, (),
                        {}, ("losa maciza: sin nervios",))

    def _familia(direccion: str, ancho_reparto: float, luz: float) -> FamiliaNervios:
        n, posiciones = _reparto(ancho_reparto, definicion["separacion"],
                                 definicion["ancho_nervio"])
        return FamiliaNervios(direccion, n, definicion["separacion"],
                              definicion["ancho_nervio"], luz, posiciones)

    # Nervios según X: corren a lo largo de lx (luz que salvan) y se reparten en ly.
    nervios_x = _familia("X", p.ly, p.lx)
    nervios_y = _familia("Y", p.lx, p.ly)

    if definicion["tipo"] == "Waffle":
        familias: tuple[FamiliaNervios, ...] = (nervios_x, nervios_y)
        angulo = None
        notas.append("2D (Waffle): nervios en ambas direcciones; el eje local no gobierna el reparto")
    else:                                  # Ribbed (1D): nervios sobre la luz corta
        if p.lx <= p.ly:
            familias = (nervios_x,)
            angulo = 0.0
        else:
            familias = (nervios_y,)
            angulo = 90.0
        notas.append("1D (Ribbed): los nervios salvan la luz corta; en ETABS siguen el "
                     "eje local 1 del área (ángulo entregado)")
    if p.direccion == "1D" and definicion["tipo"] == "Waffle":
        notas.append("declarada 1D pero la sección es 2D (Waffle): revisar la sección elegida")
    return PlanPano(p.mark, seccion, definicion["tipo"], definicion["h"],
                    definicion["topping"], angulo, familias, _chequeos(definicion),
                    tuple(notas))


def _cruzan(plan: PlanPano, borde: str) -> bool:
    """True si los nervios del paño cruzan un borde ``vertical``/``horizontal``.

    Un borde vertical (lado izq/der) lo cruzan los nervios que corren según X;
    uno horizontal, los que corren según Y. Una maciza siempre da continuidad
    de hormigón, así que cuenta como que cruza.
    """
    if plan.tipo == "Maciza":
        return True
    direccion_que_cruza = "X" if borde == "vertical" else "Y"
    return any(f.direccion == direccion_que_cruza for f in plan.nervios)


def conexiones(panos: list[PanoLosa], planes: dict[str, PlanPano]) -> list[Conexion]:
    """Las conexiones por borde compartido entre paños (adyacencia del contrato)."""
    lados = lados_continuos(panos)
    out: list[Conexion] = []
    vistos: set[tuple[str, ...]] = set()
    for p in panos:
        for lado, vecino in lados[p.mark].items():
            if vecino is None:
                continue
            clave = tuple(sorted((p.mark, vecino))) + (("v",) if lado in ("izq", "der") else ("h",))
            if clave in vistos:
                continue
            vistos.add(clave)
            borde = "vertical" if lado in ("izq", "der") else "horizontal"
            plan_i, plan_j = planes[p.mark], planes[vecino]
            cruza_i, cruza_j = _cruzan(plan_i, borde), _cruzan(plan_j, borde)
            if cruza_i and cruza_j:
                continuidad = "momento"
            elif cruza_i or cruza_j:
                continuidad = "parcial"
            else:
                continuidad = "solo topping"
            if plan_i.topping_m is None or plan_j.topping_m is None:
                topping_igual = None
            else:
                topping_igual = abs(plan_i.topping_m - plan_j.topping_m) < 1e-9
            nota = ""
            if plan_i.seccion != plan_j.seccion:
                nota = f"secciones distintas ({plan_i.seccion} / {plan_j.seccion}): revisar el detalle del borde"
            out.append(Conexion(p.mark, vecino, lado, borde, cruza_i, cruza_j,
                                continuidad, topping_igual, nota))
    return out


def plan_sistema(panos: list[PanoLosa],
                 secciones: dict[str, str] | None = None) -> dict:
    """El plan completo (JSON-able) del sistema de losas aligeradas.

    ``secciones`` permite fijar la sección por Mark; sin entrada se usa la
    regla de la biblioteca (espesor + 1D/2D). La sesión de modelado coloca el
    tipo y el ángulo del eje local tal cual: este plan ya decidió la geometría.
    """
    secciones = secciones or {}
    planes = {p.mark: plan_pano(p, secciones.get(p.mark)) for p in panos}
    return {
        "catalogo": CREDITO_CATALOGO,
        "panos": [asdict(planes[p.mark]) for p in panos],
        "conexiones": [asdict(c) for c in conexiones(panos, planes)],
        "normativa": {
            "topping_minimo_m": TOPPING_MINIMO_M,
            "luz_libre_max": f"{FACTOR_LUZ_LIBRE:g} x topping",
            "fuente": "CDCRD Tomo 1, Titulo 5 (losas nervadas)",
        },
    }


def escribir_plan_aligeradas(panos: list[PanoLosa], ruta: str,
                             secciones: dict[str, str] | None = None) -> None:
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(plan_sistema(panos, secciones), f, indent=1, ensure_ascii=False)
