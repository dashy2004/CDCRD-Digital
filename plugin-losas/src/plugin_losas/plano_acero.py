"""Dibujo del acero de losas en planta: trazos para el plano (Revit o SVG).

Genera, por losa, la representación clásica del armado en planta:

- **principal**: la barra del vano en la dirección en que trabaja el paño
  (en 2D hay principal en ambas direcciones), línea con ganchos en los
  extremos y su rótulo (#barra @ separación);
- **temperatura**: en losas 1D, el acero de retracción/temperatura
  perpendicular al principal (línea discontinua más corta);
- **adicional**: el bastón negativo sobre cada apoyo compartido,
  perpendicular al borde, entrando L/4 a cada paño, con su rótulo.

Todo en coordenadas del modelo (metros). La tool de Revit
(``revit-mcp-tools/acero_losas_plano``) convierte a pies y lo traza como
líneas de detalle + notas de texto en la vista de planta; el visor podría
pintar los mismos trazos. Función pura: no toca Revit ni archivos.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass

# Barras de uso corriente: número → diámetro en fracción de pulgada.
BARRAS_PULGADA = {"#3": '3/8"', "#4": '1/2"', "#5": '5/8"', "#6": '3/4"', "#8": '1"'}

FRACCION_LUZ_PRINCIPAL = 0.5     # largo del símbolo del principal (× luz)
FRACCION_LUZ_TEMPERATURA = 0.35
FRACCION_BASTON = 0.25           # el bastón entra L/4 a cada paño (práctica usual)
GANCHO_M = 0.30                  # tick de gancho del símbolo, en metros de plano


@dataclass(frozen=True)
class Trazo:
    clase: str                     # principal | temperatura | adicional
    puntos: tuple                  # polilínea [[x, y], ...] (m)
    texto: str
    pos_texto: tuple               # [x, y]
    discontinua: bool = False


def _bbox(contorno):
    xs = [p[0] for p in contorno]
    ys = [p[1] for p in contorno]
    return min(xs), min(ys), max(xs), max(ys)


def _linea_con_ganchos(x0, y0, x1, y1, gancho):
    """Polilínea del símbolo de barra: gancho, tramo recto, gancho."""
    if y0 == y1:    # horizontal → ganchos hacia arriba
        return ((x0, y0 + gancho), (x0, y0), (x1, y1), (x1, y1 + gancho))
    return ((x0 + gancho, y0), (x0, y0), (x1, y1), (x1 + gancho, y1))


def _trazo_barra(clase, eje, cx, cy, largo, texto, desfase=0.0, discontinua=False):
    medio = largo / 2.0
    if eje == "X":
        y = cy + desfase
        puntos = _linea_con_ganchos(cx - medio, y, cx + medio, y, GANCHO_M)
        pos = (cx, y + 0.15)
    else:
        x = cx + desfase
        puntos = _linea_con_ganchos(x, cy - medio, x, cy + medio, GANCHO_M)
        pos = (x + 0.15, cy)
    return Trazo(clase, puntos, texto, pos, discontinua)


def _direccion(contorno, es_vuelo):
    x0, y0, x1, y1 = _bbox(contorno)
    w, h = x1 - x0, y1 - y0
    eje_corto = "X" if w <= h else "Y"
    if es_vuelo:
        return "vuelo", eje_corto
    if max(w, h) / max(min(w, h), 1e-9) > 2.0:
        return "1D", eje_corto
    return "2D", None


def trazos_de_losa(contorno, es_vuelo: bool, acero_x: str, acero_y: str) -> list[Trazo]:
    """Los trazos de armado de UN paño (principal y, si es 1D, temperatura)."""
    x0, y0, x1, y1 = _bbox(contorno)
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    tipo, eje = _direccion(contorno, es_vuelo)

    if tipo == "2D":
        return [
            _trazo_barra("principal", "X", cx, cy, FRACCION_LUZ_PRINCIPAL * w,
                         acero_x or "", desfase=-0.15 * h),
            _trazo_barra("principal", "Y", cx, cy, FRACCION_LUZ_PRINCIPAL * h,
                         acero_y or "", desfase=0.15 * w),
        ]
    acero_prin = acero_x if eje == "X" else acero_y
    acero_temp = acero_y if eje == "X" else acero_x
    luz_prin = w if eje == "X" else h
    luz_temp = h if eje == "X" else w
    trazos = [_trazo_barra("principal", eje, cx, cy, FRACCION_LUZ_PRINCIPAL * luz_prin,
                           acero_prin or "")]
    if tipo == "1D":
        trazos.append(_trazo_barra(
            "temperatura", "Y" if eje == "X" else "X", cx, cy,
            FRACCION_LUZ_TEMPERATURA * luz_temp,
            ((acero_temp or "") + " (temp)").strip(), desfase=0.0, discontinua=True))
    return trazos


def trazo_de_apoyo(caja_i, caja_j, direccion: str, texto: str) -> Trazo | None:
    """El bastón adicional sobre el borde compartido (L/4 a cada lado).

    ``direccion`` es la del armado del par ("X" = borde vertical compartido).
    None si las cajas no comparten borde en esa dirección.
    """
    xi0, yi0, xi1, yi1 = caja_i
    xj0, yj0, xj1, yj1 = caja_j
    if direccion == "X":
        borde = (max(xi0, xj0) + min(xi1, xj1)) / 2.0
        ya, yb = max(yi0, yj0), min(yi1, yj1)
        if yb <= ya:
            return None
        y = (ya + yb) / 2.0
        a = borde - FRACCION_BASTON * (xi1 - xi0)
        b = borde + FRACCION_BASTON * (xj1 - xj0)
        # ganchos del bastón hacia abajo (barra superior)
        puntos = ((a, y - GANCHO_M), (a, y), (b, y), (b, y - GANCHO_M))
        return Trazo("adicional", puntos, texto, (borde, y + 0.15))
    borde = (max(yi0, yj0) + min(yi1, yj1)) / 2.0
    xa, xb = max(xi0, xj0), min(xi1, xj1)
    if xb <= xa:
        return None
    x = (xa + xb) / 2.0
    a = borde - FRACCION_BASTON * (yi1 - yi0)
    b = borde + FRACCION_BASTON * (yj1 - yj0)
    puntos = ((x - GANCHO_M, a), (x, a), (x, b), (x - GANCHO_M, b))
    return Trazo("adicional", puntos, texto, (x + 0.15, borde))


def plano_acero(proyecto: dict, resultados: dict, acero_pm: dict | None = None,
                editados: dict | None = None) -> dict:
    """El plan de dibujo completo (JSON-able) a partir de la corrida del puente.

    ``editados`` = {mark: {"x","y","apoyo"}} con el acero ajustado en el panel;
    manda sobre el comercial calculado (``acero_pm``). Para el bastón de un
    apoyo gobierna el acero "apoyo" editado de cualquiera de las dos losas y,
    si no hay, el armado balanceado de ``acero_pm``.
    """
    editados = editados or {}
    contornos = {}
    niveles = {}
    for rec in proyecto.get("losas") or []:
        mark = str(rec.get("mark") or rec.get("id"))
        c = rec.get("contorno") or []
        if c:
            contornos[mark] = [[float(x), float(y)] for x, y in c]
            niveles[mark] = rec.get("nivel")
    por_mark = {r["mark"]: r for r in resultados.get("panos") or []}
    armados_pm = (acero_pm or {}).get("losas") or {}

    def _acero(mark, clave):
        ed = (editados.get(mark) or {}).get(clave)
        if ed:
            return ed
        armados = (armados_pm.get(mark) or {}).get("armados")
        if armados:
            if clave == "x":
                return armados["mfx"]["disponer"]
            if clave == "y":
                return armados["mfy"]["disponer"]
            peor = armados["msx"] if armados["msx"]["as_diseno"] >= \
                armados["msy"]["as_diseno"] else armados["msy"]
            return peor["disponer"]
        r = por_mark.get(mark) or {}
        franja = r.get("franja_" + ("apoyo" if clave == "apoyo" else clave)) or {}
        return franja.get("disponer") or ""

    losas = []
    for mark, contorno in contornos.items():
        if mark not in por_mark:
            continue
        es_vuelo = bool(por_mark[mark].get("es_vuelo"))
        trazos = trazos_de_losa(contorno, es_vuelo, _acero(mark, "x"), _acero(mark, "y"))
        losas.append({"mark": mark, "nivel": niveles.get(mark),
                      "trazos": [asdict(t) for t in trazos]})

    armado_apoyos = {}
    for a in (acero_pm or {}).get("apoyos") or []:
        armado_apoyos[(a["losa_i"], a["losa_j"], a["direccion"])] = a["armado"]["disponer"]

    apoyos = []
    for a in (resultados.get("pieper_martens") or {}).get("apoyos") or []:
        i, j, d = a["losa_i"], a["losa_j"], a["direccion"]
        if i not in contornos or j not in contornos:
            continue
        texto = ((editados.get(i) or {}).get("apoyo") or
                 (editados.get(j) or {}).get("apoyo") or
                 armado_apoyos.get((i, j, d)) or "")
        trazo = trazo_de_apoyo(_bbox(contornos[i]), _bbox(contornos[j]), d, texto)
        if trazo is not None:
            apoyos.append({"losa_i": i, "losa_j": j, "nivel": niveles.get(i),
                           "trazo": asdict(trazo)})

    return {
        "unidades": "m",
        "convencion": "principal = vano en la dirección de trabajo; temperatura = "
                      "retracción perpendicular (1D, discontinua); adicional = bastón "
                      "negativo sobre el apoyo, L/4 a cada paño",
        "losas": losas,
        "apoyos": apoyos,
        "tabla_parametros": ["Mark", "Uso_Losa", "Tipo_Losa_PM", "Seccion_Losa",
                             "Acero_X", "Acero_Y", "Acero_Apoyo"],
    }


def escribir_plano_acero(plan: dict, ruta: str) -> None:
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1, ensure_ascii=False)


# ---------------------- formato de barra y separación ----------------------
def formatear_acero(barra: str, separacion_m: float) -> str:
    """("#4", 0.15) → '#4 @ 0.15' (el texto que viaja a Revit y al plano)."""
    if barra not in BARRAS_PULGADA:
        raise ValueError(f"barra '{barra}' fuera del catálogo {sorted(BARRAS_PULGADA)}.")
    if not 0.02 <= separacion_m <= 1.0:
        raise ValueError(f"separación {separacion_m} m fuera de rango razonable.")
    return f"{barra} @ {separacion_m:.2f}"


def partir_acero(texto: str) -> tuple[str, float] | None:
    """'#3 @ 150 mm' | '#3 @ 0.15' → ('#3', 0.15); None si no se reconoce."""
    import re
    m = re.match(r"\s*(#\d+)\s*@\s*([\d.]+)\s*(mm)?\s*$", texto or "")
    if not m:
        return None
    barra = m.group(1)
    valor = float(m.group(2))
    separacion = valor / 1000.0 if m.group(3) == "mm" or valor > 2.0 else valor
    return barra, round(separacion, 3)
