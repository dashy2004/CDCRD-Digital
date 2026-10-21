"""Cargas por uso según el flujo de la Ing. Arlette Ramírez (prompt 14/10/2026).

Biblioteca de Uniform Load Sets en t/m² (cada set = acabados Dead + carga viva;
la mampostería va aparte), reglas de mínimos y de redondeo, y combinación LRFD
del CDCRD (Vol I Título 2; misma 1.2D + 1.6L de ACI 318-19 §5.3.1 ec. b).

Unidades: t/m² en la frontera (unidades de obra); ``q_para_motor`` convierte a
N/m² (1 tonf/m² = 9 806.65 N/m²).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from puente_losas.contrato import PanoLosa

TONF_M2_A_N_M2 = 9806.65
PESO_HORMIGON_T_M3 = 2.4028       # peso específico C210 del prompt de Arlette (tonf/m³)

# Set → (Dead de acabados t/m², patrón de viva, viva t/m²). Valores del prompt
# "Modelar en ETABS desde AutoCAD" §13.1; Parqueos/Gimnasio solo si el proyecto
# los tiene (sus 0.50 vienen del Excel de Torre Nova: validar en cada proyecto).
SETS_CARGA: dict[str, tuple[float, str, float]] = {
    "entrepisos": (0.16, "Live", 0.20),
    "comun": (0.18, "Live", 0.40),
    "techo": (0.16, "LiveT", 0.10),
    "parqueos": (0.16, "LiveP", 0.50),
    "gimnasio": (0.18, "Live", 0.50),
}

MAMPOSTERIA_MINIMA_T_M2 = 0.10    # mínimo en paños apoyados (no vuelos), §13.1
FACTOR_D = 1.2                    # CDCRD/ACI 318-19 LRFD: 1.2D + 1.6L
FACTOR_L = 1.6


def redondear_arriba_005(x: float) -> float:
    """Redondeo SIEMPRE hacia arriba a múltiplos de 0.05, sin subir múltiplos exactos.

    Regla confirmada 15/10/2026: carga_asignada = techo(carga/0.05)·0.05, con
    guarda contra residuos numéricos (0.20 se queda en 0.20).
    """
    if x <= 0:
        return 0.0
    n = x / 0.05
    if abs(n - round(n)) < 1e-9:
        return round(round(n) * 0.05, 10)
    return round(math.ceil(n) * 0.05, 10)


@dataclass(frozen=True)
class CargasPano:
    """Cargas de un paño en t/m², con la mampostería ya redondeada para asignar."""
    peso_propio: float            # h · 2.4028
    acabados_dead: float          # fila Dead del set
    mamposteria_calculada: float  # valor de entrada (o mínimo aplicado), sin redondear
    mamposteria_asignada: float   # redondeada hacia arriba a 0.05 (regla 15/10/2026)
    patron_viva: str              # Live | LiveT | LiveP
    viva: float

    @property
    def d_total(self) -> float:
        return self.peso_propio + self.acabados_dead + self.mamposteria_asignada

    @property
    def q_servicio(self) -> float:
        """D + L (t/m²) — para la flecha elástica."""
        return self.d_total + self.viva

    @property
    def q_ultima(self) -> float:
        """1.2D + 1.6L (t/m²) — para momentos y acero."""
        return FACTOR_D * self.d_total + FACTOR_L * self.viva


def cargas_de_pano(p: PanoLosa, espesor: float | None = None) -> CargasPano:
    """Compone las cargas de un paño según su uso y las reglas de Arlette.

    - Vuelos: SIN mampostería y SIN el mínimo de 0.10 t/m² (excepción obligatoria
      del §13.1); conservan acabados del set, viva y peso propio.
    - Paños apoyados: mampostería = max(valor dado, 0.10), redondeada hacia
      arriba a 0.05 solo al asignar.
    """
    if p.uso not in SETS_CARGA:
        raise ValueError(f"{p.mark}: uso '{p.uso}' sin set de carga.")
    acabados, patron, viva = SETS_CARGA[p.uso]
    h = espesor if espesor is not None else p.espesor
    pp = h * PESO_HORMIGON_T_M3

    if p.es_vuelo:
        mamp_calc = 0.0
        mamp_asig = 0.0
    else:
        mamp_calc = max(p.mamposteria_tm2 or 0.0, MAMPOSTERIA_MINIMA_T_M2)
        mamp_asig = redondear_arriba_005(mamp_calc)

    return CargasPano(peso_propio=pp, acabados_dead=acabados,
                      mamposteria_calculada=mamp_calc, mamposteria_asignada=mamp_asig,
                      patron_viva=patron, viva=viva)


def q_para_motor(q_tm2: float) -> float:
    """t/m² → N/m² (presión que consume el FEM de EstructurasRD)."""
    return q_tm2 * TONF_M2_A_N_M2
