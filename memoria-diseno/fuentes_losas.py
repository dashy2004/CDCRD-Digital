"""Lee las fuentes reales de losas y las lleva al contrato de data.json.

- Listado .TXT de Losas.exe (F. Perdomo, v5.x): momentos, armaduras de vano y de apoyo.
- Archivo de datos .DL: materiales, tipo, carga, espesor, luces y recubrimiento por losa.

Mismo criterio que TxtParser.cs de MemoriaPlus (EstructurasRD, rama archive/dotnet-suite):
las secciones se reconocen por su encabezado y cada fila por un patrón propio.

Nada se descarta en silencio: toda fila con aspecto de dato que no se pudo leer, repetida
o incoherente queda en `sin_leer` o en `avisos`, y el generador las lleva al documento.
"""
import os
import re

NUM = re.compile(r"^-?\d+(?:\.\d+)?$")
BARRA = r"(\S+\s*@\s*\d+(?:\.\d+)?\s*cm)"
ENCABEZADOS = (
    ("sistema", r"SISTEMA DE LOSAS : (.+)$"),
    ("archivo", r"Archivo de datos: (.+)$"),
    ("version", r"Ver\. (\d+(?:\.\d+)*)"),
    ("reglamento", r"reglamento (.+)$"),
    ("fecha", r"DISE.O DE SISTEMAS DE LOSAS (.+)$"),
    ("fc", r"f'c : ([\d.]+\d|\d+)"),
    ("fy", r"\bfy : ([\d.]+\d|\d+) ton/cm"),
)


def _lineas(path):
    with open(path, "rb") as f:
        raw = f.read()
    for enc in ("utf-8", "cp1252"):
        try:
            return raw.decode(enc).splitlines()
        except UnicodeDecodeError:
            continue
    return raw.decode("cp1252", errors="replace").splitlines()


def _guardar(d, sec, clave, valor, linea):
    """Registra una fila; una losa repetida no pisa a la anterior: se reporta."""
    if clave in d[sec]:
        d["sin_leer"].append("losa %s repetida en %s: %s" % (clave, sec, linea))
    else:
        d[sec][clave] = valor


def leer_txt(path, nombre=None):
    """Devuelve un nivel con el contrato: meta, mom, ax, ay, apx, apy (esp y carga vacíos)."""
    d = {"nombre": nombre or os.path.splitext(os.path.basename(str(path)))[0], "fuente": os.path.basename(str(path)),
         "esp": {}, "carga": {}, "mom": {}, "ax": {}, "ay": {}, "apx": [], "apy": [], "meta": {},
         "sin_leer": [], "avisos": []}
    sec = None
    for raw in _lineas(path):
        l = " ".join(raw.split())
        if not l:
            continue
        t = l.split()
        # El punto en lugar de la vocal acentuada tolera listados en otra codificación.
        if re.search(r"C.LCULO DE MOMENTOS", l, re.I):
            sec = "mom"
            continue
        m = re.search(r"ARMADURAS SEG.N .?(X|Y).?( SOBRE LOS APOYOS)?$", l, re.I)
        if m:
            sec = ("ap" if m.group(2) else "a") + m.group(1).lower()
            continue
        for clave, pat in ENCABEZADOS:
            m = re.search(pat, l)
            if m:
                d["meta"][clave] = m.group(1).strip()
        if sec == "mom":
            if len(t) == 10 and all(NUM.match(x) for x in t):
                _guardar(d, "mom", str(int(t[0])), {"tipo": t[1], "q": t[2], "H": t[3], "Lx": t[4], "Ly": t[5],
                                                    "Mfx": t[6], "Mfy": t[7], "Msx": t[8], "Msy": t[9]}, l)
            elif t[0].isdigit():
                d["sin_leer"].append(l)
        elif sec in ("ax", "ay"):
            m = re.match(r"^(\d+) ([\d.]+) ([\d.]+) ([\d.]+) " + BARRA + r" ([\d.]+)$", l)
            if m:
                _guardar(d, sec, str(int(m.group(1))), {"d": m.group(2), "Mu": m.group(3), "As": m.group(4),
                                                        "barra": m.group(5), "Asd": m.group(6)}, l)
            elif len(t) == 5 and all(NUM.match(x) for x in t):
                _guardar(d, sec, str(int(t[0])), {"d": t[1], "Mu": t[2], "As": t[3], "barra": "—", "Asd": t[4]}, l)
            elif t[0].isdigit():
                d["sin_leer"].append(l)
        elif sec in ("apx", "apy"):
            m = re.match(r"^(\d+)- ?(\d+) " + r"([\d.]+) " * 8 + BARRA + "$", l)
            if m:
                g = m.groups()
                d[sec].append({"i": int(g[0]), "j": int(g[1]), "MuI": g[2], "MuJ": g[3], "Mu": g[4],
                               "d": g[5], "As": g[6], "DAs": g[9], "barra": g[10]})
            elif re.match(r"^\d+- ?\d+ ", l):
                d["sin_leer"].append(l)
    if not d["mom"]:
        d["avisos"].append("el listado %s no contiene ninguna fila de momentos legible" % d["fuente"])
    for sec_, nombre_ in (("ax", 'armaduras según "X"'), ("ay", 'armaduras según "Y"')):
        faltan = sorted(set(d["mom"]) - set(d[sec_]), key=int)
        if d["mom"] and faltan:
            d["avisos"].append("losas con momentos pero sin fila de %s: %s" % (nombre_, ", ".join(faltan)))
    return d


