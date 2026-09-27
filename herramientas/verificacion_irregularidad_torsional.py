# -*- coding: utf-8 -*-
"""verificacion_irregularidad_torsional: coeficiente CIT y su clasificacion segun CDCRD 2026-07, Tomo 1, Titulo 2.

Existe porque ETABS entrega la tabla 'Story Max Over Avg Drifts' pero NO aplica
el criterio del CDCRD sobre ella: no clasifica H-1, no distingue irregularidad
moderada de extrema, no conoce la prohibicion de 2.10.4.1.2.2 para CDS D/E/F, y
no verifica el tope absoluto de 1.60 de 2.10.4.1.2.1. Esta herramienta toma esa
tabla y cierra la verificacion con la clausula de origen en cada renglon.

Criterio implementado:
  CIT = Dmax / Dprom por piso y por direccion de analisis     2.10.8.1.13 Ec. 30
  CIT de la estructura en una direccion = el mayor de los pisos de esa direccion
  H-1 existe cuando CIT > 1.20 en uno o mas pisos              Tabla 12, H-1
  1.20 < CIT < 1.40   irregularidad torsional moderada         Tabla 13
  CIT = 1.40          sin clase literal; INCOMPLETO para Emil  Tabla 13
  CIT > 1.40          irregularidad torsional extrema          Tabla 13
  CIT no puede exceder 1.60 en ningun caso                     2.10.4.1.2.1
  extrema PROHIBIDA en CDS D, E o F, salvo vivienda unifamiliar de hasta 2 niveles
                                                               2.10.4.1.2.2
  con extrema en ambas direcciones, rho = 1.3                  2.10.4.1.2.3
  con H-1 en CDS C a F: fuerzas en conexiones de diafragma +25%  2.10.4.1.1
  con H-1 en CDS C a F: Ax = (dmax / 1.2 dprom)^2, 1 < Ax < 3  2.10.8.1.14 Ec. 31

Precondicion que la herramienta NO puede verificar sola y por eso exige declarar:
el CIT debe evaluarse CON excentricidad accidental del 5% de la dimension en
planta perpendicular a la direccion de analisis, en ambos signos (2.10.8.1.10).
En ETABS eso es EccenRatio = 0.05 en el caso de respuesta espectral. Si se
declara ecc_accidental = true, certifica que se evaluaron ambos signos. Si no,
la herramienta devuelve INCOMPLETO: el cociente sin excentricidad puede variar.

El diafragma se asume rigido (2.10.8.1.13 ultimo parrafo). Si el diafragma es
flexible y se comprueba, la irregularidad torsional no aplica: pasar
diafragma_flexible = true y la herramienta no emite veredicto.

Unidades generales: kN, m, MPa. Las derivas son adimensionales; los
desplazamientos entran en m y solo se usa su cociente.

Uso:
    python3 verificacion_irregularidad_torsional.py entrada.json [-o salida.json]
    python3 verificacion_irregularidad_torsional.py --test

Entrada (JSON):
{
  "id": "EDIFICIO3-TIPOC",
  "cds": "D",
  "vivienda_unifamiliar_2_niveles": false,
  "ecc_accidental": false,
  "h1_por_resistencia": null,
  "diafragma_flexible": false,
  "derivas": [
    {"piso": "NIVEL 1", "caso": "Ex", "direccion": "X", "d_max": 0.000204, "d_prom": 0.000126},
    {"piso": "NIVEL 1", "caso": "Ey", "direccion": "Y", "d_max": 0.000267, "d_prom": 0.000183}
  ],
  "desplazamientos": [
    {"piso": "NIVEL 1", "caso": "Ex", "direccion": "X", "d_max": 0.62, "d_prom": 0.40}
  ]
}
Solo se consideran los renglones donde la direccion del resultado coincide con
la direccion del caso (2.10.7.2: la irregularidad se evalua por direccion, sin
aplicacion simultanea de la ortogonal). Los renglones cruzados se descartan y se
reportan aparte: sus cocientes son numericamente grandes pero carecen de
significado porque la deriva de fondo es despreciable.
"""

import json
import math
import sys
from pathlib import Path

CDS_RESTRINGIDAS = ("D", "E", "F")   # 2.10.4.1.2.2
DIR_DE_CASO = {"EX": "X", "EY": "Y", "SX": "X", "SY": "Y"}
RUTA_UMBRALES = Path(__file__).resolve().parent.parent / "datos" / "machine" / "irregularidades_horizontales.json"


