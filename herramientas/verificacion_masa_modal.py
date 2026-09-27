# -*- coding: utf-8 -*-
"""Verifica participacion modal acumulada y numero de modos contra CDCRD T2.

Existe porque ETABS entrega participacion modal por modo, pero no emite el
veredicto de 2.10.8.2.1.2 para ambas direcciones ni el primer numero de modos
que satisface el requisito. No usa ETABS ni COM.

Entrada JSON: {"id": "...", "modos": [
  {"modo": 1, "sum_ux": 0.65, "sum_uy": 0.02}, ...]}
sum_ux/sum_uy son fracciones acumuladas de masa combinada entre 0 y 1,
tal como salen de la tabla Modal Participating Mass Ratios. Deben incluirse
todos los modos analizados en orden, desde 1 y sin saltos. No se aceptan
porcentajes (90 en lugar de 0.90). Si falta una direccion, la salida es
INCOMPLETO.

Unidades generales: kN, m, MPa; este chequeo es adimensional.
Uso: python verificacion_masa_modal.py entrada.json [-o salida.json] | --test
"""

import json
import math
import sys
from pathlib import Path


RUTA_REGLA = Path(__file__).resolve().parent.parent / "datos" / "machine" / "participacion_modal.json"
CLAUSULA = "CDCRD T2 2.10.8.2.1.2"


def _fila(direccion, demanda, capacidad=None, ratio=None, estado="INCOMPLETO",
          motivo=None, primer_modo_suficiente=None):
    fila = {"direccion": direccion, "demanda": demanda, "capacidad": capacidad,
            "ratio": ratio, "estado": estado, "clausula": CLAUSULA,
            "unidad": "fraccion", "primer_modo_suficiente": primer_modo_suficiente}
    if motivo:
        fila["motivo"] = motivo
    return fila


def verificar(entrada, ruta_regla=RUTA_REGLA):
    if not isinstance(entrada, dict):
        return {"id": None, "chequeos": [_fila(None, None, motivo="La entrada debe ser un objeto JSON.")],
                "fuente_limites": str(ruta_regla), "modos_analizados": None,
                "modos_minimos_requeridos": None, "veredicto": "INCOMPLETO"}
    salida = {"id": entrada.get("id"), "chequeos": [],
              "fuente_limites": str(ruta_regla), "modos_analizados": None,
              "modos_minimos_requeridos": None}
    try:
        with open(ruta_regla, encoding="utf-8") as fh:
            regla = json.load(fh)
        minimo = regla["participacion_minima_fraccion"]
        direcciones = regla["direcciones_horizontales"]
        if (isinstance(minimo, bool) or not isinstance(minimo, (int, float))
                or not math.isfinite(minimo) or not 0 < minimo <= 1
                or direcciones != ["X", "Y"]):
            raise ValueError("limite o direcciones invalidos en la capa maquina")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        salida["chequeos"].append(_fila(None, None, motivo="No se pudo leer la capa maquina: " + str(exc)))
        salida["veredicto"] = "INCOMPLETO"
        return salida

    modos = entrada.get("modos")
    if not isinstance(modos, list) or not modos:
        salida["chequeos"].append(_fila(None, minimo, motivo="Falta la lista de modos analizados."))
        salida["veredicto"] = "INCOMPLETO"
        return salida
    salida["modos_analizados"] = len(modos)

    # 2.10.8.2.1.2: sin una serie acumulada completa no puede deducirse
    # el primer modo que garantiza 90 % en cada direccion.
    series = {"X": [], "Y": []}
    errores = []
    for numero, modo in enumerate(modos, 1):
        if not isinstance(modo, dict):
            errores.append("modo %d no es un objeto" % numero)
            continue
        if isinstance(modo.get("modo"), bool) or modo.get("modo") != numero:
            errores.append("los modos deben numerarse desde 1 sin saltos (posicion %d)" % numero)
        for direccion, clave in (("X", "sum_ux"), ("Y", "sum_uy")):
            valor = modo.get(clave)
            if isinstance(valor, bool) or not isinstance(valor, (int, float)) or not math.isfinite(valor):
                errores.append("%s ausente o no numerico en modo %d" % (clave, numero))
                continue
            if not 0 <= valor <= 1:
                errores.append("%s fuera de [0, 1] en modo %d" % (clave, numero))
                continue
            if series[direccion] and valor + 1e-9 < series[direccion][-1]:
                errores.append("%s decrece en modo %d" % (clave, numero))
            series[direccion].append(float(valor))

    if errores:
        motivo = "; ".join(dict.fromkeys(errores))
        salida["chequeos"] = [_fila(d, minimo, motivo=motivo) for d in direcciones]
        salida["veredicto"] = "INCOMPLETO"
        return salida

    primeros = []
    for direccion in direcciones:
        valores = series[direccion]
        logrado = valores[-1]
        primero = next((i for i, valor in enumerate(valores, 1) if valor >= minimo), None)
        if primero is not None:
            primeros.append(primero)
        salida["chequeos"].append(_fila(
            direccion, minimo, round(logrado, 6),
            round(minimo / logrado, 6) if logrado > 0 else None,
            "CUMPLE" if primero is not None else "NO CUMPLE",
            primer_modo_suficiente=primero))

    salida["modos_minimos_requeridos"] = max(primeros) if len(primeros) == len(direcciones) else None
    salida["veredicto"] = ("CUMPLE" if salida["modos_minimos_requeridos"] is not None
                           else "NO CUMPLE")
    return salida


