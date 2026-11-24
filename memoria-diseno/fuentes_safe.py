"""Lee un modelo de fundaciones de SAFE y produce la clave `fundaciones` de data.json.

Igual que el lector de ETABS: `leer_tablas` habla con SAFE sobre una **copia** del modelo, en
una instancia propia; `fundaciones_de` convierte lo leído y no toca el programa. Todo en tonf y
metros.

La tabla de presiones de suelo trae una fila por nudo de malla y por caso (millones de filas en
un modelo mediano), así que se pide una combinación a la vez y solo se guarda su resumen.

Uso:  python fuentes_safe.py modelo.FDB carpeta_de_trabajo salida.json
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from collections import Counter
from typing import Any

Fila = dict[str, Any]
Tablas = dict[str, list[Fila]]

UNIDADES_TONF_M = 12
PROGID_HELPER = "SAFEv1.Helper"
PROGID_SAFE = "CSI.SAFE.API.ETABSObject"

T_PROYECTO = "Project Information"
T_PROGRAMA = "Program Control"
T_CONCRETOS = "Material Properties - Concrete Data"
T_LOSAS = "Slab Property Definitions"
T_RESORTES = "Spring Property Definitions - Area Springs"
T_AREAS_RESORTE = "Area Assignments - Area Springs"
T_ASIG_AREA = "Area Assignments - Section Properties"
T_PATRONES = "Load Pattern Definitions"
T_CASOS = "Load Case Definitions - Summary"
T_COMBOS = "Load Combination Definitions"
T_COMBOS_DISENO = "Concrete Slab Design Load Combination Data"
T_BASE = "Base Reactions"
T_PRESIONES = "Soil Pressures"
T_PUNZONADO = "Concrete Slab Design - Punching Shear Data"
T_FRANJAS = "Concrete Slab Design Summary - Flexure and Shear Data"
R_PRESIONES = "_presiones"                 # resumen por combinación, no la tabla completa

DEFINICION = (T_PROYECTO, T_PROGRAMA, T_CONCRETOS, T_LOSAS, T_RESORTES, T_AREAS_RESORTE, T_ASIG_AREA, T_PATRONES, T_CASOS,
              T_COMBOS, T_COMBOS_DISENO)
RESULTADOS = (T_BASE, T_PUNZONADO, T_FRANJAS)
ESTADO_BIEN = "OK"
PUNZONADO_SIN_CALCULAR = "Not Calculated"


class ErrorDeSafe(Exception):
    """SAFE no devolvió lo esperado."""


# ------------------------------------------------------------------ lectura por COM
def _copiar_modelo(modelo: str, carpeta_trabajo: str) -> str:
    if not os.path.isfile(modelo):
        raise ErrorDeSafe("no existe el modelo: %s" % modelo)
    carpeta = os.path.abspath(carpeta_trabajo)
    if os.path.normcase(os.path.dirname(os.path.abspath(modelo))) == os.path.normcase(carpeta):
        raise ErrorDeSafe("la carpeta de trabajo no puede ser la del modelo original")
    corrida = os.path.join(carpeta, "corrida")          # se vacía: no deben quedar resultados de otro modelo
    shutil.rmtree(corrida, ignore_errors=True)
    os.makedirs(corrida)
    copia = os.path.join(corrida, "modelo" + os.path.splitext(modelo)[1])
    shutil.copyfile(modelo, copia)
    return copia


def _tabla(sm: Any, clave: str) -> list[Fila]:
    r = sm.DatabaseTables.GetTableForDisplayArray(clave, [], "", 0, [], 0, [])
    campos, n, datos, ret = list(r[2]), int(r[3]), list(r[4]), r[-1]
    if ret != 0 or not n:
        return []
    nc = len(campos)
    return [dict(zip(campos, datos[i * nc:(i + 1) * nc])) for i in range(n)]


def _exigir(ret: Any, que: str) -> None:
    codigo = ret[-1] if isinstance(ret, (list, tuple)) else ret
    if codigo != 0:
        raise ErrorDeSafe("%s devolvió %r" % (que, ret))


def combos_de_servicio(tablas: Tablas) -> list[str]:
    """Combinaciones definidas por el usuario que no son de diseño por resistencia ni envolventes."""
    de_diseno = {_txt(f.get("ComboName")) for f in tablas.get(T_COMBOS_DISENO, [])}
    vistos: list[str] = []
    for f in tablas.get(T_COMBOS, []):
        nombre = _txt(f.get("Name"))
        if (nombre and nombre not in vistos and nombre not in de_diseno and _txt(f.get("IsAuto")) != "Yes"
                and _txt(f.get("Type")) == "Linear Add"):
            vistos.append(nombre)
    return vistos


def resumen_presiones(filas: list[Fila]) -> dict[str, Any]:
    """Mínimo y máximo de la presión de una combinación (negativo = compresión sobre el suelo)."""
    vals = [v for v in (_f(f.get("SoilPressure"), None) for f in filas) if v is not None]
    return {"n": len(vals), "min": min(vals) if vals else None, "max": max(vals) if vals else None}


def leer_tablas(modelo: str, carpeta_trabajo: str) -> Tablas:
    """Abre una copia del modelo en una instancia propia de SAFE, corre análisis y diseño y lee las tablas."""
    import comtypes.client

    copia = _copiar_modelo(modelo, carpeta_trabajo)
    app = comtypes.client.CreateObject(PROGID_HELPER).CreateObjectProgID(PROGID_SAFE)
    try:
        _exigir(app.ApplicationStart(), "ApplicationStart")
        sm = app.SapModel
        _exigir(sm.File.OpenFile(copia), "OpenFile")
        _exigir(sm.SetPresentUnits(UNIDADES_TONF_M), "SetPresentUnits")
        _exigir(sm.Analyze.RunAnalysis(), "RunAnalysis")
        _exigir(sm.DesignConcreteSlab.StartSlabDesign(), "DesignConcreteSlab.StartSlabDesign")
        _exigir(sm.SetPresentUnits(UNIDADES_TONF_M), "SetPresentUnits")
        disponibles = set(sm.DatabaseTables.GetAvailableTables()[1])
        tablas: Tablas = {k: _tabla(sm, k) for k in DEFINICION + RESULTADOS if k in disponibles}
        presiones = []
        _exigir(sm.DatabaseTables.SetLoadCasesSelectedForDisplay([]), "SetLoadCasesSelectedForDisplay")
        for combo in combos_de_servicio(tablas):
            _exigir(sm.DatabaseTables.SetLoadCombinationsSelectedForDisplay([combo]),
                    "SetLoadCombinationsSelectedForDisplay")
            presiones.append({"combo": combo, **resumen_presiones(_tabla(sm, T_PRESIONES))})
        tablas[R_PRESIONES] = presiones
        tablas["_meta"] = [{"version": sm.GetVersion()[0], "modelo": os.path.basename(modelo)}]
        return tablas
    finally:
        try:
            app.ApplicationExit(False)
        except Exception:  # noqa: BLE001 - el cierre es de mejor esfuerzo; el error original es el que importa
            pass


# ------------------------------------------------------------------ conversión al contrato
def _f(v: Any, defecto: float | None = 0.0) -> float | None:
    if v is None or v == "":
        return defecto
    try:
        return float(v)
    except (TypeError, ValueError):
        return defecto


def _txt(v: Any) -> str:
    return "" if v is None else str(v).strip()


def envolventes(tablas: Tablas, presiones: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Presión de cada combinación envolvente cuyos miembros ya se leyeron: mínimo y máximo entre ellos."""
    leidas = {p["combo"]: p for p in presiones if p.get("min") is not None}
    miembros: dict[str, list[str]] = {}
    tipo: dict[str, str] = {}
    ultimo = None
    for f in tablas.get(T_COMBOS, []):
        ultimo = f.get("Name") or ultimo
        if f.get("Type"):
            tipo[_txt(ultimo)] = _txt(f["Type"])
        if f.get("LoadName"):
            miembros.setdefault(_txt(ultimo), []).append(_txt(f["LoadName"]))
    out = []
    for nombre, lista in miembros.items():
        if tipo.get(nombre) == "Envelope" and lista and all(m in leidas for m in lista):
            out.append({"combo": nombre, "envolvente_de": lista, "n": leidas[lista[0]]["n"],
                        "min": min(leidas[m]["min"] for m in lista), "max": max(leidas[m]["max"] for m in lista)})
    return out


