# SAFE MCP — libro de verificacion de pilotes: geometria (R-024 tabla 5.1), demanda
# por pilote y por cabezal, y candidatos a eliminar. Modulo PURO: recibe los
# informes de get_pile_spacing (by_footing) y get_pile_axial_reactions (joint) y
# la definicion de las combinaciones; no toca SAFE. openpyxl solo al escribir.
#
# Reglas que fija (declaradas en la hoja Criterios):
#   - combos clasificadas por su definicion (GetCaseList), no por el nombre;
#   - demanda del cabezal = suma de reacciones por (combo, paso), maximo: con
#     pasos Max/Min de combos sismicas es cota superior, no simultanea;
#   - frames duplicados o inclinados: REVISAR MODELO, fuera de las sumas;
#   - candidato por baja demanda: el cabezal queda <= margen de (a) con un pilote
#     menos manteniendo su factor minimo actual; candidato por geometria: en una
#     pareja con S/B < 3 quitar uno repone la separacion (cual, lo decide el
#     ingeniero); duplicados: borrar del modelo;
#   - (b) pila equivalente PENDIENTE: ningun cabezal sale "cumple";
#   - la hoja reporta y senala; no decide.

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

from pilotes import PilotesError

MAX_FACTOR_SERVICIO = 1.2
MARGEN_CANDIDATO = 0.9
GROUP_PREFIX = "CAB-"     # nombre del grupo de SAFE por cabezal: CAB-<area>; igual en Excel y en SAFE


def nombre_grupo(cabezal) -> str | None:
    return f"{GROUP_PREFIX}{cabezal}" if cabezal is not None else None
_T_POR_UNIDAD = {"kN": 1 / 9.80665, "N": 1 / 9806.65, "kgf": 1 / 1000.0, "Ton": 1.0,
                 "lb": 0.000453592, "kip": 0.453592}

CLASE_DISENO = "diseno (mayorada)"
CLASE_ENVOLVENTE = "envolvente de combos (no se compara)"
CLASE_SERV_GRAV = "servicio gravitatorio"
CLASE_SERV_SISMO = "servicio sismico"


CASOS_DINAMICOS = {3, 4, 5, 6, 7, 8, 12}   # eLoadCaseType: modal, espectro, historia, dinamico, PSD
PATRONES_LATERALES = {5, 6}               # eLoadPatternType: Quake, Wind (estaticos equivalentes)


def clasificar_combos(combos: dict[str, dict], max_factor_servicio: float = MAX_FACTOR_SERVICIO) -> dict[str, str]:
    """combos: {nombre: {"tipos": [0 caso|1 combo], "casos": [...], "sf": [...],
    "tipos_caso": [eLoadCaseType por miembro, 0 si es combo],
    "tipos_patron": [eLoadPatternType del caso, 0 si es combo]}} (los dos ultimos opcionales:
    sin ellos todo caso se toma como estatico de gravedad).

    Lateral = miembro combo, caso dinamico (espectro...) o caso estatico con patron Quake/Wind.
    Envolvente (no se compara): todos los miembros laterales (QX = Qx(1/2) + Qx(2/2)).
    Diseno: prefijo DCon o algun factor de gravedad > max_factor_servicio.
    Servicio sismico: algun miembro lateral; servicio gravitatorio: el resto.
    """
    clase = {}
    for nombre, d in combos.items():
        tipos, sf = list(d["tipos"]), [float(x) for x in d["sf"]]
        tipos_caso = list(d.get("tipos_caso") or [1 if t == 0 else 0 for t in tipos])
        tipos_patron = list(d.get("tipos_patron") or [1 if t == 0 else 0 for t in tipos])
        dinamico = [t == 1 or tc in CASOS_DINAMICOS or tp in PATRONES_LATERALES
                    for t, tc, tp in zip(tipos, tipos_caso, tipos_patron)]
        if nombre.lower().startswith("dcon"):
            clase[nombre] = CLASE_DISENO + " DCon"
        elif tipos and all(dinamico):
            clase[nombre] = CLASE_ENVOLVENTE
        elif max((abs(f) for t, f, dn in zip(tipos, sf, dinamico) if t == 0 and not dn), default=0.0) > max_factor_servicio:
            clase[nombre] = CLASE_DISENO
        elif any(dinamico):
            clase[nombre] = CLASE_SERV_SISMO
        else:
            clase[nombre] = CLASE_SERV_GRAV
    return clase


def _por_pilote(registros):
    out = defaultdict(list)
    for r in registros:
        out[r["pilote"]].append(r)
    return out


def _extremos(regs, combos_set):
    cand = [r for r in regs if r["caso"] in combos_set]
    if not cand:
        return None
    mx = max(cand, key=lambda r: r["axial"])
    mn = min(cand, key=lambda r: r["axial"])
    return {"p_max": mx["axial"], "c_max": f'{mx["caso"]} {mx["paso"]}'.strip(),
            "p_min": mn["axial"], "c_min": f'{mn["caso"]} {mn["paso"]}'.strip()}


def _avisos_modelo(avisos: list[str]) -> tuple[dict[str, str], set[str]]:
    dup_de, inclinados = {}, set()
    for a in avisos:
        if "duplica la coordenada de" in a:
            partes = a.split()
            dup_de[partes[1]] = partes[6]
        elif a.startswith("Frame ") and "inclinad" in a:
            pass
        elif "inclinado(s)" in a and "[" in a:
            inclinados = {x.strip().strip("'\"") for x in a[a.index("[") + 1:a.index("]")].split(",") if x.strip()}
    return dup_de, inclinados


