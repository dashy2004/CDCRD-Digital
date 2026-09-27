# -*- coding: utf-8 -*-
"""verificacion_zapata: chequeo de zapata aislada segun CDCRD 2026-07 (T4) y ACI 318-19.

Existe porque la OAPI de SAFE 23.3.0 NO puede cerrar esta verificacion sola:
  - cDesignStrip no tiene metodo de creacion (solo ChangeName/Delete/Get) y no
    hay tabla importable de franjas -> sin franjas no hay diseno de flexion.
  - cDesignConcreteSlab no expone punzonamiento (8 metodos, ninguno Punch).
Verificado contra el typelib de SAFE 23.3.0 / OAPI 2.016 el 2026-09-27.
SAFE si entrega la presion de contacto; esta herramienta toma esa presion (o la
calcula) y cierra los chequeos que faltan, con la clausula de origen en cada uno.

Unidades de entrada y salida: kN, m, MPa.

Uso:
    python3 verificacion_zapata.py entrada.json [-o salida.json]
    python3 verificacion_zapata.py --test

Entrada (JSON):
{
  "id": "Z-1",
  "zapata":    {"B": 2.20, "L": 2.20, "h": 0.45, "recubrimiento": 0.075, "db": 0.016,
                 "As_provisto_X_mm2": null, "As_provisto_Y_mm2": null},
  "columna":   {"cx": 0.30, "cy": 0.30, "posicion": "interior"},
  "materiales":{"fc": 20.594, "fy": 411.9, "gamma_hormigon": 23.536, "db_columna": 0.01905},
  "suelo":     {"sigma_adm": 200.0, "sigma_adm_control": null},
  "cargas":    {"P_serv": 884.2, "Mx_serv": 2.7, "My_serv": 9.92,
                "P_serv_sismo": null, "Mx_serv_sismo": null, "My_serv_sismo": null,
                "sismo_aplica": null,
                "Pu": 1081.9, "Mux": 4.1, "Muy": 14.0}
}
"""

import json
import math
import sys
from copy import deepcopy
from pathlib import Path

PHI_CORTE = 0.75      # ACI 318-19 Tabla 21.2.1
PHI_FLEXION = 0.90    # ACI 318-19 Tabla 21.2.1
LAMBDA = 1.0          # hormigon de peso normal, ACI 318-19 19.2.4.2
ALFA_S = {"interior": 40, "borde": 30, "esquina": 20}   # ACI 318-19 Tabla 22.6.5.3
RUTA_FS = Path(__file__).resolve().parent.parent / "datos" / "machine" / "seguridad_cimentaciones.json"


def _factores_seguridad(ruta=RUTA_FS):
    """FS de T4 4.3.2.7 desde la capa maquina; fallback solo si falta el archivo."""
    try:
        with open(ruta, encoding="utf-8") as fh:
            valores = json.load(fh)["valores"]
    except FileNotFoundError:
        # Fallback explicito de T4 4.3.2.7, p. 222.
        return 3.0, 2.5, "FALLBACK: falta " + str(ruta)
    return (float(valores["cargas_estaticas"]),
            float(valores["solicitacion_maxima_sismo_o_viento"]), str(ruta))


def _incompleto(nombre, demanda, capacidad, unidad, clausula, motivo):
    return {"chequeo": nombre, "demanda": demanda, "capacidad": capacidad,
            "ratio": None, "estado": "INCOMPLETO", "unidad": unidad,
            "clausula": clausula, "motivo": motivo}


def _chk(nombre, demanda, capacidad, unidad, clausula, mayor_es_peor=True):
    if not capacidad or capacidad < 0:
        return _incompleto(nombre, round(demanda, 6), round(capacidad, 6), unidad,
                           clausula, "Capacidad nula o negativa: ratio indefinido.")
    ratio = demanda / capacidad
    return {
        "chequeo": nombre,
        "demanda": round(demanda, 6),
        "capacidad": round(capacidad, 6),
        "unidad": unidad,
        "ratio": round(ratio, 6),
        "estado": "CUMPLE" if ratio <= 1.0 else "NO CUMPLE",
        "clausula": clausula,
    }


