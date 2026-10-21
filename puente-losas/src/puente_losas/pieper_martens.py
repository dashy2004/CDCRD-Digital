"""Método de Pieper-Martens (Losas v5.21 de F. Perdomo) — puerto Python.

Reproduce el camino de ``Losas.exe``: momentos de losa por coeficientes
tabulados y balanceo de momentos negativos en bordes compartidos. Es el puerto
del motor nativo C# de EstructurasRD (``src.Core/Calculo/PieperMartens``,
hoy en la historia del repo), cuyas reglas están verificadas contra la salida
real de Losas.exe (fixture de oro RESTAURANTE 2).

Tablas: ``datos/TablasPerdomo.json`` — 21 subtipos × 31 filas, extraídas del
PDF de F. Perdomo «LOSAS CONTINUAS APOYADAS EN TRES Y CUATRO BORDES» (método
del Prof. Dr. Ing. Klaus Pieper y Dipl. Ing. Peter Martens, TU Braunschweig).
Convención (confirmada por el PDF y el fixture):

    Mfx = q·Lx²/Fx    Msx = q·Lx²/|Sx|     (arman según X)
    Mfy = q·Ly²/Fy    Msy = q·Ly²/|Sy|     (arman según Y)

- CADA dirección usa SU propia luz (no la luz corta).
- Índice ε = Ly/Lx, rango 0.50–2.00, interpolación lineal con clamp.
- Sx/Sy nulos ⇒ ese borde no tiene momento de empotramiento ⇒ Ms = 0.
- Balanceo "S": MuI-J = max((MuI+MuJ)/2, 0.75·max(|MuI|,|MuJ|)).
  Balanceo "N": gobierna la losa I (voladizos, nudos de tres lados).
- Tipos 71/72: voladizo (franja 1D), M_apoyo = q·L²/2 sobre la luz que vuela.

Unidades: q en ton/m², luces en m → momentos en ton·m/m (las del .DL/.TXT).
Solo el código 40 y el 71 están verificados numéricamente contra Losas.exe;
el resto del mapeo viene del PDF (ver TABLAS-PERDOMO.md en EstructurasRD).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

FACTOR_MINIMO_BALANCEO = 0.75   # piso del momento balanceado (PDF §2.1)

# Código de TIPO del .DL → subtipo de tabla. Mapeo completo del motor C#
# (commit 2756674 de EstructurasRD). Los x3/x4 son losas apoyadas en TRES
# bordes (un borde libre); 71/72 son voladizos y no usan tabla.
CODIGO_A_SUBTIPO: dict[int, str] = {
    10: "1",      # 4 apoyos simples
    21: "2a",     # 1 empotrado horizontal (N/S)
    22: "2b",     # 1 empotrado vertical (E/W)
    31: "3a",     # 2 opuestos N,S
    32: "3b",     # 2 opuestos E,W
    40: "4",      # 2 adyacentes — VERIFICADO vs Losas.exe (RESTAURANTE 2)
    51: "5a",     # 3 empotrados, apoyo simple horizontal
    52: "5b",     # 3 empotrados, apoyo simple vertical
    60: "6",      # perimetral (4 empotrados)
    13: "7a", 14: "7b",
    23: "8a", 24: "8b",
    33: "9a", 34: "9b",
    43: "10a", 44: "10b",
    53: "11a", 54: "11b",
    63: "12a", 64: "12b",
}
CODIGOS_VOLADIZO = (71, 72)     # 71 vuela sobre Ly (Msy); 72 sobre Lx (Msx)


@dataclass(frozen=True)
class MomentosLosa:
    """Momentos de diseño (ton·m/m); el subíndice es la dirección de la armadura."""
    mfx: float
    mfy: float
    msx: float
    msy: float


@dataclass(frozen=True)
class MomentoApoyo:
    """Momento balanceado del borde I–J en una dirección ("X" | "Y"), ton·m/m."""
    losa_i: str
    losa_j: str
    direccion: str
    mu_i: float
    mu_j: float
    mu_ij: float
    modo: str


@lru_cache(maxsize=1)
def _tablas() -> dict:
    texto = resources.files("puente_losas.datos").joinpath("TablasPerdomo.json").read_text("utf-8")
    return json.loads(texto)


def _interpolar(xs: list[float], ys: list[float], x: float) -> float:
    """Interpolación lineal con clamp en los extremos (igual que el C#)."""
    if x <= xs[0]:
        return ys[0]
    if x >= xs[-1]:
        return ys[-1]
    for i in range(1, len(xs)):
        if x <= xs[i]:
            f = (x - xs[i - 1]) / (xs[i] - xs[i - 1])
            return ys[i - 1] + f * (ys[i] - ys[i - 1])
    return ys[-1]


def factores(subtipo: str, eps: float) -> tuple[float, float, float | None, float | None]:
    """(Fx, Fy, Sx, Sy) del subtipo interpolados en ε = Ly/Lx. Sx/Sy None = sin empotramiento."""
    tipos = _tablas()["tipos"]
    if subtipo not in tipos:
        raise ValueError(f"Subtipo Pieper-Martens desconocido: '{subtipo}'.")
    t = tipos[subtipo]

    def col(nombre: str) -> float | None:
        ys = t[nombre]
        if ys[0] is None:       # en las tablas una columna S es nula en todo el rango o en ninguno
            return None
        return _interpolar(t["eps"], ys, eps)

    fx = _interpolar(t["eps"], t["Fx"], eps)
    fy = _interpolar(t["eps"], t["Fy"], eps)
    return fx, fy, col("Sx"), col("Sy")


def momentos_losa(codigo: int, q: float, lx: float, ly: float) -> MomentosLosa:
    """Momentos PM de una losa por su código de TIPO del .DL (ton·m/m)."""
    if lx <= 0 and codigo not in CODIGOS_VOLADIZO:
        raise ValueError("Lx debe ser positiva.")
    if ly <= 0 and codigo not in CODIGOS_VOLADIZO:
        raise ValueError("Ly debe ser positiva.")
    if codigo == 71:                     # vuela sobre Ly → momento de apoyo según Y
        return MomentosLosa(0.0, 0.0, 0.0, q * ly * ly / 2.0)
    if codigo == 72:                     # vuela sobre Lx
        return MomentosLosa(0.0, 0.0, q * lx * lx / 2.0, 0.0)
    if codigo not in CODIGO_A_SUBTIPO:
        raise ValueError(f"Código de tipo {codigo} no mapeado a subtipo de tabla.")
    fx, fy, sx, sy = factores(CODIGO_A_SUBTIPO[codigo], ly / lx)
    return MomentosLosa(
        mfx=q * lx * lx / fx,
        mfy=q * ly * ly / fy,
        msx=q * lx * lx / abs(sx) if sx is not None else 0.0,
        msy=q * ly * ly / abs(sy) if sy is not None else 0.0,
    )


def balancear(losa_i: str, losa_j: str, direccion: str, modo: str,
              momentos: dict[str, MomentosLosa]) -> MomentoApoyo:
    """Momento de diseño del borde I–J (regla de Losas.exe, verificada en el fixture)."""
    if direccion not in ("X", "Y"):
        raise ValueError("direccion debe ser 'X' o 'Y'.")
    mu_i = momentos[losa_i].msx if direccion == "X" else momentos[losa_i].msy
    mu_j = momentos[losa_j].msx if direccion == "X" else momentos[losa_j].msy
    if modo.strip().upper() == "N":      # gobierna la losa I (vuelo / nudo de tres lados)
        mu_ij = mu_i
    else:                                # "S": promedio con piso 0.75·max
        mu_ij = max((mu_i + mu_j) / 2.0,
                    FACTOR_MINIMO_BALANCEO * max(abs(mu_i), abs(mu_j)))
    return MomentoApoyo(losa_i, losa_j, direccion, mu_i, mu_j, mu_ij, modo.strip().upper())


def eps_recortado(codigo: int, lx: float, ly: float) -> bool:
    """True si ε = Ly/Lx cae fuera del rango tabulado 0.50–2.00 (se usa el extremo)."""
    if codigo in CODIGOS_VOLADIZO:
        return False
    eps = ly / lx
    return eps < 0.50 - 1e-9 or eps > 2.00 + 1e-9