def _test():
    # T2 2.10.8.2.1.2: igualdad con 90 % cumple; gobierna el ultimo
    # primer modo suficiente entre las dos direcciones ortogonales.
    base = {"id": "TEST", "modos": [
        {"modo": 1, "sum_ux": 0.70, "sum_uy": 0.30},
        {"modo": 2, "sum_ux": 0.90, "sum_uy": 0.75},
        {"modo": 3, "sum_ux": 0.93, "sum_uy": 0.90}]}
    r = verificar(base)
    assert r["veredicto"] == "CUMPLE" and r["modos_minimos_requeridos"] == 3
    assert [x["primer_modo_suficiente"] for x in r["chequeos"]] == [2, 3]
    assert all(x["clausula"] == CLAUSULA for x in r["chequeos"])

    # T2 2.10.8.2.1.2: cada direccion debe llegar al 90 %.
    insuficiente = {"id": "TEST", "modos": base["modos"][:2]}
    assert verificar(insuficiente)["veredicto"] == "NO CUMPLE"

    # No se puede inferir cobertura ni numero minimo con una direccion ausente,
    # valores en porcentaje, modos saltados o participacion acumulada decreciente.
    for invalido in (
        {"modos": [{"modo": 1, "sum_ux": 0.95}]},
        {"modos": [{"modo": 1, "sum_ux": 90, "sum_uy": 90}]},
        {"modos": [{"modo": 2, "sum_ux": 0.95, "sum_uy": 0.95}]},
        {"modos": [{"modo": 1, "sum_ux": 0.95, "sum_uy": 0.95},
                   {"modo": 2, "sum_ux": 0.90, "sum_uy": 0.98}]},
    ):
        assert verificar(invalido)["veredicto"] == "INCOMPLETO"
    print("autotest OK: 90 % por direccion, modos minimos y datos incompletos")
    return 0


def main(argv):
    if "--test" in argv:
        return _test()
    if not argv:
        print(__doc__)
        return 2
    with open(argv[0], encoding="utf-8") as fh:
        entrada = json.load(fh)
    resultado = verificar(entrada)
    txt = json.dumps(resultado, ensure_ascii=False, indent=2)
    if "-o" in argv:
        ruta = argv[argv.index("-o") + 1]
        with open(ruta, "w", encoding="utf-8") as fh:
            fh.write(txt + "\n")
        print("escrito: " + ruta)
    else:
        print(txt)
    return 0 if resultado["veredicto"] == "CUMPLE" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