def armar_verificacion(sep: dict, rea: dict, combos: dict[str, dict], q_adm: float,
                       service_combos: str | list[str] = "auto",
                       margen_candidato: float = MARGEN_CANDIDATO,
                       seismic_combos: list[str] | None = None,
                       seismic_factor: float = 1.0) -> dict:
    """Cruza geometria (sep, scope by_footing) y reacciones (rea, joint) en filas de hoja.

    Criterio doble opcional: las combos de servicio (gravedad) se comparan con q_adm*xi tal
    cual; las seismic_combos (p. ej. la envolvente sismica E) con seismic_factor*q_adm*xi
    (4/3 = aumento de un tercio para cargas transitorias). Un pilote o cabezal no cumple si
    falla cualquiera de las dos; el ratio reportado es el mayor.
    """
    if q_adm <= 0 or not math.isfinite(q_adm):
        raise PilotesError("q_adm debe ser positiva (carga admisible de servicio por pilote, FS incluido).")
    if not (0 < margen_candidato <= 1):
        raise PilotesError("margen_candidato debe estar en (0, 1].")
    if sep.get("alcance") != "by_footing":
        raise PilotesError("La verificacion por cabezal exige get_pile_spacing con scope=by_footing.")
    clase = clasificar_combos(combos)
    if isinstance(service_combos, str):
        if service_combos != "auto":
            raise PilotesError("service_combos debe ser \"auto\" o una lista de combinaciones.")
        servicio = {k for k, v in clase.items() if v.startswith("servicio")}
    else:
        servicio = {str(c) for c in service_combos}
        faltan = sorted(servicio - set(combos))
        if faltan:
            raise PilotesError(f"service_combos inexistentes: {faltan}.")
        for c in servicio:
            clase[c] = "servicio (indicada por el usuario)"
    sismo = {str(c) for c in (seismic_combos or [])}
    if sismo:
        if seismic_factor <= 0 or not math.isfinite(seismic_factor):
            raise PilotesError("seismic_factor debe ser positivo (p. ej. 4/3).")
        faltan = sorted(sismo - set(combos))
        if faltan:
            raise PilotesError(f"seismic_combos inexistentes: {faltan}.")
        servicio -= sismo
        for c in sismo:
            clase[c] = f"sismico (indicada por el usuario; admisible x {seismic_factor:g})"
    fs_ = seismic_factor if sismo else None
    diseno = {k for k, v in clase.items() if v.startswith("diseno")}
    if not servicio:
        raise PilotesError("Ninguna combinacion de servicio: indique service_combos.")
    unidad_f = rea["unidades"]["fuerza"]
    a_t = _T_POR_UNIDAD.get(unidad_f, 0.0)

    geo = {p["id"]: p for p in sep["pilotes"]}
    dup_de, inclinados = _avisos_modelo(sep["avisos"])
    regs = _por_pilote(rea["registros"])
    ids = sorted(set(geo) | set(dup_de) | set(regs), key=lambda s: (len(s), s))
    filas = []
    for pid in ids:
        g = geo.get(pid)
        cab = g["cabezal"] if g else geo.get(dup_de.get(pid, ""), {}).get("cabezal")
        factor = g["factor"] if g else None
        q_red = q_adm * factor if factor is not None else None
        es = _extremos(regs.get(pid, []), servicio)
        ss = _extremos(regs.get(pid, []), sismo) if sismo else None
        ed = _extremos(regs.get(pid, []), diseno)
        q_red_s = q_red * fs_ if (q_red is not None and fs_) else None
        falla_g = bool(es and q_red is not None and es["p_max"] > q_red)
        falla_s = bool(ss and q_red_s is not None and ss["p_max"] > q_red_s)
        revisar = []
        if pid in dup_de:
            revisar.append(f"duplicado de {dup_de[pid]}")
        if pid in inclinados:
            revisar.append("frame inclinado")
        if g is None:
            geom = "excluido de geometria (duplicado)"
        elif g["fuera_de_tabla"]:
            geom = "S/B < 3: FUERA DE TABLA"
        elif g["sin_vecino"]:
            geom = "solo en su cabezal (sin interaccion)"
        else:
            geom = "OK"
        if revisar:
            estado = "REVISAR MODELO"
        elif es is None and ss is None:
            estado = "SIN RESULTADO"
        elif q_red is None:
            estado = "SIN FACTOR (S/B < 3): criterio del geotecnista"
        elif falla_g and falla_s:
            estado = "NO CUMPLE q_adm reducida (gravedad y sismo)"
        elif falla_g:
            estado = "NO CUMPLE q_adm reducida (gravedad)"
        elif falla_s:
            estado = f"NO CUMPLE {fs_:g} x q_adm reducida (sismo)"
        else:
            estado = "OK"
        p_min = min([x["p_min"] for x in (es, ss) if x], default=None)
        c_min = next((x["c_min"] for x in sorted([x for x in (es, ss) if x], key=lambda x: x["p_min"])), "")
        ratio_g = (es["p_max"] / q_red) if (es and q_red) else None
        ratio_s = (ss["p_max"] / q_red_s) if (ss and q_red_s) else None
        vecino = (g or {}).get("vecinos") or [{}]
        filas.append({
            "id": pid, "cabezal": cab, "grupo": nombre_grupo(cab), "x": (g or {}).get("x"), "y": (g or {}).get("y"),
            "z_cabeza": (g or {}).get("z_cabeza"), "z_punta": (g or {}).get("z_punta"),
            "revisar": "; ".join(revisar), "vecino": vecino[0].get("id"), "dist": vecino[0].get("distancia"),
            "pareja": (g or {}).get("pareja_s_b"), "s_b": (g or {}).get("s_b"), "factor": factor, "geom": geom,
            "q_adm": q_adm, "q_red": q_red, "q_red_t": q_red * a_t if q_red else None,
            "p_serv": es["p_max"] if es else None, "c_serv": es["c_max"] if es else None,
            "q_red_sismo": q_red_s, "p_sismo": ss["p_max"] if ss else None, "c_sismo": ss["c_max"] if ss else None,
            "ratio_sismo": ratio_s,
            "p_trac": -p_min if (p_min is not None and p_min < 0) else 0.0,
            "c_trac": c_min if (p_min is not None and p_min < 0) else "",
            "p_dis": ed["p_max"] if ed else None, "c_dis": ed["c_max"] if ed else None,
            "ratio": max([r for r in (ratio_g, ratio_s) if r is not None], default=None),
            "ratio_gravedad": ratio_g,
            "ratio_sin_factor": (es["p_max"] / q_adm) if es else None,
            "estado": estado, "candidato": "",
        })
    por_id = {f["id"]: f for f in filas}

    cab_filas, candidatos = [], []
    for g in sorted(sep["grupos"], key=lambda t: (len(str(t["cabezal"])), str(t["cabezal"]))):
        cid = g["cabezal"]
        miembros = [f for f in filas if f["cabezal"] == cid]
        sanos = [f for f in miembros if not f["revisar"]]
        por_combo, por_combo_s = defaultdict(float), defaultdict(float)
        for f in sanos:
            for r in regs.get(f["id"], []):
                if r["caso"] in servicio:
                    por_combo[(r["caso"], r["paso"])] += r["axial"]
                elif r["caso"] in sismo:
                    por_combo_s[(r["caso"], r["paso"])] += r["axial"]
        if por_combo:
            (cc, cp), dem = max(por_combo.items(), key=lambda t: t[1])
            combo_dem = f"{cc} {cp}".strip()
        else:
            dem, combo_dem = None, None
        if por_combo_s:
            (cc, cp), dem_s = max(por_combo_s.items(), key=lambda t: t[1])
            combo_dem_s = f"{cc} {cp}".strip()
        else:
            dem_s, combo_dem_s = None, None
        n = len(sanos)
        factores = [f["factor"] for f in sanos if f["factor"] is not None]
        fuera = [f["id"] for f in sanos if f["factor"] is None]
        suma_f = sum(factores)
        cap_a = q_adm * suma_f if (factores and not fuera) else None
        cap_a_s = cap_a * fs_ if (cap_a and fs_) else None
        ratio_g = dem / cap_a if (dem is not None and cap_a) else None
        ratio_s = dem_s / cap_a_s if (dem_s is not None and cap_a_s) else None
        ratio = max([r for r in (ratio_g, ratio_s) if r is not None], default=None)
        f_min = min(factores) if factores else None
        sobran = 0
        if (dem is not None or dem_s is not None) and f_min and not fuera and n > 1:
            def cabe(k):
                base = margen_candidato * (n - k - 1) * f_min * q_adm
                return (dem is None or dem <= base) and (dem_s is None or dem_s <= base * fs_)
            while n - sobran - 1 >= 1 and cabe(sobran):
                sobran += 1
        orden = sorted([f for f in sanos if f["p_serv"] is not None], key=lambda f: f["p_serv"])
        cands = orden[:sobran]
        for f in cands:
            candidatos.append({"id": f["id"], "cabezal": cid, "p_serv": f["p_serv"], "ratio": f["ratio"],
                               "p_trac": f["p_trac"], "s_b": f["s_b"],
                               "motivo": f"baja demanda: el cabezal queda <= {margen_candidato:.0%} de (a) con este pilote menos"})
        sanos_ids = {x["id"] for x in sanos}
        for f in sanos:
            if f["factor"] is None and f["pareja"] in sanos_ids:
                candidatos.append({"id": f["id"], "cabezal": cid, "p_serv": f["p_serv"], "ratio": f["ratio"],
                                   "p_trac": f["p_trac"], "s_b": f["s_b"],
                                   "motivo": f"geometria: S/B {f['s_b']:.2f} < 3 con {f['pareja']}; eliminar uno de los dos repone la separacion (decidir cual)"})
        if fuera:
            estado = "SIN FACTOR: criterio del geotecnista"
        elif ratio is None:
            estado = "SIN RESULTADO"
        elif ratio > 1:
            estado = "NO CUMPLE (a)" + (" (sismo)" if (ratio_s or 0) > 1 and not (ratio_g or 0) > 1 else
                                      " (gravedad)" if (ratio_g or 0) > 1 and not (ratio_s or 0) > 1 else
                                      " (gravedad y sismo)" if sismo else "")
        else:
            estado = "OK frente a (a); (b) PENDIENTE"
        cab_filas.append({"cabezal": cid, "grupo": nombre_grupo(cid), "n": len(miembros), "n_sanos": n,
                          "pilotes": ", ".join(f["id"] for f in miembros),
                          "no_cumplen": ", ".join(f["id"] for f in sanos if f["estado"].startswith("NO CUMPLE")),
                          "excluidos": ", ".join(f["id"] for f in miembros if f["revisar"]),
                          "s_b_min": g["s_b_min"], "f_min": f_min, "suma_f": round(suma_f, 3),
                          "fuera": ", ".join(fuera), "cap_a": cap_a, "cap_a_t": cap_a * a_t if cap_a else None,
                          "dem": dem, "dem_t": dem * a_t if dem else None, "combo_dem": combo_dem,
                          "dem_sismo": dem_s, "combo_dem_sismo": combo_dem_s, "cap_a_sismo": cap_a_s,
                          "ratio_gravedad": ratio_g, "ratio_sismo": ratio_s,
                          "ratio": ratio, "estado": estado, "sobran": sobran,
                          "candidatos": ", ".join(f["id"] for f in cands)})
    for f in filas:
        if "duplicado" in f["revisar"]:
            candidatos.append({"id": f["id"], "cabezal": f["cabezal"], "p_serv": f["p_serv"], "ratio": None,
                               "p_trac": f["p_trac"], "s_b": None,
                               "motivo": f"modelo: frame {f['revisar']}; borrar del modelo, no es un pilote"})
    for c in candidatos:
        f = por_id[c["id"]]
        f["candidato"] = "; ".join(x for x in [f["candidato"], c["motivo"].split(":")[0]] if x)

    n_rev = sum(1 for f in filas if f["revisar"])
    validos = [f for f in filas if f["p_serv"] is not None and not f["revisar"]]
    critico = max(validos, key=lambda f: f["p_serv"]) if validos else None
    resumen = {
        "n_pilotes": len(filas), "n_frames_modelo": sep["n_frames_modelo"],
        "n_cabezales": len(cab_filas), "cabezales_un_pilote": sum(1 for c in cab_filas if c["n"] == 1),
        "fuera_de_tabla": sep["resumen"]["fuera_de_tabla"], "s_b": sep["resumen"]["s_b"],
        "histograma_s_b": sep["resumen"]["histograma_s_b"],
        "factor_minimo": sep["resumen"]["factor_minimo"],
        "factor_promedio": sep["resumen"]["factor_promedio_en_tabla"],
        "revisar_modelo": [f"{f['id']} ({f['revisar']})" for f in filas if f["revisar"]],
        "geometria_conforme": not (sep["resumen"]["fuera_de_tabla"]["n"] or n_rev),
        "servicio": sorted(servicio, key=lambda s: (len(s), s)),
        "sismo": sorted(sismo, key=lambda s: (len(s), s)), "factor_sismo": fs_,
        "n_no_cumplen_gravedad": sum(1 for f in filas if "gravedad" in f["estado"]),
        "n_no_cumplen_sismo": sum(1 for f in filas if "sismo" in f["estado"]),
        "q_adm": q_adm, "unidad_fuerza": unidad_f,
        "critico": ({"id": critico["id"], "cabezal": critico["cabezal"], "p_serv": round(critico["p_serv"], 3),
                     "combo": critico["c_serv"], "ratio": round(critico["ratio"], 4) if critico["ratio"] else None}
                    if critico else None),
        "n_no_cumplen": sum(1 for f in filas if f["estado"].startswith("NO CUMPLE")),
        "n_sin_factor": sum(1 for f in filas if f["estado"].startswith("SIN FACTOR")),
        "n_con_traccion": sum(1 for f in validos if f["p_trac"] > 0),
        "cabezales_no_cumplen": [c["cabezal"] for c in cab_filas if c["estado"].startswith("NO CUMPLE")],
        "cabezales_sin_factor": [c["cabezal"] for c in cab_filas if c["estado"].startswith("SIN FACTOR")],
        "n_candidatos": len({c["id"] for c in candidatos}),
        "candidatos_por_motivo": {k: sum(1 for c in candidatos if c["motivo"].startswith(k))
                                  for k in ("baja demanda", "geometria", "modelo")},
        "margen_candidato": margen_candidato,
        "b_pila_equivalente": "PENDIENTE en todos los cabezales; la capacidad del grupo NO esta determinada.",
    }
    ver = {"filas": filas, "cabezales": cab_filas, "candidatos": candidatos, "clase_combos": clase,
           "combos": combos, "resumen": resumen}
    ver["propuesta"] = proponer_cambios(ver, q_adm, margen_candidato)
    resumen["propuesta"] = {k: ver["propuesta"][k] for k in ("totales", "n_pilotes_hoy", "n_pilotes_propuesta")}
    return ver



