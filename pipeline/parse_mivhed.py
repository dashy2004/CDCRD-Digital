#!/usr/bin/env python3
# CDCRD Digital - parser de los Volumenes II-V (MIVHED)
# Mismo enfoque que parse_cdcrd.py (Vol I): texto por pagina con pypdf,
# segmentacion por clausula numerada, flags de formula/tabla, refs externas.
# Extensiones: config por volumen, capitulos con nombre, definiciones "N)"
# de Vols III-IV como clausulas propias (id <capitulo>.dNNN).
import json, re, sys
from pathlib import Path
from pypdf import PdfReader

CONFIG = {
 2: {"pdf": "MIVHED-Instalaciones-Hidrosanitarias-en-Edificaciones-Vol-II.pdf",
     "sigla": "DIHE", "nombre_vol": "Instalaciones Hidrosanitarias en Edificaciones",
     "body_start": 24, "defs": False,
     "titulos": {1: "Consideraciones Generales",
                 2: "Abastecimiento y Distribución de Agua en Edificios",
                 3: "Drenaje Pluvial", 4: "Drenaje Sanitario",
                 5: "Aparatos, Grifos y Accesorios Sanitarios",
                 6: "Disposición Individual de Aguas Residuales",
                 7: "Sistemas de Proyectos Residenciales Tipo Urbanización",
                 8: "Disposiciones Finales"}},
 3: {"pdf": "MIVHED-Instalaciones-Electricas-en-Edificaciones-Vol-III.pdf",
     "sigla": "IEL", "nombre_vol": "Instalaciones Eléctricas en Edificaciones",
     "body_start": 27, "defs": True,
     "titulos": {1: "Electricidad"}},
 4: {"pdf": "MIVHED-Recomendaciones-para-Instalaciones-Mecanicas-en-Edificaciones-Vol-IV.pdf",
     "sigla": "", "nombre_vol": "Recomendaciones para Instalaciones Mecánicas en Edificaciones",
     "body_start": 28, "defs": True, "anchor": "cap",
     "titulos": {1: "Definiciones", 2: "Normativa General", 3: "Ventilación",
                 4: "Sistemas de Escape", 5: "Sistemas de Conductos",
                 6: "Calderas, Calentadores de Agua y Recipientes a Presión",
                 7: "Refrigeración", 8: "Sistemas Solares"}},
 5: {"pdf": "MIVHED-Diseno-Arquitectonico-en-Edificaciones-Vol-V.pdf",
     "sigla": "", "nombre_vol": "Diseño Arquitectónico en Edificaciones",
     "body_start": 2, "defs": False,
     "titulos": {1: "Espacios Mínimos en Viviendas Urbanas",
                 2: "Medios de Circulación Vertical en Edificaciones",
                 3: "Diseño de Estacionamiento Vehicular en Edificaciones",
                 4: "Ventilación Natural en Edificaciones",
                 5: "Seguridad y Protección contra Incendios",
                 6: "Proyectar sin Barreras Arquitectónicas"}},
}

RE_TIT = re.compile(r"T[IÍ]TULO\s*(\d+)\s*[.:]?\s*\n?\s*([A-ZÁÉÍÓÚÑ][^\n]{0,80})?")

def norm(s):
    import unicodedata
    s = unicodedata.normalize("NFD", s or "")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").upper()

RE_CLAUSULA = re.compile(r"(?:^|\n)\s*(\d{1,2}(?:\.\d{1,3}){1,4})\.?\s+(?=[A-ZÁÉÍÓÚÑ¿(])")
RE_DEF = re.compile(r"(?:^|\n)\s*(\d{1,3})\)\s+(?=[A-ZÁÉÍÓÚÑ])")
RE_CAP = re.compile(r"CAP[IÍ]TULO\s+(\d{1,2}\.\d{1,2})\s*[.:]?\s*([A-ZÁÉÍÓÚÑ][^\n]{0,90})?")
RE_TABLA = re.compile(r"\bTabla\s+(\d+[A-Za-z]?)", re.IGNORECASE)

REFS_EXTERNAS = [
    (re.compile(r"\bACI\s*318(?:-\d+)?"), "ACI 318"),
    (re.compile(r"\bASCE(?:/SEI)?\s*7(?:-\d+)?"), "ASCE/SEI 7"),
    (re.compile(r"\bASTM\s*[A-Z]?\s*\d*"), "ASTM"),
    (re.compile(r"\bAWS\s*D?\d*\.?\d*"), "AWS"),
    (re.compile(r"\bASHRAE\b"), "ASHRAE"),
    (re.compile(r"\bNFPA\s*\d*"), "NFPA"),
    (re.compile(r"\bNEC\b"), "NEC"),
    (re.compile(r"\bUL\s*\d+"), "UL"),
    (re.compile(r"\bSMACNA\b"), "SMACNA"),
    (re.compile(r"\bNAIMA\b"), "NAIMA"),
    (re.compile(r"\bANSI\b"), "ANSI"),
    (re.compile(r"\bISO\s*\d+"), "ISO"),
    (re.compile(r"\bAWWA\b"), "AWWA"),
]

