"""Adaptador paño → motor FEM de EstructurasRD (motor_fea).

Por cada paño arma los parámetros de ``motor_fea.diseno_losa.disenar_losa``
(el mismo contrato del CLI ``motor-fea --disenar-losa params.json``) y devuelve
momentos, flecha y acero por franja. El motor es el de EstructurasRD
(https://github.com/dashy2004/EstructurasRD, MIT): FEM de placa ACM con
3 GDL/nodo, carga uniforme lumped, bordes "simple"/"empotrado", y diseño de
franjas ACI 318-19 en SI (N, mm, MPa).

Decisiones de la frontera (documentadas, no del motor):
- El rectángulo analizado es el equivalente lx×ly del paño; huecos y entrantes
  no entran al FEM (limitación declarada: esto es predimensionado, el análisis
  definitivo lo hace ETABS con la geometría real).
- Momentos y acero se calculan con q última (1.2D+1.6L). La flecha se reporta
  en servicio (D+L) escalando linealmente w_central (el modelo es elástico
  lineal: w ∝ q), flecha ELÁSTICA INMEDIATA con sección bruta, sin fluencia
  ni fisuración.
- E del hormigón: Ec = 15100·√f'c con f'c en kg/cm² (config. inicial del
  prompt de Arlette). Para C210: 15100·√210 = 218 819.8 kg/cm² ≈ 2.1459e10 Pa.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from puente_losas.cargas import CargasPano, cargas_de_pano, q_para_motor
from puente_losas.contrato import PanoLosa
from puente_losas.espesor import EspesorPano, espesor_de_pano

KGF_CM2_A_PA = 98066.5

# Materiales por defecto del encargo: C210 y A615 Gr60 (f'c nominal
# 210 kg/cm² = 20.6 MPa; el encargo fija 21 MPa para el diseño de acero).
FC_KG_CM2 = 210.0
FC_MPA = 21.0
FY_MPA = 420.0
NU_HORMIGON = 0.20
RECUBRIMIENTO_LOSA_MM = 25.0

# Malla: tamaño objetivo de elemento y topes (el solver del motor es denso).
LADO_ELEMENTO_OBJETIVO_M = 0.50
DIV_MIN, DIV_MAX = 8, 16


def modulo_elasticidad_pa(fc_kg_cm2: float = FC_KG_CM2) -> float:
    """Ec = 15100·√f'c (kg/cm²) → Pa."""
    return 15100.0 * math.sqrt(fc_kg_cm2) * KGF_CM2_A_PA


def divisiones_malla(lado_m: float) -> int:
    return max(DIV_MIN, min(DIV_MAX, round(lado_m / LADO_ELEMENTO_OBJETIVO_M)))


def params_motor(p: PanoLosa, cargas: CargasPano, h_usado: float) -> dict:
    """El params.json de ``motor-fea --disenar-losa`` para este paño (SI)."""
    return {
        "a": p.lx, "b": p.ly,
        "nx": divisiones_malla(p.lx), "ny": divisiones_malla(p.ly),
        "E": modulo_elasticidad_pa(), "nu": NU_HORMIGON,
        "t": h_usado,
        "q": q_para_motor(cargas.q_ultima),
        "fc": FC_MPA, "fy": FY_MPA,
        "recubrimiento": RECUBRIMIENTO_LOSA_MM,
        "borde": p.borde or "simple",
    }


@dataclass(frozen=True)
class ResultadoPano:
    pano: PanoLosa
    cargas: CargasPano
    espesor: EspesorPano
    params: dict               # entrada exacta que consumió el motor
    w_ultima_m: float          # flecha central con q última (salida cruda del FEM)
    w_servicio_m: float        # w_ultima · (q_serv/q_ult), modelo lineal
    mx_tonf_m: float           # momento de vano X (tonf·m/m)
    my_tonf_m: float           # momento de vano Y (tonf·m/m)
    m_apoyo_tonf_m: float      # momento de apoyo (tonf·m/m)
    franja_x: dict             # as_requerido/as_diseno (mm²/m), disponer, cumple...
    franja_y: dict
    franja_apoyo: dict

    @property
    def limite_flecha_m(self) -> float:
        """l/240 (ACI 318-19 T.24.2.2, techo o piso que no soporta elementos frágiles)."""
        return self.pano.luz_corta / 240.0

    @property
    def flecha_cumple(self) -> bool:
        return self.w_servicio_m <= self.limite_flecha_m + 1e-12


N_M_A_TONF_M = 1.0 / 9806.65   # N·m/m → tonf·m/m


