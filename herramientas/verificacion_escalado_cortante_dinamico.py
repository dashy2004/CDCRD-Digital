# -*- coding: utf-8 -*-
"""Calcula el ajuste de fuerzas por cortante modal, CDCRD T2 2.10.8.2.1.6.

Existe porque ETABS entrega Vb y Vu, pero no certifica que el periodo usado
para Vb respete 2.10.8.1.4 ni documenta el ajuste de todas las fuerzas en
ambas direcciones. No usa ETABS ni COM. NO CUMPLE significa que el resultado
modal sin ajustar requiere multiplicar todas sus fuerzas por factor_requerido.

Entrada JSON: {"id": "...", "direcciones": [
  {"direccion": "X", "periodo_modelo_s": 1.2,
   "periodo_limite_2_10_8_1_4_s": 1.0, "periodo_usado_vb_s": 1.0,
   "vb_kn": 500, "vu_kn": 400},
  {"direccion": "Y", ...}]}
El periodo limite es el de 2.10.8.1.4 (Cu*Ta), no Ta sin Cu. El productor
del JSON responde por el calculo de Vb y por el valor modal combinado de Vu.
La herramienta verifica la eleccion del periodo y el minimo Vu >= Vb.

Unidades: cortantes en kN, periodos en s; m y MPa no intervienen.
Uso: python verificacion_escalado_cortante_dinamico.py entrada.json [-o salida.json] | --test
"""

import json
import math
import sys
from pathlib import Path


RUTA_REGLA = Path(__file__).resolve().parent.parent / "datos" / "machine" / "escalado_cortante_dinamico.json"
CLAUSULA = "CDCRD T2 2.10.8.2.1.6"


def _numero_positivo(valor):
    return (not isinstance(valor, bool) and isinstance(valor, (int, float))
            and math.isfinite(valor) and valor > 0)


def _fila(direccion, demanda=None, capacidad=None, ratio=None, estado="INCOMPLETO",
          motivo=None, factor_requerido=None, periodo_requerido_s=None):
    fila = {"direccion": direccion, "demanda": demanda, "capacidad": capacidad,
            "ratio": ratio, "estado": estado, "clausula": CLAUSULA,
            "unidad": "kN", "factor_requerido": factor_requerido,
            "periodo_requerido_s": periodo_requerido_s}
    if motivo:
        fila["motivo"] = motivo
    return fila


def verificar(entrada, ruta_regla=RUTA_REGLA):
    salida = {"id": entrada.get("id") if isinstance(entrada, dict) else None,
              "chequeos": [], "fuente_limites": str(ruta_regla)}
    try:
        with open(ruta_regla, encoding="utf-8") as fh:
            regla = json.load(fh)
        minimo = regla["fraccion_minima_vb"]
        direcciones = regla["direcciones_horizontales"]
        if (not _numero_positivo(minimo) or minimo != 1.0
                or direcciones != ["X", "Y"]):
            raise ValueError("limite o direcciones invalidos en capa maquina")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        salida["chequeos"].append(_fila(None, motivo="No se pudo leer la capa maquina: " + str(exc)))
        salida["veredicto"] = "INCOMPLETO"
        return salida

    filas = entrada.get("direcciones") if isinstance(entrada, dict) else None
    if not isinstance(filas, list):
        salida["chequeos"].append(_fila(None, motivo="Falta la lista de direcciones X/Y."))
        salida["veredicto"] = "INCOMPLETO"
        return salida

    for direccion in direcciones:
        candidatas = [f for f in filas if isinstance(f, dict) and f.get("direccion") == direccion]
        if len(candidatas) != 1:
            salida["chequeos"].append(_fila(
                direccion, motivo="Se requiere exactamente una fila para la direccion " + direccion + "."))
            continue
        fila = candidatas[0]
        claves = ("periodo_modelo_s", "periodo_limite_2_10_8_1_4_s",
                  "periodo_usado_vb_s", "vb_kn", "vu_kn")
        invalidas = [k for k in claves if not _numero_positivo(fila.get(k))]
        if invalidas:
            salida["chequeos"].append(_fila(
                direccion, motivo="Faltan valores positivos y finitos: " + ", ".join(invalidas)))
            continue
        requerido = min(fila["periodo_modelo_s"], fila["periodo_limite_2_10_8_1_4_s"])
        usado = fila["periodo_usado_vb_s"]
        if not math.isclose(usado, requerido, rel_tol=1e-6, abs_tol=1e-9):
            salida["chequeos"].append(_fila(
                direccion, demanda=fila["vb_kn"], capacidad=fila["vu_kn"],
                periodo_requerido_s=requerido,
                motivo="Vb no usa min(periodo_modelo_s, periodo_limite_2_10_8_1_4_s); recalcular Vb (T2 2.10.8.1.4)."))
            continue
        vb, vu = fila["vb_kn"], fila["vu_kn"]
        ratio = minimo * vb / vu
        salida["chequeos"].append(_fila(
            direccion, demanda=round(minimo * vb, 6), capacidad=vu,
            ratio=ratio, estado="CUMPLE" if vu >= minimo * vb else "NO CUMPLE",
            factor_requerido=max(1.0, ratio), periodo_requerido_s=requerido))

    estados = {f["estado"] for f in salida["chequeos"]}
    salida["veredicto"] = ("INCOMPLETO" if "INCOMPLETO" in estados else
                           "NO CUMPLE" if "NO CUMPLE" in estados else "CUMPLE")
    return salida


def _test():
    # T2 2.10.8.2.1.6: Vu menor que Vb exige Vb/Vu; igualdad cumple.
    base = {"id": "TEST", "direcciones": [
        {"direccion": "X", "periodo_modelo_s": 1.2,
         "periodo_limite_2_10_8_1_4_s": 1.0, "periodo_usado_vb_s": 1.0,
         "vb_kn": 500, "vu_kn": 400},
        {"direccion": "Y", "periodo_modelo_s": 0.8,
         "periodo_limite_2_10_8_1_4_s": 1.0, "periodo_usado_vb_s": 0.8,
         "vb_kn": 300, "vu_kn": 300}]}
    r = verificar(base)
    assert r["veredicto"] == "NO CUMPLE"
    assert [f["factor_requerido"] for f in r["chequeos"]] == [1.25, 1.0]
    assert [f["estado"] for f in r["chequeos"]] == ["NO CUMPLE", "CUMPLE"]
    assert all(f["clausula"] == CLAUSULA for f in r["chequeos"])

    # T2 2.10.8.1.4 y 2.10.8.2.1.6: Vb con periodo sin limitar no es evaluable.
    erroneo = json.loads(json.dumps(base))
    erroneo["direcciones"][0]["periodo_usado_vb_s"] = 1.2
    assert verificar(erroneo)["veredicto"] == "INCOMPLETO"
    # Sin una direccion, con Vu cero o con un dato booleano no hay factor valido.
    for invalido in (
        {"direcciones": base["direcciones"][:1]},
        {"direcciones": [dict(base["direcciones"][0], vu_kn=0), base["direcciones"][1]]},
        {"direcciones": [dict(base["direcciones"][0], vb_kn=True), base["direcciones"][1]]},
    ):
        assert verificar(invalido)["veredicto"] == "INCOMPLETO"
    print("autotest OK: Vb/Vu, igualdad, periodos y datos incompletos")
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
