# -*- coding: utf-8 -*-
"""Verifica derivas de piso de diseno contra CDCRD T2 Tabla 19.

Existe porque ETABS entrega derivas, pero no aplica la seleccion de fila de la
Tabla 19 ni las restricciones de 2.10.11.1 y 2.10.11.2. Esta herramienta
recibe la deriva de diseno ya calculada por piso y direccion, no la deriva
elastica cruda; el productor del JSON responde por esa conversion.

Unidades generales: kN, m, MPa. hpx_m y deriva_diseno_m estan en m;
el ratio demanda/capacidad es adimensional.

Entrada JSON: id, categoria_riesgo (I_II, III, IV), cds (A..F),
tipo_estructura (texto literal de datos/machine/derivas_limites.json),
componentes_acomodan_desplazamiento (bool o null),
sistema_exclusivamente_porticos_momento (bool o null), rho (numero o null),
pisos [{piso, direccion, caso, hpx_m, deriva_diseno_m,
        dos_lineas_resistencia_2_10_11_2 (bool o null)}].
Para CDS D/E/F los booleanos de condicion deben ser explicitos. null significa
desconocido e impide un veredicto CUMPLE.

Uso: python verificacion_deriva.py entrada.json [-o salida.json] | --test
"""

import json
import math
import sys
from pathlib import Path


RUTA_LIMITES = Path(__file__).resolve().parent.parent / "datos" / "machine" / "derivas_limites.json"


def _fila_incompleta(piso, demanda, motivo, clausula="CDCRD T2 2.10.11; Tabla 19"):
    return {"piso": piso.get("piso"), "direccion": piso.get("direccion"),
            "caso": piso.get("caso"), "demanda": demanda, "capacidad": None,
            "ratio": None, "estado": "INCOMPLETO", "clausula": clausula,
            "unidad": "m", "motivo": motivo}


def verificar(e, ruta_limites=RUTA_LIMITES):
    salida = {"id": e.get("id"), "chequeos": [], "fuente_limites": str(ruta_limites)}
    try:
        with open(ruta_limites, encoding="utf-8") as fh:
            tabla = json.load(fh)
    except (OSError, ValueError) as exc:
        salida["chequeos"].append(_fila_incompleta({}, None, "No se pudo leer la capa maquina: " + str(exc)))
        salida["veredicto"] = "INCOMPLETO"
        return salida

    filas = {fila["tipo"]: fila for fila in tabla["valores"]}
    tipo = e.get("tipo_estructura")
    categoria = e.get("categoria_riesgo")
    cds = str(e.get("cds", "")).upper()
    pisos = e.get("pisos")
    if not isinstance(pisos, list) or not pisos:
        salida["chequeos"].append(_fila_incompleta({}, None, "Faltan pisos con deriva de diseno."))
        salida["veredicto"] = "INCOMPLETO"
        return salida

    extras = tabla["limites_adicionales"]
    for piso in pisos:
        demanda = piso.get("deriva_diseno_m")
        faltantes = []
        if tipo not in filas:
            faltantes.append("tipo_estructura no coincide con una fila de Tabla 19")
        if categoria not in ("I_II", "III", "IV"):
            faltantes.append("categoria_riesgo invalida o ausente")
        if cds not in ("A", "B", "C", "D", "E", "F"):
            faltantes.append("cds invalida o ausente")
        try:
            hpx = float(piso["hpx_m"])
            d = float(demanda)
            if not math.isfinite(hpx) or not math.isfinite(d) or hpx <= 0 or d < 0:
                faltantes.append("hpx_m debe ser finito y positivo; deriva_diseno_m finita y no negativa")
        except (KeyError, TypeError, ValueError):
            faltantes.append("hpx_m o deriva_diseno_m ausente/no numerica")
        if faltantes:
            salida["chequeos"].append(_fila_incompleta(piso, demanda, "; ".join(faltantes)))
            continue

        clausulas = ["CDCRD T2 2.10.11 Tabla 19"]
        capacidad = float(filas[tipo][categoria]) * hpx
        condiciones_pendientes = []
        componentes = e.get("componentes_acomodan_desplazamiento")
        if tipo == tabla["valores"][0]["tipo"]:
            # Tabla 19, primera fila: su seleccion exige componentes que acomoden desplazamientos.
            if componentes is not True:
                condiciones_pendientes.append("Primera fila de Tabla 19 requiere confirmar que componentes acomoden desplazamientos")
        elif tipo == extras["componentes_no_acomodan"]["aplica_fila"]:
            # Tabla 19 nota (a): en las demas estructuras se aplica 0.005 hpx si no acomodan.
            if componentes is False:
                capacidad = min(capacidad, float(extras["componentes_no_acomodan"]["factor_hpx"]) * hpx)
                clausulas.append("CDCRD T2 Tabla 19 nota (a)")
            elif componentes is not True:
                condiciones_pendientes.append("Falta condicion de componentes no estructurales, Tabla 19 nota (a)")

        if cds in ("D", "E", "F"):
            porticos = e.get("sistema_exclusivamente_porticos_momento")
            if porticos is True:
                # 2.10.11.1 divide el limite por rho para porticos a momento exclusivos.
                try:
                    rho = float(e["rho"])
                    if not math.isfinite(rho) or rho <= 0:
                        raise ValueError("rho no positivo")
                    capacidad /= rho
                    clausulas.append("CDCRD T2 2.10.11.1")
                except (KeyError, TypeError, ValueError):
                    condiciones_pendientes.append("Falta rho valido para 2.10.11.1")
            elif porticos is not False:
                condiciones_pendientes.append("Falta declarar si el sistema es exclusivamente de porticos a momento")

            dos = piso.get("dos_lineas_resistencia_2_10_11_2")
            if dos is True:
                # 2.10.11.2 limita a 0.010 hpx en la direccion con dos lineas elegibles.
                capacidad = min(capacidad, float(extras["dos_lineas_resistencia_cds_def"]["factor_hpx_maximo"]) * hpx)
                clausulas.append("CDCRD T2 2.10.11.2")
            elif dos is not False:
                condiciones_pendientes.append("Falta declarar dos lineas elegibles por direccion, 2.10.11.2")

        if condiciones_pendientes:
            salida["chequeos"].append(_fila_incompleta(piso, d, "; ".join(condiciones_pendientes), "; ".join(clausulas)))
            continue
        ratio = d / capacidad
        salida["chequeos"].append({"piso": piso.get("piso"), "direccion": piso.get("direccion"),
            "caso": piso.get("caso"), "demanda": round(d, 6), "capacidad": round(capacidad, 6),
            "ratio": round(ratio, 6), "estado": "CUMPLE" if ratio <= 1 else "NO CUMPLE",
            "clausula": "; ".join(clausulas), "unidad": "m"})

    estados = [c["estado"] for c in salida["chequeos"]]
    salida["veredicto"] = ("NO CUMPLE" if "NO CUMPLE" in estados else
                           "INCOMPLETO" if "INCOMPLETO" in estados else "CUMPLE")
    return salida


