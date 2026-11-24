"""Lee un modelo de ETABS y produce la clave `etabs` de un bloque de data.json.

Dos pasos separados:

- `leer_tablas` habla con ETABS (COM). Trabaja siempre sobre una **copia** del modelo en una
  carpeta de trabajo y en una instancia propia del programa: correr el análisis reescribe el
  archivo, así que el original nunca se abre.
- `etabs_de` convierte las tablas ya leídas al contrato de `generar.py`. No toca ETABS ni el
  disco, y es lo que cubren las pruebas.

Todo se pide en tonf y metros, sin importar las unidades en que se guardó el modelo.

Uso:  python fuentes_etabs.py modelo.EDB carpeta_de_trabajo salida.json [--diseno-guardado]
"""
from __future__ import annotations

import json
import os
import shutil
import sys
from collections import defaultdict
from typing import Any

Fila = dict[str, Any]
Tablas = dict[str, list[Fila]]

UNIDADES_TONF_M = 12                      # eUnits.Ton_m_C
PROGID_HELPER = "ETABSv1.Helper"
PROGID_ETABS = "CSI.ETABS.API.ETABSObject"
SIN_MENSAJE = "No Message"
LARGO_MENSAJE = 110
MSG_BC_EXCEDE = "Beam/Column capacity ratio exceeds limit"

T_PISOS = "Story Definitions"
T_MATERIALES = "Material Properties - General"
T_CONCRETOS = "Material Properties - Concrete Data"
T_PORTICO = "Frame Section Property Definitions - Summary"
T_AREA = "Area Section Property Definitions - Summary"
T_PATRONES = "Load Pattern Definitions"
T_CARGAS_LOSA = "Shell Uniform Load Sets"
T_FUENTE_MASA = "Mass Source Definition"
T_MASA = "Mass Summary by Story"
T_SISMO_AUTO = "Load Pattern Definitions - Auto Seismic - User Coefficient"
T_CASOS = "Load Case Definitions - Summary"
T_COMBOS = "Load Combination Definitions"
T_BASE = "Base Reactions"
T_DERIVAS = "Story Drifts"
T_CORTANTES = "Story Forces"
T_MODAL = "Modal Participating Mass Ratios"
T_PROYECTO = "Project Information"
T_PROGRAMA = "Program Control"
T_COLUMNAS = "Concrete Column Design Summary"
T_VIGAS = "Concrete Beam Design Summary"
T_NUDOS = "Concrete Joint Design Summary"

DEFINICION = (T_PISOS, T_MATERIALES, T_CONCRETOS, T_PORTICO, T_AREA, T_PATRONES, T_CARGAS_LOSA, T_FUENTE_MASA,
              T_CASOS, T_COMBOS, T_PROYECTO, T_PROGRAMA)
RESULTADOS = (T_MASA, T_SISMO_AUTO, T_BASE, T_DERIVAS, T_CORTANTES, T_MODAL)
DISENO = (T_COLUMNAS, T_VIGAS, T_NUDOS)       # el nombre real lleva el código: «... - ACI 318-19»
OBLIGATORIAS = (T_PISOS, T_BASE, T_DERIVAS, T_CORTANTES, T_MODAL)


class ErrorDeEtabs(Exception):
    """ETABS no devolvió lo esperado."""


# ------------------------------------------------------------------ lectura por COM
def _copiar_modelo(modelo: str, carpeta_trabajo: str) -> str:
    if not os.path.isfile(modelo):
        raise ErrorDeEtabs("no existe el modelo: %s" % modelo)
    carpeta = os.path.abspath(carpeta_trabajo)
    if os.path.normcase(os.path.dirname(os.path.abspath(modelo))) == os.path.normcase(carpeta):
        raise ErrorDeEtabs("la carpeta de trabajo no puede ser la del modelo original")
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


