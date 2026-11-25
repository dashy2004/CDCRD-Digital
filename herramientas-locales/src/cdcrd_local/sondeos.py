"""Verifica los dos CSV de entrada al Geotechnical Modeler antes de su importación."""
import csv
import hashlib
import io
import math
from collections import defaultdict
from decimal import Decimal, InvalidOperation


def _leer(ruta, campos, separador):
    raw = ruta.read_bytes()
    tabla = csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline=""), delimiter=separador)
    cabeceras = tabla.fieldnames or []
    if len(cabeceras) != len(set(cabeceras)) or set(campos) - set(cabeceras):
        raise ValueError(f"{ruta.name}: cabeceras requeridas: {', '.join(campos)}")
    filas = []
    for row in tabla:
        if None in row or any(v is None for v in row.values()):
            raise ValueError(f"{ruta.name}: columnas inconsistentes en línea {tabla.line_num}")
        fila = {k: v.strip() for k, v in row.items()}
        if not fila["Location ID"]:
            raise ValueError(f"{ruta.name}: falta Location ID en línea {tabla.line_num}")
        filas.append((tabla.line_num, fila))
    if not filas:
        raise ValueError(f"{ruta.name}: archivo sin datos")
    return filas, {"archivo": ruta.name, "sha256": hashlib.sha256(raw).hexdigest()}


def _valor(fila, campo):
    try:
        valor = Decimal(fila[campo])
        if not valor.is_finite() or not math.isfinite(float(valor)):
            raise ValueError
        return valor
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise ValueError(f"{fila['Location ID']}: {campo} debe ser un número finito") from exc


def revisar(ubicaciones, litologia, separador=","):
    cab = ("Location ID", "Easting", "Northing", "Ground Level", "Final Depth")
    ub, fuente_ub = _leer(ubicaciones, cab, separador)
    lit, fuente_lit = _leer(litologia, ("Location ID", "Depth Top", "Depth Base"), separador)
    profundidades = {}
    avisos = []

    def aviso(sondeo, detalle, linea=None):
        avisos.append({"sondeo": sondeo, "detalle": detalle, "linea": linea})

    for linea, fila in ub:
        sondeo = fila["Location ID"]
        for campo in cab[1:]:
            _valor(fila, campo)
        if sondeo in profundidades:
            raise ValueError(f"Sondeo duplicado en ubicaciones: {sondeo}")
        profundidad = _valor(fila, "Final Depth")
        if profundidad <= 0:
            aviso(sondeo, "Profundidad final no positiva", linea)
        profundidades[sondeo] = profundidad

    intervalos = defaultdict(list)
    for linea, fila in lit:
        sondeo = fila["Location ID"]
        if sondeo not in profundidades:
            aviso(sondeo, "Tramo sin ubicación asociada", linea)
            continue
        techo, base = _valor(fila, "Depth Top"), _valor(fila, "Depth Base")
        if techo < 0 or base <= techo:
            aviso(sondeo, "Intervalo invertido, negativo o de longitud cero", linea)
            continue
        if not any(fila.get(c) for c in ("Description", "Geology Code", "Legend Code")):
            aviso(sondeo, "Intervalo sin descripción ni código geológico", linea)
        intervalos[sondeo].append((techo, base, linea))

    for sondeo, final in profundidades.items():
        tramos = sorted(intervalos[sondeo])
        if not tramos:
            aviso(sondeo, "Sin intervalos válidos")
            continue
        cubierto = Decimal(0)
        for techo, base, linea in tramos:
            if techo != cubierto:
                tipo = "Solape" if techo < cubierto else "Hueco"
                detalle = f"{tipo} entre profundidad cubierta {cubierto} y techo {techo}"
                aviso(sondeo, detalle, linea)
            if base > final:
                aviso(sondeo, f"Base {base} excede profundidad final {final}", linea)
            cubierto = max(base, cubierto)
        if cubierto < final:
            aviso(sondeo, f"Bitácora termina en {cubierto} antes de la profundidad final {final}")
    return {"ok": not avisos, "sondeos": len(profundidades), "incidencias": avisos,
            "fuentes": [fuente_ub, fuente_lit],
            "alcance": "Integridad de sondeos y continuidad de estratos en las unidades del CSV.",
            "checklist": "https://norm.mivhed.gob.do/portal/templates/2"}