def _umbrales(ruta=RUTA_UMBRALES):
    """Lee la capa maquina; el fallback literal se usa solo si el archivo falta."""
    try:
        with open(ruta, encoding="utf-8") as fh:
            datos = json.load(fh)
    except FileNotFoundError:
        # Fallback explicito, cotejado con T2 Tabla 12, Tabla 13 y 2.10.4.1.2.1.
        return {"h1": 1.20, "extrema": 1.40, "tope": 1.60,
                "ax_divisor": 1.20, "ax_min": 1.0, "ax_max": 3.0}, "FALLBACK: falta " + str(ruta)
    filas = {fila["id"]: fila for fila in datos["valores"]}
    cl = datos["clasificacion_torsional"]
    ax = datos["amplificacion_torsion_accidental"]
    return {"h1": float(filas["H-1"]["cit_mayor_que"]),
            "extrema": float(cl["extrema"]["cit_mayor_que"]),
            "tope": float(cl["tope"]["cit_no_excede"]),
            "ax_divisor": float(ax["divisor_desplazamiento_promedio"]),
            "ax_min": float(ax["Ax_minimo"]), "ax_max": float(ax["Ax_maximo"])}, str(ruta)


def _dir_del_caso(caso, declarada=None):
    """La direccion de analisis del caso. Se toma la declarada si viene; si no,
    se infiere del nombre. Devuelve None si no se puede decidir."""
    if declarada:
        return str(declarada).upper()
    return DIR_DE_CASO.get(str(caso).upper().replace(" ", ""))


def _clasificar(cit, limites):
    if cit <= limites["h1"]:
        return "SIN IRREGULARIDAD TORSIONAL", "CDCRD T2 Tabla 12, H-1"
    # La Tabla 13 usa desigualdades estrictas en ambos intervalos: 1.40 no tiene clase.
    if math.isclose(cit, limites["extrema"], rel_tol=0.0, abs_tol=1e-12):
        return "INDETERMINADA: CIT exactamente 1.40", "CDCRD T2 Tabla 13"
    if cit < limites["extrema"]:
        return "IRREGULARIDAD TORSIONAL MODERADA", "CDCRD T2 Tabla 13"
    return "IRREGULARIDAD TORSIONAL EXTREMA", "CDCRD T2 Tabla 13"


def _ax(dmax, dprom, limites=None):
    """Factor de amplificacion de la torsion accidental, 2.10.8.1.14 Ec. 31."""
    if not dprom:
        return None
    if limites is None:
        limites, _ = _umbrales()
    ax = (dmax / (limites["ax_divisor"] * dprom)) ** 2
    return max(limites["ax_min"], min(limites["ax_max"], ax))


