"""Genera una memoria de cálculo estructural en Word a partir de data.json y memoria.json.

Uso: python generar.py data.json <referencia.pdf o ""> salida.docx carpeta_tmp carpeta_imagenes memoria.json

- data.json: los números (lo producen los lectores de fuentes; ver README, «Contrato»).
- memoria.json: lo editable (portada, hoja de control, firmas, datos del proyecto, figuras,
  observaciones). Se crea con campos vacíos la primera vez; los campos vacíos se omiten.
- referencia.pdf: solo si data.json viene de una memoria ya emitida y se quieren sus figuras.
"""
import itertools
import json
import math
import os
import re
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pymupdf
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ROW_HEIGHT_RULE, WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

DATA, REF_PDF, OUT, TMP, IMG, CFG_PATH = sys.argv[1:7]
with open(DATA, encoding="utf-8") as _f:
    D = json.load(_f)
for _k in ("sobrecarga", "niveles", "bloques", "avisos"):
    D.setdefault(_k, [])
os.makedirs(TMP, exist_ok=True)

# ------------------------------------------------------------------ contenido editable
CFG_DEFECTO = {
    "_ayuda": "Edite este archivo y vuelva a ejecutar generar.py. Los campos vacíos se omiten; las rutas de imagen vacías dejan un espacio reservado.",
    "portada": {"titulo": "Nombre del proyecto", "subtitulo": "", "documento": "MEMORIA DE CÁLCULOS ESTRUCTURALES",
                "alcance": "", "imagen": "", "logo": "", "lugar_fecha": ""},
    "responsable": {"nombre": "", "credencial": "", "contacto": "", "diseno": ""},
    "control": {"codigo": "", "revision": "A", "fecha": "", "estado": "Borrador para revisión", "origen": "",
                "marca_de_agua": "BORRADOR"},
    "revisiones": [{"rev": "A", "fecha": "", "descripcion": "Emisión para revisión.", "elaboro": ""}],
    "firmas": [{"rol": "Elaboró", "nombre": "", "credencial": "", "imagen": ""},
               {"rol": "Revisó", "nombre": "", "credencial": "", "imagen": ""},
               {"rol": "Responsable del diseño estructural", "nombre": "", "credencial": "", "imagen": ""}],
    "proyecto": [],
    "materiales": [],
    "normas": [],
    "vistas_bloque": {},
    "fundaciones": {"texto": "", "figuras_del_pdf": False, "figuras": []},
    "anexo_figuras": [],
    "observaciones_extra": [],
    "observaciones_omitir": [],
}
if not os.path.exists(CFG_PATH):
    with open(CFG_PATH, "w", encoding="utf-8") as _f:
        json.dump(CFG_DEFECTO, _f, ensure_ascii=False, indent=2)
def mezclar(defecto, dado):
    """Completa `dado` con las claves que falten, también dentro de los diccionarios anidados."""
    if not isinstance(dado, dict):
        return defecto
    for k, v in defecto.items():
        if isinstance(v, dict):
            dado[k] = mezclar(v, dado.get(k))
        elif dado.get(k) is None:
            dado[k] = v
    return dado


with open(CFG_PATH, encoding="utf-8") as _f:
    C = mezclar(CFG_DEFECTO, json.load(_f))

# ------------------------------------------------------------------ identidad visual
F_TXT = "Cambria"            # cuerpo
F_UI = "Segoe UI"            # títulos, tablas, rótulos
F_UIB = "Segoe UI Semibold"
TEAL = RGBColor(0x0F, 0x5C, 0x66)
TEAL_HEX = "0F5C66"
TEAL_CLARO = RGBColor(0x1A, 0x7F, 0x8E)
TINTA = RGBColor(0x1F, 0x29, 0x33)
GRIS = RGBColor(0x5F, 0x6B, 0x76)
FILL_HEAD = "EAF2F3"
FILL_WARN = "FBE9E7"
LINEA = "C9D3D6"
ANCHO = 17.2
G = 9.80665
OBS = []
ESTADO = {"cap": "", "tab": 0, "fig": 0}
REF = bool(D.get("referencia_pdf"))   # los datos salen de una memoria en PDF: se citan sus páginas
PDF_OK = bool(REF_PDF) and os.path.isfile(REF_PDF)
FALTAN_IMG = []

doc = Document()


def img(nombre):
    """Ruta de una imagen indicada en memoria.json; si se indicó y no existe, queda anotada."""
    if not nombre:
        return None
    for p in (nombre, os.path.join(IMG, nombre), os.path.join(os.path.dirname(CFG_PATH), nombre)):
        if os.path.isfile(p):
            return p
    if nombre not in FALTAN_IMG:
        FALTAN_IMG.append(nombre)
    return None


def fmt(x, nd=2, dash="—"):
    if x is None:
        return dash
    if isinstance(x, str):
        return x
    return f"{x:,.{nd}f}"


def fuente(run, nombre, size=None, bold=None, italic=None, color=None):
    run.font.name = nombre
    rPr = run._r.get_or_add_rPr()
    rf = rPr.find(qn("w:rFonts"))
    if rf is None:
        rf = OxmlElement("w:rFonts")
        rPr.append(rf)
    for a in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rf.set(qn(a), nombre)
    if size is not None:
        run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if italic is not None:
        run.italic = italic
    if color is not None:
        run.font.color.rgb = color
    return run


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def borde_celda(cell, **lados):
    """lados: top/bottom/left/right = (sz, color[, estilo]) o None para quitar."""
    tcPr = cell._tc.get_or_add_tcPr()
    b = tcPr.find(qn("w:tcBorders"))
    if b is None:
        b = OxmlElement("w:tcBorders")
        tcPr.append(b)
    for lado, v in lados.items():
        e = OxmlElement("w:" + lado)
        if v is None:
            e.set(qn("w:val"), "nil")
        else:
            e.set(qn("w:val"), v[2] if len(v) > 2 else "single")
            e.set(qn("w:sz"), str(v[0]))
            e.set(qn("w:space"), "0")
            e.set(qn("w:color"), v[1])
        b.append(e)


def bordes_tabla(table, estilo="libro"):
    tblPr = table._tbl.tblPr
    b = OxmlElement("w:tblBorders")
    spec = {
        "libro": {"top": (10, TEAL_HEX), "bottom": (10, TEAL_HEX), "insideH": (2, LINEA), "left": None, "right": None, "insideV": None},
        "nada": {k: None for k in ("top", "bottom", "insideH", "left", "right", "insideV")},
    }[estilo]
    for k in ("top", "left", "bottom", "right", "insideH", "insideV"):
        e = OxmlElement("w:" + k)
        v = spec[k]
        if v is None:
            e.set(qn("w:val"), "nil")
        else:
            e.set(qn("w:val"), "single")
            e.set(qn("w:sz"), str(v[0]))
            e.set(qn("w:space"), "0")
            e.set(qn("w:color"), v[1])
        b.append(e)
    tblPr.append(b)


def margenes_celda(table, top=45, bottom=45, left=70, right=70):
    tblPr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for k, v in (("top", top), ("left", left), ("bottom", bottom), ("right", right)):
        e = OxmlElement("w:" + k)
        e.set(qn("w:w"), str(v))
        e.set(qn("w:type"), "dxa")
        mar.append(e)
    tblPr.append(mar)


def fila_encabezado(row):
    trPr = row._tr.get_or_add_trPr()
    e = OxmlElement("w:tblHeader")
    e.set(qn("w:val"), "true")
    trPr.append(e)


def no_partir(row):
    trPr = row._tr.get_or_add_trPr()
    c = OxmlElement("w:cantSplit")
    c.set(qn("w:val"), "true")
    trPr.append(c)


def set_cell(cell, text, size=8.5, bold=False, align="c", color=None, italic=False, font=F_UI):
    cell.text = ""
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    pf = p.paragraph_format
    pf.space_before = pf.space_after = Pt(0)
    pf.line_spacing = 1.0
    p.alignment = {"c": WD_ALIGN_PARAGRAPH.CENTER, "l": WD_ALIGN_PARAGRAPH.LEFT, "r": WD_ALIGN_PARAGRAPH.RIGHT}[align]
    fuente(p.add_run(str(text)), F_UIB if bold else font, size, None, italic, color if color is not None else TINTA)
    return p


def mantener(table, todas=False):
    filas = table.rows
    limite = len(filas) - 1 if (todas or len(filas) <= 14) else 3
    for ri, row in enumerate(filas):
        no_partir(row)
        if ri < limite:
            for c in row.cells:
                for pp in c.paragraphs:
                    pp.paragraph_format.keep_with_next = True


def tabla(headers, rows, widths=None, aligns=None, size=8.5, warn_rows=(), total_width=ANCHO, titulo=None):
    if titulo:
        tcap(titulo)
    n = len(headers)
    t = doc.add_table(rows=1, cols=n)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    bordes_tabla(t)
    margenes_celda(t)
    if widths is None:
        widths = [total_width / n] * n
    else:
        k = total_width / sum(widths)
        widths = [w * k for w in widths]
    aligns = aligns or ["c"] * n
    for i, hd in enumerate(headers):
        c = t.rows[0].cells[i]
        set_cell(c, hd, size=size, bold=True, color=TEAL, align=aligns[i] if aligns[i] == "l" else "c")
        shade(c, FILL_HEAD)
        borde_celda(c, bottom=(6, TEAL_HEX))
        c.width = Cm(widths[i])
    fila_encabezado(t.rows[0])
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for i, v in enumerate(row):
            set_cell(cells[i], v, size=size, align=aligns[i])
            cells[i].width = Cm(widths[i])
            if ri in warn_rows:
                shade(cells[i], FILL_WARN)
    mantener(t)
    espacio(5)
    return t


def kv(pairs, w1=6.0, w2=11.2, size=9.5):
    t = doc.add_table(rows=0, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    bordes_tabla(t)
    margenes_celda(t, 55, 55, 80, 80)
    for k, v in pairs:
        c = t.add_row().cells
        set_cell(c[0], k, size=size, bold=True, align="l", color=TEAL)
        set_cell(c[1], v, size=size, align="l")
        c[0].width, c[1].width = Cm(w1), Cm(w2)
    mantener(t, todas=True)
    espacio(5)
    return t


def espacio(pt=6):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before = pf.space_after = Pt(0)
    pf.line_spacing = Pt(pt)
    return p


def par(text, size=11, bold=False, italic=False, color=None, align="j", after=6, keep=False, font=F_TXT, before=0):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after, pf.space_before = Pt(after), Pt(before)
    pf.line_spacing = 1.15
    p.alignment = {"c": WD_ALIGN_PARAGRAPH.CENTER, "j": WD_ALIGN_PARAGRAPH.JUSTIFY, "l": WD_ALIGN_PARAGRAPH.LEFT,
                   "r": WD_ALIGN_PARAGRAPH.RIGHT}[align]
    pf.keep_with_next = keep
    fuente(p.add_run(text), font, size, bold, italic, color if color is not None else TINTA)
    return p


def nota(text):
    p = par(text, size=8, italic=True, color=GRIS, after=9, font=F_UI, align="l")
    p.paragraph_format.line_spacing = 1.05
    return p


def _rotulo(tipo, text, arriba):
    clave = "tab" if tipo == "Tabla" else "fig"
    ESTADO[clave] += 1
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_before, pf.space_after = Pt(4 if arriba else 3), Pt(3 if arriba else 10)
    pf.keep_with_next = arriba
    p.alignment = WD_ALIGN_PARAGRAPH.LEFT if arriba else WD_ALIGN_PARAGRAPH.CENTER
    fuente(p.add_run("%s %s.%d" % (tipo, ESTADO["cap"], ESTADO[clave])), F_UIB, 8.5, None, None, TEAL)
    fuente(p.add_run("  " + text), F_UI, 8.5, None, None, TINTA)
    return p


def tcap(text):
    return _rotulo("Tabla", text, True)


def fcap(text):
    return _rotulo("Figura", text, False)


def h(text, level=1, cap=None):
    if level == 1:
        ESTADO["cap"], ESTADO["tab"], ESTADO["fig"] = cap, 0, 0
        ESTADO["h2"], ESTADO["h3"] = None, 0
    elif level == 2:
        m_ = re.match(r"^([A-Z\d]+\.\d+)\s", text)
        ESTADO["h2"], ESTADO["h3"] = (m_.group(1) if m_ else None), 0
    elif level == 3 and ESTADO.get("h2"):
        ESTADO["h3"] += 1
        text = "%s.%d  %s" % (ESTADO["h2"], ESTADO["h3"], text)
    p = doc.add_heading(text, level=level)
    if level == 1:
        p.paragraph_format.page_break_before = True
    return p


def bullets(items, size=11):
    for it in items:
        p = doc.add_paragraph(style="List Bullet")
        pf = p.paragraph_format
        pf.space_after = Pt(4)
        pf.line_spacing = 1.15
        fuente(p.add_run(it), F_TXT, size, None, None, TINTA)


def salto():
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)


