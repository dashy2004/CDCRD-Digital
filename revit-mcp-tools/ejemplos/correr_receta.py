# -*- coding: utf-8 -*-
"""Corre una receta (lista ordenada de tools) contra el Revit abierto, sin cliente MCP.

Uso (Python 3.10+ en la maquina con Revit, mismo interprete que usa server.py):

    python correr_receta.py residencial-4n\\receta.json                 # todo en dry_run
    python correr_receta.py residencial-4n\\receta.json --real          # escribe de verdad
    python correr_receta.py residencial-4n\\receta.json --real --desde 06 --hasta 10
    python correr_receta.py residencial-4n\\receta.json --salida C:\\salidas\\r4n
    python correr_receta.py residencial-4n\\receta.json --limpiar --real

Reglas que aplica:
  - Sin --real, fuerza dry_run=True en cada paso (aunque la receta diga otra cosa).
  - Se detiene en el primer paso con ok=False o con 'errores' no vacios.
  - "<carpeta de salida>" en los parametros se sustituye por --salida.
  - Escribe el log completo en <salida>\\receta-<fecha>.json para poder revisarlo.
"""

import argparse
import datetime
import json
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(AQUI), "src"))
import server  # noqa: E402  (usa _run_tool y el sondeo de puerto del servidor)


def sustituir(obj, salida):
    if isinstance(obj, str):
        return obj.replace("<carpeta de salida>", salida)
    if isinstance(obj, list):
        return [sustituir(x, salida) for x in obj]
    if isinstance(obj, dict):
        return dict((k, sustituir(v, salida)) for k, v in obj.items())
    return obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("receta")
    ap.add_argument("--real", action="store_true", help="dry_run=False en todos los pasos")
    ap.add_argument("--desde", default=None)
    ap.add_argument("--hasta", default=None)
    ap.add_argument("--salida", default=os.path.join(os.environ.get("TEMP", "."), "revit-tools", "receta"))
    ap.add_argument("--limpiar", action="store_true", help="correr solo el bloque 'limpieza'")
    a = ap.parse_args()
    with open(a.receta, "r", encoding="utf-8") as fh:
        receta = json.load(fh)
    os.makedirs(a.salida, exist_ok=True)
    pasos = receta["pasos"]
    if a.limpiar:
        pasos = [dict(receta["limpieza"], id="limpieza")]
    log = {"receta": receta.get("nombre"), "real": a.real, "inicio": datetime.datetime.now().isoformat(), "pasos": []}
    activo = a.desde is None
    for paso in pasos:
        if not activo and paso["id"] == a.desde:
            activo = True
        if not activo:
            continue
        params = sustituir(paso.get("params") or {}, a.salida)
        if "dry_run" in params:
            params["dry_run"] = not a.real
        print("== %s %s %s" % (paso["id"], paso["tool"], "(dry_run)" if params.get("dry_run") else ""))
        if paso.get("nota"):
            print("   nota:", paso["nota"])
        r = server._run_tool(paso["tool"], params)
        res = r.get("result") if isinstance(r, dict) else None
        log["pasos"].append({"id": paso["id"], "tool": paso["tool"], "params": params, "respuesta": r})
        ok = bool(r.get("ok")) and (res is None or res.get("ok", True) is not False) and not (res or {}).get("errores")
        resumen = {}
        if isinstance(res, dict):
            for k in ("creadas", "creados", "existian", "errores", "files", "conteos", "relectura", "excepciones"):
                if k in res:
                    v = res[k]
                    resumen[k] = (len(v) if isinstance(v, (list, dict)) and k not in ("relectura", "conteos", "excepciones") else v)
        print("   ->", "OK" if ok else "FALLO", json.dumps(resumen, ensure_ascii=False, default=str)[:400])
        if not ok:
            print("   respuesta completa:", json.dumps(r, ensure_ascii=False, default=str)[:3000])
            break
        if a.hasta is not None and paso["id"] == a.hasta:
            break
    log["fin"] = datetime.datetime.now().isoformat()
    path = os.path.join(a.salida, "receta-%s.json" % datetime.datetime.now().strftime("%Y%m%d-%H%M%S"))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(log, fh, ensure_ascii=False, indent=1, default=str)
    print("log:", path)


if __name__ == "__main__":
    main()