def leer_dl(path):
    """Devuelve {'sistema', 'fc', 'fy', 'nlosa', 'losas': {id: {...}}, 'repetidas': [...]} del archivo de datos."""
    out = {"sistema": None, "fc": None, "fy": None, "nlosa": None, "losas": {}, "repetidas": []}
    datos = [l.strip() for l in _lineas(path) if l.strip() and not l.strip().startswith("$")]
    for l in datos:
        t = l.split()
        if out["sistema"] is None and not all(NUM.match(x) for x in t):
            out["sistema"] = l
        elif len(t) == 4 and all(NUM.match(x) for x in t) and out["fc"] is None:
            out["nlosa"], out["fc"], out["fy"] = int(float(t[0])), float(t[1]), float(t[2])
        elif len(t) == 7 and all(NUM.match(x) for x in t):
            clave = str(int(t[0]))
            if clave in out["losas"]:
                out["repetidas"].append(clave)
            else:
                out["losas"][clave] = {"tipo": t[1], "q": t[2], "h": t[3], "Lx": t[4], "Ly": t[5], "rec": t[6]}
    return out


def nivel(nombre, txt, dl=None):
    """Nivel completo: listado .TXT más, si se da, el .DL (aporta espesor, carga y materiales)."""
    nv = leer_txt(txt, nombre)
    if not dl:
        return nv
    d = leer_dl(dl)
    for k, v in d["losas"].items():
        nv["esp"][k] = {"Lx": "%.2f" % float(v["Lx"]), "Ly": "%.2f" % float(v["Ly"]), "cond": "—", "h": "%.2f" % float(v["h"])}
        nv["carga"][k] = {"qu": "%.2f" % float(v["q"])}
    nv["meta"].setdefault("archivo", os.path.basename(str(dl)))
    if d["fy"] is not None:
        nv["meta"].setdefault("fy", "%g" % d["fy"])
    if d["fc"] is not None:
        nv["meta"].setdefault("fc", "%g" % (d["fc"] * 1000))      # ton/cm² -> kg/cm²
    if d["repetidas"]:
        nv["avisos"].append("losas repetidas en %s: %s" % (os.path.basename(str(dl)), ", ".join(d["repetidas"])))
    if d["nlosa"] is not None and d["nlosa"] != len(d["losas"]):
        nv["avisos"].append("%s declara %d losas y trae %d filas" % (os.path.basename(str(dl)), d["nlosa"], len(d["losas"])))
    solo_dl = sorted(set(d["losas"]) - set(nv["mom"]), key=int)
    solo_txt = sorted(set(nv["mom"]) - set(d["losas"]), key=int)
    if solo_dl:
        nv["avisos"].append("losas del archivo de datos sin resultado en el listado: " + ", ".join(solo_dl))
    if solo_txt:
        nv["avisos"].append("losas del listado que no están en el archivo de datos: " + ", ".join(solo_txt))
    return nv
