# -*- coding: utf-8 -*-
"""Verifica irregularidades verticales V-1 a V-6, CDCRD T2 Tabla 14.

Existe porque ETABS entrega rigidez y geometria por piso, pero no coteja
automaticamente Tabla 14 ni sus prohibiciones y requisitos adicionales.
No usa ETABS ni COM. La resistencia lateral debe venir de una evaluacion
de capacidad del sistema sismorresistente, no del cortante demandado.

Entrada JSON, pisos ordenados de ARRIBA hacia ABAJO:
{
  "id": "EDIFICIO", "cds": "D", "orden_pisos": "superior_a_inferior",
  "pisos": [
    {"piso": "AZOTEA", "rigidez_x_kn_m": 100, "rigidez_y_kn_m": 100,
     "resistencia_x_kn": 500, "resistencia_y_kn": 500,
     "dimension_sistema_x_m": 20, "dimension_sistema_y_m": 15,
     "desfase_en_plano": false},
    {"piso": "NIVEL 2", ...}
  ],
  "conexiones_diafragma_25pct_verificadas": null,
  "colectores_25pct_verificados": null
}
Si desfase_en_plano es true, el piso necesita
elemento_discontinuo_columna y soporte_y_conexiones_omega0_verificados.
Los dos campos de 25% solo se exigen si V-3 esta presente.
Un campo requerido ausente o indeterminado da INCOMPLETO.

Unidades: rigidez kN/m, resistencia kN, dimensiones m; MPa no interviene.
Uso: python verificacion_irregularidades_verticales.py entrada.json
     [-o salida.json] | --test
"""

import json
import math
import sys
from pathlib import Path


RUTA_REGLA = Path(__file__).resolve().parent.parent / "datos" / "machine" / "irregularidades_verticales.json"
TABLA = "CDCRD T2 Tabla 14"
DIRECCIONES = ("x", "y")


def _numero_positivo(valor):
    return (not isinstance(valor, bool) and isinstance(valor, (int, float))
            and math.isfinite(valor) and valor > 0)


def _chequeo(tipo, piso, direccion=None, demanda=None, capacidad=None,
             ratio=None, presente=None, estado="INCOMPLETO", clausula=None,
             motivo=None):
    fila = {"tipo": tipo, "piso": piso, "direccion": direccion,
            "demanda": demanda, "capacidad": capacidad, "ratio": ratio,
            "presente": presente, "estado": estado,
            "clausula": clausula or TABLA}
    if motivo:
        fila["motivo"] = motivo
    return fila


def _resultado(salida):
    estados = {fila["estado"] for fila in salida["chequeos"]}
    salida["veredicto"] = ("INCOMPLETO" if "INCOMPLETO" in estados else
                           "NO CUMPLE" if "NO CUMPLE" in estados else "CUMPLE")
    salida["irregularidades_presentes"] = sorted({
        fila["tipo"] for fila in salida["chequeos"] if fila["presente"] is True
    })
    return salida


def _comparar(salida, tipo, piso, direccion, actual, referencia, umbral,
              regla, relacion="menor", detalle=None):
    """Relacion estricta de Tabla 14: igualdad no dispara irregularidad."""
    capacidad = umbral * referencia
    if relacion == "menor":
        presente = actual < capacidad
        demanda = capacidad
        capacidad_salida = actual
        ratio = demanda / capacidad_salida
    else:
        presente = actual > capacidad
        demanda = actual
        capacidad_salida = capacidad
        ratio = demanda / capacidad_salida
    prohibida = salida["cds"] in regla[tipo].get("prohibida_cds", [])
    estado = "NO CUMPLE" if presente and prohibida else "CUMPLE"
    fila = _chequeo(tipo, piso, direccion, demanda, capacidad_salida,
                    ratio, presente, estado, TABLA + ", " + tipo)
    if detalle:
        fila["comparacion"] = detalle
    salida["chequeos"].append(fila)