def verificar(e):
    fs_estatico, fs_sismo, fuente_fs = _factores_seguridad()
    z, col, mat, suelo, car = e["zapata"], e["columna"], e["materiales"], e["suelo"], e["cargas"]
    B, L, h = float(z["B"]), float(z["L"]), float(z["h"])
    rec = float(z.get("recubrimiento", 0.075))
    db = float(z.get("db", 0.016))
    cx, cy = float(col["cx"]), float(col["cy"])
    pos = col.get("posicion", "interior")
    fc, fy = float(mat["fc"]), float(mat["fy"])
    gc = float(mat.get("gamma_hormigon", 23.536))
    sadm = float(suelo["sigma_adm"])

    d = h - rec - db / 2.0
    A = B * L
    Sx = L * B * B / 6.0      # flexion alrededor de Y (momento My) -> modulo con B
    Sy = B * L * L / 6.0
    W = A * h * gc            # peso propio de la zapata
    raiz = math.sqrt(fc)

    r = {"id": e.get("id", "zapata"),
         "geometria": {"B": B, "L": L, "h": h, "d": round(d, 4), "A": round(A, 3),
                       "peso_propio_kN": round(W, 1)},
         "chequeos": [], "avisos": [], "fuente_fs": fuente_fs}

    # --- 1. Excentricidad dentro del nucleo central: CDCRD 4.4.1.5 (c)
    P = float(car["P_serv"]) + W
    Mx = float(car.get("Mx_serv", 0.0) or 0.0)
    My = float(car.get("My_serv", 0.0) or 0.0)
    ex = My / P if P else 0.0
    ey = Mx / P if P else 0.0
    r["chequeos"].append(_chk("Excentricidad ex (nucleo central)", abs(ex), B / 6.0, "m",
                              "CDCRD T4 4.4.1.5 (c)"))
    r["chequeos"].append(_chk("Excentricidad ey (nucleo central)", abs(ey), L / 6.0, "m",
                              "CDCRD T4 4.4.1.5 (c)"))

    # --- 2. Presion de contacto en servicio: CDCRD 4.4.1.5 / 4.4.5.6
    s_med = P / A
    s_max = P / A + abs(My) / Sx + abs(Mx) / Sy
    s_min = P / A - abs(My) / Sx - abs(Mx) / Sy
    r["presion"] = {"media": round(s_med, 1), "maxima": round(s_max, 1), "minima": round(s_min, 1),
                    "unidad": "kN/m2"}
    if s_min < 0:
        r["avisos"].append("Presion minima negativa: hay levantamiento, redistribuir (CDCRD 4.4.1.5 c).")
    r["chequeos"].append(_chk("Presion de contacto, servicio gravitatorio", s_max, sadm, "kN/m2",
                              "CDCRD T4 4.4.1.5"))

    # --- 2b. Presion con sismo: admisible elevada por la relacion de FS (CDCRD 4.3.2.7)
    if car.get("P_serv_sismo") is not None:
        Ps = float(car["P_serv_sismo"]) + W
        Mxs = float(car.get("Mx_serv_sismo", 0.0) or 0.0)
        Mys = float(car.get("My_serv_sismo", 0.0) or 0.0)
        s_max_s = Ps / A + abs(Mys) / Sx + abs(Mxs) / Sy
        sadm_s = sadm * (fs_estatico / fs_sismo)
        ch_s = _chk("Presion de contacto, servicio con sismo", s_max_s, sadm_s,
                    "kN/m2", "CDCRD T4 4.3.2.7; 4.4.1.5")
        ch_s["fs_estatico"] = fs_estatico
        ch_s["fs_sismo_o_viento"] = fs_sismo
        if suelo.get("sigma_adm_control") != "corte":
            ch_s["estado"] = "INCOMPLETO"
            ch_s["motivo"] = ("No se ha confirmado que sigma_adm este controlado por falla por corte; "
                              "4.4.1.5 tambien exige revisar asentamientos. Interpretacion pendiente de Emil.")
        r["chequeos"].append(ch_s)
    elif car.get("sismo_aplica") is False:
        r["avisos"].append("Sismo declarado no aplicable por el usuario; documentar fundamento de proyecto.")
    else:
        r["chequeos"].append(_incompleto("Presion de contacto, servicio con sismo", None, None,
            "kN/m2", "CDCRD T4 4.3.2.7; 4.4.1.5", "No se declararon cargas de servicio con sismo ni sismo_aplica=false."))

    # --- carga factorizada, presion neta (sin peso propio: lo resiste el suelo directamente)
    Pu = float(car["Pu"])
    qu = Pu / A

    # --- 3. Cortante en una direccion: ACI 318-19 22.5.5.1
    xv = (B - cx) / 2.0 - d
    if xv > 0:
        Vu1 = qu * L * xv
        phiVc1 = PHI_CORTE * 0.17 * LAMBDA * raiz * (L * 1000.0) * (d * 1000.0) / 1000.0
        r["chequeos"].append(_chk("Cortante en una direccion", Vu1, phiVc1, "kN",
                                  "ACI 318-19 22.5.5.1 / phi 21.2.1"))
    else:
        r["avisos"].append("La seccion critica de cortante en una direccion cae dentro de la columna.")
        r["chequeos"].append(_incompleto("Cortante en una direccion", None, None, "kN",
            "ACI 318-19 22.5.5.1", "La seccion critica calculada cae dentro de la columna; este modelo no puede verificarla."))

    # --- 4. Punzonamiento (dos direcciones): ACI 318-19 22.6.5.2
    b0 = 2.0 * (cx + d) + 2.0 * (cy + d)
    Vu2 = Pu - qu * (cx + d) * (cy + d)
    beta = max(cx, cy) / min(cx, cy)
    a_s = ALFA_S.get(pos, 40)
    vc_a = 0.33 * LAMBDA * raiz
    vc_b = 0.17 * (1.0 + 2.0 / beta) * LAMBDA * raiz
    vc_c = 0.083 * (2.0 + a_s * d / b0) * LAMBDA * raiz
    vc = min(vc_a, vc_b, vc_c)
    phiVc2 = PHI_CORTE * vc * (b0 * 1000.0) * (d * 1000.0) / 1000.0
    ch = _chk("Punzonamiento", Vu2, phiVc2, "kN", "ACI 318-19 22.6.5.2 Tabla / phi 21.2.1")
    ch["detalle"] = {"b0_m": round(b0, 3), "beta": round(beta, 2), "alfa_s": a_s,
                     "vc_MPa": round(vc, 3),
                     "vc_expresiones_MPa": [round(vc_a, 3), round(vc_b, 3), round(vc_c, 3)]}
    r["chequeos"].append(ch)

    # --- 5. Flexion en la cara de la columna: ACI 318-19 22.2 + As_min 7.6.1.1
    for eje, bl, ancho in (("X", (B - cx) / 2.0, L), ("Y", (L - cy) / 2.0, B)):
        Mu = qu * ancho * bl * bl / 2.0
        As = Mu * 1e6 / (PHI_FLEXION * fy * 0.95 * d * 1000.0)     # mm2, brazo jd~0.95d
        As_min = 0.0018 * ancho * 1000.0 * h * 1000.0
        As_req = max(As, As_min)
        As_provisto = z.get("As_provisto_" + eje + "_mm2")
        if As_provisto is None:
            ch = _incompleto("Flexion direccion " + eje + " (As requerido vs provisto)",
                            round(As_req, 1), None, "mm2", "ACI 318-19 22.2 / As_min 7.6.1.1",
                            "No se declaro As_provisto_" + eje + "_mm2; no se puede verificar flexion.")
        else:
            ch = _chk("Flexion direccion " + eje + " (As requerido vs provisto)",
                      As_req, float(As_provisto), "mm2", "ACI 318-19 22.2 / As_min 7.6.1.1")
        ch["Mu_kNm"] = round(Mu, 1)
        ch["As_calculado_mm2"] = round(As, 0)
        ch["As_minimo_mm2"] = round(As_min, 0)
        ch["As_requerido_mm2"] = round(As_req, 0)
        ch["gobierna"] = "As_min" if As_min >= As else "flexion"
        ch["opciones_armado"] = _armados(As_req, ancho)
        r["chequeos"].append(ch)

    # --- 6. Espesor minimo por longitud de desarrollo del arranque (regla SOP: 25 db)
    dbc = float(mat.get("db_columna", 0.01905))
    h_min = 25.0 * dbc
    r["chequeos"].append(_incompleto("Espesor por longitud de desarrollo del arranque",
        round(h_min, 6), round(h, 6), "m", "SOP firma 3.4; ACI 318-19 25.4.3",
        "25 db es una regla preliminar del SOP; falta verificar ldh y detalles reales segun ACI."))

    estados = [c["estado"] for c in r["chequeos"]]
    ratios = [c["ratio"] for c in r["chequeos"] if c["ratio"] is not None]
    estado = "NO CUMPLE" if "NO CUMPLE" in estados else ("INCOMPLETO" if "INCOMPLETO" in estados else "CUMPLE")
    r["resumen"] = {"estado": estado, "cumple_todo": estado == "CUMPLE",
                    "ratio_maximo": max(ratios) if ratios else None}
    return r