def tiene_glifos_matematicos(t):
    return any(0x1D400 <= ord(c) <= 0x1D7FF for c in t)

def es_pagina_indice(t):
    lineas = [l for l in t.split("\n") if l.strip()]
    if len(lineas) < 6: return False
    con_leader = sum(1 for l in lineas if re.search(r"\.{5,}", l) or re.search(r"\t+\d{1,3}\s*$", l))
    return con_leader / len(lineas) > 0.35

def limpiar_pagina(t, sigla):
    if es_pagina_indice(t):
        return ""
    t = re.sub(r"CÓDIGO DE CONSTRUC?CIÓN DE LA REPÚBLICA DOMINICANA\s*", "", t)
    t = re.sub(r"\bCCRD\b\s*", "", t)
    t = re.sub(r"\bCDCRD\b\s*", "", t)
    t = re.sub(r"\bV-T\d+\b\s*", "", t)
    if sigla:
        t = re.sub(rf"\b{sigla}\b\s*", "", t)
    t = re.sub(r"(?:^|\n)[ \t]*\d{1,3}[ \t]*(?=\n|$)", "\n", t)  # folios sueltos
    return t

def refs_de(texto):
    out = set()
    for rx, canon in REFS_EXTERNAS:
        if rx.search(texto):
            out.add(canon)
    return sorted(out)

def parsear_volumen(vol, cfg, dir_pdfs):
    r = PdfReader(str(dir_pdfs / cfg["pdf"]))
    paginas = [limpiar_pagina(p.extract_text() or "", cfg["sigla"]) for p in r.pages]
    body0 = cfg["body_start"] - 1
    full, offsets = "", []
    for i in range(body0, len(paginas)):
        offsets.append((len(full), i + 1))
        full += paginas[i] + "\n"

    def pagina_de(off):
        pg = offsets[0][1]
        for o, p in offsets:
            if o <= off: pg = p
            else: break
        return pg

    # anclas posicionales de titulo
    anchors = []  # (offset, titulo_num)
    if len(cfg["titulos"]) > 1:
        if cfg.get("anchor") == "cap":
            visto, last_off = set(), -1
            for m in RE_CAP.finditer(full):
                tn = int(m.group(1).split(".")[0])
                if tn in cfg["titulos"] and tn not in visto and m.start() > last_off:
                    visto.add(tn); last_off = m.start()
                    anchors.append((m.start(), tn))
        else:
            for m in RE_TIT.finditer(full):
                tn = int(m.group(1))
                nom = norm(m.group(2))
                if tn in cfg["titulos"] and nom and norm(cfg["titulos"][tn])[:12] in nom[:40] or                    tn in cfg["titulos"] and nom[:12] == norm(cfg["titulos"][tn])[:12]:
                    if not any(a[1] == tn for a in anchors):
                        anchors.append((m.start(), tn))
        anchors.sort()

    def titulo_pos(off):
        if not anchors:
            return next(iter(cfg["titulos"]))
        t = anchors[0][1]
        for o, tn in anchors:
            if o <= off: t = tn
            else: break
        return t

    # eventos: clausulas, defs, capitulos
    eventos = []
    for m in RE_CLAUSULA.finditer(full):
        eventos.append(("cl", m.group(1), m.start(), m.end()))
    if cfg["defs"]:
        for m in RE_DEF.finditer(full):
            eventos.append(("def", m.group(1), m.start(), m.end()))
    caps = {}
    for m in RE_CAP.finditer(full):
        nom = (m.group(2) or "").strip()
        nom = re.sub(r"\.{3,}.*$", "", nom).strip().rstrip(".").strip()
        nom = re.sub(r"\s+\d{1,3}$", "", nom)
        eventos.append(("cap", m.group(1), m.start(), m.end()))
        caps.setdefault((m.start(), m.group(1)), nom)
    eventos.sort(key=lambda e: e[2])
    def _digitfrac(s):
        toks = s.split()
        if not toks: return 1.0
        num = sum(1 for w in toks if re.fullmatch(r"[\d.,x×%-]+", w))
        return num / len(toks)
    filtrados = []
    for j, ev in enumerate(eventos):
        tipo, val, ini, fin_m = ev
        if tipo == "cl" and re.fullmatch(r"\d{1,2}\.\d{2}", val) and val.endswith("0"):
            fin = eventos[j + 1][2] if j + 1 < len(eventos) else len(full)
            cuerpo = full[fin_m:fin]
            if len(cuerpo) < 150 and _digitfrac(cuerpo) > 0.25:
                continue
        filtrados.append(ev)
    eventos = filtrados

    clausulas, rechazadas, cap_ctx = [], 0, None
    huerfano = eventos[0][2] if eventos else len(full)
    for j, ev in enumerate(eventos):
        tipo, val, ini, fin_m = ev
        fin = eventos[j + 1][2] if j + 1 < len(eventos) else len(full)
        if tipo == "cap":
            cap_ctx = val
            continue
        cuerpo = full[fin_m:fin].strip()
        tnum = titulo_pos(ini)
        if tipo == "cl":
            cid = val
            pref = int(cid.split(".")[0])
            if pref not in cfg["titulos"] and pref != tnum:
                rechazadas += 1
                continue
            cap = ".".join(cid.split(".")[:2])
            cap_ctx = cap
            conflicto = (pref != tnum)
        else:  # def
            cap = cap_ctx or f"{tnum}.0"
            cid = f"{cap}.d{int(val):03d}"
            conflicto = False
        enc_m = re.match(r"([A-ZÁÉÍÓÚÑ0-9][^.\n]{0,120})[.:]", cuerpo)
        encabezado = enc_m.group(1).strip() if enc_m else ""
        p_ini, p_fin = pagina_de(ini), pagina_de(max(ini, fin - 1))
        clausulas.append({
            "id": cid, "titulo_num": tnum, "capitulo": cap,
            "encabezado": encabezado, "texto": cuerpo,
            "paginas": list(range(p_ini, p_fin + 1)),
            "flags": {"formula": tiene_glifos_matematicos(cuerpo),
                      "tabla": bool(RE_TABLA.search(cuerpo)),
                      "vision_ok": False},
            "refs": {"externas": refs_de(cuerpo)},
            "tablas": [], "formulas": [], "volumen": vol,
            "num_conflicto": conflicto,
        })
    caps_por_t = {}
    for (off, cnum), nom in sorted(caps.items()):
        tp = titulo_pos(off)
        if nom and cnum not in caps_por_t.setdefault(tp, {}):
            caps_por_t[tp][cnum] = nom
    return clausulas, caps_por_t, len(r.pages), rechazadas, huerfano