def verificar(entrada, ruta_regla=RUTA_REGLA):
    salida = {"id": entrada.get("id") if isinstance(entrada, dict) else None,
              "cds": entrada.get("cds") if isinstance(entrada, dict) else None,
              "fuente_limites": str(ruta_regla), "chequeos": []}
    try:
        with open(ruta_regla, encoding="utf-8") as fh:
            datos = json.load(fh)
        reglas = {fila["id"]: fila for fila in datos["valores"]}
        if set(reglas) != {"V-1", "V-2", "V-3", "V-4", "V-5", "V-6"}:
            raise ValueError("faltan tipos V-1 a V-6")
        umbrales = [
            reglas[t]["rigidez_menor_que_superior"] for t in ("V-1", "V-2")
        ] + [
            reglas[t]["rigidez_menor_que_promedio_tres_superiores"] for t in ("V-1", "V-2")
        ] + [
            reglas["V-3"]["dimension_mayor_que_adyacente"],
            reglas["V-5"]["resistencia_menor_que_superior"],
            reglas["V-6"]["resistencia_menor_que_superior"],
        ]
        if not all(_numero_positivo(v) for v in umbrales):
            raise ValueError("umbral no positivo o no finito")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        salida["chequeos"].append(_chequeo(None, None, motivo="Capa maquina invalida: " + str(exc)))
        return _resultado(salida)

    if not isinstance(entrada, dict) or entrada.get("cds") not in ("C", "D", "E", "F"):
        salida["chequeos"].append(_chequeo(None, None, motivo="Se requiere cds C, D, E o F."))
        return _resultado(salida)
    if entrada.get("orden_pisos") != "superior_a_inferior":
        salida["chequeos"].append(_chequeo(None, None,
            motivo="Declarar orden_pisos = superior_a_inferior; las comparaciones dependen del orden."))
        return _resultado(salida)
    pisos = entrada.get("pisos")
    if not isinstance(pisos, list) or len(pisos) < 2:
        salida["chequeos"].append(_chequeo(None, None, motivo="Se requieren al menos dos pisos ordenados de arriba hacia abajo."))
        return _resultado(salida)

    nombres = set()
    for indice, piso in enumerate(pisos):
        if not isinstance(piso, dict) or not isinstance(piso.get("piso"), str) or not piso["piso"].strip():
            salida["chequeos"].append(_chequeo(None, indice, motivo="Piso sin nombre valido."))
            return _resultado(salida)
        if piso["piso"] in nombres:
            salida["chequeos"].append(_chequeo(None, piso["piso"], motivo="Nombre de piso duplicado."))
            return _resultado(salida)
        nombres.add(piso["piso"])
        for eje in DIRECCIONES:
            for prefijo in ("rigidez", "resistencia", "dimension_sistema"):
                sufijo = "kn_m" if prefijo == "rigidez" else "kn" if prefijo == "resistencia" else "m"
                clave = prefijo + "_" + eje + "_" + sufijo
                if not _numero_positivo(piso.get(clave)):
                    salida["chequeos"].append(_chequeo(None, piso["piso"], eje.upper(),
                        motivo=clave + " debe ser positivo, finito y evaluado para el sistema sismorresistente."))
                    return _resultado(salida)
        if not isinstance(piso.get("desfase_en_plano"), bool):
            salida["chequeos"].append(_chequeo("V-4", piso["piso"],
                motivo="desfase_en_plano requiere true o false; no se infiere de ETABS."))
            return _resultado(salida)

    for i, piso in enumerate(pisos):
        nombre = piso["piso"]
        for eje in DIRECCIONES:
            direccion = eje.upper()
            if i > 0:
                superior = pisos[i - 1]
                k = piso["rigidez_" + eje + "_kn_m"]
                k_sup = superior["rigidez_" + eje + "_kn_m"]
                r = piso["resistencia_" + eje + "_kn"]
                r_sup = superior["resistencia_" + eje + "_kn"]
                if salida["cds"] in reglas["V-1"]["cds_aplicable"]:
                    for tipo in ("V-1", "V-2"):
                        _comparar(salida, tipo, nombre, direccion, k, k_sup,
                                  reglas[tipo]["rigidez_menor_que_superior"], reglas,
                                  detalle="piso inmediatamente superior")
                        if i >= 3:
                            promedio = sum(p["rigidez_" + eje + "_kn_m"] for p in pisos[i-3:i]) / 3
                            _comparar(salida, tipo, nombre, direccion, k, promedio,
                                      reglas[tipo]["rigidez_menor_que_promedio_tres_superiores"],
                                      reglas, detalle="promedio de tres pisos superiores")
                    for tipo in ("V-5", "V-6"):
                        _comparar(salida, tipo, nombre, direccion, r, r_sup,
                                  reglas[tipo]["resistencia_menor_que_superior"], reglas,
                                  detalle="piso inmediatamente superior")
                dimension = piso["dimension_sistema_" + eje + "_m"]
                dimension_sup = superior["dimension_sistema_" + eje + "_m"]
                _comparar(salida, "V-3", nombre, direccion, max(dimension, dimension_sup),
                          min(dimension, dimension_sup),
                          reglas["V-3"]["dimension_mayor_que_adyacente"], reglas,
                          relacion="mayor", detalle="pisos adyacentes: " + superior["piso"])

        desfase = piso["desfase_en_plano"]
        if not desfase:
            salida["chequeos"].append(_chequeo("V-4", nombre, presente=False,
                estado="CUMPLE", clausula="CDCRD T2 2.10.4.2.3 y Tabla 14"))
            continue
        columna = piso.get("elemento_discontinuo_columna")
        omega = piso.get("soporte_y_conexiones_omega0_verificados")
        clausula = "CDCRD T2 2.10.4.2.3/2.10.4.2.3.1"
        if salida["cds"] not in reglas["V-4"]["excepcion_columna_cds"] or columna is False:
            estado, motivo = "NO CUMPLE", "V-4 prohibida sin excepcion aplicable."
        elif columna is True and omega is True:
            estado, motivo = "CUMPLE", "Excepcion de columna y soporte/conexiones con Omega0 verificados."
        elif columna is True and omega is False:
            estado, motivo = "NO CUMPLE", "Falta verificar soporte y conexiones con Omega0."
        else:
            estado, motivo = "INCOMPLETO", "Declarar si el elemento es columna y si soporte/conexiones se verificaron con Omega0."
        salida["chequeos"].append(_chequeo("V-4", nombre, presente=True,
            estado=estado, clausula=clausula, motivo=motivo))

    if any(f["tipo"] == "V-3" and f["presente"] for f in salida["chequeos"]):
        # T2 2.10.4.2.4: los dos grupos de fuerzas se amplifican 25%.
        for clave, nombre in (
            ("conexiones_diafragma_25pct_verificadas", "conexiones de diafragma"),
            ("colectores_25pct_verificados", "colectores y sus conexiones"),
        ):
            valor = entrada.get(clave)
            estado = "CUMPLE" if valor is True else "NO CUMPLE" if valor is False else "INCOMPLETO"
            factor = (reglas["V-3"]["amplificacion_conexiones_diafragma"]
                      if clave.startswith("conexiones") else
                      reglas["V-3"]["amplificacion_colectores_y_conexiones"])
            salida["chequeos"].append(_chequeo("V-3", nombre, demanda=factor,
                capacidad=factor if valor is True else None,
                ratio=1.0 if valor is True else None, presente=True,
                estado=estado, clausula="CDCRD T2 2.10.4.2.4",
                motivo=None if valor is True else "Declarar y verificar amplificacion de fuerzas de 25%."))
    return _resultado(salida)


