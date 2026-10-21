"""Tipo de losa según el tipo de apoyo, listo para escribirse en Revit.

El "tipo de losa" del flujo Losas.exe ES el código de apoyos del .DL (Pieper-
Martens): qué bordes están empotrados por continuidad con el paño vecino y
cuáles simplemente apoyados. El puente ya lo deduce de la adyacencia
(``puente_losas.tipo_pm.clasificar_panos``, convención validada contra el
fixture RESTAURANTE 2 de Losas.exe); este módulo lo empaqueta por Mark con una
descripción corta y el texto que la tool ``uso_losa`` de ``revit-mcp-tools``
escribe en el parámetro ``Tipo_Losa_PM`` del modelo, para que el tipo quede
visible en la paleta de Propiedades de Revit.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

from puente_losas.contrato import PanoLosa, asignar_bordes
from puente_losas.tipo_pm import clasificar_panos

PARAM_TIPO = "Tipo_Losa_PM"

# Descripción corta de cada código de TIPO del .DL (los 9 casos apoyados en
# los 4 bordes + voladizos; igual que _codigo_por_lados de tipo_pm).
DESCRIPCION_CODIGO = {
    10: "apoyada en 4 bordes",
    21: "1 borde empotrado (N/S)",
    22: "1 borde empotrado (E/W)",
    31: "2 empotrados opuestos N-S",
    32: "2 empotrados opuestos E-W",
    40: "2 empotrados adyacentes",
    51: "3 empotrados (simple N/S)",
    52: "3 empotrados (simple E/W)",
    60: "4 bordes empotrados",
    71: "voladizo (vuela según Y)",
    72: "voladizo (vuela según X)",
}

# lado del contrato (bbox) → punto cardinal en planta
CARDINAL = {"sup": "N", "inf": "S", "der": "E", "izq": "W"}


@dataclass(frozen=True)
class TipoLosa:
    mark: str
    codigo: int                    # TIPO del .DL
    descripcion: str
    empotrados: tuple[str, ...]    # cardinales (N/S/E/W) con vecino que empotra
    borde_fem: str | None          # "simple"/"empotrado" (modelo FEM del puente)
    es_vuelo: bool
    nota: str

    @property
    def texto_param(self) -> str:
        """El valor que se escribe en el parámetro Tipo_Losa_PM de Revit."""
        emp = ",".join(self.empotrados) if self.empotrados else "ninguno"
        return f"{self.codigo} {self.descripcion} | empotrados: {emp}"


def tipos_de_panos(panos: list[PanoLosa]) -> dict[str, TipoLosa]:
    """Tipo de losa por Mark, deducido de la adyacencia (apoyos)."""
    con_borde = asignar_bordes(panos)
    clasif = clasificar_panos(con_borde)
    out: dict[str, TipoLosa] = {}
    for p in con_borde:
        c = clasif[p.mark]
        if c.codigo not in DESCRIPCION_CODIGO:
            raise ValueError(f"{p.mark}: código PM desconocido {c.codigo}.")
        cardinales = tuple(sorted(CARDINAL[lado] for lado in c.empotrados))
        out[p.mark] = TipoLosa(
            mark=p.mark, codigo=c.codigo,
            descripcion=DESCRIPCION_CODIGO[c.codigo],
            empotrados=cardinales, borde_fem=p.borde,
            es_vuelo=p.es_vuelo, nota=c.nota)
    return out


def payload_revit(tipos: dict[str, TipoLosa]) -> dict[str, str]:
    """El dict {Mark: texto} que consume ``uso_losa`` (P["escribir_tipos"])."""
    return {mark: t.texto_param for mark, t in tipos.items()}


def escribir_tipos_json(tipos: dict[str, TipoLosa], ruta: str) -> None:
    datos = {
        "parametro_revit": PARAM_TIPO,
        "metodo": "código de apoyos del .DL (Pieper-Martens, Losas.exe de F. Perdomo); "
                  "empotramiento por adyacencia de paños, un vuelo vecino no empotra",
        "tipos": {mark: asdict(t) for mark, t in tipos.items()},
        "asignar_en_revit": payload_revit(tipos),
    }
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=1, ensure_ascii=False)
