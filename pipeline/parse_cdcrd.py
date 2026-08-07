#!/usr/bin/env python3
# CDCRD Digital - parser de clausulas
# Extrae texto por pagina, segmenta por clausula numerada, detecta formulas
# (glifos matematicos), tablas y referencias externas. Salida: JSON por titulo.
import json
import re
import sys
import unicodedata
from pathlib import Path

from pypdf import PdfReader

TOMOS = {
    1: "TOMO-1-VOLUMEN-1-JULIO-2026.pdf",
    2: "MIVHED-Analisis-y-Diseno-Estructural-de-Edificaciones-Vol-1-Tomo-2.pdf",
}

NOMBRES_TITULOS = {
    1: "Consideraciones Generales",
    2: "Cargas Minimas para Analisis y Diseño Estructural",
    3: "Procedimientos para la Tramitacion de Planos, Inspeccion y Supervision",
    4: "Suelos y Fundaciones",
    5: "Hormigon Armado",
    6: "Muros de Hormigon Armado de Ductilidad Limitada",
    7: "Aluminio",
    8: "Mamposteria",
    9: "Acero",
    10: "Madera",
    11: "Vidrio y Acristalado",
}

# Clausula: "2.10.3.2.1. ENCABEZADO..." al inicio logico de linea.
RE_CLAUSULA = re.compile(r"(?:^|\n)\s*(\d{1,2}(?:\.\d{1,2}){1,5})\.\s+(?=[A-ZÁÉÍÓÚÑ¿(])")
RE_TABLA = re.compile(r"\bTabla\s+(\d+[A-Za-z]?)", re.IGNORECASE)

REFS_EXTERNAS = [
    (re.compile(r"\bACI\s*318(?:-\d+)?"), "ACI 318"),
    (re.compile(r"\bACI\s*530"), "ACI 530"),
    (re.compile(r"\bASCE(?:/SEI)?\s*7(?:-\d+)?"), "ASCE/SEI 7"),
    (re.compile(r"\bASCE(?:/SEI)?\s*41"), "ASCE/SEI 41"),
    (re.compile(r"\b(?:ANSI/)?AISC\s*360"), "ANSI/AISC 360"),
    (re.compile(r"\b(?:ANSI/)?AISC\s*341"), "ANSI/AISC 341"),
    (re.compile(r"\bAISI\s*S(\d{3})"), "AISI S{m1}"),
    (re.compile(r"\bASTM\s*[A-Z]?\s*\d*"), "ASTM"),
    (re.compile(r"\bAWS\s*D?\d*\.?\d*"), "AWS"),
    (re.compile(r"\bNDS\b"), "NDS"),
    (re.compile(r"\bTMS\s*402"), "TMS 402"),
    (re.compile(r"\bTMS\s*602"), "TMS 602"),
    (re.compile(r"\bASHRAE\b"), "ASHRAE"),
    (re.compile(r"\bNFPA\s*\d*"), "NFPA"),
]

def tiene_glifos_matematicos(t: str) -> bool:
    return any(0x1D400 <= ord(c) <= 0x1D7FF for c in t)

def limpiar_pagina(t: str) -> str:
    # Quita encabezados repetidos de pagina para no contaminar clausulas.
    t = re.sub(r"CÓDIGO DE CONSTRUCCIÓN DE LA REPÚBLICA DOMINICANA\s*", "", t)
    t = re.sub(r"\bCDCRD\b\s*", "", t)
    t = re.sub(r"\bV[I1]-T\d+\s*", "", t)
    t = re.sub(r"(?:^|\n)\s*\d{1,3}\s*(?=\n)", "\n", t)  # numeros de pagina sueltos
    return t

def refs_de(texto: str):
    out = set()
    for rx, canon in REFS_EXTERNAS:
        for m in rx.finditer(texto):
            if "{m1}" in canon:
                out.add(canon.replace("{m1}", m.group(1)))
            else:
                out.add(canon)
    return sorted(out)

def parsear_tomo(num_tomo: int, ruta_pdf: Path):
    r = PdfReader(str(ruta_pdf))
    # 1) texto por pagina con offsets para mapear clausula->paginas
    paginas = []
    for i, pg in enumerate(r.pages):
        t = pg.extract_text() or ""
        paginas.append(limpiar_pagina(t))
    full = ""
    offsets = []  # (offset_inicio, num_pagina_1based)
    for i, t in enumerate(paginas):
        offsets.append((len(full), i + 1))
        full += t + "\n"

    def pagina_de(off: int) -> int:
        pg = 1
        for o, p in offsets:
            if o <= off:
                pg = p
            else:
                break
        return pg

    # 2) segmentar por clausula
    matches = list(RE_CLAUSULA.finditer(full))
    clausulas = []
    for j, m in enumerate(matches):
        cid = m.group(1)
        ini = m.start()
        fin = matches[j + 1].start() if j + 1 < len(matches) else len(full)
        cuerpo = full[m.end():fin].strip()
        # encabezado: hasta el primer punto seguido de espacio/salto (mayusculas)
        enc_m = re.match(r"([A-ZÁÉÍÓÚÑ0-9][^.\n]{0,120})\.", cuerpo)
        encabezado = enc_m.group(1).strip() if enc_m else ""
        p_ini, p_fin = pagina_de(ini), pagina_de(fin - 1)
        pgs = list(range(p_ini, p_fin + 1))
        clausulas.append({
            "id": cid,
            "titulo_num": int(cid.split(".")[0]),
            "capitulo": ".".join(cid.split(".")[:2]),
            "encabezado": encabezado,
            "texto": cuerpo,
            "paginas": pgs,
            "flags": {
                "formula": tiene_glifos_matematicos(cuerpo),
                "tabla": bool(RE_TABLA.search(cuerpo)),
                "vision_ok": False,
            },
            "refs": {"externas": refs_de(cuerpo)},
            "tablas": [],
            "formulas": [],
        })
    return clausulas, len(r.pages)

def main(dir_pdfs: Path, dir_salida: Path):
    todos = {}
    stats = {}
    for num_tomo, nombre in TOMOS.items():
        ruta = dir_pdfs / nombre
        cls, npag = parsear_tomo(num_tomo, ruta)
        stats[num_tomo] = {"paginas": npag, "clausulas": len(cls)}
        for c in cls:
            c["tomo"] = num_tomo
            todos.setdefault(c["titulo_num"], []).append(c)

    dir_salida.mkdir(parents=True, exist_ok=True)
    resumen = []
    for tnum in sorted(todos):
        cls = todos[tnum]
        # dedupe defensivo por (id, primera pagina)
        vistos, unicos = set(), []
        for c in cls:
            k = (c["id"], c["paginas"][0], c["tomo"])
            if k not in vistos:
                vistos.add(k)
                unicos.append(c)
        doc = {
            "titulo": tnum,
            "nombre": NOMBRES_TITULOS.get(tnum, ""),
            "version_codigo": "2026-07",
            "clausulas": unicos,
        }
        out = dir_salida / f"T{tnum:02d}.json"
        out.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        nf = sum(1 for c in unicos if c["flags"]["formula"])
        nt = sum(1 for c in unicos if c["flags"]["tabla"])
        resumen.append((tnum, len(unicos), nf, nt))
    print("tomo -> paginas/clausulas:", stats)
    print(f"{'Titulo':>6} {'clausulas':>10} {'c/formula':>10} {'c/tabla':>8}")
    for tnum, n, nf, nt in resumen:
        print(f"{tnum:>6} {n:>10} {nf:>10} {nt:>8}")

if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
