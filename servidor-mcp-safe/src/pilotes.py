# SAFE MCP — separacion de pilotes y factor de grupo (MOPC R-024, tabla 5.1).
# Modulo PURO: no importa comtypes ni toca SAFE. Safe.py le entrega los frames,
# las secciones circulares y las areas de cabezal ya leidas por OAPI, y este
# modulo devuelve el informe. Asi las fixtures sinteticas de tests/ prueban el
# criterio completo sin modelo ni COM.
#
# Criterio normativo (R-024 5.1.7.1, corpus-reglamentos/data/R-024.md):
#   TABLA 5.1  S/B 6 -> 1.0 ; 5 -> 0.9 ; 4 -> 0.8 ; 3 -> 0.7
#   "Cuando el espaciamiento entre centros de pilotes sea menor que 6 diametros,
#    la capacidad ULTIMA de los pilotes debera ser reducida por el factor de
#    interaccion. La capacidad ultima del grupo sera la menor de (a) la suma de
#    las capacidades ultimas reducidas y (b) la de una pila de dimensiones
#    externas iguales a las del grupo."
# La norma NO autoriza interpolar: el defecto es el escalon inferior (step_down).
# S/B < 3 queda fuera de tabla: factor None, nunca extrapolado.

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable

TABLA_5_1: tuple[tuple[float, float], ...] = ((6.0, 1.0), (5.0, 0.9), (4.0, 0.8), (3.0, 0.7))
SB_MINIMO_TABLA = TABLA_5_1[-1][0]
SB_SIN_REDUCCION = TABLA_5_1[0][0]
INTERPOLACIONES = ("step_down", "linear")
BANDAS_HISTOGRAMA = (("<3", -math.inf, 3.0), ("3-4", 3.0, 4.0), ("4-5", 4.0, 5.0),
                     ("5-6", 5.0, 6.0), (">=6", 6.0, math.inf))
CELDA_EN_DIAMETROS = 8.0
_TOL_SB = 1e-9


class PilotesError(ValueError):
    """Entrada incoherente para el calculo (sin pilotes, parametro invalido...)."""


def factor_tabla_5_1(s_b: float | None, interpolation: str = "step_down") -> tuple[float | None, bool]:
    """Factor de reduccion de capacidad axial. Devuelve (factor, fuera_de_tabla).

    step_down: escalon inferior de la tabla (conservador). linear: interpolacion
    entre los cuatro puntos, que la norma no autoriza; quien la pida lo declara.
    S/B >= 6 -> 1.0. S/B < 3 -> (None, True): no se extrapola.
    """
    if interpolation not in INTERPOLACIONES:
        raise PilotesError(f"interpolation debe ser {INTERPOLACIONES}, no {interpolation!r}.")
    if s_b is None or not math.isfinite(s_b):
        return None, True
    if s_b + _TOL_SB < SB_MINIMO_TABLA:
        return None, True
    if s_b + _TOL_SB >= SB_SIN_REDUCCION:
        return 1.0, False
    if interpolation == "step_down":
        for sb_tabla, factor in TABLA_5_1:
            if s_b + _TOL_SB >= sb_tabla:
                return factor, False
    for (sb_alto, f_alto), (sb_bajo, f_bajo) in zip(TABLA_5_1, TABLA_5_1[1:]):
        if sb_bajo - _TOL_SB <= s_b <= sb_alto + _TOL_SB:
            t = (s_b - sb_bajo) / (sb_alto - sb_bajo)
            return round(f_bajo + t * (f_alto - f_bajo), 6), False
    return None, True  # inalcanzable; defensa ante NaN tolerado arriba


@dataclass
class Pilote:
    id: str
    seccion: str
    x: float
    y: float
    z_cabeza: float
    z_punta: float
    diametro: float
    punto_cabeza: str = ""
    punto_punta: str = ""
    inclinado: bool = False
    grupo: str | None = None
    vecinos: list[dict] = field(default_factory=list)
    s_b: float | None = None
    pareja_s_b: str | None = None
    factor: float | None = None
    fuera_de_tabla: bool = False
    sin_vecino: bool = False