def _analizar_vuelo(p: PanoLosa, cargas: CargasPano, esp: EspesorPano) -> ResultadoPano:
    """Vuelo como franja en voladizo (el FEM del motor apoya los 4 bordes: no aplica).

    Por franja de 1 m: M_apoyo = q·l²/2 y w_punta = q·l⁴/(8D), con l = luz corta
    (la proyección del vuelo) y D = E·t³/12(1−ν²). El acero sale del mismo
    módulo ACI 318-19 del motor (diseno_losa_franja); el vano lleva el mínimo
    de retracción/temperatura (momento 0 hacia el borde libre).
    """
    from motor_fea.normativa.aci318 import diseno_losa_franja

    h = esp.h_usado
    l = p.luz_corta
    q_u = q_para_motor(cargas.q_ultima)              # N/m²
    q_s = q_para_motor(cargas.q_servicio)
    m_apoyo = q_u * l ** 2 / 2.0                     # N·m/m
    e_pa = modulo_elasticidad_pa()
    d_placa = e_pa * h ** 3 / (12.0 * (1.0 - NU_HORMIGON ** 2))
    w_u = q_u * l ** 4 / (8.0 * d_placa)
    h_mm = h * 1000.0
    d_mm = h_mm - RECUBRIMIENTO_LOSA_MM
    apoyo = diseno_losa_franja(m_apoyo * 1000.0, 1000.0, h_mm, d_mm, FC_MPA, FY_MPA)
    minimo = diseno_losa_franja(0.0, 1000.0, h_mm, d_mm, FC_MPA, FY_MPA)

    def _franja(f) -> dict:
        a = f.armadura
        return {"as_requerido": f.as_requerido, "as_minimo": f.as_minimo,
                "as_diseno": f.as_diseno, "seccion_insuficiente": f.seccion_insuficiente,
                "gobierna_minimo": f.gobierna_minimo, "numero_barra": a.numero_barra,
                "espaciamiento": a.espaciamiento, "as_provista": a.as_provista,
                "cumple": a.cumple, "disponer": a.disponer}

    params = {"modelo": "voladizo_analitico", "l": l, "t": h, "q": q_u,
              "E": e_pa, "nu": NU_HORMIGON, "fc": FC_MPA, "fy": FY_MPA,
              "recubrimiento": RECUBRIMIENTO_LOSA_MM,
              "formulas": "M=q*l^2/2; w=q*l^4/(8D)"}
    return ResultadoPano(
        pano=p, cargas=cargas, espesor=esp, params=params,
        w_ultima_m=w_u, w_servicio_m=w_u * q_s / q_u,
        mx_tonf_m=0.0, my_tonf_m=0.0,
        m_apoyo_tonf_m=m_apoyo * N_M_A_TONF_M,
        franja_x=_franja(minimo), franja_y=_franja(minimo), franja_apoyo=_franja(apoyo),
    )


def analizar_pano(p: PanoLosa) -> ResultadoPano:
    """FEM + diseño de un paño con el motor de EstructurasRD (import directo).

    Los vuelos no pasan por el FEM de placa (que apoya el contorno completo):
    van como franja en voladizo analítica con el acero del módulo ACI del motor.
    """
    from motor_fea.api.contrato import disenar_losa_dict

    if p.borde is None:
        raise ValueError(f"{p.mark}: borde sin asignar; pase los paños por asignar_bordes().")
    esp = espesor_de_pano(p)
    cargas = cargas_de_pano(p, espesor=esp.h_usado)
    if p.es_vuelo:
        return _analizar_vuelo(p, cargas, esp)
    params = params_motor(p, cargas, esp.h_usado)
    r = disenar_losa_dict(params)

    factor_servicio = cargas.q_servicio / cargas.q_ultima
    return ResultadoPano(
        pano=p, cargas=cargas, espesor=esp, params=params,
        w_ultima_m=r["w_central"],
        w_servicio_m=r["w_central"] * factor_servicio,
        mx_tonf_m=r["mx_max"] * N_M_A_TONF_M,
        my_tonf_m=r["my_max"] * N_M_A_TONF_M,
        m_apoyo_tonf_m=r["m_apoyo_max"] * N_M_A_TONF_M,
        franja_x=r["franja_x"], franja_y=r["franja_y"], franja_apoyo=r["franja_apoyo"],
    )


def analizar_panos(panos: list[PanoLosa]) -> list[ResultadoPano]:
    return [analizar_pano(p) for p in panos]
