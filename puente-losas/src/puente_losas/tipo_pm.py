"""Clasificación de cada paño en el código de TIPO del .DL de Losas.exe.

El código sale del patrón de bordes continuos (= empotrados para Pieper-
Martens) que el puente ya detecta por adyacencia: N=sup, S=inf, E=der, W=izq.
Cubre los 9 casos de losa apoyada en los 4 bordes (10..60) y los voladizos
(71/72). Las losas apoyadas en TRES bordes (códigos x3/x4, borde libre real)
no se clasifican automáticamente: el export esquemático no distingue un borde
libre de uno simplemente apoyado, así que exigen declaración manual.
"""
from __future__ import annotations

from dataclasses import dataclass

from puente_losas.contrato import PanoLosa, lados_continuos, lados_empotrados
from puente_losas.pieper_martens import eps_recortado


@dataclass(frozen=True)
class ClasificacionPM:
    mark: str
    codigo: int
    empotrados: tuple[str, ...]   # lados continuos (izq/der/inf/sup)
    eps_recortado: bool           # Ly/Lx fuera del rango tabulado 0.50–2.00
    nota: str = ""


def _codigo_por_lados(sup: bool, inf: bool, izq: bool, der: bool) -> int:
    horizontales = sup + inf          # bordes N/S empotrados
    verticales = izq + der            # bordes E/W empotrados
    total = horizontales + verticales
    if total == 0:
        return 10
    if total == 1:
        return 21 if horizontales else 22
    if total == 2:
        if horizontales == 2:
            return 31
        if verticales == 2:
            return 32
        return 40                      # dos adyacentes (cualquier esquina)
    if total == 3:
        return 51 if horizontales == 1 else 52   # el apoyo simple que queda
    return 60


def clasificar_panos(panos: list[PanoLosa]) -> dict[str, ClasificacionPM]:
    """Código PM por Mark. Vuelos → 71/72 según la dirección en que vuelan.

    Un vuelo vecino NO empotra el borde de la losa (convención de Losas.exe
    verificada en RESTAURANTE 2); su momento entra por el balanceo "N".
    """
    lados = lados_empotrados(panos)
    resultado: dict[str, ClasificacionPM] = {}
    for p in panos:
        v = lados[p.mark]
        empotrados = tuple(k for k, w in v.items() if w is not None)
        if p.es_vuelo:
            # La ménsula proyecta sobre la luz corta: Ly corta → 71 (Msy),
            # Lx corta → 72 (Msx). Igual que la losa 5 del fixture RESTAURANTE 2.
            codigo = 71 if p.ly <= p.lx else 72
            nota = "voladizo: M_apoyo = q·L²/2 sobre la luz que vuela"
        else:
            codigo = _codigo_por_lados("sup" in empotrados, "inf" in empotrados,
                                       "izq" in empotrados, "der" in empotrados)
            nota = ""
        recorte = eps_recortado(codigo, p.lx, p.ly)
        if recorte:
            nota = (nota + "; " if nota else "") + \
                "ε=Ly/Lx fuera de 0.50–2.00: se usa el extremo tabulado"
        resultado[p.mark] = ClasificacionPM(p.mark, codigo, empotrados, recorte, nota)
    return resultado


def pares_balanceo(panos: list[PanoLosa]) -> tuple[list[tuple[str, str, str]],
                                                   list[tuple[str, str, str]]]:
    """Pares (I, J, modo) de bordes compartidos, según X y según Y.

    Un borde vertical compartido (vecino izq/der) arma acero según X → par X;
    uno horizontal (inf/sup) → par Y. Si una de las dos losas es un vuelo, va
    como losa I con modo "N" (gobierna el vuelo, igual que en el fixture);
    el resto balancea con "S".
    """
    lados = lados_continuos(panos)
    por_mark = {p.mark: p for p in panos}
    x: list[tuple[str, str, str]] = []
    y: list[tuple[str, str, str]] = []
    vistos: set[tuple[str, str, str]] = set()
    for p in panos:
        for lado, vecino in lados[p.mark].items():
            if vecino is None:
                continue
            i, j = p.mark, vecino
            if por_mark[j].es_vuelo and not p.es_vuelo:
                i, j = j, i                         # el vuelo siempre es la losa I
            modo = "N" if por_mark[i].es_vuelo else "S"
            direccion = "X" if lado in ("izq", "der") else "Y"
            clave = (direccion, *sorted((i, j)))
            if clave in vistos:
                continue
            vistos.add(clave)
            (x if direccion == "X" else y).append((i, j, modo))
    return x, y