def _leer(sm: Any, disponibles: list[str], nombres: tuple[str, ...]) -> Tablas:
    """Lee las tablas pedidas; una tabla de diseño se localiza por prefijo (lleva el código al final)."""
    out: Tablas = {}
    for nombre in nombres:
        clave = nombre if nombre in disponibles else next(
            (k for k in disponibles if k.startswith(nombre + " - ")), None)
        if clave:
            out[nombre] = _tabla(sm, clave)
    return out


def _exigir(ret: Any, que: str) -> None:
    if ret != 0:
        raise ErrorDeEtabs("%s devolvió %r" % (que, ret))


def _cerrar(app: Any) -> None:
    """Cierra la instancia sin tapar el error que se esté propagando."""
    try:
        app.ApplicationExit(False)
    except Exception:  # noqa: BLE001 - el cierre es de mejor esfuerzo; el error original es el que importa
        pass


def leer_tablas(modelo: str, carpeta_trabajo: str, diseno_guardado: bool = False) -> Tablas:
    """Abre una copia del modelo en una instancia propia de ETABS, corre el análisis y lee las tablas.

    Con `diseno_guardado` las tablas de diseño se leen antes de correr, tal como las dejó quien
    guardó el modelo; si no, se rediseña con los resultados del análisis recién corrido.
    """
    import comtypes.client

    copia = _copiar_modelo(modelo, carpeta_trabajo)
    helper = comtypes.client.CreateObject(PROGID_HELPER)
    import comtypes.gen.ETABSv1 as ETABSv1

    app = helper.QueryInterface(ETABSv1.cHelper).CreateObjectProgID(PROGID_ETABS)
    try:
        _exigir(app.ApplicationStart(), "ApplicationStart")
        sm = app.SapModel
        _exigir(sm.File.OpenFile(copia), "OpenFile")
        _exigir(sm.SetPresentUnits(UNIDADES_TONF_M), "SetPresentUnits")
        tablas: Tablas = {}
        if diseno_guardado:
            tablas.update(_leer(sm, list(sm.DatabaseTables.GetAvailableTables()[1]), DISENO))
        _exigir(sm.Analyze.RunAnalysis(), "RunAnalysis")
        if not diseno_guardado:
            _exigir(sm.DesignConcrete.StartDesign(), "DesignConcrete.StartDesign")
        _exigir(sm.SetPresentUnits(UNIDADES_TONF_M), "SetPresentUnits")
        disponibles = list(sm.DatabaseTables.GetAvailableTables()[1])
        tablas.update(_leer(sm, disponibles, DEFINICION + RESULTADOS + (() if diseno_guardado else DISENO)))
        tablas["_meta"] = [{"version": sm.GetVersion()[0], "modelo": os.path.basename(modelo),
                            "diseno": "guardado en el modelo" if diseno_guardado else "recalculado"}]
        return tablas
    finally:
        _cerrar(app)


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


def _arrastrar(filas: list[Fila], campo: str) -> list[Fila]:
    """Las filas de continuación traen el nombre vacío: hereda el de la fila anterior."""
    out, ultimo = [], None
    for f in filas:
        ultimo = f.get(campo) or ultimo
        out.append({**f, campo: ultimo})
    return out


def _sin_repetir(m: str) -> str:
    """ETABS a veces pega el mismo mensaje dos veces seguidas."""
    mitad = len(m) // 2
    return m[:mitad] if len(m) % 2 == 0 and m[:mitad] == m[mitad:] else m


def _mensajes_completos(fila: Fila) -> list[str]:
    return [_sin_repetir(m) for m in (_txt(fila.get("WarnMsg")), _txt(fila.get("ErrMsg"))) if m and m != SIN_MENSAJE]


def _mensajes(fila: Fila) -> list[str]:
    return [m[:LARGO_MENSAJE] for m in _mensajes_completos(fila)]


