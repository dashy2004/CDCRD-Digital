"""Perfil de superficie por progresiva sobre un alineamiento, via el puente (solo lectura).

Flujo (todas llamadas de lectura, sin token):
  1. alineamiento: StartingStation / EndingStation / Length  (objects.query)
  2. por estacion: XY = Alignment.GetPointAtDist(est - StartingStation)   (objects.invoke)
     -- sin parametros ref; vale para alineamientos sin ecuaciones de estacion.
     Con puente >= build "ref/out" se puede usar PointLocation(est, 0, null, null)
     y leer salidas.easting/northing: ver `xy_en_estacion`.
  3. z_superficie = TinSurface.FindElevationAtXY(x, y)                    (objects.invoke)
  4. opcional: z_perfil = Profile.ElevationAt(est) del perfil nativo       (objects.invoke)
  5. comparacion z_superficie vs z_perfil: estadisticas y desvios > tolerancia.

La parte numerica (`estaciones`, `comparar`, `resumen`) no toca CAD y se prueba con
datos sinteticos en tests/test_perfil.py. La parte de CAD recibe una funcion
`llamar(metodo, parametros)` para poder sustituir el puente por un doble en pruebas.

CLI (requiere Civil 3D abierto con el dibujo):
  python perfil.py --alineamiento E469 --superficie E400 --paso 20 [--perfil E46C]
                   [--inicio 0] [--fin 1000] [--tolerancia 0.05] [--csv salida.csv] [--json salida.json]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path

VERSION = "0.1.0"


# --------------------------------------------------------------------------
# Nucleo puro (sin CAD)
# --------------------------------------------------------------------------

def estaciones(inicio: float, fin: float, paso: float) -> list:
    """Estaciones inicio..fin cada `paso`, incluyendo siempre `fin`. Deterministas (redondeo a mm)."""
    if not all(math.isfinite(v) for v in (inicio, fin, paso)):
        raise ValueError("inicio, fin y paso deben ser finitos")
    if paso <= 0:
        raise ValueError("paso debe ser > 0")
    if fin < inicio:
        raise ValueError("fin debe ser >= inicio")
    n = int(math.floor((fin - inicio) / paso + 1e-9))
    out = [round(inicio + i * paso, 3) for i in range(n + 1)]
    # la ultima estacion se trunca (no se redondea) para no pasar del final del
    # alineamiento: PointLocation lanza PointNotOnEntity con 0.0003 m de exceso
    fin_t = math.floor(fin * 1000) / 1000
    if out[-1] > fin_t:
        out[-1] = fin_t
    elif out[-1] < fin_t:
        out.append(fin_t)
    return out


def comparar(muestras: list, tolerancia: float) -> dict:
    """Compara z_superficie vs z_perfil en cada muestra que tenga ambos valores.

    muestras: [{estacion, z_superficie, z_perfil}, ...]. Devuelve estadisticas de la
    diferencia (perfil - superficie) y la lista de estaciones fuera de tolerancia.
    """
    if tolerancia < 0:
        raise ValueError("tolerancia debe ser >= 0")
    pares = [m for m in muestras if m.get("z_superficie") is not None and m.get("z_perfil") is not None]
    if not pares:
        return {"comparadas": 0, "max_abs_m": None, "media_m": None, "rms_m": None,
                "fuera_tolerancia": [], "tolerancia_m": tolerancia, "veredicto": "sin_datos"}
    difs = [m["z_perfil"] - m["z_superficie"] for m in pares]
    abs_d = [abs(d) for d in difs]
    fuera = [{"estacion": m["estacion"], "diferencia_m": round(d, 4)}
             for m, d in zip(pares, difs) if abs(d) > tolerancia]
    return {
        "comparadas": len(pares),
        "max_abs_m": round(max(abs_d), 4),
        "estacion_max_abs": pares[abs_d.index(max(abs_d))]["estacion"],
        "media_m": round(sum(difs) / len(difs), 4),
        "rms_m": round(math.sqrt(sum(d * d for d in difs) / len(difs)), 4),
        "fuera_tolerancia": fuera,
        "tolerancia_m": tolerancia,
        "veredicto": "coincide" if not fuera else "difiere",
    }


def resumen(muestras: list) -> dict:
    zs = [m["z_superficie"] for m in muestras if m.get("z_superficie") is not None]
    sin = [m["estacion"] for m in muestras if m.get("z_superficie") is None]
    out = {"muestras": len(muestras), "con_cota": len(zs), "sin_cota": sin}
    if zs:
        out.update({"z_min_m": round(min(zs), 3), "z_max_m": round(max(zs), 3),
                    "z_inicio_m": round(zs[0], 3), "z_fin_m": round(zs[-1], 3)})
    if len(zs) >= 2:
        est = [m["estacion"] for m in muestras if m.get("z_superficie") is not None]
        pend = [(zs[i + 1] - zs[i]) / (est[i + 1] - est[i]) for i in range(len(zs) - 1) if est[i + 1] > est[i]]
        if pend:
            out["pendiente_media"] = round((zs[-1] - zs[0]) / (est[-1] - est[0]), 6)
            out["pendiente_max"] = round(max(pend), 6)
            out["pendiente_min"] = round(min(pend), 6)
    return out


# --------------------------------------------------------------------------
# Acceso al puente (inyectable)
# --------------------------------------------------------------------------

def _res(r):
    """objects.invoke devuelve {objetivo, metodo, resultado}; se extrae resultado."""
    return r.get("resultado") if isinstance(r, dict) and "resultado" in r else r


def _num(v, nombre):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise ValueError("%s: el puente no devolvio un numero (%r)" % (nombre, v))
    return float(v)


def leer_alineamiento(llamar, handle: str) -> dict:
    # el puente recibe listas (server.py separa las comas antes de llamar)
    r = llamar("objects.query", {"handles": [handle], "props": ["Name", "StartingStation", "EndingStation", "Length"],
                                 "limite": 1})
    objs = r.get("objetos") if isinstance(r, dict) else None
    if not objs:
        raise LookupError("alineamiento %s no encontrado" % handle)
    o = objs[0]
    p = o.get("props") or o.get("propiedades") or o
    return {"handle": handle, "nombre": p.get("Name"),
            "inicio": _num(p.get("StartingStation"), "StartingStation"),
            "fin": _num(p.get("EndingStation"), "EndingStation"),
            "longitud": _num(p.get("Length"), "Length")}


def xy_en_estacion(llamar, alineamiento: dict, estacion: float, usar_pointlocation: bool = False) -> tuple:
    """XY del eje en la estacion. Por defecto GetPointAtDist (sin ref); opcional PointLocation."""
    if usar_pointlocation:
        r = _res(llamar("objects.invoke", {"handle": alineamiento["handle"], "metodo": "PointLocation",
                                          "args": [estacion, 0.0, None, None]}))
        s = (r or {}).get("salidas") or {}
        return _num(s.get("easting"), "easting"), _num(s.get("northing"), "northing")
    dist = estacion - alineamiento["inicio"]
    r = _res(llamar("objects.invoke", {"handle": alineamiento["handle"], "metodo": "GetPointAtDist", "args": [dist]}))
    if not isinstance(r, list) or len(r) < 2:
        raise ValueError("GetPointAtDist no devolvio un punto: %r" % (r,))
    return _num(r[0], "x"), _num(r[1], "y")


def cota_superficie(llamar, superficie: str, x: float, y: float):
    try:
        r = _res(llamar("objects.invoke", {"handle": superficie, "metodo": "FindElevationAtXY", "args": [x, y]}))
    except Exception as ex:  # fuera de la superficie: el puente devuelve error de la API
        return None, str(ex)
    return _num(r, "FindElevationAtXY"), None


def cota_perfil(llamar, perfil: str, estacion: float):
    try:
        r = _res(llamar("objects.invoke", {"handle": perfil, "metodo": "ElevationAt", "args": [estacion]}))
    except Exception as ex:
        return None, str(ex)
    return _num(r, "ElevationAt"), None


def muestrear(llamar, alineamiento: str, superficie: str, paso: float, inicio: float = None,
              fin: float = None, perfil: str = None, usar_pointlocation: bool = False,
              progreso: int = 0) -> dict:
    al = leer_alineamiento(llamar, alineamiento)
    ini = al["inicio"] if inicio is None else max(inicio, al["inicio"])
    fn = al["fin"] if fin is None else min(fin, al["fin"])
    muestras = []
    lista = estaciones(ini, fn, paso)
    for i, est in enumerate(lista):
        if progreso and i % progreso == 0:
            print("  estacion %d/%d (%.3f)" % (i + 1, len(lista), est), file=sys.stderr, flush=True)
        try:
            x, y = xy_en_estacion(llamar, al, est, usar_pointlocation)
        except Exception as ex:  # fuera del eje u otro error de la API: se registra y se sigue
            muestras.append({"estacion": est, "x": None, "y": None, "z_superficie": None,
                             "error_xy": str(ex)})
            continue
        z, err = cota_superficie(llamar, superficie, x, y)
        m = {"estacion": est, "x": round(x, 4), "y": round(y, 4),
             "z_superficie": None if z is None else round(z, 4)}
        if err:
            m["error_superficie"] = err
        if perfil:
            zp, errp = cota_perfil(llamar, perfil, est)
            m["z_perfil"] = None if zp is None else round(zp, 4)
            if errp:
                m["error_perfil"] = errp
        muestras.append(m)
    return {"version": VERSION, "alineamiento": al, "superficie": superficie, "perfil": perfil,
            "paso_m": paso, "metodo_xy": "PointLocation" if usar_pointlocation else "GetPointAtDist",
            "unidades": "m (INSUNITS del dibujo; verificar con info_dibujo)",
            "muestras": muestras, "resumen": resumen(muestras)}


def escribir_csv(muestras: list, ruta: Path) -> None:
    campos = ["estacion", "x", "y", "z_superficie", "z_perfil", "error_xy", "error_superficie", "error_perfil"]
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=campos, extrasaction="ignore")
        w.writeheader()
        for m in muestras:
            w.writerow(m)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--alineamiento", required=True)
    ap.add_argument("--superficie", required=True)
    ap.add_argument("--paso", type=float, default=20.0)
    ap.add_argument("--perfil")
    ap.add_argument("--inicio", type=float)
    ap.add_argument("--fin", type=float)
    ap.add_argument("--tolerancia", type=float, default=0.05)
    ap.add_argument("--pointlocation", action="store_true", help="usar PointLocation (puente con ref/out)")
    ap.add_argument("--csv")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import puente_cliente  # noqa: E402  (solo cuando se corre contra Civil 3D)
    res = muestrear(puente_cliente.llamar, a.alineamiento, a.superficie, a.paso, a.inicio, a.fin,
                    a.perfil, a.pointlocation, progreso=50)
    if a.perfil:
        res["comparacion"] = comparar(res["muestras"], a.tolerancia)
    if a.csv:
        escribir_csv(res["muestras"], Path(a.csv))
    if a.json:
        Path(a.json).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    salida = {k: v for k, v in res.items() if k != "muestras"}
    print(json.dumps(salida, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