# ---------------------------------------------------------------------------
# Propuesta de cambios por cabezal (sugerencia, no decision)
# ---------------------------------------------------------------------------

XI_MALLA = 0.9        # malla regular a 5 diametros (2.25 m con 0.45): factor 0.9 por escalon


def proponer_cambios(ver: dict, q_adm: float, margen_candidato: float = MARGEN_CANDIDATO,
                     xi_malla: float = XI_MALLA) -> dict:
    """Por cabezal: cuantos pilotes exige la demanda con (a) y margen, y que accion sale.

    n_min_xi = ceil(dem / (margen * q_adm * xi_min actual)); n_min_malla idem con xi_malla
    (reespaciar a malla de 5 diametros). Acciones: anadir / quitar / reespaciar (cabezal
    sin factor por S/B < 3) / mantener / sin_resultado. Los pilotes a quitar son los
    candidatos de baja demanda ya calculados (los menos cargados). Todo exige reanalisis:
    quitar pilotes sube la traccion de los que quedan y la demanda es cota superior.
    """
    if not (0 < margen_candidato <= 1) or not (0 < xi_malla <= 1):
        raise PilotesError("margen_candidato y xi_malla deben estar en (0, 1].")
    filas = []
    totales = {"anadir": 0, "quitar": 0, "redistribuir": 0, "reespaciar": 0, "mantener": 0, "sin_resultado": 0}
    sobrecargados = {}
    for f in ver["filas"]:
        if f["estado"].startswith("NO CUMPLE"):
            sobrecargados.setdefault(f["cabezal"], []).append(f["id"])
    n_hoy = n_prop = 0
    for c in ver["cabezales"]:
        n, dem, xi = c["n_sanos"], c["dem"], c["f_min"]
        dem_s, f_s = c.get("dem_sismo"), (c["cap_a_sismo"] / c["cap_a"]) if (c.get("cap_a_sismo") and c.get("cap_a")) else None
        if dem is None and dem_s is not None:
            dem = 0.0
        fila = {"cabezal": c["cabezal"], "n_hoy": n, "excluidos": c["excluidos"], "dem": dem,
                "xi_min": xi, "cap_a": c["cap_a"], "ratio": c["ratio"], "s_b_min": c["s_b_min"],
                "n_min_xi": None, "n_min_malla": None, "accion": "", "delta": 0, "pilotes": "", "detalle": ""}
        if dem is None:
            fila["accion"], fila["detalle"] = "sin_resultado", "sin reacciones en la salida seleccionada"
        else:
            def n_min(f_grupo):
                k = math.ceil(dem / (margen_candidato * q_adm * f_grupo))
                if dem_s is not None and f_s:
                    k = max(k, math.ceil(dem_s / (margen_candidato * q_adm * f_grupo * f_s)))
                return k
            n_malla = n_min(xi_malla)
            fila["n_min_malla"] = n_malla
            if xi is None or c["fuera"]:
                fila["accion"], fila["delta"] = "reespaciar", n_malla - n
                fila["detalle"] = (f"pareja(s) con S/B < 3 ({c['fuera']}): reespaciar a >= 5 diametros y dejar "
                                   f"{n_malla} pilote(s) (hoy {n})")
            else:
                n_xi = n_min(xi)
                fila["n_min_xi"] = n_xi
                if n_xi > n:
                    fila["accion"], fila["delta"] = "anadir", n_xi - n
                    fila["detalle"] = f"anadir {n_xi - n} (a {n_xi}) manteniendo el factor {xi:g}"
                    if n_malla < n_xi:
                        fila["detalle"] += f"; o reespaciar a malla de 5 diametros y {n_malla}"
                elif n_xi < n and sobrecargados.get(c["cabezal"]):
                    # La suma cumple pero hay pilotes individualmente sobrecargados: el problema
                    # es la distribucion (bordes, rigidez del cabezal), no el numero. No se quita.
                    fila["accion"], fila["delta"] = "redistribuir", 0
                    fila["n_min_xi"] = n_xi
                    fila["detalle"] = (f"la suma (a) admite {n_xi} pero {len(sobrecargados[c['cabezal']])} pilote(s) superan "
                                       f"q_adm·f ({', '.join(sobrecargados[c['cabezal']][:8])}): mover pilotes hacia la zona "
                                       f"cargada o revisar rigidez del cabezal; no quitar sin reanalizar")
                elif n_xi < n:
                    fila["accion"], fila["delta"] = "quitar", n_xi - n
                    cands = [x for x in c["candidatos"].split(", ") if x][: n - n_xi]
                    fila["pilotes"] = ", ".join(cands)
                    fila["detalle"] = f"quitar hasta {n - n_xi} (a {n_xi}); los menos cargados: {fila['pilotes'] or 'ver Candidatos'}"
                else:
                    fila["accion"], fila["detalle"] = "mantener", f"n minimo {n_xi} = n actual"
            n_hoy += n
            n_prop += n + fila["delta"]
        totales[fila["accion"]] += 1
        filas.append(fila)
    modelo = [f"{f['id']}: {f['revisar']}" for f in ver["filas"] if f["revisar"]]
    orden = {"reespaciar": 0, "anadir": 1, "redistribuir": 2, "quitar": 3, "mantener": 4, "sin_resultado": 5}
    filas.sort(key=lambda f: (orden[f["accion"]], -(f["ratio"] or 0), str(f["cabezal"])))
    return {"filas": filas, "totales": totales, "n_pilotes_hoy": n_hoy, "n_pilotes_propuesta": n_prop,
            "modelo_a_revisar": modelo, "q_adm": q_adm, "margen": margen_candidato, "xi_malla": xi_malla,
            "advertencias": [
                "Propuesta por capacidad (a) con margen; no es una decision: reanalizar en copia y revisar el firmante.",
                "Quitar pilotes redistribuye carga y sube la traccion de los restantes; la capacidad a traccion no esta evaluada.",
                "La demanda del cabezal es cota superior (suma de maximos por combo); (b) pila equivalente sigue pendiente.",
                "Anadir pilotes: respetar >= 5 diametros entre ejes para no bajar el factor de grupo."]}