def pilotes_desde_frames(frames: Iterable[dict], secciones: dict[str, dict],
                         sections: str | list[str] = "auto", diameter: float = 0.0,
                         tol_inclinacion: float = 1e-3,
                         necesita_diametro: bool = True) -> tuple[list[Pilote], list[str]]:
    """Convierte frames leidos de SAFE en pilotes con cabeza = extremo de Z mayor.

    frames: dicts con id, seccion, p1, p2, x1, y1, z1, x2, y2, z2.
    secciones: {nombre: {"diametro": d, ...}} de las secciones circulares.
    sections: "auto" = todas las circulares; lista = solo esas (si una no es
      circular, exige diameter > 0). Nunca se filtra por el nombre del frame.
    diameter: override del diametro en unidades activas (0 = de la seccion).
    tol_inclinacion: desplazamiento horizontal entre extremos a partir del cual
      el frame se marca inclinado (unidades activas).
    necesita_diametro: False para lecturas que no usan S/B (reacciones): una
      seccion no circular pasa con diametro 0 en vez de ser error.
    """
    if diameter < 0 or not math.isfinite(diameter):
        raise PilotesError("diameter debe ser 0 (de la seccion) o un valor positivo.")
    if isinstance(sections, str):
        if sections.strip().lower() != "auto":
            raise PilotesError("sections debe ser \"auto\" o una lista de nombres de seccion.")
        elegidas = set(secciones)
        if not elegidas and diameter <= 0:
            raise PilotesError("El modelo no tiene secciones de frame circulares; "
                               "indique sections y diameter explicitamente.")
    else:
        elegidas = {str(s) for s in sections}
        if not elegidas:
            raise PilotesError("sections no puede ser una lista vacia.")
        no_circulares = sorted(elegidas - set(secciones))
        if no_circulares and diameter <= 0 and necesita_diametro:
            raise PilotesError(f"Secciones sin diametro circular conocido: {no_circulares}; "
                               "indique diameter para usarlas.")
    avisos: list[str] = []
    pilotes: list[Pilote] = []
    for fr in frames:
        sec = str(fr["seccion"])
        if sections != "auto" and sec not in elegidas:
            continue
        if sections == "auto" and sec not in secciones:
            continue
        d = diameter if diameter > 0 else float(secciones.get(sec, {}).get("diametro", 0.0))
        if d <= 0 and necesita_diametro:
            raise PilotesError(f"Seccion {sec}: diametro {d} no valido.")
        z1, z2 = float(fr["z1"]), float(fr["z2"])
        cabeza_es_1 = z1 >= z2
        xc, yc = (fr["x1"], fr["y1"]) if cabeza_es_1 else (fr["x2"], fr["y2"])
        inclinado = math.hypot(float(fr["x1"]) - float(fr["x2"]),
                               float(fr["y1"]) - float(fr["y2"])) > tol_inclinacion
        if math.isclose(z1, z2, abs_tol=tol_inclinacion):
            avisos.append(f"Frame {fr['id']}: extremos a la misma Z; no es un pilote vertical "
                          "(cabeza tomada en el primer extremo).")
        pilotes.append(Pilote(id=str(fr["id"]), seccion=sec, x=float(xc), y=float(yc),
                              z_cabeza=max(z1, z2), z_punta=min(z1, z2), diametro=d,
                              punto_cabeza=str(fr["p1"] if cabeza_es_1 else fr["p2"]),
                              punto_punta=str(fr["p2"] if cabeza_es_1 else fr["p1"]),
                              inclinado=inclinado))
    inclinados = [p.id for p in pilotes if p.inclinado]
    if inclinados:
        avisos.append(f"{len(inclinados)} frame(s) inclinado(s); se usa la proyeccion en planta "
                      f"de la cabeza: {inclinados[:20]}{'...' if len(inclinados) > 20 else ''}")
    diametros = sorted({round(p.diametro, 6) for p in pilotes})
    if len(diametros) > 1:
        avisos.append(f"Diametros mezclados {diametros}: S/B de cada pareja usa el MAYOR "
                      "de los dos diametros (conservador).")
    return pilotes, avisos