def campo(paragraph, instr, size=8):
    r = paragraph.add_run()
    fuente(r, F_UI, size, None, None, GRIS)
    for kind in ("begin", "instr", "separate", "txt", "end"):
        if kind in ("begin", "separate", "end"):
            e = OxmlElement("w:fldChar")
            e.set(qn("w:fldCharType"), kind)
        elif kind == "instr":
            e = OxmlElement("w:instrText")
            e.set(qn("xml:space"), "preserve")
            e.text = instr
        else:
            e = OxmlElement("w:t")
            e.text = "1"
        r._r.append(e)


def borde_parrafo(p, lado="bottom", sz=6, color=TEAL_HEX, space=3):
    pPr = p._p.get_or_add_pPr()
    bd = OxmlElement("w:pBdr")
    e = OxmlElement("w:" + lado)
    for k, v in (("val", "single"), ("sz", str(sz)), ("space", str(space)), ("color", color)):
        e.set(qn("w:" + k), v)
    bd.append(e)
    pPr.append(bd)


def figura(path, ancho_cm, titulo, alto_max=None):
    from PIL import Image
    w, hh = Image.open(path).size
    if alto_max and ancho_cm * hh / w > alto_max:
        ancho_cm = alto_max * w / hh
    doc.add_picture(path, width=Cm(ancho_cm))
    p = doc.paragraphs[-1]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.keep_with_next = True
    p.paragraph_format.space_before = Pt(4)
    fcap(titulo)


def reserva(titulo, alto_cm=8.5):
    """Espacio reservado para una figura que se insertará a mano."""
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    bordes_tabla(t, "nada")
    c = t.rows[0].cells[0]
    c.width = Cm(ANCHO)
    borde_celda(c, top=(6, "9AA7AD", "dashed"), bottom=(6, "9AA7AD", "dashed"), left=(6, "9AA7AD", "dashed"),
                right=(6, "9AA7AD", "dashed"))
    t.rows[0].height = Cm(alto_cm)
    t.rows[0].height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
    p = set_cell(c, "Espacio reservado", size=10, bold=True, color=GRIS)
    r = p.add_run()
    r.add_break()
    fuente(p.add_run("Insertar: " + titulo), F_UI, 9, None, True, GRIS)
    for pp in c.paragraphs:
        pp.paragraph_format.keep_with_next = True
    fcap(titulo)


# ------------------------------------------------------------------ estilos y página
def configurar():
    st = doc.styles["Normal"]
    st.font.name = F_TXT
    st.element.rPr.rFonts.set(qn("w:eastAsia"), F_TXT)
    st.font.size = Pt(11)
    for name, fnt, size, before, after, color in (("Heading 1", F_UIB, 19, 0, 14, TEAL), ("Heading 2", F_UIB, 13, 16, 6, TEAL),
                                                    ("Heading 3", F_UIB, 10.5, 10, 4, TINTA)):
        s = doc.styles[name]
        s.font.name = fnt
        for a in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
            s.element.rPr.rFonts.set(qn(a), fnt)
        s.font.size = Pt(size)
        s.font.bold = False
        s.font.color.rgb = color
        s.paragraph_format.space_before = Pt(before)
        s.paragraph_format.space_after = Pt(after)
        s.paragraph_format.keep_with_next = True
    pPr = doc.styles["Heading 1"].element.get_or_add_pPr()
    bd = OxmlElement("w:pBdr")
    e = OxmlElement("w:bottom")
    for k, v in (("val", "single"), ("sz", "8"), ("space", "6"), ("color", TEAL_HEX)):
        e.set(qn("w:" + k), v)
    bd.append(e)
    pPr.append(bd)
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Cm(21.59), Cm(27.94)
    sec.orientation = WD_ORIENT.PORTRAIT
    sec.left_margin, sec.right_margin = Cm(2.4), Cm(1.99)
    sec.top_margin, sec.bottom_margin = Cm(2.6), Cm(2.2)
    sec.header_distance, sec.footer_distance = Cm(1.0), Cm(1.0)
    sec.different_first_page_header_footer = True
    hp = sec.header.paragraphs[0]
    hp.style = doc.styles["Normal"]          # sin las tabulaciones propias del estilo de encabezado
    sec.footer.paragraphs[0].style = doc.styles["Normal"]
    hp.paragraph_format.tab_stops.add_tab_stop(Cm(ANCHO), WD_TAB_ALIGNMENT.RIGHT)
    logo = img(C["portada"].get("logo"))
    if logo:
        hp.add_run().add_picture(logo, height=Cm(0.95))
    rev = C["control"].get("revision", "")
    fuente(hp.add_run("\t" + " · ".join(x for x in (C["portada"]["titulo"], C["portada"].get("subtitulo")) if x)), F_UIB, 8.5, None, None, TEAL)
    fuente(hp.add_run("   |   Memoria de cálculos estructurales" + ("   |   Rev. %s" % rev if rev else "")), F_UI, 8, None, None, GRIS)
    borde_parrafo(hp, "bottom", 4, LINEA, 4)
    fp = sec.footer.paragraphs[0]
    fp.paragraph_format.tab_stops.add_tab_stop(Cm(ANCHO), WD_TAB_ALIGNMENT.RIGHT)
    borde_parrafo(fp, "top", 4, LINEA, 4)
    fuente(fp.add_run(" · ".join(x for x in (C["responsable"].get("nombre"), C["responsable"].get("credencial")) if x)), F_UI, 8, None, None, GRIS)
    fuente(fp.add_run("\tPágina "), F_UI, 8, None, None, GRIS)
    campo(fp, "PAGE")
    fuente(fp.add_run(" de "), F_UI, 8, None, None, GRIS)
    campo(fp, "NUMPAGES")
    texto = re.sub(r"[\x00-\x1f]", " ", C["control"].get("marca_de_agua") or "").strip()
    if texto:
        marca_de_agua(sec.header.paragraphs[0], texto, 1)
        primera = sec.first_page_header
        marca_de_agua(primera.paragraphs[0], texto, 2)


def marca_de_agua(parrafo, texto, n):
    """Marca de agua de texto en diagonal, igual a la de Diseño > Marca de agua de Word (se quita desde ahí)."""
    from docx.oxml import parse_xml
    from xml.sax.saxutils import quoteattr
    xml = (
        '<w:r xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">'
        '<w:rPr><w:noProof/></w:rPr><w:pict>'
        '<v:shapetype id="_x0000_t136" coordsize="21600,21600" o:spt="136" adj="10800" '
        'path="m@7,l@8,m@5,21600l@6,21600e">'
        '<v:formulas><v:f eqn="sum #0 0 10800"/><v:f eqn="prod #0 2 1"/><v:f eqn="sum 21600 0 @1"/>'
        '<v:f eqn="sum 0 0 @2"/><v:f eqn="sum 21600 0 @3"/><v:f eqn="if @0 @3 0"/><v:f eqn="if @0 21600 @1"/>'
        '<v:f eqn="if @0 0 @2"/><v:f eqn="if @0 @4 21600"/><v:f eqn="mid @5 @6"/><v:f eqn="mid @8 @5"/>'
        '<v:f eqn="mid @7 @8"/><v:f eqn="mid @6 @7"/><v:f eqn="sum @6 0 @5"/></v:formulas>'
        '<v:path textpathok="t" o:connecttype="custom" o:connectlocs="@9,0;@10,10800;@11,21600;@12,10800" '
        'o:connectangles="270,180,90,0"/><v:textpath on="t" fitshape="t"/>'
        '<o:lock v:ext="edit" text="t" shapetype="t"/></v:shapetype>'
        '<v:shape id="PowerPlusWaterMarkObject%d" o:spid="_x0000_s20%d" type="#_x0000_t136" '
        'style="position:absolute;margin-left:0;margin-top:0;width:430pt;height:120pt;rotation:315;z-index:-251656192;'
        'mso-position-horizontal:center;mso-position-horizontal-relative:margin;'
        'mso-position-vertical:center;mso-position-vertical-relative:margin" '
        'o:allowincell="f" fillcolor="#c9d3d6" stroked="f">'
        '<v:fill opacity=".45"/>'
        '<v:textpath style="font-family:&quot;Segoe UI Semibold&quot;;font-size:1pt" string=%s/>'
        '</v:shape></w:pict></w:r>' % (n, n, quoteattr(texto)))
    parrafo._p.append(parse_xml(xml))


# ------------------------------------------------------------------ portada, control, índice
def portada():
    P, R = C["portada"], C["responsable"]
    espacio(12)
    im = img(P.get("imagen"))
    if im:
        doc.add_picture(im, width=Cm(15.5))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        espacio(220)
    espacio(26)
    par(P["titulo"], size=38, color=TEAL_CLARO, align="c", after=0 if P.get("subtitulo") else 14)
    if P.get("subtitulo"):
        par(P["subtitulo"], size=26, color=TEAL_CLARO, align="c", after=14)
    p = par(P["documento"], size=13, color=TINTA, align="c", after=3, font=F_UIB)
    borde_parrafo(p, "top", 6, TEAL_HEX, 10)
    par(P.get("alcance") or " ", size=10.5, color=GRIS, align="c", after=0, font=F_UI)
    espacio(34)
    t = doc.add_table(rows=1, cols=2)
    t.autofit = False
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    bordes_tabla(t, "nada")
    a, b = t.rows[0].cells
    a.width, b.width = Cm(7.0), Cm(ANCHO - 7.0)
    a.vertical_alignment = b.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM
    logo = img(P.get("logo"))
    if logo:
        a.paragraphs[0].add_run().add_picture(logo, width=Cm(4.6))
    p = b.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.line_spacing = 1.2

    def linea(txt, f, s, col, saltos=1):
        fuente(p.add_run(txt), f, s, None, None, col)
        r = p.add_run()
        for _ in range(saltos):
            r.add_break()

    if R.get("nombre"):
        linea("Preparado por", F_UI, 8.5, GRIS)
        linea(R["nombre"], F_UIB, 13, TINTA)
    if R.get("credencial"):
        linea(R["credencial"], F_UI, 10, TINTA)
    if R.get("contacto"):
        linea(R["contacto"], F_UI, 8.5, GRIS, 2)
    if R.get("diseno"):
        fuente(p.add_run("Diseño  "), F_UI, 8.5, None, None, GRIS)
        linea(R["diseno"], F_UIB, 10.5, TINTA, 2)
    fuente(p.add_run(P.get("lugar_fecha") or " "), F_UI, 10, None, None, TINTA)
    salto()


def titulo_suelto(text):
    p = par(text, size=19, color=TEAL, align="l", after=14, font=F_UIB)
    borde_parrafo(p, "bottom", 8, TEAL_HEX, 6)
    return p


