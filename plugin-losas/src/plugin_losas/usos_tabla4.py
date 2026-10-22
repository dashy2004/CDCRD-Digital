"""Usos de la Tabla 4 del CDCRD (cargas vivas mínimas) para el desplegable Uso_Losa.

Fuente de datos: ``datos/machine/cargas_vivas.json`` del repo (Tabla 4,
cláusula 2.7.2, Tomo 1, versión 2026-07 — la extracción de la Ing. Arlette
Ramírez para la máquina). Este módulo NO inventa valores: carga ese JSON, le
da un id estable a cada uso y sugiere el set de carga del flujo Excel/ETABS
(``puente_losas.cargas.SETS_CARGA``) que cubre la viva de la tabla.

Unidades: la Tabla 4 está en kN/m²; los sets de Arlette en t/m²
(1 t/m² = 9.80665 kN/m²).
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass

from puente_losas.cargas import SETS_CARGA

KN_M2_A_T_M2 = 1.0 / 9.80665
RUTA_RELATIVA_TABLA4 = os.path.join("datos", "machine", "cargas_vivas.json")

# Sets candidatos para usos de piso, del más liviano al más pesado. "techo" y
# "parqueos" tienen patrón de viva propio (LiveT/LiveP) y se sugieren solo a
# sus grupos; "gimnasio" es el set de piso más pesado disponible (0.50 t/m²).
_SETS_PISO = ("entrepisos", "comun", "gimnasio")


@dataclass(frozen=True)
class UsoTabla4:
    """Un renglón de la Tabla 4, con id estable para guardarlo en Uso_Losa."""
    id: str
    grupo: str
    uso: str
    viva_kn_m2: float | None      # None = la tabla da una regla, no un número
    concentrada_kn: float | None
    nota: str | None = None
    regla: str | None = None

    @property
    def viva_tm2(self) -> float | None:
        if self.viva_kn_m2 is None:
            return None
        return self.viva_kn_m2 * KN_M2_A_T_M2

    @property
    def etiqueta(self) -> str:
        """Texto del desplegable: grupo — uso (viva)."""
        viva = f"{self.viva_kn_m2:.2f} kN/m²" if self.viva_kn_m2 is not None else "regla"
        return f"{self.grupo} — {self.uso} ({viva})"


@dataclass(frozen=True)
class SugerenciaSet:
    """Set de carga del flujo Excel/ETABS sugerido para un uso de la Tabla 4."""
    set_carga: str | None         # clave de SETS_CARGA o None (requiere declaración)
    cubre: bool                   # viva del set ≥ viva de la Tabla 4
    viva_set_tm2: float | None
    nota: str = ""


@dataclass(frozen=True)
class TablaUsos:
    usos: tuple[UsoTabla4, ...]
    fuente: dict

    def por_id(self, uso_id: str) -> UsoTabla4:
        for u in self.usos:
            if u.id == uso_id:
                return u
        raise KeyError(f"uso '{uso_id}' no está en la Tabla 4 cargada.")


def _slug(texto: str) -> str:
    # los comparadores distinguen renglones (helipuertos <= / > 13.35 kN)
    con_comparadores = texto.lower().replace("<=", " max ").replace(">", " mas ")
    return re.sub(r"[^a-z0-9]+", "-", con_comparadores).strip("-")


def ruta_tabla4_por_defecto(desde: str | None = None) -> str:
    """Busca ``datos/machine/cargas_vivas.json`` subiendo desde este paquete.

    Funciona en el checkout del repo (layout documentado). Para instalaciones
    fuera del repo, pasar la ruta explícita a ``cargar_tabla4``.
    """
    base = os.path.dirname(os.path.abspath(desde or __file__))
    for _ in range(8):
        candidata = os.path.join(base, RUTA_RELATIVA_TABLA4)
        if os.path.isfile(candidata):
            return candidata
        padre = os.path.dirname(base)
        if padre == base:
            break
        base = padre
    raise FileNotFoundError(
        f"No se encontró {RUTA_RELATIVA_TABLA4} subiendo desde {desde or __file__}; "
        "pase la ruta explícita a cargar_tabla4().")


def cargar_tabla4(ruta: str | None = None) -> TablaUsos:
    """Carga la Tabla 4 desde el JSON del repo (o la ruta dada) y valida lo mínimo."""
    with open(ruta or ruta_tabla4_por_defecto(), encoding="utf-8") as f:
        d = json.load(f)
    if d.get("parametro") != "cargas_vivas_minimas" or "valores" not in d:
        raise ValueError("El JSON no es la Tabla 4 de cargas vivas (cargas_vivas.json).")
    notas = d.get("notas") or {}
    usos = []
    vistos: set[str] = set()
    for rec in d["valores"]:
        uso_id = _slug(f"{rec['grupo']}/{rec['uso']}")
        if uso_id in vistos:
            raise ValueError(f"id duplicado en la Tabla 4: {uso_id}")
        vistos.add(uso_id)
        nota = rec.get("nota")
        usos.append(UsoTabla4(
            id=uso_id, grupo=rec["grupo"], uso=rec["uso"],
            viva_kn_m2=rec.get("uniforme"), concentrada_kn=rec.get("concentrada"),
            nota=notas.get(nota) if nota else None, regla=rec.get("regla")))
    return TablaUsos(usos=tuple(usos), fuente=d.get("fuente") or {})


def opciones_desplegable(tabla: TablaUsos) -> list[dict]:
    """Las opciones del combo Uso_Losa, en el orden de la Tabla 4."""
    return [{"id": u.id, "etiqueta": u.etiqueta, "grupo": u.grupo} for u in tabla.usos]


def set_sugerido(uso: UsoTabla4) -> SugerenciaSet:
    """Sugerencia de set de carga (flujo de Arlette) para un uso de la Tabla 4.

    - Garajes/estacionamientos → ``parqueos`` (patrón LiveP).
    - Techos → ``techo`` (patrón LiveT); si la viva de la tabla supera el set
      (p. ej. techos de almacenamiento, 4.79 kN/m²), se marca ``cubre=False``.
    - Resto: el set de piso más liviano cuya viva ≥ la de la tabla; si ninguno
      llega (p. ej. escenarios, 7.18 kN/m²), el más pesado con ``cubre=False``.
    - Usos por regla (balcones: 1.5× el área servida) → sin set: hay que
      declarar la carga del área servida; el paño además es candidato a vuelo.
    """
    if uso.viva_kn_m2 is None:
        return SugerenciaSet(None, False, None,
                             nota=uso.regla or "la Tabla 4 da una regla, no un valor: declarar la carga")
    viva = uso.viva_tm2
    tol = 1e-9

    def _sugerir(nombre: str) -> SugerenciaSet:
        viva_set = SETS_CARGA[nombre][2]
        cubre = viva_set + tol >= viva
        nota = "" if cubre else (
            f"viva Tabla 4 ({uso.viva_kn_m2:.2f} kN/m² = {viva:.3f} t/m²) supera el set "
            f"'{nombre}' ({viva_set:.2f} t/m²): declarar carga especial en el proyecto")
        return SugerenciaSet(nombre, cubre, viva_set, nota)

    if uso.grupo == "Garajes y estacionamientos":
        return _sugerir("parqueos")
    if uso.grupo == "Techos":
        return _sugerir("techo")
    for nombre in _SETS_PISO:
        s = _sugerir(nombre)
        if s.cubre:
            return s
    return _sugerir(_SETS_PISO[-1])
