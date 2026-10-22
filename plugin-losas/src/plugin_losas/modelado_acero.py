"""Plan de MODELADO 3D del acero de losas (sets de Rebar para Revit).

Produce, por losa, los *sets* de barras físicas que la tool
``acero_losas_modelar`` de ``revit-mcp-tools`` convierte en ``Rebar`` reales
(un set = un ``Rebar.CreateFromCurves`` + layout por separación, no una barra
por elemento):

- **principal** (capa inferior; SUPERIOR en vuelos): barras del vano en la
  dirección de trabajo; en 2D ambas direcciones llevan principal y la de la
  luz corta va más abajo (mayor peralte útil);
- **temperatura** (losas 1D): retracción perpendicular al principal;
- **adicional**: bastones superiores sobre cada apoyo compartido, entrando
  L/4 a cada paño (misma convención del dibujo en planta);
- **aligeradas**: la principal va POR NERVIO (posiciones del plan de
  aligeradas, una barra por nervio) y la temperatura en el topping.

SOLAPE (criterio maestro de Emil, mismo del botón Solape de RevitWrite):
barra comercial de 9.0 m; cuando el vano la excede, las
piezas se empalman por traslape recto de 50·db y como máximo el 50% del
refuerzo empalma en una misma sección: el grupo A arranca con pieza entera y
el grupo B (barras alternas) con media pieza, mitad y mitad corrida.

Función pura: no toca Revit. Coordenadas del modelo en metros (el plan lleva
``origen_m`` para deshacer la traslación de origen del export, igual que el
dibujo en planta).
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass

from plugin_losas.plano_acero import _bbox, _direccion, partir_acero

RECUBRIMIENTO_LOSA_M = 0.025     # recubrimiento del acero de losa (ambas caras)
BARRA_COMERCIAL_M = 9.0          # largo comercial de la barra
SOLAPE_DIAMETROS = 50            # traslape recto = 50·db (criterio maestro)
PIEZA_MINIMA_M = 1.0             # una pieza final más corta se come solape extra
FRACCION_BASTON = 0.25           # el bastón entra L/4 a cada paño
SEPARACION_CAPAS_M = 0.003       # holgura libre entre capas cruzadas

DIAMETROS_M = {"#3": 0.009525, "#4": 0.0127, "#5": 0.015875,
               "#6": 0.01905, "#8": 0.0254}


@dataclass(frozen=True)
class SetBarras:
    """Un set de Revit: la PRIMERA barra (línea en planta) + su reparto."""
    mark: str                  # losa anfitriona
    clase: str                 # principal | temperatura | adicional
    capa: str                  # inferior | superior
    eje: str                   # "X" | "Y": dirección en que corre la barra
    diam: str                  # "#4"
    db_m: float
    orden: int                 # 1 = más pegada a la cara; 2 = capa cruzada encima
    linea: tuple               # ((x0, y0), (x1, y1)) de la primera barra (m)
    n: int                     # barras del set
    paso_m: float              # separación del set (2·S cuando hay grupos A/B)
    grupo: str | None          # None sin solape; "A"/"B" con solape
    pieza: int                 # 1..n_piezas dentro de la barra empalmada
    n_piezas: int
    solape_m: float            # traslape entre piezas consecutivas (0 sin solape)


def piezas_con_solape(longitud: float, db_m: float, grupo: int) -> list[tuple[float, float]]:
    """Las piezas comerciales de UNA barra de ``longitud`` m, con traslape.

    ``grupo`` 0 (A) arranca con pieza entera; 1 (B) con media pieza, para que
    las secciones de empalme de barras alternas no coincidan (máx 50%
    empalmado por sección, mitad y mitad corrida).
    """
    if longitud <= BARRA_COMERCIAL_M + 1e-9:
        return [(0.0, longitud)]
    lap = SOLAPE_DIAMETROS * db_m
    primera = BARRA_COMERCIAL_M if grupo == 0 else BARRA_COMERCIAL_M / 2.0
    piezas = [(0.0, min(primera, longitud))]
    while piezas[-1][1] < longitud - 1e-9:
        ini = piezas[-1][1] - lap
        fin = min(ini + BARRA_COMERCIAL_M, longitud)
        piezas.append((round(ini, 6), round(fin, 6)))
    if len(piezas) > 1 and piezas[-1][1] - piezas[-1][0] < PIEZA_MINIMA_M:
        piezas[-1] = (round(longitud - PIEZA_MINIMA_M, 6), longitud)
    return piezas


def _posiciones(b0: float, b1: float, paso: float) -> list[float]:
    """Posiciones centradas de b0 a b1 cada ``paso`` (como el reparto de nervios)."""
    largo = b1 - b0
    if largo <= 0 or paso <= 0:
        return []
    n = int(math.floor(largo / paso + 1e-9)) + 1
    margen = (largo - (n - 1) * paso) / 2.0
    return [round(b0 + margen + i * paso, 6) for i in range(n)]


def _linea(eje, a0, a1, pos):
    if eje == "X":
        return ((round(a0, 6), pos), (round(a1, 6), pos))
    return ((pos, round(a0, 6)), (pos, round(a1, 6)))


def _sets_en_posiciones(mark, clase, capa, eje, diam, posiciones, paso,
                        a0, a1, orden) -> list[SetBarras]:
    """Los sets para barras según ``eje`` entre a0..a1, en ``posiciones``."""
    if not posiciones:
        return []
    db = DIAMETROS_M[diam]
    largo = a1 - a0
    if largo <= 0:
        return []
    piezas_a = piezas_con_solape(largo, db, 0)
    if len(piezas_a) == 1:
        return [SetBarras(mark, clase, capa, eje, diam, db, orden,
                          _linea(eje, a0, a1, posiciones[0]),
                          len(posiciones), paso, None, 1, 1, 0.0)]
    lap = round(SOLAPE_DIAMETROS * db, 6)
    sets = []
    grupos = (("A", piezas_a, posiciones[0::2]),
              ("B", piezas_con_solape(largo, db, 1), posiciones[1::2]))
    for nombre, piezas, pos_grupo in grupos:
        if not pos_grupo:
            continue
        for k, (ini, fin) in enumerate(piezas):
            sets.append(SetBarras(mark, clase, capa, eje, diam, db, orden,
                                  _linea(eje, a0 + ini, a0 + fin, pos_grupo[0]),
                                  len(pos_grupo), 2 * paso, nombre,
                                  k + 1, len(piezas), lap))
    return sets


def _acero_de(mark, clave, editados, armados_pm, por_mark):
    """El texto '#b @ S' que gobierna: editado > comercial PM > franja."""
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


def _partir(texto, contexto, avisos):
    par = partir_acero(texto or "")
    if par is None:
        avisos.append(f"{contexto}: sin armado legible ('{texto}'); se omite.")
        return None
    if par[0] not in DIAMETROS_M:
        avisos.append(f"{contexto}: barra '{par[0]}' fuera del catálogo; se omite.")
        return None
    return par


def _nervios_por_eje(plan_pano):
    out = {}
    for fam in (plan_pano or {}).get("nervios") or []:
        out[fam["direccion"]] = fam
    return out


def _sets_de_losa(mark, contorno, es_vuelo, aceros, plan_alig, avisos):
    """Todos los sets de UNA losa (sin los bastones, que van por apoyo)."""
    x0, y0, x1, y1 = _bbox(contorno)
    rec = RECUBRIMIENTO_LOSA_M
    tipo, eje_corto = _direccion(contorno, es_vuelo)
    capa_principal = "superior" if es_vuelo else "inferior"
    nervios = _nervios_por_eje(plan_alig)
    es_aligerada = bool(nervios)

    def _familia(eje, clase, orden, capa):
        par = _partir(aceros["x" if eje == "X" else "y"],
                      f"{mark} acero {'X' if eje == 'X' else 'Y'}", avisos)
        if par is None:
            return []
        diam, s = par
        a0, a1 = (x0 + rec, x1 - rec) if eje == "X" else (y0 + rec, y1 - rec)
        b0, b1 = (y0 + rec, y1 - rec) if eje == "X" else (x0 + rec, x1 - rec)
        fam = nervios.get(eje) if clase == "principal" else None
        if clase == "principal" and es_aligerada:
            if fam is None:
                return []            # aligerada 1D: la otra dirección no lleva nervios
            base = y0 if eje == "X" else x0
            posiciones = [round(base + p, 6) for p in fam["posiciones_m"]]
            paso = fam["separacion_m"]
        else:
            posiciones = _posiciones(b0, b1, s)
            paso = s
        return _sets_en_posiciones(mark, clase, capa, eje, diam,
                                   posiciones, paso, a0, a1, orden)

    sets = []
    if tipo == "2D":
        # en 2D ambas direcciones son principal; la luz corta va más abajo
        primero = eje_corto or ("X" if (x1 - x0) <= (y1 - y0) else "Y")
        segundo = "Y" if primero == "X" else "X"
        sets += _familia(primero, "principal", 1, capa_principal)
        sets += _familia(segundo, "principal", 2, capa_principal)
    else:                            # 1D o vuelo: principal en el eje corto
        eje_temp = "Y" if eje_corto == "X" else "X"
        sets += _familia(eje_corto, "principal", 1, capa_principal)
        # temperatura: en aligeradas va en el topping (cara superior)
        capa_temp = "superior" if (es_aligerada or es_vuelo) else "inferior"
        sets += _familia(eje_temp, "temperatura", 2, capa_temp)
    return sets


def _sets_de_apoyo(apoyo, contornos, armado, avisos):
    """El set del bastón superior de UN apoyo compartido (host = losa_i)."""
    i, j, d = apoyo["losa_i"], apoyo["losa_j"], apoyo["direccion"]
    if i not in contornos or j not in contornos:
        return []
    par = _partir(armado, f"apoyo {i}-{j}", avisos)
    if par is None:
        return []
    diam, s = par
    rec = RECUBRIMIENTO_LOSA_M
    xi0, yi0, xi1, yi1 = _bbox(contornos[i])
    xj0, yj0, xj1, yj1 = _bbox(contornos[j])
    if d == "X":                     # borde vertical compartido: barras según X
        borde = (max(xi0, xj0) + min(xi1, xj1)) / 2.0
        a0 = borde - FRACCION_BASTON * (xi1 - xi0)
        a1 = borde + FRACCION_BASTON * (xj1 - xj0)
        b0, b1 = max(yi0, yj0) + rec, min(yi1, yj1) - rec
        eje = "X"
    else:                            # borde horizontal: barras según Y
        borde = (max(yi0, yj0) + min(yi1, yj1)) / 2.0
        a0 = borde - FRACCION_BASTON * (yi1 - yi0)
        a1 = borde + FRACCION_BASTON * (yj1 - yj0)
        b0, b1 = max(xi0, xj0) + rec, min(xi1, xj1) - rec
        eje = "Y"
    if b1 <= b0:
        return []
    return _sets_en_posiciones(i, "adicional", "superior", eje, diam,
                               _posiciones(b0, b1, s), s, a0, a1, 1)


def plan_modelado(proyecto: dict, resultados: dict, acero_pm: dict | None = None,
                  editados: dict | None = None, secciones: dict | None = None,
                  aligeradas: dict | None = None) -> dict:
    """El plan completo de modelado 3D (JSON-able) a partir de la corrida.

    ``secciones`` es el ``secciones_losas.json`` de ``plugin-losas secciones``
    (espesor/sección final por losa) y ``aligeradas`` el
    ``plan_aligeradas.json`` (posiciones de nervios). ``editados`` manda sobre
    el acero comercial PM, igual que en el dibujo en planta.
    """
    editados = editados or {}
    avisos: list[str] = []
    contornos, niveles = {}, {}
    for rec in proyecto.get("losas") or []:
        mark = str(rec.get("mark") or rec.get("id"))
        c = rec.get("contorno") or []
        if c:
            contornos[mark] = [[float(x), float(y)] for x, y in c]
            niveles[mark] = rec.get("nivel")
    por_mark = {r["mark"]: r for r in resultados.get("panos") or []}
    armados_pm = (acero_pm or {}).get("losas") or {}
    secciones_por_mark = (secciones or {}).get("secciones") or {}
    alig_por_mark = {p["mark"]: p for p in (aligeradas or {}).get("panos") or []
                     if p.get("nervios")}

    losas = []
    for mark in sorted(contornos):
        if mark not in por_mark:
            continue
        es_vuelo = bool(por_mark[mark].get("es_vuelo"))
        aceros = {
            "x": _acero_de(mark, "x", editados, armados_pm, por_mark),
            "y": _acero_de(mark, "y", editados, armados_pm, por_mark),
        }
        sets = _sets_de_losa(mark, contornos[mark], es_vuelo, aceros,
                             alig_por_mark.get(mark), avisos)
        resuelta = secciones_por_mark.get(mark) or {}
        losas.append({
            "mark": mark, "nivel": niveles.get(mark),
            "seccion": resuelta.get("seccion"),
            "espesor_m": resuelta.get("espesor_m"),
            "aligerada": mark in alig_por_mark,
            "sets": [asdict(s) for s in sets],
            "resumen": {"sets": len(sets),
                        "barras": sum(s.n for s in sets if s.pieza == 1),
                        "solapes": sum(s.n * (s.n_piezas - 1) for s in sets
                                       if s.pieza == 1)},
        })

    armado_apoyos = {}
    for a in (acero_pm or {}).get("apoyos") or []:
        armado_apoyos[(a["losa_i"], a["losa_j"], a["direccion"])] = a["armado"]["disponer"]
    bastones = []
    for a in (resultados.get("pieper_martens") or {}).get("apoyos") or []:
        armado = ((editados.get(a["losa_i"]) or {}).get("apoyo") or
                  (editados.get(a["losa_j"]) or {}).get("apoyo") or
                  armado_apoyos.get((a["losa_i"], a["losa_j"], a["direccion"])) or "")
        for s in _sets_de_apoyo(a, contornos, armado, avisos):
            bastones.append({"losa_i": a["losa_i"], "losa_j": a["losa_j"],
                             "nivel": niveles.get(a["losa_i"]),
                             "set": asdict(s)})

    origen_mm = (proyecto.get("meta") or {}).get("traslacion_origen_mm") or [0.0, 0.0]
    return {
        "unidades": "m",
        "origen_m": [origen_mm[0] / 1000.0, origen_mm[1] / 1000.0],
        "recubrimiento_m": RECUBRIMIENTO_LOSA_M,
        "separacion_capas_m": SEPARACION_CAPAS_M,
        "criterio_solape": (f"barra comercial {BARRA_COMERCIAL_M} m; traslape recto "
                            f"{SOLAPE_DIAMETROS}·db; máx 50% empalmado por sección "
                            "(grupo B arranca con media pieza, mitad y mitad corrida)"),
        "convencion": ("principal = vano en la dirección de trabajo (capa inferior; "
                       "superior en vuelos); temperatura = retracción perpendicular "
                       "(1D; en aligeradas va en el topping); adicional = bastón "
                       "superior sobre el apoyo, L/4 a cada paño; en aligeradas la "
                       "principal va por nervio"),
        "losas": losas,
        "bastones": bastones,
        "avisos": avisos,
    }


def escribir_plan_modelado(plan: dict, ruta: str) -> None:
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=1, ensure_ascii=False)