def verificar(e):
    limites, fuente_umbrales = _umbrales()
    cds = str(e.get("cds", "")).upper()
    ecc = e.get("ecc_accidental") is True  # true certifica 5% en ambos signos
    flexible = bool(e.get("diafragma_flexible", False))
    unifamiliar = bool(e.get("vivienda_unifamiliar_2_niveles", False))

    pisos, descartados = [], []
    for r in e.get("derivas", []):
        d_caso = _dir_del_caso(r.get("caso"), r.get("direccion_caso"))
        d_res = str(r.get("direccion", "")).upper()
        fila = {
            "piso": r.get("piso"),
            "caso": r.get("caso"),
            "direccion": d_res,
            "d_max": r.get("d_max"),
            "d_prom": r.get("d_prom"),
        }
        if d_caso is None:
            fila["motivo"] = "no se pudo determinar la direccion de analisis del caso"
            descartados.append(fila)
            continue
        if d_res != d_caso:
            fila["motivo"] = "resultado en direccion ortogonal al caso; 2.10.7.2"
            descartados.append(fila)
            continue
        try:
            dp = float(r["d_prom"])
            dm = float(r["d_max"])
            valido = math.isfinite(dp) and math.isfinite(dm) and dp > 0 and dm >= 0
        except (KeyError, TypeError, ValueError):
            valido = False
        fila["CIT"] = dm / dp if valido else None
        if fila["CIT"] is None:
            fila["motivo"] = "deriva maxima/promedio ausente, no finita o promedio no positivo: CIT indefinido (2.10.8.1.13)"
        pisos.append(fila)

    por_direccion = {}
    for f in pisos:
        if f["CIT"] is None:
            continue
        d = f["direccion"]
        if d not in por_direccion or f["CIT"] > por_direccion[d]["CIT"]:
            por_direccion[d] = {"CIT": f["CIT"], "piso": f["piso"], "caso": f["caso"]}

    for d, v in por_direccion.items():
        v["clasificacion"], v["clausula"] = _clasificar(v["CIT"], limites)
        v["H1"] = v["CIT"] > limites["h1"]
        v["extrema"] = v["CIT"] > limites["extrema"]
        v["excede_tope_1.60"] = v["CIT"] > limites["tope"]

    ax = {}
    for r in e.get("desplazamientos", []):
        d_caso = _dir_del_caso(r.get("caso"), r.get("direccion_caso"))
        if d_caso is None or str(r.get("direccion", "")).upper() != d_caso:
            continue
        v = _ax(float(r["d_max"]), float(r["d_prom"]), limites)
        if v is None:
            continue
        if d_caso not in ax or v > ax[d_caso]["Ax"]:
            ax[d_caso] = {"Ax": round(v, 3), "piso": r.get("piso"), "caso": r.get("caso"),
                          "clausula": "CDCRD T2 2.10.8.1.14 Ec. 31"}

    hallazgos = []
    h1 = [d for d, v in por_direccion.items() if v["H1"]]
    extremas = [d for d, v in por_direccion.items() if v["extrema"]]
    sobre_tope = [d for d, v in por_direccion.items() if v["excede_tope_1.60"]]
    sin_clase = [d for d, v in por_direccion.items() if v["clasificacion"].startswith("INDETERMINADA")]
    sin_cit = [f for f in pisos if f["CIT"] is None]
    chequeos = []
    for d, v in sorted(por_direccion.items()):
        chequeos.append({"chequeo": "Tope CIT " + d, "demanda": round(v["CIT"], 6),
                         "capacidad": limites["tope"], "ratio": round(v["CIT"] / limites["tope"], 6),
                         "estado": "NO CUMPLE" if v["excede_tope_1.60"] else "CUMPLE",
                         "clausula": "CDCRD T2 2.10.4.1.2.1"})
    for f in sin_cit:
        chequeos.append({"chequeo": "CIT " + str(f["piso"]), "demanda": f["d_max"],
                         "capacidad": f["d_prom"], "ratio": None, "estado": "INCOMPLETO",
                         "clausula": "CDCRD T2 2.10.8.1.13", "motivo": f["motivo"]})

    if h1 and cds in ("C", "D", "E", "F"):
        hallazgos.append({
            "nivel": "REQUISITO",
            "texto": "Irregularidad horizontal H-1 en %s. En CDS C a F las fuerzas de diseno en "
                     "las conexiones del diafragma con elementos verticales y colectores se "
                     "amplifican 25%%." % ", ".join(sorted(h1)),
            "clausula": "CDCRD T2 Tabla 12 H-1 y 2.10.4.1.1"})
        hallazgos.append({
            "nivel": "REQUISITO",
            "texto": "Con H-1 y CDS C a F, el momento de torsion accidental de cada nivel se "
                     "multiplica por Ax.",
            "clausula": "CDCRD T2 2.10.8.1.14"})
    if extremas and cds in CDS_RESTRINGIDAS and not unifamiliar:
        hallazgos.append({
            "nivel": "PROHIBIDO",
            "texto": "Irregularidad torsional extrema en %s con CDS %s. No se permiten estructuras "
                     "con irregularidad torsional extrema en las categorias D, E o F, salvo "
                     "viviendas unifamiliares de hasta dos niveles. La estructura debe cambiarse, "
                     "no ajustarse." % (", ".join(sorted(extremas)), cds),
            "clausula": "CDCRD T2 2.10.4.1.2.2"})
    elif extremas:
        hallazgos.append({
            "nivel": "ADVERTENCIA",
            "texto": "Irregularidad torsional extrema en %s. Verificar la aplicabilidad de la "
                     "prohibicion segun la CDS y el uso." % ", ".join(sorted(extremas)),
            "clausula": "CDCRD T2 2.10.4.1.2.2"})
    if sobre_tope:
        hallazgos.append({
            "nivel": "PROHIBIDO",
            "texto": "CIT excede 1.60 en %s. El coeficiente no puede exceder 1.60 en ningun caso."
                     % ", ".join(sorted(sobre_tope)),
            "clausula": "CDCRD T2 2.10.4.1.2.1"})
    if len(extremas) >= 2:
        hallazgos.append({
            "nivel": "REQUISITO",
            "texto": "Irregularidad torsional extrema en ambas direcciones: el factor de "
                     "redundancia rho se toma igual a 1.3.",
            "clausula": "CDCRD T2 2.10.4.1.2.3"})

    if flexible:
        veredicto = "NO APLICA"
        nota = ("Diafragma declarado flexible y comprobado: la irregularidad torsional no es "
                "aplicable (2.10.8.1.13). No se emite veredicto.")
    elif not ecc:
        veredicto = "INCOMPLETO"
        nota = ("El analisis NO incluye la excentricidad accidental del 5% exigida por 2.10.8.1.10 "
                "para evaluar el CIT. El cociente calculado no es valido y puede variar al incluirla. "
                "Repetir con EccenRatio = 0.05 en "
                "ambos signos antes de dar el resultado por bueno.")
    elif any(h["nivel"] == "PROHIBIDO" for h in hallazgos):
        veredicto = "NO CUMPLE"
        nota = "Hay al menos una condicion prohibida por el reglamento."
    elif (sin_cit or sin_clase or not {"X", "Y"}.issubset(por_direccion) or descartados
          or cds not in ("A", "B", "C", "D", "E", "F")
          or (not h1 and e.get("h1_por_resistencia") is not False)):
        veredicto = "INCOMPLETO"
        nota = ("Hay CIT indefinido, sin clase textual, direccion no identificada, falta descartar "
                "H-1 por concentracion de resistencia lateral o no hay datos utiles; revisar pisos y casos.")
    elif hallazgos:
        veredicto = "CUMPLE CON REQUISITOS ADICIONALES"
        nota = "La estructura es admisible pero arrastra los requisitos listados."
    else:
        veredicto = "CUMPLE"
        nota = "CIT <= 1.20 en todos los pisos y ambas direcciones."

    return {
        "id": e.get("id"),
        "cds": cds,
        "ecc_accidental_incluida": ecc,
        "diafragma_flexible": flexible,
        "veredicto": veredicto,
        "nota": nota,
        "CIT_por_direccion": por_direccion,
        "Ax_por_direccion": ax,
        "chequeos": chequeos,
        "fuente_umbrales": fuente_umbrales,
        "hallazgos": hallazgos,
        "pisos": sorted(pisos, key=lambda f: (f["direccion"], -(f["CIT"] or 0))),
        "descartados": descartados,
        "codigo": "CDCRD 2026-07 Tomo 1 Titulo 2",
    }