def separar_duplicados(pilotes: list[Pilote], tol: float = 1e-6) -> tuple[list[Pilote], list[str]]:
    """Quita del analisis los pilotes cuya cabeza coincide con otra ya vista.

    Dos frames en la misma coordenada son un error de modelado, no un grupo:
    se reportan y se excluyen para no contaminar la separacion real.
    """
    vistos: dict[tuple[int, int], Pilote] = {}
    unicos, avisos = [], []
    for p in pilotes:
        clave = (round(p.x / tol), round(p.y / tol))
        if clave in vistos:
            avisos.append(f"Pilote {p.id} duplica la coordenada de {vistos[clave].id} "
                          f"({p.x:g}, {p.y:g}); excluido del analisis.")
            continue
        vistos[clave] = p
        unicos.append(p)
    return unicos, avisos


class GrillaEspacial:
    """Vecino mas cercano por celdas (O(n) promedio), no O(n^2)."""

    def __init__(self, pilotes: list[Pilote], celda: float):
        if celda <= 0 or not math.isfinite(celda):
            raise PilotesError("La celda de la grilla debe ser positiva.")
        self.pilotes = pilotes
        self.celda = celda
        self.celdas: dict[tuple[int, int], list[int]] = {}
        for i, p in enumerate(pilotes):
            self.celdas.setdefault(self._clave(p.x, p.y), []).append(i)
        self.max_anillo = 0
        if self.celdas:
            ix = [c[0] for c in self.celdas]
            iy = [c[1] for c in self.celdas]
            self.max_anillo = max(max(ix) - min(ix), max(iy) - min(iy))

    def _clave(self, x: float, y: float) -> tuple[int, int]:
        return math.floor(x / self.celda), math.floor(y / self.celda)

    @staticmethod
    def _perimetro(anillo: int):
        """Celdas con distancia Chebyshev exactamente `anillo` (O(anillo), no O(anillo^2))."""
        if anillo == 0:
            yield (0, 0)
            return
        for dx in range(-anillo, anillo + 1):
            yield (dx, -anillo)
            yield (dx, anillo)
        for dy in range(-anillo + 1, anillo):
            yield (-anillo, dy)
            yield (anillo, dy)

    def _distancias(self, i: int, indices) -> dict[int, float]:
        p = self.pilotes[i]
        return {j: math.hypot(p.x - self.pilotes[j].x, p.y - self.pilotes[j].y) for j in indices if j != i}

    def vecinos(self, i: int, k: int = 1) -> list[tuple[int, float]]:
        """k vecinos mas cercanos de pilotes[i] como (indice, distancia).

        Expande anillos de celdas; todo lo que queda fuera del anillo r esta a mas
        de r*celda, asi que el k-esimo candidato dentro de esa cota es definitivo.
        Un punto aislado (anillos mas grandes que el numero de celdas ocupadas)
        cae a fuerza bruta sobre las celdas ocupadas en vez de barrer vacio.
        """
        p = self.pilotes[i]
        cx, cy = self._clave(p.x, p.y)
        candidatos: dict[int, float] = {}
        anillo = 0
        while True:
            if (2 * anillo + 1) ** 2 > len(self.celdas):
                candidatos = self._distancias(i, (j for idx in self.celdas.values() for j in idx))
                return sorted(candidatos.items(), key=lambda t: (t[1], t[0]))[:k]
            for dx, dy in self._perimetro(anillo):
                candidatos.update(self._distancias(i, self.celdas.get((cx + dx, cy + dy), ())))
            mejores = sorted(candidatos.items(), key=lambda t: (t[1], t[0]))[:k]
            if len(mejores) >= k and mejores[-1][1] <= anillo * self.celda:
                return mejores
            if anillo > self.max_anillo:
                return mejores
            anillo += 1

    def en_radio(self, i: int, radio: float) -> dict[int, float]:
        """Todos los pilotes a distancia <= radio de pilotes[i] como {indice: distancia}."""
        p = self.pilotes[i]
        cx, cy = self._clave(p.x, p.y)
        anillos = math.ceil(radio / self.celda)
        if (2 * anillos + 1) ** 2 > len(self.celdas):
            indices = (j for idx in self.celdas.values() for j in idx)
        else:
            indices = (j for a in range(anillos + 1) for dx, dy in self._perimetro(a)
                       for j in self.celdas.get((cx + dx, cy + dy), ()))
        return {j: d for j, d in self._distancias(i, indices).items() if d <= radio + 1e-9}