def _definicion(t: Tablas) -> dict[str, Any]:
    patrones = [{"name": _txt(f.get("Name")), "auto": _txt(f.get("IsAuto")), "type": _txt(f.get("Type")),
                 "sw": _txt(f.get("SelfWtMult")), "autoload": _txt(f.get("AutoLoad"))} for f in t.get(T_PATRONES, [])]
    combos: dict[str, Any] = {}
    for f in _arrastrar(t.get(T_COMBOS, []), "Name"):
        c = combos.setdefault(_txt(f["Name"]), {"tipo": _txt(f.get("Type")), "terms": [], "nota": _txt(f.get("Notes"))})
        if f.get("LoadName"):
            c["terms"].append([_txt(f["LoadName"]), _f(f.get("SF"))])
    return {
        "stories": [[_txt(f.get("Story")), _f(f.get("Height"))] for f in t.get(T_PISOS, [])],
        "concretos": [_txt(f.get("Material")) for f in t.get(T_MATERIALES, []) if _txt(f.get("Type")) == "Concrete"],
        "fc": {_txt(f.get("Material")): _f(f.get("Fc")) for f in t.get(T_CONCRETOS, [])},
        "frame": {_txt(f.get("Name")): {"mat": _txt(f.get("Material")), "shape": _txt(f.get("Shape")),
                                         "A": _f(f.get("Area")), "I33": _f(f.get("I33")), "I22": _f(f.get("I22")),
                                         "mJ": _f(f.get("JMod"), None), "mI33": _f(f.get("I3Mod"), None),
                                         "mI22": _f(f.get("I2Mod"), None)} for f in t.get(T_PORTICO, [])},
        "area": [{"name": _txt(f.get("Name")), "type": _txt(f.get("Type")), "elem": _txt(f.get("AnalType")),
                  "mat": _txt(f.get("Material")), "t": _f(f.get("TotalThick"))} for f in t.get(T_AREA, [])],
        "patterns": patrones,
        "tiene_viento": any(p["type"].lower() == "wind" for p in patrones),
        "loadsets": [[_txt(f["Name"]), _txt(f.get("LoadPattern")), _f(f.get("LoadValue"))]
                     for f in _arrastrar(t.get(T_CARGAS_LOSA, []), "Name")],
        "mass_source": [[_txt(f.get("LoadPattern")), _f(f.get("Multiplier"))]
                        for f in t.get(T_FUENTE_MASA, []) if f.get("LoadPattern")],
        "cases": [[_txt(f.get("Name")), _txt(f.get("Type"))] for f in t.get(T_CASOS, [])],
        "combos": combos,
    }


def _resultados(t: Tablas) -> dict[str, Any]:
    auto: dict[str, dict[str, float]] = {}
    for f in t.get(T_SISMO_AUTO, []):
        a = auto.setdefault(_txt(f.get("Name")).split("(")[0], {})
        for clave, campo in (("C", "C"), ("W", "WeightUsed"), ("V", "BaseShear")):
            v = _f(f.get(campo), None)
            if v is not None and clave not in a:
                a[clave] = v
    base: dict[str, list[dict[str, Any]]] = {}
    for f in t.get(T_BASE, []):
        base.setdefault(_txt(f.get("OutputCase")), []).append(
            {"step": _txt(f.get("StepType")), "FX": _f(f.get("FX")), "FY": _f(f.get("FY")), "FZ": _f(f.get("FZ"))})
    drift: dict[str, float] = {}
    for f in t.get(T_DERIVAS, []):
        k = "%s|%s|%s" % (_txt(f.get("Story")), _txt(f.get("OutputCase")), _txt(f.get("Direction")))
        drift[k] = max(drift.get(k, 0.0), abs(_f(f.get("Drift"))))
    shear: dict[str, list[float]] = {}
    for f in t.get(T_CORTANTES, []):
        if _txt(f.get("Location")) != "Bottom":
            continue
        k = "%s|%s" % (_txt(f.get("Story")), _txt(f.get("OutputCase")))
        ant = shear.get(k, [0.0, 0.0])
        shear[k] = [max(ant[0], abs(_f(f.get("VX")))), max(ant[1], abs(_f(f.get("VY"))))]
    modal = [[int(_f(f.get("Mode")))] + [_f(f.get(c)) for c in
                                          ("Period", "UX", "UY", "UZ", "SumUX", "SumUY", "SumUZ", "RX", "RY", "RZ")]
             for f in t.get(T_MODAL, [])]
    return {"mass_story": [[_txt(f.get("Story")), _f(f.get("UX")), _f(f.get("UY"))] for f in t.get(T_MASA, [])],
            "auto_seis": auto, "base": base, "drift": drift, "shear": shear, "modal": modal}


