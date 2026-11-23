"""Arma data.json desde las fuentes reales declaradas en un manifiesto.

Uso: python armar_datos.py fuentes.json data.json

fuentes.json:
{
  "niveles": [ {"nombre": "Nivel 1", "txt": "nivel-1.TXT", "dl": "nivel-1.DL"} ],
  "bloques_json": [ "bloque-a.json" ]      (opcional: bloques ya extraídos con el contrato del README)
}
Las rutas relativas se resuelven contra la carpeta del manifiesto.
Termina con código 1 si falta un archivo o el manifiesto está mal formado; los avisos de
lectura no detienen el proceso: quedan en data.json y el generador los lleva al documento.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fuentes_losas  # noqa: E402


class ErrorDeFuentes(Exception):
    pass


def _ruta(base, p, que):
    if not p:
        raise ErrorDeFuentes("falta la ruta de %s" % que)
    p = p if os.path.isabs(p) else os.path.join(base, p)
    if not os.path.isfile(p):
        raise ErrorDeFuentes("no existe el archivo de %s: %s" % (que, p))
    return p


def armar(man_path):
    base = os.path.dirname(os.path.abspath(man_path))
    try:
        with open(man_path, encoding="utf-8") as f:
            man = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise ErrorDeFuentes("no se pudo leer el manifiesto %s: %s" % (man_path, e))
    data = {"referencia_pdf": False, "paginas_total": 0, "sobrecarga": [], "niveles": [], "bloques": [], "avisos": []}
    for i, n in enumerate(man.get("niveles", []), 1):
        nombre = n.get("nombre") or "Nivel %d" % i
        txt = _ruta(base, n.get("txt"), "listado .TXT del nivel «%s»" % nombre)
        dl = _ruta(base, n["dl"], "datos .DL del nivel «%s»" % nombre) if n.get("dl") else None
        nv = fuentes_losas.nivel(nombre, txt, dl)
        for a in nv["avisos"]:
            data["avisos"].append("Losas, nivel %s: %s." % (nombre, a))
        if nv["sin_leer"]:
            data["avisos"].append("Losas, nivel %s: %d fila(s) del listado no se pudieron leer: %s."
                                  % (nombre, len(nv["sin_leer"]), " | ".join(nv["sin_leer"][:5])))
        data["niveles"].append(nv)
    for p in man.get("bloques_json", []):
        with open(_ruta(base, p, "bloque"), encoding="utf-8") as f:
            data["bloques"].append(json.load(f))
    return data


def main(argv):
    if len(argv) != 3:
        sys.stderr.write(__doc__)
        return 1
    try:
        data = armar(argv[1])
    except ErrorDeFuentes as e:
        sys.stderr.write("ERROR: %s\n" % e)
        return 1
    with open(argv[2], "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    for nv in data["niveles"]:
        sys.stdout.write("%s: %d losas, %d bordes X, %d bordes Y\n" % (nv["nombre"], len(nv["mom"]), len(nv["apx"]), len(nv["apy"])))
    for a in data["avisos"]:
        sys.stderr.write("AVISO: %s\n" % a)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