def asignar_vecinos(pilotes: list[Pilote], k: int, interpolation: str,
                    celda: float | None = None, objetivo: list[int] | None = None) -> None:
    """Rellena vecinos, s_b, factor y fuera_de_tabla (in place, objetos de esta corrida).

    objetivo: indices de los pilotes a evaluar (None = todos). Los vecinos se
    buscan siempre entre todos los de la lista.

    S/B del pilote = el MENOR S/B entre todas las parejas a menos de 6*Dmax (con
    diametros mezclados el vecino mas cercano en distancia no es siempre el peor);
    mas alla de 6 diametros la tabla da 1.0 y no hace falta mirar. Sin vecino
    (pilote solo en su cabezal o en el modelo) no hay interaccion de grupo:
    factor 1.0, s_b None y bandera sin_vecino; NO es "fuera de tabla".
    """
    if k < 1:
        raise PilotesError("neighbors debe ser >= 1.")
    if not pilotes:
        return
    d_max = max(p.diametro for p in pilotes)
    if celda is None:
        celda = CELDA_EN_DIAMETROS * d_max
    grilla = GrillaEspacial(pilotes, celda)
    for i in (range(len(pilotes)) if objetivo is None else objetivo):
        p = pilotes[i]
        p.vecinos = [{"id": pilotes[j].id, "distancia": round(dist, 6),
                      "s_b": round(dist / max(p.diametro, pilotes[j].diametro), 6)}
                     for j, dist in grilla.vecinos(i, k)]
        if not p.vecinos:
            p.s_b, p.pareja_s_b, p.factor, p.fuera_de_tabla, p.sin_vecino = None, None, 1.0, False, True
            continue
        cercanos = grilla.en_radio(i, SB_SIN_REDUCCION * d_max)
        if not cercanos:
            cercanos = {j: d for j, d in grilla.vecinos(i, 1)}
        j, s_b = min(((j, round(d / max(p.diametro, pilotes[j].diametro), 6)) for j, d in cercanos.items()),
                     key=lambda t: (t[1], t[0]))
        p.s_b, p.pareja_s_b, p.sin_vecino = s_b, pilotes[j].id, False
        p.factor, p.fuera_de_tabla = factor_tabla_5_1(s_b, interpolation)


def punto_en_poligono(x: float, y: float, xs: list[float], ys: list[float]) -> bool:
    """Ray casting; un punto sobre el borde cuenta como dentro."""
    n = len(xs)
    dentro = False
    for i in range(n):
        x1, y1, x2, y2 = xs[i], ys[i], xs[(i + 1) % n], ys[(i + 1) % n]
        if _sobre_segmento(x, y, x1, y1, x2, y2):
            return True
        if (y1 > y) != (y2 > y):
            xi = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < xi:
                dentro = not dentro
    return dentro


def _sobre_segmento(x, y, x1, y1, x2, y2, tol=1e-9) -> bool:
    cruz = (x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)
    if abs(cruz) > tol * max(1.0, abs(x2 - x1) + abs(y2 - y1)):
        return False
    return min(x1, x2) - tol <= x <= max(x1, x2) + tol and min(y1, y2) - tol <= y <= max(y1, y2) + tol


