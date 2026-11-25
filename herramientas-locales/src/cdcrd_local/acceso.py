"""Coordinación geométrica de un acceso. Todos los puntos son E/N/Z en metros."""
from __future__ import annotations

import json
import math
from collections.abc import Iterable
from pathlib import Path

ROLES = ("umbral", "llegada", "sumidero", "control_revit", "control_civil")
REVIT = ("umbral", "control_revit")
CIVIL = ("llegada", "sumidero", "control_civil")


def leer_json(ruta: Path):
    def sin_repetidas(pares):
        datos = {}
        for clave, valor in pares:
            if clave in datos:
                raise ValueError(f"Clave JSON repetida: {clave}")
            datos[clave] = valor
        return datos

    try:
        return json.loads(ruta.read_bytes(), object_pairs_hook=sin_repetidas)
    except (UnicodeError, ValueError) as exc:
        raise ValueError(f"{ruta.name}: {exc}") from exc


def leer_mediciones(rutas: Iterable[Path]) -> list:
    mediciones = []
    for ruta in rutas:
        datos = leer_json(ruta)
        mediciones.extend(datos if isinstance(datos, list) else [datos])
    return mediciones


def texto(valor, nombre):
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"Se requiere texto en {nombre}")
    return valor


def numero(valor, nombre):
    if type(valor) not in (int, float):
        raise ValueError(f"{nombre} debe ser numérico")
    try:
        finito = math.isfinite(valor)
    except OverflowError:
        finito = False
    if not finito:
        raise ValueError(f"{nombre} debe ser finito")
    return valor


def indexar(registros):
    por_rol = {}
    for r in registros:
        if not isinstance(r, dict):
            raise ValueError("Se esperaba un registro JSON por punto")
        if set(r) != {"rol", "documento", "revision", "laminas", "elemento",
                      "punto_m", "marco", "metodo"}:
            raise ValueError("La medición no se ajusta al contrato de ocho campos")
        rol = texto(r.get("rol"), "rol")
        if rol not in ROLES or rol in por_rol:
            raise ValueError(f"Rol desconocido o repetido: {rol}")
        for campo in ("documento", "revision", "elemento", "marco", "metodo"):
            texto(r.get(campo), campo)
        if not isinstance(r.get("laminas"), list) or not r["laminas"]:
            raise ValueError(f"{rol}: faltan láminas de referencia")
        for lamina in r["laminas"]:
            texto(lamina, "lámina")
        p = r.get("punto_m")
        if not isinstance(p, list) or len(p) != 3:
            raise ValueError(f"{rol}: se requieren [E, N, Z] en metros")
        for componente in p:
            numero(componente, "coordenada")
        por_rol[rol] = r
    return por_rol


def distancia_xy(p, q):
    return math.hypot(p[0] - q[0], p[1] - q[1])


def excede(medida, limite):
    # Permite únicamente ruido de representación en la frontera del intervalo.
    return medida > limite and not math.isclose(medida, limite, rel_tol=1e-12, abs_tol=1e-12)