def _test():
    base = {"id": "TEST", "cds": "D", "orden_pisos": "superior_a_inferior", "pisos": [
        {"piso": "P3", "rigidez_x_kn_m": 100, "rigidez_y_kn_m": 100,
         "resistencia_x_kn": 100, "resistencia_y_kn": 100,
         "dimension_sistema_x_m": 10, "dimension_sistema_y_m": 10,
         "desfase_en_plano": False},
        {"piso": "P2", "rigidez_x_kn_m": 70, "rigidez_y_kn_m": 100,
         "resistencia_x_kn": 100, "resistencia_y_kn": 100,
         "dimension_sistema_x_m": 10, "dimension_sistema_y_m": 10,
         "desfase_en_plano": False},
    ]}
    # Tabla 14 V-1: rigidez igual a 70% no es menor; V-3 exige >130%.
    r = verificar(base)
    assert r["veredicto"] == "CUMPLE" and not r["irregularidades_presentes"]
    # Tabla 14 V-1: con tres pisos superiores aplica tambien el 80% del promedio.
    caso = json.loads(json.dumps(base))
    caso["pisos"] = [dict(base["pisos"][0], piso="P4"),
                     dict(base["pisos"][0], piso="P3"),
                     dict(base["pisos"][0], piso="P2"),
                     dict(base["pisos"][1], piso="P1", rigidez_x_kn_m=79)]
    r = verificar(caso)
    assert r["veredicto"] == "CUMPLE" and "V-1" in r["irregularidades_presentes"]
    # Tabla 14 V-2 y 2.10.4.2.1: <60% es extrema y se prohibe en CDS E/F.
    caso = json.loads(json.dumps(base))
    caso["cds"] = "E"
    caso["pisos"][1]["rigidez_x_kn_m"] = 59
    r = verificar(caso)
    assert r["veredicto"] == "NO CUMPLE" and "V-2" in r["irregularidades_presentes"]
    # Tabla 14 V-2: con tres pisos superiores, 69% del promedio tambien dispara.
    caso["pisos"] = [dict(base["pisos"][0], piso="P4"),
                     dict(base["pisos"][0], piso="P3"),
                     dict(base["pisos"][0], piso="P2"),
                     dict(base["pisos"][1], piso="P1", rigidez_x_kn_m=69)]
    assert verificar(caso)["veredicto"] == "NO CUMPLE"
    # Tabla 14 V-5: resistencia menor a la superior se prohibe en CDS D.
    caso = json.loads(json.dumps(base))
    caso["pisos"][1]["resistencia_y_kn"] = 99
    assert verificar(caso)["veredicto"] == "NO CUMPLE"
    # Tabla 14 V-6: por debajo del 65% es extrema.
    caso["pisos"][1]["resistencia_y_kn"] = 64
    assert "V-6" in verificar(caso)["irregularidades_presentes"]
    # Tabla 14 V-3 / 2.10.4.2.4: >130% exige ambas verificaciones de +25%.
    caso = json.loads(json.dumps(base))
    caso["pisos"][1]["dimension_sistema_x_m"] = 13
    assert "V-3" not in verificar(caso)["irregularidades_presentes"]
    caso["pisos"][1]["dimension_sistema_x_m"] = 13.01
    assert verificar(caso)["veredicto"] == "INCOMPLETO"
    caso["conexiones_diafragma_25pct_verificadas"] = True
    caso["colectores_25pct_verificados"] = True
    assert verificar(caso)["veredicto"] == "CUMPLE"
    # 2.10.4.2.3.1: la excepcion V-4 requiere columna y Omega0; CDS F no la admite.
    caso = json.loads(json.dumps(base))
    caso["pisos"][1].update(desfase_en_plano=True, elemento_discontinuo_columna=True,
                             soporte_y_conexiones_omega0_verificados=True)
    assert verificar(caso)["veredicto"] == "CUMPLE"
    caso["cds"] = "F"
    assert verificar(caso)["veredicto"] == "NO CUMPLE"
    caso["cds"] = "D"
    caso["pisos"][1]["soporte_y_conexiones_omega0_verificados"] = None
    assert verificar(caso)["veredicto"] == "INCOMPLETO"
    # La falta de capacidad lateral no se reemplaza por cortante de piso demandado.
    caso = json.loads(json.dumps(base))
    del caso["pisos"][1]["resistencia_x_kn"]
    assert verificar(caso)["veredicto"] == "INCOMPLETO"
    print("autotest OK: Tabla 14 V-1 a V-6, prohibiciones, excepcion y datos incompletos")
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
    texto = json.dumps(resultado, ensure_ascii=False, indent=2)
    if "-o" in argv:
        with open(argv[argv.index("-o") + 1], "w", encoding="utf-8") as fh:
            fh.write(texto + "\n")
    else:
        print(texto)
    return 0 if resultado["veredicto"] == "CUMPLE" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