def agrupar_por_cabezal(pilotes: list[Pilote], cabezales: list[dict]) -> list[str]:
    """Asigna p.grupo = id del cabezal (area) que contiene la cabeza. Devuelve avisos.

    cabezales: dicts con id, xs, ys. Un pilote dentro de varios cabezales
    (areas solapadas) se asigna al primero y se avisa.
    """
    avisos = []
    for p in pilotes:
        contienen = [c["id"] for c in cabezales if punto_en_poligono(p.x, p.y, c["xs"], c["ys"])]
        p.grupo = contienen[0] if contienen else None
        if len(contienen) > 1:
            avisos.append(f"Pilote {p.id} cae en {len(contienen)} cabezales {contienen}; "
                          f"asignado a {contienen[0]}.")
    sueltos = [p.id for p in pilotes if p.grupo is None]
    if sueltos:
        avisos.append(f"{len(sueltos)} pilote(s) fuera de todo cabezal; su vecino se busca "
                      f"en todo el modelo: {sueltos[:20]}{'...' if len(sueltos) > 20 else ''}")
    return avisos


def percentil(valores: list[float], q: float) -> float | None:
    if not valores:
        return None
    v = sorted(valores)
    pos = (len(v) - 1) * q
    lo, hi = math.floor(pos), math.ceil(pos)
    return round(v[lo] + (v[hi] - v[lo]) * (pos - lo), 6)


def estadisticas(valores: list[float]) -> dict:
    return {"n": len(valores), "min": percentil(valores, 0.0), "p5": percentil(valores, 0.05),
            "mediana": percentil(valores, 0.5), "p95": percentil(valores, 0.95),
            "max": percentil(valores, 1.0)}


def histograma_sb(valores: list[float]) -> dict[str, int]:
    out = {nombre: 0 for nombre, _, _ in BANDAS_HISTOGRAMA}
    for v in valores:
        for nombre, lo, hi in BANDAS_HISTOGRAMA:
            if lo <= v < hi:
                out[nombre] += 1
                break
    return out


def resumen_grupo(nombre: str, miembros: list[Pilote]) -> dict:
    factores = [p.factor for p in miembros if p.factor is not None]
    fuera = [p.id for p in miembros if p.fuera_de_tabla]
    return {"cabezal": nombre, "n_pilotes": len(miembros),
            "s_b_min": min((p.s_b for p in miembros if p.s_b is not None), default=None),
            "factor_minimo": min(factores) if factores else None,
            "factor_promedio": round(sum(factores) / len(factores), 4) if factores else None,
            "suma_factores": round(sum(factores), 4) if factores else None,
            "n_fuera_de_tabla": len(fuera), "fuera_de_tabla": fuera,
            "sin_vecino": [p.id for p in miembros if p.sin_vecino]}


def capacidad_grupo(grupo: dict, q_ult: float, fs: float, q_adm: float) -> dict:
    """(a) suma de ultimas reducidas y (b) pila equivalente, R-024 5.1.7.1.

    Solo tiene sentido por cabezal (scope by_footing): el "grupo" del R-024 es el
    de un cabezal, no el modelo entero. El factor reduce la capacidad ULTIMA;
    Qadm = Qult_reducida / FS. Una Ra ya calculada solo admite el factor si su FS
    no cambia. (b) necesita suelo que SAFE no tiene: queda pendiente y la tool
    nunca dice "cumple".
    """
    out: dict = {"cabezal": grupo["cabezal"], "n_pilotes": grupo["n_pilotes"],
                 "a_suma_ultimas_reducidas": None, "q_adm_grupo_por_a": None,
                 "b_pila_equivalente": "PENDIENTE: requiere parametros de suelo y dimensiones "
                                       "externas del grupo; no se obtiene del modelo SAFE.",
                 "capacidad_grupo": "NO DETERMINADA: es la menor de (a) y (b), y (b) no esta calculada.",
                 "notas": []}
    if grupo["n_fuera_de_tabla"]:
        out["notas"].append(f"{grupo['n_fuera_de_tabla']} pilote(s) con S/B < 3 sin factor: "
                            "(a) no se calcula; criterio del geotecnista.")
        return out
    if grupo["suma_factores"] is None:
        return out
    if q_ult > 0:
        out["a_suma_ultimas_reducidas"] = round(q_ult * grupo["suma_factores"], 4)
        if fs > 0:
            out["q_adm_grupo_por_a"] = round(out["a_suma_ultimas_reducidas"] / fs, 4)
        else:
            out["notas"].append("Sin FS: se reporta la suma de ultimas reducidas, no la admisible.")
    elif q_adm > 0:
        out["q_adm_grupo_por_a"] = round(q_adm * grupo["suma_factores"], 4)
        out["notas"].append("q_adm recibida ya dividida por su FS: multiplicarla por el factor "
                            "equivale a reducir la ultima SOLO si el FS no cambia (R-024 5.2).")
    else:
        out["notas"].append("Sin q_ult ni q_adm: solo se reporta la suma de factores.")
    return out