def _diseno(t: Tablas) -> dict[str, Any]:
    msgs: dict[str, int] = defaultdict(int)

    def por_elemento(tabla: str, etiqueta: str, inicial: dict[str, Any]) -> dict[str, dict[str, Any]]:
        elems: dict[str, dict[str, Any]] = {}
        for f in _arrastrar(t.get(tabla, []), "UniqueName"):
            e = elems.setdefault(_txt(f.get("UniqueName")), {"story": _txt(f.get("Story")),
                                                              "sect": _txt(f.get("DesignSect")), "msg": 0, **inicial})
            for m in _mensajes(f):
                e["msg"] += 1
                msgs["%s: %s" % (etiqueta, m)] += 1
            yield_fila(tabla, e, f)
        return elems

    def yield_fila(tabla: str, e: dict[str, Any], f: Fila) -> None:
        if tabla == T_COLUMNAS:
            pmm = _f(f.get("PMMRatio"))
            if pmm >= e["pmm"]:
                e["pmm"], e["combo"] = pmm, _txt(f.get("PMMCombo"))
            e["As"], e["AsMin"] = max(e["As"], _f(f.get("As"))), max(e["AsMin"], _f(f.get("AsMin")))
        elif tabla == T_VIGAS:
            e["AsTop"] = max(e["AsTop"], _f(f.get("AsTop")))
            e["AsBot"] = max(e["AsBot"], _f(f.get("AsBot")))
            e["Av"] = max(e["Av"], _f(f.get("VRebar")))
        else:
            e["bc"] = max([x for x in (e["bc"], _f(f.get("BCMajRatio"), None), _f(f.get("BCMinRatio"), None))
                           if x is not None], default=None)
            e["js"] = max([x for x in (e["js"], _f(f.get("JSMajRatio"), None), _f(f.get("JSMinRatio"), None))
                           if x is not None], default=None)
            # cuando la relación excede el límite, ETABS 23 deja el valor vacío y solo emite el mensaje
            e["bc_excede"] = e.get("bc_excede", False) or (
                any(MSG_BC_EXCEDE in m for m in _mensajes_completos(f))
                and (_f(f.get("BCMajRatio"), None) is None or _f(f.get("BCMinRatio"), None) is None))

    cols = por_elemento(T_COLUMNAS, "col", {"pmm": 0.0, "combo": "", "As": 0.0, "AsMin": 0.0})
    vigas = por_elemento(T_VIGAS, "viga", {"AsTop": 0.0, "AsBot": 0.0, "Av": 0.0})
    nudos = por_elemento(T_NUDOS, "nudo", {"bc": None, "js": None})

    col: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "pmm": 0.0, "combo": "", "As": 0.0, "AsMin": 0.0, "warn": 0})
    for e in cols.values():
        a = col["%s|%s" % (e["story"], e["sect"])]
        a["n"] += 1
        if e["pmm"] >= a["pmm"]:
            a["pmm"], a["combo"] = e["pmm"], e["combo"]
        a["As"], a["AsMin"] = max(a["As"], e["As"]), max(a["AsMin"], e["AsMin"])
        a["warn"] += 1 if e["msg"] else 0
    beam: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "AsTop": 0.0, "AsBot": 0.0, "Av": 0.0, "err": 0})
    for e in vigas.values():
        a = beam["%s|%s" % (e["story"], e["sect"])]
        a["n"] += 1
        a["AsTop"], a["AsBot"], a["Av"] = max(a["AsTop"], e["AsTop"]), max(a["AsBot"], e["AsBot"]), max(a["Av"], e["Av"])
        a["err"] += 1 if e["msg"] else 0
    joint: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"n": 0, "bc": 0.0, "js": 0.0, "bc_gt1": 0, "js_gt1": 0, "sin_bc": 0, "bc_sin_valor": 0, "err": 0})
    for e in nudos.values():
        a = joint[e["story"]]
        a["n"] += 1
        if e.get("bc_excede"):
            a["bc_gt1"] += 1
            a["bc_sin_valor"] += 1
            if e["bc"] is not None:
                a["bc"] = max(a["bc"], e["bc"])
        elif e["bc"] is None:
            a["sin_bc"] += 1
        else:
            a["bc"] = max(a["bc"], e["bc"])
            a["bc_gt1"] += 1 if e["bc"] > 1.0 else 0
        if e["js"] is not None:
            a["js"] = max(a["js"], e["js"])
            a["js_gt1"] += 1 if e["js"] > 1.0 else 0
        a["err"] += 1 if e["msg"] else 0
    return {"col": dict(col), "beam": dict(beam), "joint": dict(joint), "msgs": dict(msgs),
            "n_col": len(cols), "n_beam": len(vigas), "n_joint": len(nudos)}