def comparar_verificaciones(antes: dict, despues: dict) -> dict:
    """Antes/despues por cabezal y global entre dos armar_verificacion (ensayo en copia)."""
    def por_cab(ver):
        return {c["cabezal"]: c for c in ver["cabezales"]}
    a, d = por_cab(antes), por_cab(despues)
    cabezales = []
    for cid in sorted(set(a) | set(d), key=lambda s: (len(str(s)), str(s))):
        ca, cd = a.get(cid), d.get(cid)
        cabezales.append({"cabezal": cid,
                          "n": (ca["n_sanos"] if ca else None, cd["n_sanos"] if cd else None),
                          "dem": (ca["dem"] if ca else None, cd["dem"] if cd else None),
                          "ratio": (ca["ratio"] if ca else None, cd["ratio"] if cd else None),
                          "estado": (ca["estado"] if ca else None, cd["estado"] if cd else None)})
    def trac_max(ver):
        return max((f["p_trac"] for f in ver["filas"] if not f["revisar"]), default=0.0)
    ra, rd = antes["resumen"], despues["resumen"]
    claves = ("n_pilotes", "n_no_cumplen", "n_sin_factor", "n_con_traccion", "n_candidatos", "geometria_conforme")
    return {"global": {k: (ra[k], rd[k]) for k in claves},
            "critico": (ra["critico"], rd["critico"]),
            "traccion_max": (trac_max(antes), trac_max(despues)),
            "cabezales_no_cumplen": (ra["cabezales_no_cumplen"], rd["cabezales_no_cumplen"]),
            "cabezales": cabezales,
            "empeoran": [c["cabezal"] for c in cabezales if (c["ratio"][0] or 0) < (c["ratio"][1] or 0) - 1e-9],
            "mejoran": [c["cabezal"] for c in cabezales if (c["ratio"][0] or 0) > (c["ratio"][1] or 0) + 1e-9]}

