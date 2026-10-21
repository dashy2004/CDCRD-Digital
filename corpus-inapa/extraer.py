"""Extraccion del Reglamento Tecnico INAPA (DIG-PO-001) a un corpus JSON con procedencia.

Unidad de corpus: la PAGINA. Cada pagina conserva su numero PDF, su numero impreso
(leido del encabezado de esa misma pagina, nunca inferido por desplazamiento), el
total impreso que declara ese encabezado, y la estructura vigente (titulo, capitulo,
seccion numerada) arrastrada desde la ultima cabecera detectada.

Uso:
    python extraer.py <reglamento.pdf> <carpeta_salida> [--fuente-oficial URL]

Requiere `pdftotext` (poppler) en el PATH. La extraccion es OCR del PDF: el campo
`revision_humana` queda en false hasta que alguien coteje el texto contra el PDF.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

VERSION_EXTRACTOR = "0.1.0"
CLASE = "norma"
FUENTE_OFICIAL_DEFECTO = (
    "https://inapa.gob.do/wp-content/uploads/2024/11/"
    "ReglamentoTecnicoParaDisenoDeObrasEIstalacionesHidro.pdf"
)

_RE_PAGINA = re.compile(r"P[aá]gina\s+(\d+)\s+de\s+(\d+)", re.IGNORECASE)
_RE_CODIGO = re.compile(r"C[oó]digo:\s*([A-Z]{2,4}\s*-?\s*[A-Z]{2}-\d{3})", re.IGNORECASE)
_RE_VERSION = re.compile(r"Versi[oó]n:\s*(\d+)", re.IGNORECASE)
_RE_FECHA = re.compile(r"\b(\d{1,2})-([a-záéíóú]+)-(\d{4})\b", re.IGNORECASE)
_MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
          "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
          "noviembre": 11, "diciembre": 12}

# Lineas del encabezado repetido en cada pagina (OCR con variantes de guion y espacios).
_RE_LINEAS_ENCABEZADO = [
    re.compile(r"^\s*REGLAMENTO\s+TECNICO\s+PARA\s+DISE", re.IGNORECASE),
    re.compile(r"^\s*INSTALACIONES\s+HIDRO\s*[-–]\s*SANITARIO", re.IGNORECASE),
    re.compile(r"^\s*[AÁ]rea:\s*Direcci", re.IGNORECASE),
    re.compile(r"^\s*Fecha\s+de\s+emisi", re.IGNORECASE),
    _RE_CODIGO, _RE_VERSION, _RE_PAGINA,
    re.compile(r"^\s*\d{1,2}-[a-záéíóú]+-\d{4}\s*$", re.IGNORECASE),
]

# Cabeceras estructurales. El OCR a veces separa letras: "C AP I T U L O I".
_RE_TITULO = re.compile(r"^\s*T\s*[IÍ]\s*T\s*U\s*L\s*O\s+([IVXLC]+)\s*\.*\s*$", re.IGNORECASE)
_RE_CAPITULO = re.compile(r"^\s*C\s*A\s*P\s*[IÍ]\s*T\s*U\s*L\s*O\s+([IVXLC]+)\s*\.*\s*$", re.IGNORECASE)
_RE_SECCION = re.compile(r"^\s*(\d{1,2}(?:\.\d{1,2}){1,3})\.?\s+([A-ZÁÉÍÓÚa-záéíóú][^\n]{2,120})$")
_RE_PUNTOS_INDICE = re.compile(r"\.{4,}|(?:\s\.){4,}")


def parsear_encabezado(texto_pagina: str) -> dict:
    """Lee codigo, version, fecha y 'Pagina N de M' del encabezado de UNA pagina."""
    out = {"codigo": None, "version": None, "fecha_emision": None,
           "pagina_impresa": None, "total_impreso": None}
    m = _RE_PAGINA.search(texto_pagina)
    if m:
        out["pagina_impresa"] = int(m.group(1))
        out["total_impreso"] = int(m.group(2))
    m = _RE_CODIGO.search(texto_pagina)
    if m:
        out["codigo"] = re.sub(r"\s+", "", m.group(1)).upper()
    m = _RE_VERSION.search(texto_pagina)
    if m:
        out["version"] = m.group(1).zfill(2)
    m = _RE_FECHA.search(texto_pagina)
    if m and m.group(2).lower() in _MESES:
        out["fecha_emision"] = "%s-%02d-%02d" % (m.group(3), _MESES[m.group(2).lower()], int(m.group(1)))
    return out


def quitar_encabezado(texto_pagina: str) -> str:
    """Elimina las lineas del encabezado repetido; conserva el cuerpo sin cambiar su orden."""
    cuerpo = []
    for linea in texto_pagina.splitlines():
        if any(r.search(linea) for r in _RE_LINEAS_ENCABEZADO):
            continue
        cuerpo.append(linea.rstrip())
    # colapsar lineas vacias iniciales/finales y triples
    texto = "\n".join(cuerpo)
    texto = re.sub(r"\n{3,}", "\n\n", texto).strip("\n")
    return texto


def _siguiente_no_vacia(lineas: list, i: int) -> str:
    for j in range(i + 1, min(i + 4, len(lineas))):
        if lineas[j].strip():
            return lineas[j].strip()
    return ""


def detectar_estructura(cuerpo: str, estado: dict) -> list:
    """Actualiza `estado` (titulo/capitulo/seccion vigentes) con las cabeceras de esta pagina.

    Devuelve la lista de cabeceras detectadas. Las lineas de indice (con puntos de
    relleno) se ignoran para no tomar el indice de contenido como cuerpo normativo.
    """
    lineas = cuerpo.splitlines()
    encontradas = []
    for i, linea in enumerate(lineas):
        if _RE_PUNTOS_INDICE.search(linea):
            continue
        m = _RE_TITULO.match(linea)
        if m:
            nombre = _siguiente_no_vacia(lineas, i)
            estado["titulo"] = {"num": m.group(1).upper(), "nombre": nombre}
            estado["capitulo"] = None
            estado["seccion"] = None
            encontradas.append({"tipo": "titulo", "num": m.group(1).upper(), "nombre": nombre})
            continue
        m = _RE_CAPITULO.match(linea)
        if m:
            nombre = _siguiente_no_vacia(lineas, i)
            estado["capitulo"] = {"num": m.group(1).upper(), "nombre": nombre}
            estado["seccion"] = None
            encontradas.append({"tipo": "capitulo", "num": m.group(1).upper(), "nombre": nombre})
            continue
        m = _RE_SECCION.match(linea)
        if m:
            estado["seccion"] = {"num": m.group(1), "nombre": m.group(2).strip()}
            encontradas.append({"tipo": "seccion", "num": m.group(1), "nombre": m.group(2).strip()})
    return encontradas


def construir_corpus(paginas_texto: list, meta: dict) -> dict:
    """Arma el corpus a partir del texto por pagina (ya separado) y metadatos del documento.

    Separado de pdftotext para poder probarlo con paginas sinteticas.
    """
    estado = {"titulo": None, "capitulo": None, "seccion": None}
    paginas = []
    codigos, versiones, fechas = set(), set(), set()
    for idx, texto in enumerate(paginas_texto, start=1):
        enc = parsear_encabezado(texto)
        cuerpo = quitar_encabezado(texto)
        cabeceras = detectar_estructura(cuerpo, estado)
        for k, s in (("codigo", codigos), ("version", versiones), ("fecha_emision", fechas)):
            if enc[k]:
                s.add(enc[k])
        paginas.append({
            "pagina_pdf": idx,
            "pagina_impresa": enc["pagina_impresa"],
            "total_impreso": enc["total_impreso"],
            "titulo": dict(estado["titulo"]) if estado["titulo"] else None,
            "capitulo": dict(estado["capitulo"]) if estado["capitulo"] else None,
            "seccion": dict(estado["seccion"]) if estado["seccion"] else None,
            "cabeceras": cabeceras,
            "texto": cuerpo,
            "caracteres": len(cuerpo),
            "sha256_texto": hashlib.sha256(cuerpo.encode("utf-8")).hexdigest(),
        })
    doc = {
        "esquema": "corpus-inapa/0.1",
        "clase": CLASE,
        "documento": meta.get("documento"),
        "codigo": meta.get("codigo") or (sorted(codigos)[0] if len(codigos) == 1 else None),
        "codigos_detectados": sorted(codigos),
        "version": meta.get("version") or (sorted(versiones)[0] if len(versiones) == 1 else None),
        "fecha_emision": meta.get("fecha_emision") or (sorted(fechas)[0] if len(fechas) == 1 else None),
        "organismo": meta.get("organismo", "INAPA"),
        "fuente_oficial": meta.get("fuente_oficial"),
        "fuente_local": meta.get("fuente_local"),
        "sha256_pdf": meta.get("sha256_pdf"),
        "paginas_pdf": len(paginas),
        "totales_impresos_declarados": sorted({p["total_impreso"] for p in paginas if p["total_impreso"]}),
        "paginas_sin_numero_impreso": [p["pagina_pdf"] for p in paginas if p["pagina_impresa"] is None],
        "extractor": meta.get("extractor"),
        "extractor_version": VERSION_EXTRACTOR,
        "fecha_extraccion": meta.get("fecha_extraccion"),
        "revision_humana": False,
        "alcance": ("Texto OCR del reglamento, unidad = pagina. La cita obligatoria es por pagina "
                    "impresa y PDF con la estructura vigente; no sustituye la lectura del PDF ni "
                    "determina por si sola la aplicabilidad del reglamento a un proyecto."),
        "paginas": paginas,
    }
    return doc


def _pdftotext(pdf: Path) -> list:
    exe = shutil.which("pdftotext")
    if not exe:
        raise RuntimeError("pdftotext no esta en el PATH (instalar poppler-utils)")
    res = subprocess.run([exe, "-layout", "-enc", "UTF-8", str(pdf), "-"],
                         capture_output=True, check=True)
    texto = res.stdout.decode("utf-8", errors="replace")
    paginas = texto.split("\f")
    if paginas and not paginas[-1].strip():
        paginas.pop()
    return paginas


def _version_pdftotext() -> str:
    exe = shutil.which("pdftotext")
    if not exe:
        return "pdftotext (no disponible)"
    res = subprocess.run([exe, "-v"], capture_output=True)
    linea = (res.stderr or res.stdout).decode("utf-8", errors="replace").splitlines()
    return linea[0].strip() if linea else "pdftotext"


def extraer(pdf: Path, salida: Path, fuente_oficial: str = FUENTE_OFICIAL_DEFECTO,
            documento: str = "Reglamento Tecnico para Diseno de Obras e Instalaciones Hidro-Sanitario del INAPA") -> Path:
    pdf = Path(pdf)
    if not pdf.is_file():
        raise FileNotFoundError(str(pdf))
    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    paginas = _pdftotext(pdf)
    meta = {
        "documento": documento,
        "fuente_oficial": fuente_oficial,
        "fuente_local": pdf.name,  # solo el nombre: no se publican rutas privadas
        "sha256_pdf": sha,
        "extractor": _version_pdftotext() + " -layout",
        "fecha_extraccion": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ"),
    }
    doc = construir_corpus(paginas, meta)
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    destino = salida / "corpus.json"
    destino.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    resumen = {k: v for k, v in doc.items() if k != "paginas"}
    (salida / "resumen.json").write_text(json.dumps(resumen, ensure_ascii=False, indent=1), encoding="utf-8")
    return destino


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("pdf")
    ap.add_argument("salida")
    ap.add_argument("--fuente-oficial", default=FUENTE_OFICIAL_DEFECTO)
    a = ap.parse_args(argv)
    destino = extraer(Path(a.pdf), Path(a.salida), a.fuente_oficial)
    doc = json.loads(destino.read_text(encoding="utf-8"))
    print(json.dumps({"corpus": str(destino), "codigo": doc["codigo"], "version": doc["version"],
                      "fecha_emision": doc["fecha_emision"], "paginas_pdf": doc["paginas_pdf"],
                      "totales_impresos": doc["totales_impresos_declarados"],
                      "sin_numero_impreso": doc["paginas_sin_numero_impreso"],
                      "sha256_pdf": doc["sha256_pdf"]}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