def revisar(registros, criterios):
    if not isinstance(criterios, dict):
        raise ValueError("Se requiere un objeto de criterios")
    if set(criterios) != {"uso", "marco", "tolerancia_xy_m", "tolerancia_z_m",
                         "desnivel_previsto_m", "pendiente_min_pct"}:
        raise ValueError("La entrada no se ajusta al contrato de seis criterios")
    texto(criterios.get("uso"), "procedencia/uso de los criterios")
    marco = texto(criterios.get("marco"), "marco común")
    xy = numero(criterios.get("tolerancia_xy_m"), "tolerancia_xy_m")
    z = numero(criterios.get("tolerancia_z_m"), "tolerancia_z_m")
    objetivo = numero(criterios.get("desnivel_previsto_m"), "desnivel_previsto_m")
    pendiente_min = numero(criterios.get("pendiente_min_pct"), "pendiente_min_pct")
    if min(xy, z) <= 0 or pendiente_min < 0:
        raise ValueError("Tolerancias positivas y pendiente mínima no negativa requeridas")
    por_rol = indexar(registros)
    problemas = []
    medidas = {}
    informe = {
        "estado": "pendiente", "incidencias": problemas, "medidas": medidas,
        "criterios": criterios, "evidencia": por_rol,
        "checklist": {"lista": "CHECK-HOMOLOGACIÓN-DE-PLANOS", "items_relacionados": [2, 4, 6, 7],
                      "fuente": "https://norm.mivhed.gob.do/portal/templates/33"},
        "alcance": "Comparación geométrica puntual. Las láminas identifican la revisión a cotejar.",
    }
    for rol in ROLES:
        if rol not in por_rol:
            problemas.append(f"Falta la medición {rol}")
        elif por_rol[rol]["marco"] != marco:
            problemas.append(f"{rol}: marco horizontal/vertical distinto del declarado")
    if problemas:
        return informe
    for grupo in (REVIT, CIVIL):
        fuentes = {(por_rol[r]["documento"], por_rol[r]["revision"]) for r in grupo}
        if len(fuentes) != 1:
            problemas.append(f"Documento o revisión incompatibles entre {', '.join(grupo)}")
    if problemas:
        return informe

    puerta, llegada, rejilla, ctrl_r, ctrl_c = (por_rol[r]["punto_m"] for r in ROLES)
    medidas.update(control_xy_m=distancia_xy(ctrl_r, ctrl_c), control_z_m=ctrl_r[2]-ctrl_c[2])
    if excede(medidas["control_xy_m"], xy) or excede(abs(medidas["control_z_m"]), z):
        problemas.append("Los puntos homólogos de control discrepan")
    if min(distancia_xy(ctrl_r, puerta), distancia_xy(ctrl_c, llegada)) <= xy:
        problemas.append("El punto independiente de control coincide con el acceso")
    medidas["separacion_acceso_xy_m"] = distancia_xy(puerta, llegada)
    if excede(medidas["separacion_acceso_xy_m"], xy):
        problemas.append("El umbral y la llegada no representan el mismo encuentro en planta")
    longitud = distancia_xy(llegada, rejilla)
    if longitud <= xy:
        problemas.append("Longitud en planta insuficiente para medir la caída hacia la rejilla")
    for valor in (*medidas.values(), longitud):
        numero(valor, "resultado de control geométrico")
    if problemas:
        return informe

    desnivel = puerta[2] - llegada[2]
    caida = llegada[2] - rejilla[2]
    pendiente = 100 * caida / longitud
    for valor in (desnivel, desnivel - objetivo, caida, longitud, pendiente):
        numero(valor, "resultado de geometría")
    medidas.update(desnivel_m=desnivel, desviacion_m=desnivel-objetivo,
                   caida_hacia_rejilla_m=caida, longitud_en_planta_m=longitud,
                   pendiente_entre_extremos_pct=pendiente)
    if excede(abs(desnivel - objetivo), z):
        problemas.append("Desnivel umbral–llegada fuera de la tolerancia del proyecto")
    if caida <= 0 or excede(pendiente_min, pendiente):
        problemas.append("Caída hacia la rejilla insuficiente entre los dos puntos medidos")
    informe["estado"] = "observado" if problemas else "dentro_de_criterios"
    return informe


def comparar(antes, despues, criterios):
    previo = revisar(antes, criterios)
    nuevo = revisar(despues, criterios)
    anterior, actual = previo["evidencia"], nuevo["evidencia"]
    for rol in anterior.keys() & actual.keys():
        a, b = anterior[rol], actual[rol]
        if (a["documento"], a["elemento"]) != (b["documento"], b["elemento"]):
            raise ValueError(f"{rol}: cambió la identidad del documento u objeto entre lecturas")
        if excede(distancia_xy(a["punto_m"], b["punto_m"]), criterios["tolerancia_xy_m"]):
            raise ValueError(f"{rol}: cambió el emplazamiento de la medición entre revisiones")
        if rol.startswith("control_") and excede(abs(a["punto_m"][2] - b["punto_m"][2]),
                                                 criterios["tolerancia_z_m"]):
            raise ValueError(f"{rol}: cambió la cota del testigo independiente entre revisiones")
        if a["punto_m"] != b["punto_m"] and a["revision"] == b["revision"]:
            raise ValueError(f"{rol}: cambió la medición sin identificar una revisión nueva")
    nuevo["estado_anterior"] = previo["estado"]
    nuevo["medidas_anteriores"] = previo["medidas"]
    nuevo["incidencias_anteriores"] = previo["incidencias"]
    nuevo["evidencia_anterior"] = anterior
    if previo["estado"] == "observado" and nuevo["estado"] == "dentro_de_criterios":
        nuevo["cambio"] = "correccion_geometrica_releida"
    else:
        nuevo["cambio"] = "sin_correccion_geometrica_demostrada"
    return nuevo


def ejecutar(args):
    reglas = leer_json(args.criterios)
    actual = leer_mediciones(args.medicion)
    if args.anterior:
        return comparar(leer_mediciones(args.anterior), actual, reglas)
    return revisar(actual, reglas)