def evaluar_separacion(pilotes: list[Pilote], scope: str = "nearest_neighbor", neighbors: int = 1,
                       interpolation: str = "step_down", cabezales: list[dict] | None = None,
                       q_ult: float = 0.0, fs: float = 0.0, q_adm: float = 0.0) -> dict:
    """Informe completo de separacion y factor de grupo. Entrada ya en unidades activas."""
    if scope not in ("nearest_neighbor", "by_footing"):
        raise PilotesError("scope debe ser \"nearest_neighbor\" o \"by_footing\".")
    if any(v < 0 or not math.isfinite(v) for v in (q_ult, fs, q_adm)):
        raise PilotesError("q_ult, fs y q_adm deben ser 0 o positivos.")
    if q_ult > 0 and q_adm > 0:
        raise PilotesError("Indique q_ult (+ fs) o q_adm, no ambos: son dos vias distintas (R-024 5.2).")
    if fs > 0 and q_ult <= 0:
        raise PilotesError("fs solo aplica junto con q_ult (Qadm = Qult_reducida / FS).")
    pilotes, avisos = separar_duplicados(pilotes)
    if not pilotes:
        raise PilotesError("Ningun pilote que analizar tras aplicar el filtro de secciones.")
    grupos: list[dict] = []
    if scope == "by_footing":
        if cabezales is None:
            raise PilotesError("by_footing requiere la lista de cabezales.")
        avisos += agrupar_por_cabezal(pilotes, cabezales)
        celda = CELDA_EN_DIAMETROS * max(p.diametro for p in pilotes)
        por_grupo: dict[str | None, list[Pilote]] = {}
        for p in pilotes:
            por_grupo.setdefault(p.grupo, []).append(p)
        for nombre, miembros in por_grupo.items():
            if nombre is None:
                continue
            asignar_vecinos(miembros, neighbors, interpolation, celda)
            grupos.append(resumen_grupo(nombre, miembros))
        sueltos = [i for i, p in enumerate(pilotes) if p.grupo is None]
        if sueltos:
            asignar_vecinos(pilotes, neighbors, interpolation, celda, objetivo=sueltos)
        solos = [p for p in pilotes if p.grupo is not None and len(por_grupo[p.grupo]) == 1]
        for p in solos:
            avisos.append(f"Cabezal {p.grupo}: un solo pilote ({p.id}); sin separacion que evaluar.")
    else:
        asignar_vecinos(pilotes, neighbors, interpolation)
    separaciones = [p.vecinos[0]["distancia"] for p in pilotes if p.vecinos]
    sbs = [p.s_b for p in pilotes if p.s_b is not None]
    factores = [p.factor for p in pilotes if p.factor is not None and not p.sin_vecino]
    fuera = [p.id for p in pilotes if p.fuera_de_tabla]
    sin_vecino = [p.id for p in pilotes if p.sin_vecino]
    resumen = {"n_pilotes": len(pilotes), "separacion": estadisticas(separaciones),
               "s_b": estadisticas(sbs), "histograma_s_b": histograma_sb(sbs),
               "fuera_de_tabla": {"n": len(fuera), "ids": fuera},
               "sin_vecino": {"n": len(sin_vecino), "ids": sin_vecino},
               "factor_minimo": min(factores) if factores else None,
               "factor_promedio_en_tabla": round(sum(factores) / len(factores), 4) if factores else None}
    if grupos:
        capacidad = [capacidad_grupo(g, q_ult, fs, q_adm) for g in grupos]
    else:
        capacidad = []
        if q_ult > 0 or q_adm > 0 or scope == "by_footing":
            avisos.append("Capacidad de grupo no calculada: el grupo del R-024 es el de un cabezal "
                          "(scope=by_footing con areas de cabezal); el barrido global no es un grupo.")
    return {"alcance": scope, "interpolacion": interpolation,
            "tabla_5_1": {str(int(sb)): f for sb, f in TABLA_5_1},
            "pilotes": pilotes, "resumen": resumen, "grupos": grupos,
            "capacidad": capacidad, "avisos": avisos}