def hoja_control():
    K = C["control"]
    titulo_suelto("Hoja de control")
    kv([("Proyecto", " — ".join(x for x in (C["portada"]["titulo"], C["portada"].get("subtitulo")) if x)),
        ("Documento", "Memoria de cálculos estructurales"),
        ("Alcance", C["portada"].get("alcance") or "—"),
        ("Código del documento", K.get("codigo") or "—"),
        ("Revisión / fecha", " · ".join(x for x in (K.get("revision"), K.get("fecha")) if x) or "—"),
        ("Estado", K.get("estado") or "—"),
        ("Origen de los datos", K.get("origen") or "—")])
    par("Registro de revisiones", size=11, color=TEAL, after=4, font=F_UIB, align="l", keep=True, before=8)
    rows = [[r.get("rev", ""), r.get("fecha", ""), r.get("descripcion", ""), r.get("elaboro", "") or "—"] for r in C["revisiones"]]
    rows += [["", "", "", ""]] * 2
    t = doc.add_table(rows=1, cols=4)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    bordes_tabla(t)
    margenes_celda(t, 70, 70, 70, 70)
    ws = [1.6, 3.4, 8.8, 3.4]
    for i, hd in enumerate(["Rev.", "Fecha", "Descripción", "Elaboró"]):
        c = t.rows[0].cells[i]
        set_cell(c, hd, bold=True, color=TEAL, size=9, align="l" if i == 2 else "c")
        shade(c, FILL_HEAD)
        borde_celda(c, bottom=(6, TEAL_HEX))
        c.width = Cm(ws[i])
    for r in rows:
        cs = t.add_row().cells
        for i, v in enumerate(r):
            set_cell(cs[i], v or " ", size=9, align="l" if i == 2 else "c")
            cs[i].width = Cm(ws[i])
    espacio(16)
    firmas = C["firmas"] or []
    if not firmas:
        salto()
        return
    par("Firmas", size=11, color=TEAL, after=4, font=F_UIB, align="l", keep=True)
    n = len(firmas)
    hueco = 0.7
    ancho_f = (ANCHO - hueco * (n - 1)) / n
    t = doc.add_table(rows=2, cols=2 * n - 1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    bordes_tabla(t, "nada")
    margenes_celda(t, 40, 40, 40, 40)
    t.rows[0].height = Cm(2.8)
    t.rows[0].height_rule = WD_ROW_HEIGHT_RULE.EXACTLY
    for j in range(1, 2 * n - 1, 2):
        for row in t.rows:
            row.cells[j].width = Cm(hueco)
            set_cell(row.cells[j], " ", size=6)
    for i, f in enumerate(firmas):
        top, bot = t.rows[0].cells[2 * i], t.rows[1].cells[2 * i]
        top.width = bot.width = Cm(ancho_f)
        pf_ = set_cell(top, " ", size=8)
        top.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.BOTTOM
        firma = img(f.get("imagen"))
        if firma:
            from PIL import Image
            w_, h_ = Image.open(firma).size
            alto = min(2.3, (ancho_f - 0.6) * h_ / w_)
            pf_.runs[0].text = ""
            pf_.add_run().add_picture(firma, height=Cm(alto))
        borde_celda(top, bottom=(6, "1F2933"))
        p = set_cell(bot, f.get("rol", ""), size=8, color=GRIS)
        for txt, fn, sz, col in ((f.get("nombre") or " ", F_UIB, 9.5, TINTA), (f.get("credencial") or " ", F_UI, 8.5, TINTA),
                                 ("Fecha: ____ / ____ / ________", F_UI, 8, GRIS)):
            p.add_run().add_break()
            fuente(p.add_run(txt), fn, sz, None, None, col)
    espacio(10)
    nota("El espacio sobre cada línea queda libre para firma y sello. Este documento no tiene validez como memoria "
         "emitida hasta estar firmado por el ingeniero responsable.")
    salto()


def indice():
    titulo_suelto("Contenido")
    p = doc.add_paragraph()
    r = p.add_run()
    for kind, text in (("begin", None), ("instr", 'TOC \\o "1-2" \\h \\z \\u'), ("separate", None),
                       ("txt", "Actualizar campo para ver el índice."), ("end", None)):
        if kind in ("begin", "separate", "end"):
            e = OxmlElement("w:fldChar")
            e.set(qn("w:fldCharType"), kind)
            if kind == "begin":
                e.set(qn("w:dirty"), "true")
        elif kind == "txt":
            e = OxmlElement("w:t")
            e.text = text
        else:
            e = OxmlElement("w:instrText")
            e.set(qn("xml:space"), "preserve")
            e.text = text
        r._r.append(e)


# ------------------------------------------------------------------ utilidades de datos
def unidades(e):
    if e.get("unidad_long") not in ("m", "mm"):
        sys.exit("ERROR: unidad de longitud de ETABS no admitida: %r (se esperaba 'm' o 'mm')" % e.get("unidad_long"))
    mm = e["unidad_long"] == "mm"
    return {"L": 0.001 if mm else 1.0, "A_cm2": 0.01 if mm else 1e4, "L_cm": 0.1 if mm else 100.0,
            "q": 1e6 if mm else 1.0, "W": 9806.65 if mm else G, "Avs": 10.0 if mm else 1e4}


def story_key(s):
    m = re.search(r"(\d+)$", s)
    return -int(m.group(1)) if m else 0


def resumen_bloque(b):
    e = b["etabs"]
    con_masa = [s for s in e["mass_story"] if s[0] != "Base" and s[1] > 0]
    ex, ey = e["base"].get("Ex"), e["base"].get("Ey")
    return {
        "niveles": len(con_masa),
        "W": (e["auto_seis"].get("Qx") or {}).get("W"),
        "T1": e["modal"][0][1] if e["modal"] else None,
        "Vx": max(abs(x["FX"]) for x in ex) if ex else None,
        "Vy": max(abs(x["FY"]) for x in ey) if ey else None,
        "dx": max([v for k, v in e["drift"].items() if k.endswith("|Ex|X")], default=None),
        "dy": max([v for k, v in e["drift"].items() if k.endswith("|Ey|Y")], default=None),
        "pmm": max((c["pmm"] for c in e["col"].values()), default=None),
        "nudos": sum(j["bc_gt1"] + j["js_gt1"] for j in e["joint"].values()),
    }


# ------------------------------------------------------------------ 1. proyecto
def cap_proyecto(num):
    h("%d  Descripción del proyecto" % num, cap=str(num))
    if C["proyecto"]:
        kv([tuple(x) for x in C["proyecto"]])
    k = 0
    if C["materiales"]:
        k += 1
        h("%d.%d  Materiales" % (num, k), 2)
        tabla(["Material", "Resistencia especificada"], C["materiales"], widths=[10, 7.2], aligns=["l", "l"], size=9.5,
              titulo="Materiales del proyecto")
    if C["normas"]:
        k += 1
        h("%d.%d  Normas y reglamentos" % (num, k), 2)
        bullets(C["normas"])
    k += 1
    h("%d.%d  Herramientas y trazabilidad" % (num, k), 2)
    if REF:
        par("Cada capítulo indica la herramienta de la que proviene y las páginas de la memoria original donde está el "
            "listado completo. Los valores se transcriben tal como aparecen en esa memoria; las conversiones de unidades "
            "se señalan en cada tabla.")
    else:
        par("Cada capítulo indica la herramienta y el archivo de los que proviene. Los valores se transcriben tal como "
            "los entrega cada programa; las conversiones de unidades se señalan en cada tabla.")
    rows = []
    for nv in D["niveles"]:
        m = nv["meta"]
        rows.append(["Losas — nivel %s" % nv["nombre"], herramienta_losas(m),
                     (nv.get("paginas") or "—") if REF else (m.get("archivo") or nv.get("fuente") or "—")])
    if D["sobrecarga"]:
        rows.insert(0, ["Cargas y espesores de losas", "Hoja de cálculo (Excel)", D.get("paginas_cargas", "—") if REF else "—"])
    for b in D["bloques"]:
        pg = b.get("paginas") or {}
        if len(hojas_ausentes(b)) < 3 or b.get("torsion"):
            rows.append(["%s — espectro, torsión, Art. 38, cuasiestático" % b["nombre"], "Hoja de cálculo (Excel)",
                         "%d–%d y %d" % (pg["inicio"] + 1, pg["reporte"] - 1, pg["cuasi"] + 1) if REF else "—"])
        rows.append(["%s — análisis y diseño" % b["nombre"], b["etabs"]["version"] or "ETABS",
                     "%d–%d" % (pg["reporte"] + 1, pg["cuasi"] - 1) if REF else (b["etabs"].get("modelo") or "—")])
    if rows:
        tabla(["Contenido", "Herramienta", "Páginas en la memoria original" if REF else "Archivo fuente"], rows,
              widths=[8, 5.4, 3.8], aligns=["l", "l", "c"], size=8.5, titulo="Origen de cada parte de la memoria")
    if D["bloques"]:
        k += 1
        h("%d.%d  Resumen de resultados por bloque" % (num, k), 2)
        rows, warn = [], []
        for b in D["bloques"]:
            r = resumen_bloque(b)
            if r["nudos"] or (r["pmm"] or 0) > 1:
                warn.append(len(rows))
            rows.append([b["nombre"].replace("Bloque ", ""), str(r["niveles"]), fmt(r["W"], 0), fmt(r["T1"], 3), fmt(r["Vx"], 1),
                         fmt(r["Vy"], 1), fmt(r["dx"], 5), fmt(r["dy"], 5), fmt(r["pmm"], 3), str(r["nudos"])])
        tabla(["Bloque", "Niveles con masa", "W (ton)", "T modo 1 (s)", "V base Ex (ton)", "V base Ey (ton)", "Deriva máx. X",
               "Deriva máx. Y", "P-M-M máx.", "Nudos > 1.00"], rows,
              widths=[1.3, 1.6, 1.7, 1.7, 1.9, 1.9, 1.9, 1.9, 1.7, 1.6], size=8.5, warn_rows=warn,
              titulo="Indicadores principales del análisis y diseño en ETABS")
        nota("W: peso sísmico usado por ETABS. Derivas elásticas de entrepiso para los casos espectrales. P-M-M: relación "
             "demanda/capacidad máxima en columnas. Nudos > 1.00: verificaciones de nudo (capacidad viga/columna o cortante) "
             "por encima de 1.00; las filas sombreadas se detallan en el capítulo de observaciones.")


# ------------------------------------------------------------------ 2. cargas
def cap_cargas(num):
    h("%d  Cuantificación de cargas" % num, cap=str(num))
    par("La carga última se obtiene con qu = 1.2·qd + 1.6·ql. El peso propio de la losa se calcula con un peso "
        "unitario del hormigón de 2.40 ton/m³.")
    sc_e, sc_t = D["sobrecarga"]
    titulo_t = (sc_t.get("titulo") or "").strip()
    n_techo = "Techo" if titulo_t.lower() in ("", "techo") else "Techo (%s)" % titulo_t
    h("%d.1  Terminaciones y carga viva" % num, 2)
    rows = []
    for nombre, sc in (("Entrepiso", sc_e), (n_techo, sc_t)):
        for p in sc["pesos"]:
            rows.append([nombre, p[0], fmt(p[1]), fmt(p[2]), fmt(p[3])])
    tabla(["Nivel", "Terminación", "Espesor (m)", "γ (ton/m³)", "w (ton/m²)"], rows,
          widths=[4, 5, 2.8, 2.8, 2.6], aligns=["l", "l", "c", "c", "c"], size=9, titulo="Peso de terminaciones")
    rows = [["Entrepiso", v[0], fmt(v[1])] for v in sc_e["vivas"]] + [[n_techo, v[0], fmt(v[1])] for v in sc_t["vivas"]]
    tabla(["Nivel", "Uso", "ql (ton/m²)"], rows, widths=[5, 8, 4.2], aligns=["l", "l", "c"], size=9, titulo="Carga viva por uso")
    h("%d.2  Carga muerta según espesor de losa" % num, 2)
    rows = [[fmt(a[0] * 100, 0), fmt(a[2]), fmt(a[3]), fmt(b[3])] for a, b in zip(sc_e["espesores"], sc_t["espesores"])]
    tabla(["Espesor h (cm)", "Peso propio (ton/m²)", "qd entrepiso (ton/m²)", "qd techo (ton/m²)"], rows,
          widths=[3.5, 4.5, 4.6, 4.6], size=9, titulo="Carga muerta total (peso propio más terminaciones)")
    h("%d.3  Cargas de diseño" % num, 2)
    rows = [["Entrepiso", r[0], fmt(r[1]), fmt(r[2]), fmt(r[3])] for r in sc_e["resumen"]]
    rows += [[n_techo, r[0], fmt(r[1]), fmt(r[2]), fmt(r[3])] for r in sc_t["resumen"]]
    tabla(["Nivel", "Caso", "qd (ton/m²)", "ql (ton/m²)", "qu (ton/m²)"], rows,
          widths=[4, 5.6, 2.5, 2.5, 2.6], aligns=["l", "l", "c", "c", "c"], size=9, titulo="Cargas de diseño resumidas")
    if REF:
        nota("Fuente: hoja de cuantificación de sobrecarga, páginas %s de la memoria original." % D.get("paginas_sobrecarga", "—"))
    meta = D.get("cargas_meta") or {}
    if meta.get("archivo"):
        nota("Fuente: libro de cargas y espesores «%s»." % meta["archivo"])
    portada = C.get("portada") or {}
    palabras = [w for w in re.findall(r"\w+", ("%s %s" % (portada.get("titulo") or "", portada.get("subtitulo") or "")).lower())
                if len(w) > 3]
    if meta.get("proyecto") and palabras and not any(w in meta["proyecto"].lower() for w in palabras):
        OBS.append("Cargas: el libro de cargas y espesores lleva como proyecto «%s»%s."
                   % (meta["proyecto"], " y fecha %s" % meta["fecha"] if meta.get("fecha") else ""))


# ------------------------------------------------------------------ 3. losas
def herramienta_losas(meta):
    """Programa que produjo los resultados de un nivel, según lo que declara la fuente."""
    if meta.get("motor"):
        return "LosasPlus (%s)" % meta["motor"]
    return "Losas.exe v%s (F. Perdomo)" % meta["version"] if meta.get("version") else "Losas.exe (F. Perdomo)"


def cap_losas(num):
    h("%d  Diseño de losas" % num, cap=str(num))
    programas = sorted({herramienta_losas(nv["meta"]) for nv in D["niveles"]})
    par("Las losas se diseñan con %s por el método de Pieper-Martens." % " y ".join(programas))
    # La verificación de espesor mínimo solo se menciona si los datos la traen.
    if any("hcalc" in e for nv in D["niveles"] for e in nv["esp"].values()):
        par("El espesor mínimo se verifica según ACI 318-08, artículo 9.5.2.1 para losas en una dirección y 9.5.3.3 "
            "para losas en dos direcciones.")
    par("Para cada nivel se presenta una tabla con la geometría, la carga última, los momentos y la armadura de vano de "
        "cada losa y, a continuación, la armadura negativa sobre los apoyos. Los momentos están en ton·m/m y la armadura "
        "dispuesta es la que entrega el programa.")
    for i, nv in enumerate(D["niveles"], 1):
        m = nv["meta"]
        nombre_nv = nv["nombre"] if nv["nombre"].lower().startswith("nivel") else "Nivel %s" % nv["nombre"]
        h("%d.%d  %s" % (num, i, nombre_nv), 2)
        ficha = [("Programa", herramienta_losas(m)),
                 ("Archivo de datos", m.get("archivo")),
                 ("Sistema", m.get("sistema")),
                 ("Reglamento del programa", m.get("reglamento")),
                 ("Materiales", "f'c = %s kg/cm² · fy = %s ton/cm²" % (m.get("fc", "—"), m.get("fy", "—"))),
                 ("Fecha de la corrida", m.get("fecha"))]
        kv([(k_, v_) for k_, v_ in ficha if v_], w1=5.8, w2=11.4, size=9)
        if REF and m.get("archivo", "").replace(".DL", "") != m.get("sistema", ""):
            OBS.append("Losas, nivel %s: el listado declara el sistema «%s» pero el archivo de datos es «%s»."
                       % (nv["nombre"], m.get("sistema"), m.get("archivo")))
        ids = sorted(set(int(k) for k in nv["esp"]) | set(int(k) for k in nv["mom"]))
        rows = []
        for k in ids:
            ks = str(k)
            e, c, mo = nv["esp"].get(ks, {}), nv["carga"].get(ks, {}), nv["mom"].get(ks, {})
            ax, ay = nv["ax"].get(ks, {}), nv["ay"].get(ks, {})
            cond = (e.get("cond", "—") or "—").replace("id", "1D")
            h_losa = e.get("h") or ("%.2f" % (float(mo["H"]) / 100) if mo.get("H") else "—")
            rows.append([ks, e.get("Lx", mo.get("Lx", "—")), e.get("Ly", mo.get("Ly", "—")), cond,
                         h_losa, mo.get("tipo", "—"), c.get("qu", mo.get("q", "—")),
                         mo.get("Mfx", "—"), mo.get("Mfy", "—"), mo.get("Msx", "—"), mo.get("Msy", "—"),
                         ax.get("barra", "—"), ay.get("barra", "—")])
        tabla(["Losa", "Lx (m)", "Ly (m)", "Cond.", "h (m)", "Tipo", "qu (t/m²)", "Mfx", "Mfy", "−Msx", "−Msy",
               "Acero X", "Acero Y"], rows,
              widths=[0.9, 1.1, 1.1, 1.0, 1.0, 0.9, 1.3, 1.2, 1.2, 1.2, 1.2, 2.6, 2.6], size=7.5,
              titulo="Nivel %s — geometría, carga, momentos y armadura de vano" % nv["nombre"])
        nota("Cond.: 2D = armada en dos direcciones, 1D = en una dirección. Tipo: caso de apoyo de Pieper-Martens. "
             "«—»: el listado no trae el dato para esa losa.")
        for direc, lista in (("X", nv["apx"]), ("Y", nv["apy"])):
            mitad = (len(lista) + 1) // 2
            rows = []
            for j in range(mitad):
                a = lista[j]
                b = lista[j + mitad] if j + mitad < len(lista) else None
                rows.append(["%d–%d" % (a["i"], a["j"]), a["Mu"], a["DAs"], a["barra"]] +
                            (["%d–%d" % (b["i"], b["j"]), b["Mu"], b["DAs"], b["barra"]] if b else ["—", "—", "—", "—"]))
            tabla(["Borde", "Mu", "As (cm²/m)", "Disponer", "Borde", "Mu", "As (cm²/m)", "Disponer"], rows,
                  widths=[1.7, 1.6, 2.0, 3.3, 1.7, 1.6, 2.0, 3.3], size=7.5,
                  titulo="Nivel %s — armadura negativa sobre apoyos, dirección %s (%d bordes)" % (nv["nombre"], direc, len(lista)))
        nota("Mu: momento de diseño del borde, a partir de los de las dos losas que concurren (ton·m/m)."
             + (" Listado completo: páginas %s de la memoria original." % nv["paginas"] if REF and nv.get("paginas") else ""))


# ------------------------------------------------------------------ bloques
def grafico_espectro(b, idx):
    pts = b["tabla_espectro"]
    if not pts:
        return None
    plt.rcParams["font.family"] = "Segoe UI"
    fig, ax = plt.subplots(figsize=(6.4, 2.6), dpi=220)
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    ax.plot(xs, ys, color="#0F5C66", lw=1.8)
    ax.fill_between(xs, ys, color="#0F5C66", alpha=0.07)
    ax.set_xlabel("Período T (s)", fontsize=8, color="#1F2933")
    ax.set_ylabel("Sa de diseño (m/s²)", fontsize=8, color="#1F2933")
    ax.set_xlim(0, max(xs))
    ax.set_ylim(0, max(ys) * 1.15)
    ax.grid(True, color="#E1E7E9", lw=0.6)
    ax.tick_params(labelsize=7, colors="#5F6B76")
    for s_ in ("top", "right"):
        ax.spines[s_].set_visible(False)
    for s_ in ("left", "bottom"):
        ax.spines[s_].set_color("#9AA7AD")
    fig.tight_layout()
    path = os.path.join(TMP, "espectro_%d.png" % idx)
    fig.savefig(path)
    plt.close(fig)
    return path


def hojas_ausentes(b):
    """Nombres de las hojas de cálculo que el bloque no trae; sus secciones se omiten."""
    return [n for n, hay in (("espectro", b["espectro"]), ("Art. 38", b["art38"]), ("cuasiestático", b["cuasi"])) if not hay]


def bloque_parametros(titulo, b, idx):
    sp = b["espectro"]
    h(titulo, 2)
    kv([("Uso / ubicación", "%s · %s" % (sp["uso"], sp["ubicacion"])),
        ("Geometría declarada", "%s piso(s) · altura total %s m · planta %s × %s m"
         % (fmt(sp["pisos"], 0), fmt(sp["htotal"]), fmt(sp["dx"]), fmt(sp["dy"]))),
        ("Categoría ocupacional (Art. 22)", "I = %s" % sp["I"]),
        ("Zona sísmica (Art. 8) · Factor de uso (Art. 36)", "Z = %s · U = %s" % (sp["Z"], sp["U"])),
        ("Clasificación de sitio (Art. 12)", sp["S"]),
        ("Sistema estructural (Art. 37)", sp["sistema"]),
        ("Factor de reducción", "Rd = %s · Rd final = %s (%s)" % (fmt(sp["Rd"]), fmt(sp["Rd_final"]), sp["Rd_nota"])),
        ("Ordenadas espectrales (Art. 21)", "Ss = %s · S1 = %s" % (fmt(sp["Ss"]), fmt(sp["S1"]))),
        ("Factores de suelo", "Fa = %s · Fv = %s" % (fmt(sp["Fa"]), fmt(sp["Fv"]))),
        ("Aceleraciones de diseño", "SDS = %s m/s² · SD1 = %s m/s²" % (fmt(sp["SDS"]), fmt(sp["SD1"]))),
        ("Períodos de esquina", "To = %s s · Ts = %s s" % (fmt(sp["To"]), fmt(sp["Ts"])))], w1=7.0, w2=10.2, size=9)
    g = grafico_espectro(b, idx)
    if g:
        pts = b["tabla_espectro"]
        figura(g, 13.5, "Espectro de diseño (elástico dividido entre Rd) — meseta de %s m/s²" % fmt(max(p[1] for p in pts)))
        nota("Sa(T = %s s) = %s m/s². La tabla T–Sa tiene %d puntos%s."
             % (fmt(pts[-1][0]), fmt(pts[-1][1]), len(pts), " y está completa en la memoria original" if REF else ""))


def bloque_torsion(titulo, b):
    e, u, nombre = b["etabs"], unidades(b["etabs"]), b["nombre"]
    h(titulo, 2)
    rows = [[t["tipo"], fmt(t["Bw"], 0), fmt(t["H"], 0), fmt(t["hf"], 0), fmt(t["Bf"], 0), fmt(t["fc"], 0), fmt(t["Acp"], 0),
             fmt(t["Pcp"], 0), fmt(t["Tmin"], 1), fmt(t["Tu"], 1), fmt(t["factor"], 4)] for t in b.get("torsion") or []]
    if rows:
        tabla(["Sección", "bw (cm)", "h (cm)", "hf (cm)", "bf (cm)", "f'c (kg/cm²)", "Acp (cm²)", "Pcp (cm)",
               "T mín. (kg·cm)", "T corrida (kg·cm)", "Factor"], rows,
              widths=[1.5, 1.2, 1.2, 1.2, 1.2, 1.6, 1.6, 1.4, 2.2, 2.4, 1.5], size=8,
              titulo="Modificador de la constante de torsión J")
        nota("T mín.: momento torsional por debajo del cual se desprecia la torsión (φ = 0.75). Factor = T mín. / T de la "
             "corrida; es el modificador de J asignado a las vigas.")
    elif not torsion_del_modelo(e, u):
        par("Las fuentes leídas para este bloque no incluyen la hoja de reducción de la constante de torsión."
            if not REF else "La memoria original no trae la hoja de reducción de la constante de torsión de este bloque.")
        if REF:
            OBS.append("%s: no se encontró la hoja de reducción de la constante de torsión en vigas." % nombre)


def bloque_art38(titulo, b):
    h(titulo, 2)
    casos = {c["caso"]: {f["story"]: f for f in c["filas"]} for c in b["art38"]}
    stories = sorted({s for c in casos.values() for s in c}, reverse=True)
    rows, peor = [], 0.0
    for s in stories:
        row, oks = [str(s)], []
        for c in ("1", "2"):
            f = casos.get(c, {}).get(s)
            if f:
                rx, ry = max(f["rx1"], f["rx2"]), max(f["ry1"], f["ry2"])
                peor = max(peor, rx, ry)
                row += [fmt(rx, 4), fmt(ry, 4)]
                oks += f["ok"]
            else:
                row += ["—", "—"]
        row.append("Ok" if oks and all(o.lower() == "ok" for o in oks) else "Revisar")
        rows.append(row)
    tabla(["Nivel", "X, caso 1 (adim.)", "Y, caso 1 (adim.)", "X, caso 2 (adim.)", "Y, caso 2 (adim.)", "Comprobación"], rows,
          widths=[1.8, 3, 3, 3, 3, 3.4], size=9, titulo="Relación Δmáx / Δprom por nivel y dirección (adimensional)")
    nota("Δmáx y Δprom son desplazamientos laterales en las esquinas del nivel, en las mismas unidades; su cociente "
         "no tiene unidades. Criterio de la hoja: relación < 1.2, Ok; entre 1.2 y 1.4, reducir Rd; > 1.4, rediseñar. Se muestra el mayor de "
         "los dos pares de esquinas. Máximo del bloque: %s. Los casos 1 y 2 son las dos excentricidades accidentales." % fmt(peor, 4))


def bloque_cuasi(titulo, b):
    e, cu, nombre = b["etabs"], b["cuasi"], b["nombre"]
    con_masa = [s for s in e["mass_story"] if s[0] != "Base" and s[1] > 0]
    h(titulo, 2)
    W_etabs = (e["auto_seis"].get("Qx") or {}).get("W")
    detalle_w = peso_sismico_detallado(cu)
    kv([("Geometría declarada", "%s piso(s) · altura total %s m · planta %s × %s m"
         % (fmt(cu["pisos"], 0), fmt(cu["htotal"]), fmt(cu["dx"]), fmt(cu["dy"]))),
        ("Carga muerta", "%s ton" % fmt(cu["muerta"])),
        ("Carga viva participante", "%s ton%s" % (fmt(cu["viva_part"]), "" if detalle_w else
         " (φ: entrepisos %s · común %s · techo %s)" % (fmt(cu["phi_entrepiso"]), fmt(cu["phi_comun"]), fmt(cu["phi_techo"])))),
        ("Peso sísmico total W", "%s ton" % fmt(cu["total"])),
        ("Período aproximado", "Ta = Ct·H^x = %s s (Ct = %s, x = %s)" % (fmt(cu["Ta"][0] if cu["Ta"] else None, 3), fmt(cu["Ct"], 3), fmt(cu["X"], 1))),
        ("Períodos del modelo", "Tx = %s s · Ty = %s s" % (fmt(cu["Tx"], 3), fmt(cu["Ty"], 3))),
        ("Coeficiente de cortante basal", "CBx = %s · CBy = %s" % (fmt(cu["CBX"], 3), fmt(cu["CBY"], 3))),
        ("Cortante basal estático", "Vx = %s ton · Vy = %s ton" % (fmt(cu["Vx"]), fmt(cu["Vy"]))),
        ("Mínimo para el análisis espectral (65 %)", "Vx = %s ton · Vy = %s ton" % (fmt(cu["Vx65"]), fmt(cu["Vy65"])))],
       w1=7.0, w2=10.2, size=9)
    rows = []
    for k, lab in (("Ex", "Ex (X-X)"), ("Ey", "Ey (Y-Y)")):
        v = cu.get(k)
        if v:
            rows.append([lab, fmt(v[0]), fmt(cu["Vx65"] if k == "Ex" else cu["Vy65"]), v[1], fmt(v[2], 4)])
    tabla(["Caso espectral", "Cortante dinámico (ton)", "65 % del estático (ton)", "Comprobación", "Factor a usar"], rows,
          widths=[3.2, 4, 4, 3, 3], size=9, titulo="Escalado del análisis espectral")
    for k, comp in (("Ex", "FX"), ("Ey", "FY")):
        v, br = cu.get(k), e["base"].get(k)
        if v and br:
            base = max(abs(x[comp]) for x in br)
            if base and abs(base - v[0]) / base > 0.005:
                OBS.append("%s: la hoja cuasiestática toma %s ton como cortante dinámico de %s, y el reporte de ETABS da "
                           "%s ton en la base para ese caso." % (nombre, fmt(v[0]), k, fmt(base)))
    if W_etabs and cu["total"] and abs(W_etabs - cu["total"]) / cu["total"] > 0.02:
        OBS.append("%s: el peso sísmico de la hoja cuasiestática (%s ton) difiere del W que ETABS usa en los patrones "
                   "Qx/QY (%s ton)." % (nombre, fmt(cu["total"]), fmt(W_etabs)))
    if cu["pisos"] is not None and abs(cu["pisos"] - len(con_masa)) >= 1:
        OBS.append("%s: las hojas de espectro y cuasiestático declaran %s piso(s) y altura total %s m, pero el modelo de "
                   "ETABS tiene %d niveles con masa. El período Ta = %s s y el coeficiente CB = %s dependen de esa altura."
                   % (nombre, fmt(cu["pisos"], 0), fmt(cu["htotal"]), len(con_masa),
                      fmt(cu["Ta"][0] if cu["Ta"] else None, 3), fmt(cu["CBX"], 3)))


def cap_bloque(num, b, idx):
    e, sp, cu, u = b["etabs"], b["espectro"], b["cuasi"], unidades(b["etabs"])
    nombre = b["nombre"]
    pg = b.get("paginas") or {}
    h("%d  %s" % (num, nombre), cap=str(num))
    con_masa = [s for s in e["mass_story"] if s[0] != "Base" and s[1] > 0]
    vista = img(C["vistas_bloque"].get(nombre))
    if vista:
        figura(vista, 11.0, "Vista isométrica del modelo de análisis — %s" % nombre, alto_max=8.2)
    kv([("Modelo de ETABS", "%s (%s)" % (e["modelo"], e["version"])),
        ("Niveles definidos / con masa", "%d / %d" % (len(e["stories"]), len(con_masa))),
        ("Elementos diseñados", "%d columnas · %d vigas · %d nudos" % (e["n_col"], e["n_beam"], e["n_joint"]))]
       + ([("Páginas en la memoria original", "%d a %d" % (pg["inicio"], pg["cuasi"] + 1))] if REF else []))

    orden = itertools.count(1)

    def titulo(texto):
        return "%d.%d  %s" % (num, next(orden), texto)

    faltan = hojas_ausentes(b)
    if faltan:
        OBS.append("%s: las fuentes no incluyen las hojas de cálculo de %s; el capítulo omite esas secciones y "
                   "muestra solo lo leído del modelo de ETABS."
                   % (nombre, " y ".join([", ".join(faltan[:-1])] * (len(faltan) > 1) + faltan[-1:])))
    if sp:
        bloque_parametros(titulo("Parámetros sísmicos (R-001)"), b, idx)
    bloque_torsion(titulo("Reducción de la constante de torsión en vigas"), b)
    if b["art38"]:
        bloque_art38(titulo("Irregularidad torsional (Art. 38)"), b)
    if cu:
        bloque_cuasi(titulo("Cortante basal cuasiestático y factor de escala"), b)

    h(titulo("Modelo de análisis (ETABS)"), 2)
    h("Niveles y masa", 3)
    mass = {s[0]: s[1] for s in e["mass_story"]}
    rows = [[name, fmt(height * u["L"]), fmt(mass.get(name, 0.0) * u["W"] / G, 2), fmt(mass.get(name, 0.0) * u["W"], 1)]
            for name, height in e["stories"]]
    if "Base" in mass:
        rows.append(["Base", "—", fmt(mass["Base"] * u["W"] / G, 2), fmt(mass["Base"] * u["W"], 1)])
    tabla(["Nivel", "Altura (m)", "Masa (ton·s²/m)", "Peso equivalente (ton)"], rows, widths=[4, 4, 4.6, 4.6], size=9,
          titulo="Niveles del modelo y masa por nivel")
    nota("Fuente de masa: " + " + ".join("%s·%s" % (fmt(m[1], 2), m[0]) for m in e["mass_source"]) + ". Peso equivalente = masa × g.")
    h("Secciones", 3)
    rows = []
    en_uso_p, en_uso_a = e.get("frame_en_uso"), e.get("area_en_uso")
    for name, f in e["frame"].items():
        if en_uso_p is not None and name not in en_uso_p:
            continue
        A, I33 = f["A"], f["I33"]
        rect = "Rectangular" in f["shape"] and A > 0 and I33 > 0
        hh = math.sqrt(12 * I33 / A) * u["L_cm"] if rect else 0.0
        bb = A * u["A_cm2"] / hh if rect else 0.0
        rows.append([name, f["mat"], "%s × %s" % (fmt(bb, 0), fmt(hh, 0)) if rect else "—", fmt(A * u["A_cm2"], 0),
                     fmt(f.get("mI33"), 2), fmt(f.get("mI22"), 2), fmt(f.get("mJ"), 2)])
        m = re.match(r"^V(\d{2})(\d{2})$", name)
        if m and rect and (abs(int(m.group(1)) - bb) > 0.6 or abs(int(m.group(2)) - hh) > 0.6):
            OBS.append("%s: la sección «%s» tiene dimensiones %s × %s cm en el modelo, distintas de las que indica su nombre."
                       % (nombre, name, fmt(bb, 0), fmt(hh, 0)))
    tabla(["Sección", "Material", "b × h (cm)", "Área (cm²)", "Modif. I33", "Modif. I22", "Modif. J"], rows,
          widths=[3, 2.4, 3, 2.6, 2.1, 2.1, 2.0], size=9, titulo="Secciones de pórtico y modificadores de rigidez")
    nota("b × h se deduce del área y la inercia I33 reportadas. «—»: el reporte no incluye esa columna."
         + (" Solo se listan las secciones asignadas a algún elemento del modelo." if en_uso_p is not None else ""))
    rows = [[a["name"], a["type"], a["elem"], a["mat"], fmt(a["t"] * u["L_cm"], 1)] for a in e["area"]
            if en_uso_a is None or a["name"] in en_uso_a]
    tabla(["Sección de área", "Tipo", "Elemento", "Material", "Espesor (cm)"], rows, widths=[4, 3, 4, 3, 3.2], size=9,
          titulo="Secciones de losa y muro")
    h("Cargas", 3)
    sets = {}
    for name, pat, val in e["loadsets"]:
        sets.setdefault(name, {})[pat] = val * u["q"]
    pats = sorted({p for v in sets.values() for p in v})
    rows = [[n] + [fmt(v.get(p), 2) for p in pats] for n, v in sets.items()]
    tabla(["Conjunto de carga uniforme"] + ["%s (ton/m²)" % p for p in pats], rows,
          widths=[6] + [11.2 / max(len(pats), 1)] * len(pats), aligns=["l"] + ["c"] * len(pats), size=9,
          titulo="Cargas uniformes sobre losas (adicionales al peso propio)")
    rows = [[p["name"], p["type"], p["sw"], p["autoload"] or "—"] for p in e["patterns"]
            if not p["name"].startswith("~") and "(" not in p["name"]]
    tabla(["Patrón", "Tipo", "Multiplicador de peso propio", "Carga automática"], rows, widths=[3.5, 4, 5, 4.7], size=9,
          titulo="Patrones de carga")
    rows = []
    for k in ("Qx", "QY"):
        a = e["auto_seis"].get(k)
        if a and "W" in a:
            rows.append([k, fmt(a.get("C"), 3), fmt(a["W"], 2), fmt(a["V"], 2)])
    if rows:
        tabla(["Patrón sísmico estático", "Coeficiente C", "W (ton)", "V = C·W (ton)"], rows, widths=[5, 4, 4.1, 4.1], size=9,
              titulo="Sismo estático por coeficiente")
    h("Casos y combinaciones", 3)
    par("Casos de carga: " + "; ".join("%s (%s)" % (c[0], c[1]) for c in e["cases"]) + ".", size=10.5)
    rows = []
    for name, c in e["combos"].items():
        if not name.startswith("DCon"):
            continue
        expr = " ".join(("+ " if sf >= 0 else "− ") + ("%g %s" % (abs(sf), ld)) for ld, sf in c["terms"]).lstrip("+ ")
        rows.append([name, expr])
    half = (len(rows) + 1) // 2
    rows2 = [[rows[i][0], rows[i][1]] + (rows[i + half] if i + half < len(rows) else ["", ""]) for i in range(half)]
    tabla(["Combinación", "Expresión", "Combinación", "Expresión"], rows2, widths=[2.3, 6.3, 2.3, 6.3],
          aligns=["l", "l", "l", "l"], size=8.5, titulo="Combinaciones de resistencia (ACI 318-19)")
    otros = [n for n in e["combos"] if not n.startswith("DCon")]
    if otros:
        nota("El modelo incluye además %d combinaciones %s…%s equivalentes para el diseño de muros." % (len(otros), otros[0], otros[-1]))

    h(titulo("Resultados del análisis"), 2)
    h("Reacciones en la base", 3)
    tipos = dict((c[0], c[1]) for c in e["cases"])
    rows = []
    for k in ("Dead", "Live", "LiveT", "Ex", "Ey", "Qx", "QY"):
        v = e["base"].get(k)
        if v:
            rows.append([k, tipos.get(k, ""), fmt(max(abs(x["FX"]) for x in v)), fmt(max(abs(x["FY"]) for x in v)),
                         fmt(max(abs(x["FZ"]) for x in v))])
    tabla(["Caso", "Tipo", "|FX| (ton)", "|FY| (ton)", "FZ (ton)"], rows, widths=[2.6, 5, 3.2, 3.2, 3.2],
          aligns=["l", "l", "c", "c", "c"], size=9, titulo="Reacciones totales en la base por caso de carga")
    h("Modos de vibración", 3)
    modal = e["modal"]
    rows = [[str(m[0]), fmt(m[1], 3), fmt(m[2], 4), fmt(m[3], 4), fmt(m[10], 4), fmt(m[5], 4), fmt(m[6], 4)] for m in modal[:12] if len(m) >= 11]
    tabla(["Modo", "Período (s)", "UX", "UY", "RZ", "Σ UX", "Σ UY"], rows, widths=[1.8, 2.8, 2.5, 2.5, 2.5, 2.5, 2.6], size=9,
          titulo="Períodos y participación de masa")
    if modal:
        last = modal[-1]
        nota("Se muestran %d de %d modos. Con todos los modos: ΣUX = %s, ΣUY = %s."
             % (min(12, len(modal)), len(modal), fmt(last[5], 4), fmt(last[6], 4)))
        bajas = ["Σ%s = %s %%" % (eje, fmt(v * 100, 1)) for eje, v in (("UX", last[5]), ("UY", last[6])) if v < MASA_MINIMA]
        if bajas:
            par("La participación de masa acumulada queda por debajo del %d %%: %s. Con los %d modos del modelo no se "
                "alcanza el mínimo en esa dirección." % (MASA_MINIMA * 100, " y ".join(bajas), len(modal)),
                size=9.5, bold=True, color=ALERTA, align="l")
        if last[5] < MASA_MINIMA or last[6] < MASA_MINIMA:
            OBS.append("%s: la masa participante acumulada con los %d modos del reporte es ΣUX = %s y ΣUY = %s (referencia "
                       "usual: 90 %%)." % (nombre, len(modal), fmt(last[5], 4), fmt(last[6], 4)))
    h("Cortantes y derivas por nivel", 3)
    rows = []
    for name, _ in e["stories"]:
        sx, sy = e["shear"].get("%s|Ex" % name), e["shear"].get("%s|Ey" % name)
        dx, dy = e["drift"].get("%s|Ex|X" % name), e["drift"].get("%s|Ey|Y" % name)
        if sx is None and dx is None:
            continue
        rows.append([name, fmt(sx[0] if sx else None), fmt(sy[1] if sy else None), fmt(dx, 6), fmt(dy, 6)])
    tabla(["Nivel", "Vx por Ex (ton)", "Vy por Ey (ton)", "Deriva X por Ex", "Deriva Y por Ey"], rows,
          widths=[3, 3.5, 3.5, 3.6, 3.6], size=9, titulo="Cortante de piso y deriva de entrepiso (casos espectrales)")
    nota("Cortante en la base del nivel y deriva máxima (Δ/h) para los casos espectrales ya escalados, tal como los "
         "reporta ETABS (valores elásticos reducidos). «—»: el reporte no lista deriva en esa dirección."
         + (" Listados completos: páginas %d a %d de la memoria original." % (pg["reporte"] + 1, pg["cuasi"] - 1) if REF else ""))

    h(titulo("Diseño de elementos (ACI 318-19)"), 2)
    h("Columnas", 3)
    rows, warn = [], []
    for k in sorted(e["col"], key=lambda k: (story_key(k.split("|")[0]), k.split("|")[1])):
        c = e["col"][k]
        st, sect = k.split("|")
        A = (e["frame"].get(sect) or {}).get("A")
        if c["pmm"] > 1.0:
            warn.append(len(rows))
        rows.append([st, sect, str(c["n"]), fmt(c["pmm"], 3), c["combo"], fmt(c["As"] * u["A_cm2"], 1),
                     fmt(c["As"] / A * 100 if A else None, 2)])
    tabla(["Nivel", "Sección", "Cant.", "Relación P-M-M máx.", "Combinación", "As (cm²)", "ρ (%)"], rows,
          widths=[2.4, 2.8, 1.6, 3.3, 2.8, 2.2, 2.1], size=9, warn_rows=warn, titulo="Verificación de columnas por nivel y sección")
    nota("Columnas en modo de verificación (armado definido en la sección). Relación P-M-M = demanda / capacidad; debe ser ≤ 1.00.")
    h("Vigas", 3)
    rows = []
    for k in sorted(e["beam"], key=lambda k: (story_key(k.split("|")[0]), k.split("|")[1])):
        c = e["beam"][k]
        st, sect = k.split("|")
        rows.append([st, sect, str(c["n"]), fmt(c["AsTop"] * u["A_cm2"], 2), fmt(c["AsBot"] * u["A_cm2"], 2),
                     fmt(c["Av"] * u["Avs"], 2)])
    tabla(["Nivel", "Sección", "Cant.", "As sup. máx. (cm²)", "As inf. máx. (cm²)", "Av/s máx. (cm²/m)"], rows,
          widths=[2.8, 3.2, 2.0, 3.1, 3.1, 3.0], size=9, titulo="Acero requerido en vigas por nivel y sección")
    nota("Envolvente del acero requerido por flexión y cortante en todas las estaciones de las vigas de cada nivel y sección.")
    h("Nudos viga-columna", 3)
    rows, warn = [], []
    for st in sorted(e["joint"], key=story_key):
        j = e["joint"][st]
        if j["bc_gt1"] or j["js_gt1"]:
            warn.append(len(rows))
        rows.append([st, str(j["n"]), fmt(j["bc"], 3) if j["bc"] else "—", str(j["bc_gt1"]),
                     fmt(j["js"], 3) if j["js"] else "—", str(j["js_gt1"])])
    tabla(["Nivel", "Nudos", "Capacidad viga/columna máx.", "Nudos > 1.00", "Cortante en nudo máx.", "Nudos > 1.00"], rows,
          widths=[2.6, 1.8, 4.1, 2.3, 4.1, 2.3], size=9, warn_rows=warn, titulo="Verificación de nudos por nivel")
    nota("Relaciones reportadas por ETABS: capacidad viga/columna (criterio 6/5 de columna fuerte–viga débil) y cortante "
         "en el nudo. Las filas sombreadas tienen nudos por encima de 1.00.")
    tot_bc = sum(j["bc_gt1"] for j in e["joint"].values())
    tot_js = sum(j["js_gt1"] for j in e["joint"].values())
    if tot_bc or tot_js:
        OBS.append("%s: ETABS reporta %d nudo(s) con relación de capacidad viga/columna > 1.00 y %d con cortante en el "
                   "nudo > 1.00 (máximos %s y %s)." % (nombre, tot_bc, tot_js,
                   fmt(max(j["bc"] for j in e["joint"].values()), 3), fmt(max(j["js"] for j in e["joint"].values()), 3)))
    muros_del_modelo(e.get("muros"), u, nombre)
    for k, v in sorted(e["msgs"].items(), key=lambda x: -x[1]):
        el, msg = k.split(": ", 1)
        if el == "viga":
            OBS.append("%s: %d estación(es) de viga con el mensaje «%s»." % (nombre, v, msg.replace(" No Message", "")))


def _lista(nombres, maximo=8):
    return ", ".join(nombres[:maximo]) + ("…" if len(nombres) > maximo else "")


def muros_del_modelo(m, u, nombre):
    """Subsección de muros: resumen del diseño de pilas de ETABS. Nada si el modelo no tiene pilas."""
    if not m:
        return
    h("Muros", 3)
    if m["estado"] != "diseñado":
        par("No se incluye el diseño de muros: %s." % m["motivo"], size=10)
        OBS.append("%s: falta el diseño de muros de ETABS (%s)." % (nombre, m["motivo"]))
        return
    p = m["preferencias"]
    combos = m["combinaciones"]
    par("ETABS diseña los muros por pilas con %s%s. Sistema: %s; categoría de diseño sísmico %s; R = %s, Ω₀ = %s, "
        "Cd = %s; φ de cortante sísmico = %s. Combinaciones de diseño: %s."
        % (m["codigo"] or "el código del modelo", " y refuerzo %s" % p["RebarMat"] if p.get("RebarMat") else "",
           p.get("Ductility", "—"), p.get("SDC", "—"), p.get("R", "—"), p.get("Omega0", "—"), p.get("Cd", "—"),
           p.get("PhiShrSeis", "—"), "%s…%s (%d)" % (combos[0], combos[-1], len(combos)) if combos else "—"),
        size=10)
    limite = _f(p.get("DCLimit")) or 1.0
    rows, warn = [], []
    for pila, d in m["pilas"].items():
        verif, nivel = _verificacion_pila(d)
        if (d["dc"] or 0) > limite or d["cortante"] or _cuantia_insuficiente(d):
            warn.append(len(rows))
        rows.append([pila, ", ".join(d["secciones"]) or ", ".join(d.get("tipos", [])) or "—", str(d["niveles"]),
                     str(d.get("tramos", 1)), fmt(d["t"] * u["L"], 2), verif, nivel or "—", fmt(d["av"] * u["Avs"], 2),
                     "%d de %d" % (d["cortante"], d["estaciones"]) if d["cortante"] else "—"])
    tabla(["Pila", "Sección o tipo", "Niveles", "Tramos", "t (m)", "Flexocompresión", "Nivel crítico",
           "Av/s máx. (cm²/m)", "Cortante > máx."], rows, widths=[1.7, 2.4, 1.4, 1.3, 1.1, 3.0, 1.9, 2.1, 2.3],
          size=8.5, warn_rows=warn, titulo="Diseño de muros por pila")
    nota("Flexocompresión: con sección de Section Designer, relación demanda/capacidad (D/C) con el armado definido, "
         "límite %s; con refuerzo uniforme, cuantía vertical requerida frente a la colocada (ρ). Máximo entre niveles, "
         "estaciones y tramos de la pila. Av/s: acero horizontal requerido por cortante. «Cortante > máx.»: "
         "estaciones en que ETABS reporta que el cortante excede el máximo permitido por la sección. Las filas "
         "sombreadas superan el límite, no alcanzan la cuantía requerida o tienen esas estaciones." % fmt(limite, 2))
    if m["sin_diseno"]:
        nota("Pilas asignadas sin resultado de diseño: %s." % _lista(m["sin_diseno"]))
    if m["sin_pila"]:
        nota("%d área(s) con sección de muro no tienen pila asignada; ETABS no las diseña." % m["sin_pila"])

    con_cortante = [k for k, d in m["pilas"].items() if d["cortante"]]
    if con_cortante:
        n = sum(m["pilas"][k]["cortante"] for k in con_cortante)
        tot = sum(d["estaciones"] for d in m["pilas"].values())
        OBS.append("%s: en %d de %d estaciones de muro ETABS reporta que el cortante excede el máximo permitido "
                   "(pilas %s)." % (nombre, n, tot, _lista(con_cortante)))
    altas = [k for k, d in m["pilas"].items() if (d["dc"] or 0) > limite]
    if altas:
        OBS.append("%s: pilas con relación D/C por encima del límite de %s: %s." % (
            nombre, fmt(limite, 2), ", ".join("%s (%s)" % (k, fmt(m["pilas"][k]["dc"], 3)) for k in altas)))
    cortas = [k for k, d in m["pilas"].items() if _cuantia_insuficiente(d)]
    if cortas:
        OBS.append("%s: pilas con cuantía vertical requerida mayor que la colocada: %s." % (nombre, ", ".join(
            "%s (%s %% frente a %s %%)" % (k, fmt(m["pilas"][k]["rho_req"], 2), fmt(m["pilas"][k]["rho_act"], 2))
            for k in cortas)))
    otros = {}
    for d in m["pilas"].values():
        for msg, v in d["mensajes"].items():
            otros[msg] = otros.get(msg, 0) + v
    for msg, v in sorted(otros.items(), key=lambda x: -x[1]):
        OBS.append("%s: %d estación(es) de muro con el mensaje «%s»." % (nombre, v, msg))
    if m["sin_diseno"]:
        OBS.append("%s: pilas sin resultado de diseño de muros: %s." % (nombre, _lista(m["sin_diseno"])))
    if m["sin_pila"]:
        OBS.append("%s: %d área(s) de muro sin pila asignada no se diseñan en ETABS." % (nombre, m["sin_pila"]))
    for aviso in m.get("avisos") or []:
        OBS.append("%s: aviso de ETABS durante el diseño de muros: «%s»." % (nombre, aviso))


def _verificacion_pila(d):
    """Texto de flexocompresión de una pila y su nivel crítico, según el tipo de diseño de ETABS."""
    partes, nivel = [], ""
    if d.get("dc") is not None:
        partes.append("D/C = %s" % fmt(d["dc"], 3))
        nivel = d["dc_nivel"]
    if d.get("rho_req") is not None:
        partes.append("ρ req. %s %% (col. %s %%)" % (fmt(d["rho_req"], 2), fmt(d.get("rho_act"), 2)))
        nivel = nivel or d.get("rho_nivel", "")
    return "; ".join(partes) or "—", nivel


def _cuantia_insuficiente(d):
    return d.get("rho_req") is not None and d.get("rho_act") is not None and d["rho_req"] > d["rho_act"]


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


MASA_MINIMA = 0.90                       # participación de masa acumulada mínima
ALERTA = RGBColor(0xB4, 0x23, 0x18)


def torsion_del_modelo(e, u):
    """Tabla del modificador de la constante de torsión J de las vigas, tomado del modelo. False si no hay datos."""
    vigas = {k.split("|")[1] for k in e.get("beam", {})}
    en_uso = e.get("frame_en_uso")
    rows = []
    for name, f in e["frame"].items():
        if f.get("mJ") is None or name not in vigas or (en_uso is not None and name not in en_uso):
            continue
        A, I33 = f["A"], f["I33"]
        rect = "Rectangular" in f["shape"] and A > 0 and I33 > 0
        hh = math.sqrt(12 * I33 / A) * u["L_cm"] if rect else 0.0
        rows.append([name, f["mat"], "%s × %s" % (fmt(A * u["A_cm2"] / hh, 0), fmt(hh, 0)) if rect else "—", fmt(f["mJ"], 2),
                     "%s %%" % fmt((1 - f["mJ"]) * 100, 0)])
    if not rows:
        return False
    tabla(["Sección de viga", "Material", "b × h (cm)", "Modificador de J", "Reducción"], rows,
          widths=[4, 3, 3.4, 3.6, 3.2], size=9, titulo="Modificador de la constante de torsión J asignado en ETABS")
    nota("Valores leídos de las secciones de viga del modelo de ETABS. El modificador multiplica la constante de "
         "torsión J de la sección bruta; la reducción es la parte de esa rigidez que el modelo no considera.")
    return True


def peso_sismico_detallado(cu):
    """Tabla del peso sísmico: carga muerta más cada carga viva por su factor de participación. False si faltan datos."""
    vivas = [("Carga viva de entrepisos", cu.get("viva_entrepiso"), cu.get("phi_entrepiso")),
             ("Carga viva de áreas comunes", cu.get("viva_comun"), cu.get("phi_comun")),
             ("Carga viva de techo", cu.get("viva_techo"), cu.get("phi_techo"))]
    if cu.get("muerta") is None or not any(v is not None for _, v, _ in vivas):
        return False
    rows = [["Carga muerta", fmt(cu["muerta"]), "1.00", fmt(cu["muerta"])]]
    for rotulo, carga, phi in vivas:
        rows.append([rotulo, fmt(carga), fmt(phi), fmt(carga * phi) if carga is not None and phi is not None else "—"])
    rows.append(["Peso sísmico total W", "", "", fmt(cu.get("total"))])
    tabla(["Carga", "Total del edificio (ton)", "Factor de participación φ", "Entra en W (ton)"], rows,
          widths=[5.6, 4.0, 4.0, 3.6], aligns=["l", "c", "c", "c"], size=9, titulo="Peso sísmico: cargas muertas y vivas consideradas")
    nota("W = carga muerta + Σ φ · carga viva. La carga muerta entra completa; de cada carga viva solo participa la "
         "fracción φ. «—»: la hoja no trae carga para ese uso.")
    return True


# ------------------------------------------------------------------ fundaciones, observaciones, anexo
TON_M2_A_KG_CM2 = 0.1
TOLERANCIA_DESPEGUE = 0.01               # ton/m²: por debajo es ruido numérico
FC_EN_NOMBRE = re.compile(r"(?<!\d)(\d{3})(?!\d)")
FC_RAZONABLE = (140, 700)                # kg/cm²
TOLERANCIA_FC = 5                        # kg/cm²


def fundaciones_del_modelo(num, S, q_adm, mostrar=None):
    """Tablas del capítulo de fundaciones a partir del modelo de SAFE (tonf y metros)."""
    h("%d.1  Modelo de fundaciones" % num, 2)
    kv([(k_, v_) for k_, v_ in [
        ("Modelo de SAFE", "%s (%s)" % (S.get("modelo") or S.get("archivo") or "—", S.get("version") or "SAFE")),
        ("Código de diseño", S.get("codigo")),
        ("Concretos", " · ".join("%s: f'c = %s kg/cm²" % (k_, fmt(v_ * TON_M2_A_KG_CM2, 0))
                                 for k_, v_ in (S.get("concretos") or {}).items())),
        ("Suelo", " · ".join("%s: k = %s ton/m³ (%s)" % (r["name"], fmt(r["k"], 0), r.get("tipo") or "lineal")
                             for r in S.get("resortes") or [])),
        ("Áreas apoyadas en el suelo", str(S["areas_con_resorte"]) if S.get("areas_con_resorte") else None),
        ("Patrones de carga", ", ".join(p[0] for p in S.get("patrones") or []))] if v_], w1=5.8, w2=11.4, size=9)
    en_uso = S.get("losas_en_uso")
    rows = [[l["name"], l["tipo"], l["mat"], fmt(l["t"] * 100, 0)] for l in S.get("losas") or []
            if en_uso is None or l["name"] in en_uso]
    tabla(["Propiedad", "Tipo", "Material", "Espesor (cm)"], rows, widths=[4.3, 4.3, 4.3, 4.3], size=9,
          aligns=["l", "l", "c", "c"], titulo="Espesores de zapatas y losas de fundación")

    h("%d.2  Presiones sobre el suelo" % num, 2)
    pres = [p for p in S.get("presiones") or [] if p.get("min") is not None]
    if mostrar:
        faltan = [c for c in mostrar if c not in {p["combo"] for p in pres}]
        if faltan:
            OBS.append("Fundaciones: memoria.json pide mostrar combinaciones que el modelo no tiene: %s." % ", ".join(faltan))
        pres = [p for p in pres if p["combo"] in mostrar]
    rows, exceden, traccion = [], [], []
    for p in pres:
        q = -p["min"]
        if p.get("envolvente_de"):
            m_ = p["envolvente_de"]
            terminos = "Envolvente de %s" % (m_[0] if len(m_) == 1 else "%s a %s (%d combinaciones)" % (m_[0], m_[-1], len(m_)))
        else:
            terminos = " + ".join("%s %s" % (fmt(sf, 2), nombre) for nombre, sf in (S.get("combos") or {}).get(p["combo"], []))
        estado = "—" if not q_adm else ("Cumple" if q <= q_adm else "Excede")
        if q_adm and q > q_adm:
            exceden.append((p["combo"], q))
        if p["max"] > TOLERANCIA_DESPEGUE:
            traccion.append(p["combo"])
        rows.append([p["combo"], terminos or "—", fmt(q, 2), fmt(q * TON_M2_A_KG_CM2, 2), estado])
    tabla(["Combinación", "Expresión", "q máx. (ton/m²)", "q máx. (kg/cm²)", "Frente al admisible"], rows,
          widths=[2.4, 6.6, 2.7, 2.7, 2.8], size=8.5, aligns=["l", "l", "c", "c", "c"],
          titulo="Presión máxima de contacto por combinación")
    nota("Presión máxima de compresión entre todos los nudos de la malla."
         + (" Esfuerzo admisible: %s ton/m² (%s kg/cm²)." % (fmt(q_adm, 1), fmt(q_adm * TON_M2_A_KG_CM2, 2)) if q_adm
            else " No se indicó el esfuerzo admisible en memoria.json, así que no se compara."))
    if exceden:
        peor = max(exceden, key=lambda x: x[1])
        OBS.append("Fundaciones: %d combinación(es) de servicio superan el esfuerzo admisible de %s ton/m²; la mayor es "
                   "%s con %s ton/m² (%s kg/cm²). Verificar si a las combinaciones con sismo les corresponde un "
                   "admisible incrementado." % (len(exceden), fmt(q_adm, 1), peor[0], fmt(peor[1], 2),
                                                fmt(peor[1] * TON_M2_A_KG_CM2, 2)))
    if traccion:
        OBS.append("Fundaciones: hay presión positiva (despegue) en %d combinación(es): %s."
                   % (len(traccion), ", ".join(traccion[:8])))

    h("%d.3  Diseño de la losa de fundación" % num, 2)
    pz, fr = S.get("punzonado") or {}, S.get("franjas") or {}
    kv([("Puntos de punzonado", "%d · calculados: %d · sin calcular: %d"
         % (pz.get("n", 0), pz.get("calculados", 0), pz.get("sin_calcular", 0))),
        ("Relación máxima de punzonado", fmt(pz.get("max"), 3)),
        ("Franjas de diseño", "%d franjas · %d estaciones" % (fr.get("n", 0), fr.get("estaciones", 0))),
        ("Estado de las estaciones", " · ".join("%s: %d" % kv_ for kv_ in sorted((fr.get("estados") or {}).items())) or "—")],
       w1=5.8, w2=11.4, size=9)
    if pz.get("n") and not pz.get("calculados"):
        OBS.append("Fundaciones: SAFE no calculó el punzonado en ninguno de los %d puntos (estado «Not Calculated»)."
                   % pz["n"])
    if pz.get("mayores_que_1"):
        OBS.append("Fundaciones: %d punto(s) con relación de punzonado mayor que 1.00 (máximo %s)."
                   % (pz["mayores_que_1"], fmt(pz.get("max"), 3)))
    malas = {k_: v_ for k_, v_ in (fr.get("estados") or {}).items() if k_ != "OK"}
    if malas:
        OBS.append("Fundaciones: estaciones de franja con estado distinto de OK: %s."
                   % ", ".join("%s (%d)" % kv_ for kv_ in sorted(malas.items())))
    portada = C.get("portada") or {}
    palabras = [w for w in re.findall(r"\w+", ("%s %s" % (portada.get("titulo") or "", portada.get("subtitulo") or "")).lower())
                if len(w) > 3]
    if S.get("proyecto") and palabras and not any(w in S["proyecto"].lower() for w in palabras):
        OBS.append("Fundaciones: el modelo de SAFE lleva como nombre de proyecto «%s»." % S["proyecto"])
    for nombre, fc in (S.get("concretos") or {}).items():
        m_fc = FC_EN_NOMBRE.search(nombre)
        if m_fc and FC_RAZONABLE[0] <= int(m_fc.group(1)) <= FC_RAZONABLE[1] \
                and abs(int(m_fc.group(1)) - fc * TON_M2_A_KG_CM2) > TOLERANCIA_FC:
            OBS.append("Fundaciones: el material «%s» de SAFE tiene f'c = %s kg/cm², distinto de lo que indica su nombre."
                       % (nombre, fmt(fc * TON_M2_A_KG_CM2, 0)))


def cap_fundaciones(num):
    from PIL import Image, ImageChops
    F = C.get("fundaciones") or {}
    del_pdf = REF and F.get("figuras_del_pdf") and PDF_OK
    if REF and F.get("figuras_del_pdf") and not PDF_OK:
        OBS.append("Fundaciones: no se encontró el PDF de referencia; sus figuras no se incluyeron.")
    S = D.get("fundaciones") or {}
    if not (F.get("texto") or F.get("figuras") or del_pdf or S):
        return False
    h("%d  Fundaciones" % num, cap=str(num))
    if F.get("texto"):
        par(F["texto"])
    if S:
        fundaciones_del_modelo(num, S, F.get("esfuerzo_admisible_ton_m2"), F.get("combinaciones"))
    if del_pdf:
        pdf = pymupdf.open(REF_PDF)
        n = pdf.page_count
        for k, pno in enumerate(range(max(n - 2, 0), n), 1):
            pix = pdf[pno].get_pixmap(dpi=220)
            path = os.path.join(TMP, "safe_%d.png" % k)
            pix.save(path)
            im = Image.open(path).convert("RGB")
            w0, h0 = im.size
            cuerpo = im.crop((0, int(h0 * 0.075), w0, h0))
            r_, g_, b_ = cuerpo.split()
            sat = ImageChops.subtract(ImageChops.lighter(ImageChops.lighter(r_, g_), b_),
                                      ImageChops.darker(ImageChops.darker(r_, g_), b_))
            bbox = sat.point(lambda v: 255 if v > 60 else 0).getbbox()
            if bbox:
                m = 70
                cuerpo = cuerpo.crop((max(bbox[0] - m, 0), max(bbox[1] - m, 0), min(bbox[2] + m, cuerpo.size[0]), min(bbox[3] + m, cuerpo.size[1])))
            cuerpo.save(path)
            texto = pdf[pno].get_text()
            caso = "envolvente" if "Envelope" in texto else ("combinación Comb2" if "Comb2" in texto else "")
            figura(path, ANCHO, "Presiones de suelo en SAFE%s (kgf/cm²) — página %d de la memoria original"
                   % (", " + caso if caso else "", pno + 1), alto_max=8.0)
    for f in F.get("figuras") or []:
        p = img(f.get("ruta"))
        if p:
            figura(p, ANCHO, f["titulo"], alto_max=9.5)
        else:
            reserva(f["titulo"], 8.0)
    return True


def cap_observaciones(num):
    for b in D["bloques"]:
        m = b["etabs"].get("modelo") or ""
        letra = b["nombre"].replace("Bloque ", "")
        if REF and not re.search(r"Bloque %s$" % re.escape(letra), m):
            OBS.append("%s: el reporte de ETABS identifica el modelo como «%s»." % (b["nombre"], m))
        if b["etabs"].get("tiene_viento") is False:
            OBS.append("%s: el modelo de ETABS no define ningún patrón de carga de viento." % b["nombre"])
        sin_valor = sum(j.get("bc_sin_valor", 0) for j in b["etabs"].get("joint", {}).values())
        if sin_valor:
            OBS.append("%s: en %d nudo(s) ETABS indica que la relación de capacidad viga/columna excede el límite "
                       "sin reportar su valor; el máximo de la tabla solo considera los nudos con valor."
                       % (b["nombre"], sin_valor))
        if b["etabs"].get("origen_diseno") == "recalculado" and b["etabs"].get("version"):
            OBS.append("%s: análisis y diseño recalculados con %s sobre una copia del modelo; pueden diferir de los "
                       "de la versión con que se guardó." % (b["nombre"], b["etabs"]["version"]))
    for nombre in FALTAN_IMG:
        OBS.append("No se encontró la imagen «%s» indicada en memoria.json." % nombre)
    omitir = C.get("observaciones_omitir", [])
    todas, seen = [], set()
    for o in [x for x in C.get("observaciones_extra", []) + D["avisos"] + OBS if x and x.strip()]:
        if o not in seen and not any(x and x in o for x in omitir):
            seen.add(o)
            todas.append(o)
    if not todas:
        return 0
    h("%d  Observaciones para revisión" % num, cap=str(num))
    par("Al %s se detectaron los puntos siguientes. No se corrigió ningún valor: se listan para que "
        "el ingeniero responsable los confirme o ajuste antes de emitir el documento."
        % ("condensar la memoria" if REF else "reunir los datos de los distintos programas"))
    por_bloque = {b["nombre"]: [] for b in D["bloques"]}
    generales = []
    for o in todas:
        dueno = next((n for n in por_bloque if o.startswith(n + ":")), None)
        if dueno:
            por_bloque[dueno].append(o[len(dueno) + 1:].strip())
        else:
            generales.append(o)
    grupos = [("Generales", generales)] + list(por_bloque.items())
    k = 0
    for titulo, items in grupos:
        if not items:
            continue
        k += 1
        h("%d.%d  %s" % (num, k, titulo), 2)
        bullets([it[0].upper() + it[1:] for it in items], size=10.5)
    return len(todas)


def cap_anexo(letra):
    figs = C.get("anexo_figuras", [])
    if not figs:
        return
    h("Anexo %s  Planos y vistas complementarias" % letra, cap=letra)
    par("Planos y vistas de apoyo a la memoria. Los espacios reservados se completan indicando la ruta de la imagen en "
        "memoria.json o insertándola directamente en este documento.")
    for f in figs:
        p = img(f.get("ruta"))
        if p:
            figura(p, ANCHO, f["titulo"], alto_max=10.5)
        else:
            reserva(f["titulo"], 8.6)


COLOR_ESTADO = {"Falta": "F4D6D2", "Parcial": "FBEBD0"}


def cap_cruce_mivhed(letra):
    """Anexo con el cruce del checklist de Estructura del MIVHED, si memoria.json indica el checklist."""
    ruta = C.get("checklist_mivhed")
    if not ruta:
        return False
    import cruce_mivhed as cm

    if not os.path.isabs(ruta):
        ruta = os.path.join(os.path.dirname(os.path.abspath(CFG_PATH)), ruta)
    try:
        cl = cm.cargar_checklist(ruta)
    except (OSError, ValueError, cm.ErrorDeChecklist) as e:       # va después de las observaciones: se avisa aquí
        sys.stderr.write("AVISO: no se pudo leer el checklist del MIVHED (%s); se omite el anexo.\n" % e)
        return False
    todas = cm.cruzar(D, C, cl)
    filas = [f for f in todas if f["estado"] != cm.PLANOS]
    r = cm.resumen(todas)
    h("Anexo %s  Cruce con el checklist de Estructura del MIVHED" % letra, cap=letra)
    par("Cruce automático de esta memoria con el checklist %s, versión %s, publicado el %s. Cada ítem se evaluó con lo "
        "leído de los modelos, las hojas de cálculo y los datos del proyecto. No sustituye la evaluación del MIVHED ni "
        "la del ingeniero responsable; los ítems de planos (%d) quedan fuera."
        % (cl.get("codigo"), cl.get("version"), (cl.get("publicadoEn") or "")[:10], r[cm.PLANOS]), size=10)
    nota("Resumen: " + " · ".join("%s %d" % (e, n) for e, n in r.items() if n and e != cm.PLANOS) + ".")
    t = tabla(["Ítem", "Requisito", "Estado", "Nota"],
              [[str(f["numero"]), f["requisito"], f["estado"],
                f["nota"] + ("" if not f["motivos"] else " Motivo%s %s." % (
                    "s" if len(f["motivos"]) > 1 else "", ", ".join(c for c, _ in f["motivos"])))] for f in filas],
              widths=[1.1, 5.2, 1.8, 9.1], aligns=["c", "l", "c", "l"], size=8, titulo="Estado por ítem del checklist")
    for i, f in enumerate(filas, start=1):
        if f["estado"] in COLOR_ESTADO:
            shade(t.rows[i].cells[2], COLOR_ESTADO[f["estado"]])
    return True


# ------------------------------------------------------------------ principal
configurar()
portada()
hoja_control()
indice()
num = 1
cap_proyecto(num)
if len(D["sobrecarga"]) == 2:
    num += 1
    cap_cargas(num)
elif D["sobrecarga"]:
    OBS.append("Cargas: se esperaban dos hojas de sobrecarga (entrepiso y techo) y llegaron %d; el capítulo se omitió."
               % len(D["sobrecarga"]))
if D["niveles"]:
    num += 1
    cap_losas(num)
for i, b in enumerate(D["bloques"]):
    num += 1
    cap_bloque(num, b, i)
if cap_fundaciones(num + 1):
    num += 1
n_obs = cap_observaciones(num + 1)
cap_anexo("A")
cap_cruce_mivhed("B" if C.get("anexo_figuras") else "A")
doc.save(OUT)
print("guardado", OUT, "observaciones", n_obs)
