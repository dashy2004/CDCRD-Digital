"""Espesor mínimo normativo y mapeo a la biblioteca de losas de ETABS.

Espesores mínimos sin calcular flechas, ACI 318-19 (base del CDCRD Vol I T05):
- Losas en UNA dirección, macizas (Tabla 7.3.1.1, fy = 420 MPa):
  l/20 simplemente apoyada · l/28 ambos extremos continuos · l/10 voladizo.
- Losas en DOS direcciones CON VIGAS entre todos los apoyos y αfm > 2
  (§8.3.1.2 ec. b): h ≥ ln·(0.8 + fy/1400)/(36 + 9β), y h ≥ 90 mm, con fy en
  MPa, ln la luz libre larga y β la relación de luces libres. Las losas
  esquemáticas del puente apoyan en vigas en todo su contorno: se asume
  αfm > 2 (vigas rígidas) y se declara como supuesto en el informe.

La biblioteca de secciones (L12/L15/L20 macizas, L20A/L25A aligeradas, todas
Shell-Thick) es la del prompt de la Ing. Arlette Ramírez (14/10/2026); las
aligeradas valen 25 cm por defecto.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from puente_losas.contrato import PanoLosa

FY_MPA_DEFECTO = 420.0


def redondear_arriba_005_m(x: float) -> float:
    """Dimensiones/espesores hacia arriba al múltiplo de 0.05 m (Anexo A de Arlette)."""
    if x <= 0:
        return 0.0
    n = x / 0.05
    if abs(n - round(n)) < 1e-9:
        return round(round(n) * 0.05, 10)
    return round(math.ceil(n) * 0.05, 10)


def h_min_una_direccion(luz_corta_m: float, es_vuelo: bool, borde: str) -> float:
    """Tabla 7.3.1.1 (m). El vano se toma como la luz corta (dirección de trabajo)."""
    if es_vuelo:
        return luz_corta_m / 10.0
    return luz_corta_m / (28.0 if borde == "empotrado" else 20.0)


def h_min_dos_direcciones(luz_larga_m: float, relacion_luces: float,
                          fy_mpa: float = FY_MPA_DEFECTO) -> float:
    """§8.3.1.2 ec. (b) en metros, con piso absoluto de 0.090 m.

    Usa las luces entre ejes como aproximación de las luces libres (el export
    esquemático no trae anchos de viga): queda del lado conservador.
    """
    h = luz_larga_m * (0.8 + fy_mpa / 1400.0) / (36.0 + 9.0 * relacion_luces)
    return max(h, 0.090)


@dataclass(frozen=True)
class EspesorPano:
    h_min_normativo: float      # m, sin redondear
    h_recomendado: float        # m, redondeado hacia arriba a 0.05
    h_usado: float              # m, el mayor entre el actual del modelo y el recomendado
    criterio: str               # referencia normativa aplicada
    seccion_etabs: str          # nombre de la biblioteca de Arlette
    seccion_nueva: bool         # True si no está en la biblioteca y hay que definirla
    espesor_modelo_insuficiente: bool


def espesor_de_pano(p: PanoLosa, fy_mpa: float = FY_MPA_DEFECTO) -> EspesorPano:
    if p.trabaja_1d:
        h_min = h_min_una_direccion(p.luz_corta, p.es_vuelo, p.borde or "simple")
        criterio = ("ACI 318-19 T.7.3.1.1 (1D, voladizo l/10)" if p.es_vuelo else
                    f"ACI 318-19 T.7.3.1.1 (1D, {'l/28 continua' if p.borde == 'empotrado' else 'l/20 apoyada'})")
    else:
        h_min = h_min_dos_direcciones(p.luz_larga, p.relacion_luces, fy_mpa)
        criterio = "ACI 318-19 §8.3.1.2(b) (2D con vigas, supuesto αfm>2)"
    h_rec = max(redondear_arriba_005_m(h_min), 0.10)
    h_usado = max(p.espesor, h_rec)
    seccion, nueva = seccion_biblioteca(h_usado, p.trabaja_1d)
    return EspesorPano(h_min_normativo=h_min, h_recomendado=h_rec, h_usado=h_usado,
                       criterio=criterio, seccion_etabs=seccion, seccion_nueva=nueva,
                       espesor_modelo_insuficiente=p.espesor + 1e-9 < h_rec)


def seccion_biblioteca(h_m: float, trabaja_1d: bool) -> tuple[str, bool]:
    """Espesor usado → sección de la biblioteca de Arlette.

    Macizas hasta 0.20 (L12/L15/L20); por encima, aligerada de 25 por defecto
    (L25A-1D / L25A-2D). Un espesor mayor que 0.25 pide una definición nueva
    L[h]A según el esquema (se marca ``seccion_nueva=True``: consultar, no
    inventar nervios). El espesor NO se redondea a 0.05 aquí: la biblioteca
    tiene macizas de 0.12, y las identificadas de 12/15/20 se respetan.
    """
    tol = 1e-9
    if h_m <= 0.12 + tol:
        return "L12", False
    if h_m <= 0.15 + tol:
        return "L15", False
    if h_m <= 0.20 + tol:
        return "L20", False
    sufijo = "1D" if trabaja_1d else "2D"
    if h_m <= 0.25 + tol:
        return f"L25A-{sufijo}", False
    return f"L{int(round(h_m * 100))}A-{sufijo}", True