_BARRAS = [("#4 (1/2\")", 129.0), ("#5 (5/8\")", 198.0), ("#6 (3/4\")", 285.0)]


def _armados(As_req_mm2, ancho_m):
    out = []
    for nom, a in _BARRAS:
        for sep in (0.10, 0.125, 0.15, 0.20, 0.25):
            prov = a * (ancho_m / sep)
            if prov >= As_req_mm2:
                out.append({"barra": nom, "separacion_m": sep,
                            "As_provisto_mm2": round(prov, 0)})
                break
    return out


def _test():
    e = {"id": "TEST", "zapata": {"B": 2.0, "L": 2.0, "h": 0.40, "recubrimiento": 0.075, "db": 0.016},
         "columna": {"cx": 0.40, "cy": 0.40, "posicion": "interior"},
         "materiales": {"fc": 21.0, "fy": 420.0},
         "suelo": {"sigma_adm": 200.0},
         "cargas": {"P_serv": 600.0, "Mx_serv": 0.0, "My_serv": 0.0, "Pu": 800.0}}
    r = verificar(e)
    d = r["geometria"]["d"]
    assert abs(d - 0.317) < 1e-3, d
    b0 = 4 * (0.40 + d)
    ch = [c for c in r["chequeos"] if c["chequeo"] == "Punzonamiento"][0]
    assert abs(ch["detalle"]["b0_m"] - b0) < 1e-3
    vu = 800.0 - (800.0 / 4.0) * (0.40 + d) ** 2
    assert abs(ch["demanda"] - vu) < 0.05, (ch["demanda"], vu)
    s = [c for c in r["chequeos"] if c["chequeo"].startswith("Presion")][0]
    esperado = (600.0 + 4.0 * 0.40 * 23.536) / 4.0
    assert abs(s["demanda"] - esperado) < 0.05, (s["demanda"], esperado)

    # T4 4.4.1.5(c): justo fuera de B/6 hay excentricidad inadmisible.
    e_ex = deepcopy(e)
    peso = 4.0 * 0.40 * 23.536
    e_ex["cargas"]["My_serv"] = (600.0 + peso) * (2.0 / 6.0 + 0.0001)
    rx = verificar(e_ex)
    ex = next(c for c in rx["chequeos"] if c["chequeo"].startswith("Excentricidad ex"))
    assert ex["estado"] == "NO CUMPLE" and ex["ratio"] > 1.0, ex

    # ACI 318-19 Tabla 22.6.5.3: alfa_s es 40 interior y 20 esquina.
    e_es = deepcopy(e)
    e_es["columna"]["posicion"] = "esquina"
    esquina = next(c for c in verificar(e_es)["chequeos"] if c["chequeo"] == "Punzonamiento")
    assert ch["detalle"]["alfa_s"] == 40 and esquina["detalle"]["alfa_s"] == 20
    assert esquina["detalle"]["vc_expresiones_MPa"][2] < ch["detalle"]["vc_expresiones_MPa"][2]

    # T4 4.3.2.7: sin sismo declarado no se da conformidad por omision.
    assert r["resumen"]["estado"] != "CUMPLE"
    assert any(c["estado"] == "INCOMPLETO" and "sismo" in c["chequeo"].lower()
               for c in r["chequeos"])
    # T4 4.3.2.7: el fallback conserva FS y anuncia ausencia de la capa maquina.
    fse, fss, origen = _factores_seguridad(Path(__file__).parent / "__fs_ausente__.json")
    assert (fse, fss) == (3.0, 2.5) and origen.startswith("FALLBACK")
    print("autotest OK: geometria, presion, nucleo, alfa_s y sismo no declarado")
    return 0


def main(argv):
    if "--test" in argv:
        return _test()
    if not argv:
        print(__doc__)
        return 1
    with open(argv[0], "r") as fh:
        data = json.load(fh)
    casos = data if isinstance(data, list) else [data]
    res = [verificar(c) for c in casos]
    salida = None
    if "-o" in argv:
        salida = argv[argv.index("-o") + 1]
    txt = json.dumps(res if len(res) > 1 else res[0], indent=1, ensure_ascii=False)
    if salida:
        with open(salida, "w") as fh:
            fh.write(txt)
        print("escrito " + salida)
    else:
        print(txt)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
