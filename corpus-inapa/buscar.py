"""Busqueda con procedencia sobre el corpus INAPA y construccion de referencias.

Dos clases de referencia, que nunca se mezclan:

- `norma`: texto del reglamento, con codigo, version, fecha, titulo/capitulo/seccion
  vigentes, pagina impresa, pagina PDF, hash del texto y fuente. Solo puede
  construirse a partir de una pagina que exista en el corpus.
- `hipotesis`: supuesto hidraulico o de proyecto (caudal adoptado, rugosidad, nivel
  de agua...). Lleva enunciado, justificacion y fuente, y `normativa=False`.

Uso CLI:
    python buscar.py <corpus.json> "velocidad minima" [--limite 5] [--titulo II] [--capitulo V]
    python buscar.py <corpus.json> impresa:60
    python buscar.py <corpus.json> pdf:61
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from pathlib import Path

MAX_TEXTO = 2500


def cargar(ruta) -> dict:
    doc = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if doc.get("esquema", "").split("/")[0] != "corpus-inapa":
        raise ValueError("el archivo no es un corpus-inapa")
    return doc


def _pagina_por(doc: dict, campo: str, valor: int):
    for p in doc["paginas"]:
        if p.get(campo) == valor:
            return p
    return None


def cita(doc: dict, pagina: dict) -> str:
    """Cita textual completa: documento, edicion, estructura vigente, paginas y fuente."""
    partes = ["%s, %s" % (doc.get("organismo", "INAPA"), doc.get("documento") or "documento sin nombre")]
    edicion = ", ".join(x for x in (doc.get("codigo"), "version " + doc["version"] if doc.get("version") else None,
                                    doc.get("fecha_emision")) if x)
    if edicion:
        partes[0] += " (%s)" % edicion
    est = []
    if pagina.get("titulo"):
        est.append("Titulo %s %s" % (pagina["titulo"]["num"], pagina["titulo"]["nombre"]))
    if pagina.get("capitulo"):
        est.append("Cap. %s %s" % (pagina["capitulo"]["num"], pagina["capitulo"]["nombre"]))
    if pagina.get("seccion"):
        est.append("seccion %s %s" % (pagina["seccion"]["num"], pagina["seccion"]["nombre"]))
    if est:
        partes.append(", ".join(est))
    pi = pagina.get("pagina_impresa")
    partes.append("pag. impresa %s (PDF %s)" % (pi if pi is not None else "sin numero", pagina["pagina_pdf"]))
    if doc.get("fuente_oficial"):
        partes.append("Fuente: " + doc["fuente_oficial"])
    if not doc.get("revision_humana", False):
        partes.append("Extraccion OCR sin revision humana")
    return ". ".join(partes) + "."


def referencia_norma(doc: dict, pagina_impresa: int = None, pagina_pdf: int = None, fragmento: str = "") -> dict:
    """Referencia clase `norma` ligada a una pagina real del corpus. Falla si no existe."""
    if pagina_impresa is None and pagina_pdf is None:
        raise ValueError("indique pagina_impresa o pagina_pdf")
    pagina = (_pagina_por(doc, "pagina_impresa", pagina_impresa) if pagina_impresa is not None
              else _pagina_por(doc, "pagina_pdf", pagina_pdf))
    if pagina is None:
        raise LookupError("la pagina no existe en el corpus; no se cita lo que no se encontro")
    if fragmento and _normalizar(fragmento) not in _normalizar(pagina["texto"]):
        raise LookupError("el fragmento citado no aparece en el texto de esa pagina")
    return {
        "clase": "norma", "normativa": True,
        "documento": doc.get("documento"), "codigo": doc.get("codigo"), "version": doc.get("version"),
        "fecha_emision": doc.get("fecha_emision"),
        "titulo": pagina.get("titulo"), "capitulo": pagina.get("capitulo"), "seccion": pagina.get("seccion"),
        "pagina_impresa": pagina.get("pagina_impresa"), "pagina_pdf": pagina["pagina_pdf"],
        "fragmento": fragmento, "sha256_texto": pagina["sha256_texto"],
        "fuente_oficial": doc.get("fuente_oficial"), "sha256_pdf": doc.get("sha256_pdf"),
        "revision_humana": doc.get("revision_humana", False),
        "cita": cita(doc, pagina),
    }


def referencia_hipotesis(enunciado: str, justificacion: str, fuente: str = None,
                         unidades: str = None) -> dict:
    """Referencia clase `hipotesis`: nunca es norma, aunque la fuente sea un reglamento."""
    if not enunciado or not enunciado.strip():
        raise ValueError("una hipotesis necesita enunciado")
    if not justificacion or not justificacion.strip():
        raise ValueError("una hipotesis necesita justificacion explicita")
    return {"clase": "hipotesis", "normativa": False, "enunciado": enunciado.strip(),
            "justificacion": justificacion.strip(), "fuente": fuente, "unidades": unidades}


def validar_referencias(refs: list) -> dict:
    """Comprueba que cada referencia este completa segun su clase. Devuelve conteos y errores."""
    errores = []
    conteo = {"norma": 0, "hipotesis": 0}
    for i, r in enumerate(refs):
        clase = r.get("clase")
        if clase == "norma":
            faltan = [k for k in ("codigo", "pagina_pdf", "fuente_oficial", "sha256_texto", "cita") if not r.get(k)]
            if r.get("normativa") is not True:
                faltan.append("normativa=True")
            if faltan:
                errores.append({"indice": i, "clase": clase, "faltan": faltan})
        elif clase == "hipotesis":
            faltan = [k for k in ("enunciado", "justificacion") if not r.get(k)]
            if r.get("normativa") is not False:
                faltan.append("normativa=False")
            if faltan:
                errores.append({"indice": i, "clase": clase, "faltan": faltan})
        else:
            errores.append({"indice": i, "clase": clase, "faltan": ["clase norma|hipotesis"]})
            continue
        conteo[clase] += 1
    return {"ok": not errores, "conteo": conteo, "errores": errores}


def _normalizar(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def _romano(valor: str) -> str:
    return valor.strip().upper()


def buscar(query: str, doc: dict, limite: int = 5, titulo: str = None, capitulo: str = None) -> dict:
    """Busca por terminos (FTS5, todos los terminos, orden bm25) o por pagina directa.

    `impresa:N` o `pdf:N` devuelven esa pagina. Los filtros `titulo`/`capitulo` son
    numeros romanos de la estructura vigente de cada pagina.
    """
    q = (query or "").strip()
    if not q or len(q) > 500:
        raise ValueError("La consulta debe tener de 1 a 500 caracteres.")
    if not 1 <= limite <= 50:
        raise ValueError("limite 1..50")
    paginas = doc["paginas"]
    if titulo:
        paginas = [p for p in paginas if p.get("titulo") and p["titulo"]["num"] == _romano(titulo)]
    if capitulo:
        paginas = [p for p in paginas if p.get("capitulo") and p["capitulo"]["num"] == _romano(capitulo)]

    m = re.fullmatch(r"(impresa|pdf):(\d+)", q, flags=re.IGNORECASE)
    if m:
        campo = "pagina_impresa" if m.group(1).lower() == "impresa" else "pagina_pdf"
        hallazgos = [p for p in paginas if p.get(campo) == int(m.group(2))][:limite]
        fragmentos = {p["pagina_pdf"]: p["texto"][:300] for p in hallazgos}
    else:
        terminos = re.findall(r"\w+", q, flags=re.UNICODE)
        if not terminos or len(terminos) > 30:
            raise ValueError("La consulta debe contener entre 1 y 30 terminos.")
        expr = " AND ".join('"' + t.replace('"', '""') + '"' for t in terminos)
        with sqlite3.connect(":memory:") as db:
            db.execute("CREATE VIRTUAL TABLE c USING fts5(texto, tokenize='unicode61 remove_diacritics 2')")
            db.executemany("INSERT INTO c(rowid, texto) VALUES (?, ?)",
                           ((i + 1, p["texto"]) for i, p in enumerate(paginas)))
            filas = db.execute(
                "SELECT rowid, snippet(c, 0, '[', ']', ' ... ', 24) FROM c WHERE c MATCH ? "
                "ORDER BY bm25(c) LIMIT ?", (expr, limite)).fetchall()
        hallazgos = [paginas[i - 1] for i, _ in filas]
        fragmentos = {paginas[i - 1]["pagina_pdf"]: s for i, s in filas}

    resultados = []
    for p in hallazgos:
        resultados.append({
            "clase": "norma",
            "pagina_pdf": p["pagina_pdf"], "pagina_impresa": p.get("pagina_impresa"),
            "titulo": p.get("titulo"), "capitulo": p.get("capitulo"), "seccion": p.get("seccion"),
            "fragmento": fragmentos.get(p["pagina_pdf"], ""),
            "texto": p["texto"][:MAX_TEXTO], "texto_truncado": len(p["texto"]) > MAX_TEXTO,
            "sha256_texto": p["sha256_texto"],
            "cita": cita(doc, p),
        })
    return {
        "query": q, "documento": doc.get("documento"), "codigo": doc.get("codigo"),
        "version": doc.get("version"), "fecha_emision": doc.get("fecha_emision"),
        "paginas_indexadas": len(paginas), "resultados": resultados,
        "alcance": doc.get("alcance"),
        "nota": "Resultados clase norma: texto del reglamento. Los supuestos del proyecto son "
                "clase hipotesis y se construyen con referencia_hipotesis(), nunca desde aqui.",
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("corpus")
    ap.add_argument("query")
    ap.add_argument("--limite", type=int, default=5)
    ap.add_argument("--titulo")
    ap.add_argument("--capitulo")
    ap.add_argument("--solo-citas", action="store_true")
    a = ap.parse_args(argv)
    doc = cargar(a.corpus)
    res = buscar(a.query, doc, a.limite, a.titulo, a.capitulo)
    if a.solo_citas:
        for r in res["resultados"]:
            print(r["cita"])
            print("   " + r["fragmento"].replace("\n", " "))
    else:
        print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