def fundaciones_de(tablas: Tablas) -> dict[str, Any]:
    """Tablas de SAFE (tonf y metros) -> clave `fundaciones` de data.json."""
    if not tablas.get(T_LOSAS) or not tablas.get(R_PRESIONES):
        raise ErrorDeSafe("faltan las propiedades de losa o las presiones de suelo")
    meta = (tablas.get("_meta") or [{}])[0]
    proyecto = (tablas.get(T_PROYECTO) or [{}])[0]
    programa = (tablas.get(T_PROGRAMA) or [{}])[0]
    version = _txt(meta.get("version")) or _txt(programa.get("Version"))
    combos: dict[str, list[list[Any]]] = {}
    ultimo = None
    for f in tablas.get(T_COMBOS, []):
        ultimo = f.get("Name") or ultimo
        if f.get("LoadName"):
            combos.setdefault(_txt(ultimo), []).append([_txt(f["LoadName"]), _f(f.get("SF"))])
    punz = tablas.get(T_PUNZONADO, [])
    ratios = [r for r in (_f(f.get("Ratio"), None) for f in punz) if r is not None]
    franjas = tablas.get(T_FRANJAS, [])
    definidas = {_txt(f.get("Name")) for f in tablas[T_LOSAS]}
    asignadas = tablas.get(T_ASIG_AREA, [])
    en_uso = sorted({v for f in asignadas for v in f.values() if isinstance(v, str) and v in definidas}) \
        if asignadas else None
    return {
        "modelo": _txt(proyecto.get("ModelName")),
        "proyecto": _txt(proyecto.get("ProjectName")),
        "archivo": _txt(meta.get("modelo")),
        "version": "SAFE v%s" % version if version else "SAFE",
        "codigo": _txt(programa.get("ConcSlbCode")),
        "concretos": {_txt(f.get("Material")): _f(f.get("Fc")) for f in tablas.get(T_CONCRETOS, [])},
        "losas": [{"name": _txt(f.get("Name")), "tipo": _txt(f.get("PropType")), "mat": _txt(f.get("Material")),
                   "t": _f(f.get("Thickness"))} for f in tablas[T_LOSAS]],
        "losas_en_uso": en_uso,
        "resortes": [{"name": _txt(f.get("Name")), "k": _f(f.get("StiffU3")), "tipo": _txt(f.get("NonlinOpt3"))}
                     for f in tablas.get(T_RESORTES, [])],
        "areas_con_resorte": len(tablas.get(T_AREAS_RESORTE, [])),
        "patrones": [[_txt(f.get("Name")), _txt(f.get("Type"))] for f in tablas.get(T_PATRONES, [])
                     if not _txt(f.get("Name")).startswith("~")],
        "casos": [[_txt(f.get("Name")), _txt(f.get("Type"))] for f in tablas.get(T_CASOS, [])],
        "combos": combos,
        "base": {_txt(f.get("OutputCase")): _f(f.get("FZ")) for f in tablas.get(T_BASE, [])
                 if _txt(f.get("CaseType")) == "LinStatic"},
        "presiones": [dict(p) for p in tablas[R_PRESIONES]] + envolventes(tablas, tablas[R_PRESIONES]),
        "punzonado": {"n": len(punz), "calculados": len(ratios), "max": max(ratios) if ratios else None,
                      "mayores_que_1": sum(1 for r in ratios if r > 1.0),
                      "sin_calcular": sum(1 for f in punz if _txt(f.get("Status")) == PUNZONADO_SIN_CALCULAR)},
        "franjas": {"n": len({_txt(f.get("StripObject")) for f in franjas}),
                    "estaciones": len(franjas),
                    "estados": dict(Counter(_txt(f.get("Status")) or "—" for f in franjas))},
    }


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        sys.stderr.write("uso: python fuentes_safe.py modelo.FDB carpeta_de_trabajo salida.json\n")
        return 2
    try:
        tablas = leer_tablas(argv[1], argv[2])
        datos = fundaciones_de(tablas)
    except ErrorDeSafe as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    with open(os.path.join(argv[2], "tablas.json"), "w", encoding="utf-8") as f:
        json.dump(tablas, f, ensure_ascii=False)
    with open(argv[3], "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    peor = min((p["min"] for p in datos["presiones"] if p["min"] is not None), default=None)
    sys.stdout.write("%s: %d combinaciones de servicio, presión máxima %s tonf/m², %d puntos de punzonado\n" % (
        datos["modelo"], len(datos["presiones"]), "—" if peor is None else "%.2f" % -peor, datos["punzonado"]["n"]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