def pilote_a_dict(p: Pilote, factor_mm: float) -> dict:
    return {"id": p.id, "seccion": p.seccion, "x": p.x, "y": p.y, "z_cabeza": p.z_cabeza,
            "z_punta": p.z_punta, "punto_cabeza": p.punto_cabeza, "punto_punta": p.punto_punta,
            "diametro": p.diametro, "diametro_mm": round(p.diametro * factor_mm, 3),
            "vecinos": p.vecinos, "s_b": p.s_b, "pareja_s_b": p.pareja_s_b, "factor": p.factor,
            "fuera_de_tabla": p.fuera_de_tabla, "sin_vecino": p.sin_vecino,
            "inclinado": p.inclinado, "cabezal": p.grupo}


# ---------------------------------------------------------------------------
# Reacciones axiales: envolvente y pilote critico
# ---------------------------------------------------------------------------

def envolvente_axial(registros: list[dict], q_adm: float = 0.0) -> dict:
    """registros: dicts con pilote, caso, paso, axial (compresion positiva).

    Devuelve por pilote la compresion maxima (caso y paso), la traccion maxima si
    existe, el ratio contra q_adm si se dio, y el pilote critico. El ratio se
    compara sin redondear; q_adm es una sola cifra en compresion, asi que un
    pilote sin compresion (solo traccion) no se declara "cumple": su capacidad
    a traccion no se evaluo. No propone nada.
    """
    if q_adm < 0 or not math.isfinite(q_adm):
        raise PilotesError("q_adm debe ser 0 o positivo.")
    por_pilote: dict[str, list[dict]] = {}
    for r in registros:
        por_pilote.setdefault(r["pilote"], []).append(r)
    filas = []
    for pid, regs in por_pilote.items():
        peor = max(regs, key=lambda r: r["axial"])
        traccion = min(regs, key=lambda r: r["axial"])
        fila = {"pilote": pid, "compresion_max": round(peor["axial"], 4), "caso": peor["caso"],
                "paso": peor["paso"], "n_registros": len(regs),
                "traccion_max": round(-traccion["axial"], 4) if traccion["axial"] < 0 else 0.0,
                "caso_traccion": traccion["caso"] if traccion["axial"] < 0 else None}
        if q_adm > 0:
            fila["ratio"] = round(peor["axial"] / q_adm, 4)
            fila["cumple_q_adm"] = (peor["axial"] <= q_adm) if peor["axial"] > 0 else None
        filas.append(fila)
    filas.sort(key=lambda f: -f["compresion_max"])
    critico = filas[0] if filas else None
    out = {"n_pilotes_con_resultado": len(filas), "critico": critico, "pilotes": filas}
    if q_adm > 0:
        out["q_adm"] = q_adm
        out["no_cumplen"] = [f["pilote"] for f in filas if f["cumple_q_adm"] is False]
        out["solo_traccion_sin_evaluar"] = [f["pilote"] for f in filas if f["cumple_q_adm"] is None]
        out["ratio_max"] = critico["ratio"] if critico else None
    return out