def main(dir_pdfs, dir_salida):
    dir_pdfs, dir_salida = Path(dir_pdfs), Path(dir_salida)
    for vol, cfg in CONFIG.items():
        cls, caps, npag, rech, huerf, = parsear_volumen(vol, cfg, dir_pdfs)
        por_t = {}
        for c in cls:
            por_t.setdefault(c["titulo_num"], []).append(c)
        vdir = dir_salida / f"vol-{vol}"
        vdir.mkdir(parents=True, exist_ok=True)
        print(f"VOL {vol}: {npag} pp, {len(cls)} clausulas, {rech} rechazadas, "
              f"{huerf} chars huerfanos pre-primer-evento, {len(caps)} capitulos con nombre")
        for tnum in sorted(por_t):
            u, vistos = [], set()
            for c in por_t[tnum]:
                k = (c["id"], c["paginas"][0])
                if k not in vistos:
                    vistos.add(k); u.append(c)
            # regresiones de secuencia (ids dotted en orden de documento)
            def key(c):
                try: return [int(x) for x in c["id"].split(".") if x.isdigit()]
                except: return []
            regr = sum(1 for a, b in zip(u, u[1:])
                       if key(a) and key(b) and key(b) < key(a))
            ncf = sum(1 for c in u if c.get("num_conflicto"))
            doc = {"volumen": vol, "sigla": cfg["sigla"] or None,
                   "nombre_volumen": cfg["nombre_vol"],
                   "titulo": tnum, "nombre": cfg["titulos"][tnum],
                   "fuente_pdf": cfg["pdf"],
                   "version_codigo": None,
                   "nota_version": "Edición MIVHED sin fecha impresa; volumen complementario del CCRD/CDCRD.",
                   "capitulos": dict(sorted(caps.get(tnum, {}).items())),
                   "clausulas": u}
            (vdir / f"T{tnum:02d}.json").write_text(
                json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
            nf = sum(1 for c in u if c["flags"]["formula"])
            nt = sum(1 for c in u if c["flags"]["tabla"])
            nd = sum(1 for c in u if ".d" in c["id"])
            print(f"  T{tnum:02d} {cfg['titulos'][tnum][:45]:45s} "
                  f"{len(u):4d} cl ({nd:3d} defs) formula:{nf:3d} tabla:{nt:3d} regr:{regr} conflictos:{ncf}")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
