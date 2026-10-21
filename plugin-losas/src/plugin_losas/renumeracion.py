"""Renumeración de losas en orden de lectura (ley de Emil, 2026-10-21).

Las losas se numeran **como se lee un libro**: filas de arriba hacia abajo
(Y descendente en planta) y, dentro de cada fila, de izquierda a derecha
(X ascendente). Excepciones de la regla: indicación contraria explícita y las
**losas en vuelo**, que quedan fuera de la numeración corrida y conservan su
marca.

Las filas se arman por solape vertical: una losa pertenece a la fila si su
rango Y solapa al menos ``SOLAPE_FILA`` de la altura de la caja de referencia
de la fila; si no, abre fila nueva. Esto tolera losas de altos distintos en la
misma banda (el caso real de una planta con paños desiguales).
"""
from __future__ import annotations

from dataclasses import dataclass

# Solape vertical mínimo (fracción de la altura menor) para compartir fila.
SOLAPE_FILA = 0.5


@dataclass(frozen=True)
class CajaLosa:
    """Lo mínimo para ordenar: marca actual, caja en planta y si es vuelo."""
    mark: str
    x0: float
    y0: float
    x1: float
    y1: float
    es_vuelo: bool = False

    @property
    def alto(self) -> float:
        return self.y1 - self.y0


def caja_desde_contorno(mark: str, contorno, es_vuelo: bool = False) -> CajaLosa:
    xs = [p[0] for p in contorno]
    ys = [p[1] for p in contorno]
    return CajaLosa(mark, min(xs), min(ys), max(xs), max(ys), es_vuelo)


def _solape_vertical(a: CajaLosa, b: CajaLosa) -> float:
    s = min(a.y1, b.y1) - max(a.y0, b.y0)
    menor = max(min(a.alto, b.alto), 1e-9)
    return max(0.0, s) / menor


def orden_lectura(cajas: list[CajaLosa]) -> list[CajaLosa]:
    """Las cajas en orden de lectura (sin filtrar vuelos: solo ordena)."""
    filas: list[list[CajaLosa]] = []
    for caja in sorted(cajas, key=lambda c: -c.y1):          # borde superior, de arriba abajo
        for fila in filas:
            if _solape_vertical(caja, fila[0]) >= SOLAPE_FILA:
                fila.append(caja)
                break
        else:
            filas.append([caja])
    return [c for fila in filas for c in sorted(fila, key=lambda c: c.x0)]


def renumerar(cajas: list[CajaLosa], prefijo: str, inicio: int = 1,
              relleno: int = 0) -> dict[str, str]:
    """Mapa {mark actual: mark nuevo} en orden de lectura.

    Los vuelos NO entran en la numeración corrida (conservan su marca) y no
    consumen número. ``relleno`` = ancho con ceros (0 = sin relleno: T1, T2…;
    2 = N2-01, N2-02…). ValueError si una marca nueva choca con la marca
    conservada de un vuelo.
    """
    ordenadas = orden_lectura(cajas)
    conservadas = {c.mark for c in ordenadas if c.es_vuelo}
    mapa: dict[str, str] = {}
    n = inicio
    for c in ordenadas:
        if c.es_vuelo:
            continue
        nuevo = f"{prefijo}{n:0{relleno}d}" if relleno else f"{prefijo}{n}"
        if nuevo in conservadas:
            raise ValueError(f"la marca nueva '{nuevo}' choca con un vuelo que conserva su marca.")
        mapa[c.mark] = nuevo
        n += 1
    return mapa


def renumerar_por_grupos(cajas_por_grupo: dict[str, list[CajaLosa]],
                         prefijos: dict[str, str],
                         rellenos: dict[str, int] | None = None) -> dict[str, str]:
    """Renumera varios grupos (p. ej. niveles) a la vez; un mapa global único.

    ValueError si el resultado global repite marcas (incluidas las de vuelos).
    """
    rellenos = rellenos or {}
    mapa: dict[str, str] = {}
    for grupo, cajas in cajas_por_grupo.items():
        mapa.update(renumerar(cajas, prefijos[grupo], relleno=rellenos.get(grupo, 0)))
    nuevas = list(mapa.values()) + [c.mark for cs in cajas_por_grupo.values()
                                    for c in cs if c.es_vuelo]
    if len(nuevas) != len(set(nuevas)):
        raise ValueError("la renumeración produce marcas repetidas entre grupos.")
    return mapa