def _test():
    e = {
        "id": "AUTOTEST",
        "cds": "D",
        "ecc_accidental": True,
        "derivas": [
            {"piso": "N2", "caso": "Ex", "direccion": "X", "d_max": 0.0012, "d_prom": 0.0010},
            {"piso": "N1", "caso": "Ex", "direccion": "X", "d_max": 0.0015, "d_prom": 0.0010},
            {"piso": "N1", "caso": "Ex", "direccion": "Y", "d_max": 0.0001, "d_prom": 0.00001},
            {"piso": "N1", "caso": "Ey", "direccion": "Y", "d_max": 0.0011, "d_prom": 0.0010},
        ],
        "desplazamientos": [
            {"piso": "N1", "caso": "Ex", "direccion": "X", "d_max": 1.5, "d_prom": 1.0},
        ],
    }
    r = verificar(e)
    assert r["CIT_por_direccion"]["X"]["CIT"] == 1.5, r["CIT_por_direccion"]
    assert r["CIT_por_direccion"]["X"]["piso"] == "N1"
    assert r["CIT_por_direccion"]["Y"]["CIT"] == 1.1
    assert r["CIT_por_direccion"]["X"]["extrema"] is True
    assert r["CIT_por_direccion"]["Y"]["H1"] is False
    assert len(r["descartados"]) == 1, r["descartados"]
    assert r["veredicto"] == "NO CUMPLE", r["veredicto"]
    assert any(h["clausula"] == "CDCRD T2 2.10.4.1.2.2" for h in r["hallazgos"])
    assert abs(r["Ax_por_direccion"]["X"]["Ax"] - 1.563) < 0.002, r["Ax_por_direccion"]

    # tope 1.60
    e2 = dict(e)
    e2["derivas"] = [{"piso": "N1", "caso": "Ex", "direccion": "X", "d_max": 0.0017, "d_prom": 0.0010}]
    r2 = verificar(e2)
    assert any(h["clausula"] == "CDCRD T2 2.10.4.1.2.1" for h in r2["hallazgos"])

    # sin excentricidad accidental -> incompleto, no veredicto limpio
    e3 = dict(e); e3["ecc_accidental"] = False
    assert verificar(e3)["veredicto"] == "INCOMPLETO"

    # regular
    e4 = {"id": "REG", "cds": "D", "ecc_accidental": True,
          "h1_por_resistencia": False,
          "derivas": [{"piso": "N1", "caso": "Ex", "direccion": "X", "d_max": 0.001, "d_prom": 0.0009},
                     {"piso": "N1", "caso": "Ey", "direccion": "Y", "d_max": 0.001, "d_prom": 0.0009}]}
    assert verificar(e4)["veredicto"] == "CUMPLE"

    # T2 2.10.8.1.13 exige revisar ambas direcciones antes de declarar conformidad.
    una_direccion = dict(e4, derivas=e4["derivas"][:1])
    assert verificar(una_direccion)["veredicto"] == "INCOMPLETO"

    # diafragma flexible -> no aplica
    e5 = dict(e); e5["diafragma_flexible"] = True
    assert verificar(e5)["veredicto"] == "NO APLICA"

    # Ax acotado entre 1 y 3
    assert _ax(1.0, 1.0) == 1.0
    assert _ax(10.0, 1.0) == 3.0

    # T2 2.10.8.1.13: Dprom = 0 deja CIT indefinido, nunca CUMPLE.
    e_cero = dict(e4)
    e_cero["derivas"] = [{"piso": "N1", "caso": "Ex", "direccion": "X",
                          "d_max": 0.001, "d_prom": 0.0}]
    rc = verificar(e_cero)
    assert rc["veredicto"] == "INCOMPLETO" and rc["pisos"][0]["CIT"] is None

    # T2 2.10.7.2: sin direccion de caso inferible se requiere declaracion explicita.
    e_nombre = dict(e4)
    e_nombre["derivas"] = [{"piso": "N1", "caso": "SISMO-01", "direccion": "X",
                            "d_max": 0.001, "d_prom": 0.001}]
    rn = verificar(e_nombre)
    assert rn["veredicto"] == "INCOMPLETO" and len(rn["descartados"]) == 1
    e_nombre["derivas"][0]["direccion_caso"] = "X"
    assert verificar(e_nombre)["CIT_por_direccion"]["X"]["CIT"] == 1.0

    # Tabla 12 H-1: exactamente 1.20 no excede el umbral.
    e_120 = dict(e4)
    e_120["derivas"] = [{"piso": "N1", "caso": "Ex", "direccion": "X",
                         "d_max": 0.0012, "d_prom": 0.001}]
    assert verificar(e_120)["CIT_por_direccion"]["X"]["H1"] is False

    # Tabla 13: ambos intervalos excluyen exactamente 1.40; decision pendiente de Emil.
    e_140 = dict(e4)
    e_140["derivas"] = [{"piso": "N1", "caso": "Ex", "direccion": "X",
                         "d_max": 0.0014, "d_prom": 0.001}]
    r140 = verificar(e_140)
    assert r140["veredicto"] == "INCOMPLETO"
    assert r140["CIT_por_direccion"]["X"]["clasificacion"].startswith("INDETERMINADA")

    # Tablas 12 y 13: fallback explicito si falta el archivo de la capa maquina.
    limites, origen = _umbrales(Path(__file__).parent / "__irregularidades_ausente__.json")
    assert limites["h1"] == 1.20 and limites["extrema"] == 1.40 and origen.startswith("FALLBACK")
    print("autotest: OK")
    return 0


def main(argv):
    if "--test" in argv:
        return _test()
    if not argv:
        print(__doc__)
        return 2
    entrada = argv[0]
    salida = None
    if "-o" in argv:
        salida = argv[argv.index("-o") + 1]
    with open(entrada, "r") as f:
        e = json.load(f)
    r = verificar(e)
    txt = json.dumps(r, indent=2, ensure_ascii=False)
    if salida:
        with open(salida, "w") as f:
            f.write(txt)
        print("escrito: %s" % salida)
    print(txt)
    return 0 if r["veredicto"] in ("CUMPLE", "CUMPLE CON REQUISITOS ADICIONALES", "NO APLICA") else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