def etabs_de(tablas: Tablas) -> dict[str, Any]:
    """Tablas de ETABS (en tonf y metros) -> clave `etabs` de un bloque."""
    faltan = [k for k in OBLIGATORIAS if not tablas.get(k)]
    if faltan:
        raise ErrorDeEtabs("faltan tablas o vinieron vacías: %s" % ", ".join(faltan))
    meta = (tablas.get("_meta") or [{}])[0]
    proyecto = (tablas.get(T_PROYECTO) or [{}])[0]
    programa = (tablas.get(T_PROGRAMA) or [{}])[0]
    version = _txt(meta.get("version")) or _txt(programa.get("Version"))
    return {
        "modelo": _txt(proyecto.get("ModelName")) or _txt(meta.get("modelo")),
        "archivo": _txt(meta.get("modelo")),
        "version": "ETABS v%s" % version if version else "ETABS",
        "codigo_concreto": _txt(programa.get("ConcFrmCode")),
        "origen_diseno": _txt(meta.get("diseno")),
        "unidad_long": "m",
        **_definicion(tablas), **_resultados(tablas), **_diseno(tablas),
    }


def bloque_etabs(modelo: str, carpeta_trabajo: str, diseno_guardado: bool = False) -> dict[str, Any]:
    return etabs_de(leer_tablas(modelo, carpeta_trabajo, diseno_guardado))


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    desconocidas = [a for a in argv[1:] if a.startswith("--") and a != "--diseno-guardado"]
    if len(args) != 3 or desconocidas:
        sys.stderr.write("uso: python fuentes_etabs.py modelo.EDB carpeta_de_trabajo salida.json [--diseno-guardado]\n")
        return 2
    try:
        tablas = leer_tablas(args[0], args[1], "--diseno-guardado" in argv)
        datos = etabs_de(tablas)
    except ErrorDeEtabs as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    with open(os.path.join(args[1], "tablas.json"), "w", encoding="utf-8") as f:
        json.dump(tablas, f, ensure_ascii=False)
    with open(args[2], "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=1)
    sys.stdout.write("%s: %d niveles, %d columnas, %d vigas, %d nudos, %d modos\n" % (
        datos["modelo"], len(datos["stories"]), datos["n_col"], datos["n_beam"], datos["n_joint"], len(datos["modal"])))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