# ---------------------------------------------------------------------------
# Escritura del libro
# ---------------------------------------------------------------------------

def escribir_libro(ver: dict, path: str, meta: dict) -> list[str]:
    """Escribe el .xlsx y devuelve los nombres de hoja. meta: modelo, unidades, origen."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    cab = Font(bold=True, color="FFFFFF")
    cab_fill = PatternFill("solid", fgColor="1F4E78")
    rojo, amarillo, verde = (PatternFill("solid", fgColor=c) for c in ("F8CBAD", "FFE699", "C6E0B4"))

    def hoja(ws, cols, rows, color=None):
        ws.append([c[0] for c in cols])
        for cell in ws[1]:
            cell.font, cell.fill = cab, cab_fill
            cell.alignment = Alignment(wrap_text=True, vertical="center")
        for r in rows:
            ws.append([r.get(c[1]) for c in cols])
            fill = color(r) if color else None
            if fill:
                for cell in ws[ws.max_row]:
                    cell.fill = fill
        for i, c in enumerate(cols, 1):
            ws.column_dimensions[get_column_letter(i)].width = c[2]
            if len(c) > 3:
                for cell in ws[get_column_letter(i)][1:]:
                    cell.number_format = c[3]
        ws.freeze_panes = "B2"
        if rows:
            ws.auto_filter.ref = ws.dimensions

    def color_estado(r):
        e = str(r.get("estado", ""))
        if e.startswith(("REVISAR", "NO CUMPLE")):
            return rojo
        if e.startswith("SIN"):
            return amarillo
        if e.startswith("OK"):
            return amarillo if r.get("candidato") else verde
        return None

    res = ver["resumen"]
    u = res["unidad_fuerza"]
    wb = Workbook()
    ws = wb.active
    ws.title = "Resumen"
    crit = res["critico"]
    lineas = [
        ("Verificacion de pilotes: geometria (MOPC R-024 tabla 5.1) y demanda", ""),
        ("Modelo", meta.get("modelo", "")), ("Fecha", str(date.today())),
        ("Origen", meta.get("origen", "SAFE-MCP export_pile_check_xlsx")),
        ("Unidades de lectura", f"{meta.get('unidades', '')}; columnas en t solo si la fuerza es convertible"),
        ("", ""),
        ("GEOMETRIA", ""),
        ("Pilotes leidos / frames del modelo", f"{res['n_pilotes']} / {res['n_frames_modelo']}"),
        ("Cabezales (areas de cabezal)", f"{res['n_cabezales']} (de un solo pilote: {res['cabezales_un_pilote']})"),
        ("S/B min / mediana / max", f"{res['s_b']['min']} / {res['s_b']['mediana']} / {res['s_b']['max']}"),
        ("Histograma S/B (<3, 3-4, 4-5, 5-6, >=6)", ", ".join(f"{k}: {v}" for k, v in res["histograma_s_b"].items())),
        ("Factor minimo / promedio (step_down)", f"{res['factor_minimo']} / {res['factor_promedio']}"),
        ("Pilotes con S/B < 3 (fuera de tabla, por cabezal)", f"{res['fuera_de_tabla']['n']}: {', '.join(res['fuera_de_tabla']['ids'])}"),
        ("Frames a revisar en el modelo (duplicados / inclinados)", f"{len(res['revisar_modelo'])}: {', '.join(res['revisar_modelo'])}"),
        ("GEOMETRIA CONFORME A TABLA 5.1", "SI" if res["geometria_conforme"] else "NO"),
        ("", ""),
        ("DEMANDA (combinaciones de servicio / gravedad)", ", ".join(res["servicio"])),
        ("Combinaciones sismicas y factor sobre la admisible",
         (", ".join(res["sismo"]) + f"  ->  admisible x {res['factor_sismo']:g}") if res["sismo"] else "no indicadas (criterio simple)"),
        (f"Carga admisible por pilote ({u}, FS incluido)", f"{res['q_adm']:g}; reducida por grupo = q_adm x factor (equivale solo si el FS no cambia, R-024 5.2)"),
        ("Pilote critico en servicio (sin frames a revisar)",
         f"{crit['id']} (cabezal {crit['cabezal']}): {crit['p_serv']} {u} en {crit['combo']}; ratio {crit['ratio']} frente a q_adm reducida" if crit else "sin resultados"),
        ("Pilotes que NO CUMPLEN q_adm reducida en servicio", str(res["n_no_cumplen"]) +
         (f" (gravedad: {res['n_no_cumplen_gravedad']}, sismo: {res['n_no_cumplen_sismo']})" if res["sismo"] else "")),
        ("Pilotes sin factor (S/B < 3): criterio del geotecnista", str(res["n_sin_factor"])),
        ("Pilotes con traccion en servicio", str(res["n_con_traccion"])),
        ("Cabezales que NO CUMPLEN (a)", f"{len(res['cabezales_no_cumplen'])}: {', '.join(map(str, res['cabezales_no_cumplen']))}"),
        ("Cabezales sin factor (pareja con S/B < 3)", ", ".join(map(str, res["cabezales_sin_factor"])) or "ninguno"),
        ("Capacidad (b) pila equivalente", res["b_pila_equivalente"] + " Ningun cabezal puede darse por 'cumple'."),
        ("", ""),
        ("CANDIDATOS A ELIMINAR", f"{res['n_candidatos']} pilotes (hoja Candidatos): {res['candidatos_por_motivo']}. Son candidatos, no decisiones: cualquier eliminacion exige reanalisis y revision del ingeniero firmante."),
        ("Criterio de baja demanda", f"el cabezal queda <= {res['margen_candidato']:.0%} de (a) con un pilote menos, manteniendo su factor minimo actual; se proponen los menos cargados"),
        ("Demanda del cabezal", "suma de reacciones por combo y paso (cota superior con pasos Max/Min de combos sismicas), sin los frames a revisar"),
    ]
    for a, b in lineas:
        ws.append([a, b])
        if (a.isupper() and not b) or a.startswith(("GEOMETRIA CONFORME", "CANDIDATOS")):
            ws[ws.max_row][0].font = Font(bold=True)
    ws.column_dimensions["A"].width = 58
    ws.column_dimensions["B"].width = 120
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")

    hoja(wb.create_sheet("Pilotes"), [
        ("Pilote", "id", 9), ("Cabezal", "cabezal", 9), ("Grupo SAFE", "grupo", 11), ("X", "x", 9, "0.000"), ("Y", "y", 9, "0.000"),
        ("Z cabeza", "z_cabeza", 8, "0.00"), ("Z punta", "z_punta", 8, "0.00"), ("Revisar modelo", "revisar", 22),
        ("Vecino", "vecino", 8), ("Dist.", "dist", 9, "0.000"), ("Pareja S/B", "pareja", 9), ("S/B", "s_b", 8, "0.000"),
        ("Factor (5.1)", "factor", 9, "0.00"), ("Geometria", "geom", 30),
        (f"q_adm ({u})", "q_adm", 9, "0.0"), (f"q_adm·f ({u})", "q_red", 10, "0.0"), ("q_adm·f (t)", "q_red_t", 9, "0.0"),
        (f"P max servicio ({u})", "p_serv", 11, "0.0"), ("Combo", "c_serv", 16),
        ("Ratio gravedad", "ratio_gravedad", 9, "0.00"),
        (f"q_adm·f x factor sismo ({u})", "q_red_sismo", 11, "0.0"),
        (f"P max sismo ({u})", "p_sismo", 11, "0.0"), ("Combo sismo", "c_sismo", 16), ("Ratio sismo", "ratio_sismo", 9, "0.00"),
        (f"Traccion max servicio ({u})", "p_trac", 11, "0.0"), ("Combo traccion", "c_trac", 16),
        (f"P max diseno ({u})", "p_dis", 11, "0.0"), ("Combo diseno", "c_dis", 14),
        ("Ratio (mayor)", "ratio", 10, "0.00"), ("Ratio P/q_adm", "ratio_sin_factor", 10, "0.00"),
        ("Estado", "estado", 36), ("Candidato a eliminar", "candidato", 40),
    ], ver["filas"], color_estado)
    hoja(wb.create_sheet("Grupos"), [
        ("Grupo SAFE", "grupo", 12), ("Cabezal (area)", "cabezal", 10), ("Pilotes", "n", 8),
        ("Estado del cabezal", "estado", 36), ("Ratio (mayor)", "ratio", 10, "0.00"),
        ("Pilotes que no cumplen", "no_cumplen", 40), ("Candidatos a eliminar", "candidatos", 30),
        ("Pilotes del grupo", "pilotes", 90),
    ], ver["cabezales"], lambda r: rojo if r["estado"].startswith("NO") else amarillo if r["estado"].startswith("SIN") else verde)
    wsg = wb["Grupos"]
    wsg.append([])
    wsg.append([f"Un grupo de SAFE por cabezal ({GROUP_PREFIX}<area>): el area y sus pilotes. Revisar por grupo "
                "(Select > Groups en SAFE) en vez de pilote a pilote. assign_pile_groups los crea en el modelo."])
    hoja(wb.create_sheet("Cabezales"), [
        ("Cabezal", "cabezal", 9), ("Grupo SAFE", "grupo", 11), ("Pilotes", "n", 8), ("Sanos", "n_sanos", 8), ("Excluidos (revisar)", "excluidos", 18),
        ("S/B min", "s_b_min", 8, "0.000"), ("f min", "f_min", 7, "0.00"), ("Suma f", "suma_f", 8, "0.000"), ("S/B<3", "fuera", 18),
        (f"(a) Suma q_adm·f ({u})", "cap_a", 12, "0.0"), ("(a) (t)", "cap_a_t", 9, "0.0"),
        (f"Demanda servicio ({u})", "dem", 12, "0.0"), ("Demanda (t)", "dem_t", 9, "0.0"), ("Combo", "combo_dem", 16),
        ("Ratio gravedad", "ratio_gravedad", 9, "0.00"),
        (f"(a) x factor sismo ({u})", "cap_a_sismo", 12, "0.0"), (f"Demanda sismo ({u})", "dem_sismo", 12, "0.0"),
        ("Combo sismo", "combo_dem_sismo", 16), ("Ratio sismo", "ratio_sismo", 9, "0.00"),
        ("Ratio (mayor)", "ratio", 10, "0.00"), ("Estado", "estado", 36),
        ("Pilotes que sobran por capacidad", "sobran", 10), ("Candidatos", "candidatos", 30),
    ], ver["cabezales"], lambda r: rojo if r["estado"].startswith("NO") else amarillo if r["estado"].startswith("SIN") else verde)
    hoja(wb.create_sheet("Candidatos"), [
        ("Pilote", "id", 9), ("Cabezal", "cabezal", 9), ("Motivo", "motivo", 90),
        (f"P max servicio ({u})", "p_serv", 12, "0.0"), ("Ratio", "ratio", 8, "0.00"),
        (f"Traccion ({u})", "p_trac", 10, "0.0"), ("S/B", "s_b", 8, "0.000"),
    ], sorted(ver["candidatos"], key=lambda c: (str(c["cabezal"]), c["id"])))
    wsc = wb["Candidatos"]
    wsc.append([])
    wsc.append(["Toda eliminacion exige reanalizar el modelo: la carga se redistribuye y el factor de grupo cambia. "
                "Lista para el ingeniero firmante, no una decision."])
    wsc[wsc.max_row][0].font = Font(bold=True, color="C00000")
    prop = ver.get("propuesta")
    if prop:
        hoja(wb.create_sheet("Propuesta"), [
            ("Cabezal", "cabezal", 9), ("Pilotes hoy", "n_hoy", 9), ("Excluidos", "excluidos", 14),
            (f"Demanda ({u})", "dem", 11, "0.0"), ("f min", "xi_min", 7, "0.00"), (f"(a) ({u})", "cap_a", 11, "0.0"),
            ("Ratio", "ratio", 7, "0.00"), ("S/B min", "s_b_min", 8, "0.000"),
            ("n min (f actual)", "n_min_xi", 9), ("n min (malla 5D)", "n_min_malla", 9),
            ("Accion", "accion", 12), ("Delta", "delta", 7), ("Pilotes a quitar", "pilotes", 30), ("Detalle", "detalle", 80),
        ], prop["filas"], lambda r: rojo if r["accion"] in ("anadir", "reespaciar", "redistribuir") else amarillo if r["accion"] == "quitar" else None)
        wsp = wb["Propuesta"]
        wsp.append([])
        wsp.append([f"Pilotes hoy (sanos): {prop['n_pilotes_hoy']}; con la propuesta: {prop['n_pilotes_propuesta']}; "
                    f"acciones: {prop['totales']}; margen {prop['margen']:.0%}; malla 5D con factor {prop['xi_malla']:g}."])
        wsp.append(["Modelo a revisar: " + ("; ".join(prop["modelo_a_revisar"]) or "nada")])
        for adv in prop["advertencias"]:
            wsp.append([adv])
            wsp[wsp.max_row][0].font = Font(bold=True, color="C00000")
    hoja(wb.create_sheet("Combos"), [("Combinacion", "n", 12), ("Clase", "clase", 34), ("Definicion", "d", 90)],
         [{"n": k, "clase": ver["clase_combos"].get(k, ""),
           "d": " + ".join(f"{float(f):g}·{c}" for c, f in zip(v["casos"], v["sf"]))} for k, v in ver["combos"].items()])
    wsk = wb.create_sheet("Criterios")
    for linea in CRITERIOS:
        wsk.append([linea])
    wsk.column_dimensions["A"].width = 160
    wb.save(path)
    return wb.sheetnames


CRITERIOS = (
    "MOPC R-024 5.1.7.1, tabla 5.1: S/B 6 -> 1.0, 5 -> 0.9, 4 -> 0.8, 3 -> 0.7. Escalon inferior (la norma no interpola). S/B < 3 fuera de tabla: sin factor.",
    "El factor reduce la capacidad ULTIMA; Qadm = Qult reducida / FS. Aplicado sobre la admisible (FS incluido) equivale solo si el FS no cambia (R-024 5.2).",
    "Capacidad del grupo = menor de (a) suma de ultimas reducidas y (b) pila equivalente de las dimensiones del grupo. (b) PENDIENTE: no sale del modelo. Ningun cabezal esta 'cumple'.",
    "S/B del pilote = pareja mas desfavorable a menos de 6 diametros dentro de su cabezal; cabeza = extremo de Z mayor; grupo = pilotes dentro del area de cabezal.",
    "Demanda: reaccion F3 en la punta (positiva = compresion). Combos de servicio clasificadas por su definicion (factores de gravedad <= 1.2, sin prefijo DCon); las mayoradas se listan solo como referencia.",
    "Demanda del cabezal: suma de reacciones por combo y paso; con pasos Max/Min es una cota superior (no simultanea).",
    "Frames duplicados en la misma coordenada o inclinados: artefactos probables de modelado; se excluyen de las sumas por cabezal y se marcan REVISAR MODELO.",
    "Candidato por baja demanda: el cabezal queda <= margen de (a) con un pilote menos, manteniendo el factor minimo actual; se listan los menos cargados. Candidato por geometria: una pareja con S/B < 3 se repone eliminando uno (cual, lo decide el ingeniero).",
    "Esta hoja reporta y senala. No decide ni reemplaza la revision del ingeniero firmante ni el criterio del geotecnista.",
)