def _test():
    tipo = "Todas las demas estructuras"
    base = {"id": "TEST", "tipo_estructura": tipo, "categoria_riesgo": "I_II",
            "cds": "C", "componentes_acomodan_desplazamiento": True,
            "sistema_exclusivamente_porticos_momento": False,
            "pisos": [{"piso": "N1", "direccion": "X", "caso": "Ex",
                       "hpx_m": 3.0, "deriva_diseno_m": 0.048,
                       "dos_lineas_resistencia_2_10_11_2": False}]}
    # T2 Tabla 19: 0.016 hpx para I/II en las demas estructuras; igualdad cumple.
    r = verificar(base)
    assert r["veredicto"] == "CUMPLE" and abs(r["chequeos"][0]["ratio"] - 1) < 1e-9

    # T2 Tabla 19 nota (a): sin acomodacion, 0.005 hpx gobierna.
    no_acomoda = dict(base, componentes_acomodan_desplazamiento=False)
    rn = verificar(no_acomoda)
    assert rn["veredicto"] == "NO CUMPLE" and rn["chequeos"][0]["capacidad"] == 0.015

    # T2 2.10.11.1: en CDS D y solo porticos a momento, dividir entre rho.
    rho = dict(base, cds="D", sistema_exclusivamente_porticos_momento=True, rho=1.3)
    rr = verificar(rho)
    assert rr["chequeos"][0]["capacidad"] == round(0.048 / 1.3, 6)
    assert rr["veredicto"] == "NO CUMPLE"

    # T2 2.10.11.2: dos lineas elegibles restringen a 0.010 hpx.
    dos = dict(base, cds="D")
    dos["pisos"] = [dict(base["pisos"][0], dos_lineas_resistencia_2_10_11_2=True)]
    rd = verificar(dos)
    assert rd["chequeos"][0]["capacidad"] == 0.03

    # Datos desconocidos de 2.10.11.2 no equivalen a condicion falsa.
    falta = dict(base, cds="D")
    falta["pisos"] = [dict(base["pisos"][0], dos_lineas_resistencia_2_10_11_2=None)]
    assert verificar(falta)["veredicto"] == "INCOMPLETO"
    print("autotest OK: Tabla 19, nota (a), rho, dos lineas y datos incompletos")
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
