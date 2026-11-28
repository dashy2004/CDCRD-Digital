"""Rendering regressions use only fictitious data and generated local PDFs."""

from pathlib import Path
from zipfile import ZipFile

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject, TextStringObject
from reportlab.pdfgen.canvas import Canvas

from cdcrd_memoria.renderers import RenderError, render_docx, render_html, render_pdf


@pytest.fixture
def view():
    return {"title": "Memoria de diseño del ejemplo", "subtitle": "Expediente sintético para revisión",
        "project_id": "DEMO-001", "revision": "R00", "document_status": "draft", "engineering_approval": False,
        "sections": [{"title": "Resultados disponibles", "paragraphs": [
            "Valor transcrito con precisión original y unidad explícita.",
            '<script>alert("x")</script> & prueba <b>literal</b>',
        ], "tables": [{"title": "Resultados", "columns": ["Magnitud", "Valor", "Unidad"],
            "rows": [["Carga", "123.4567890123", "kN"], ["Dato ausente", "Pendiente", "kPa"]]}]}],
        "annexes": []}


def make_annex(path: Path, pages: int = 3) -> None:
    canvas = Canvas(str(path))
    for number in range(1, pages + 1):
        canvas.drawString(60, 700, f"Original page {number}")
        canvas.showPage()
    canvas.save()


def test_html_escapes_text_and_retains_precision(view, tmp_path):
    path = tmp_path / "memory.html"
    render_html(view, path)
    text = path.read_text(encoding="utf-8")
    assert "<script>" not in text
    assert "&lt;script&gt;" in text
    assert "123.4567890123" in text
    assert 'scope="col"' in text
    assert "Content-Security-Policy" in text
    assert "default-src 'none'" in text


def test_docx_editable_fields_headers_and_title(view, tmp_path):
    path = tmp_path / "memory.docx"
    render_docx(view, path)
    with ZipFile(path) as package:
        document = package.read("word/document.xml").decode()
        footer = package.read("word/footer1.xml").decode()
        styles = package.read("word/styles.xml").decode()
        assert "123.4567890123" in document
        assert 'w:pStyle w:val="Title"' in document
        assert "tblHeader" in document
        assert 'w:instr="PAGE"' in footer
        assert 'w:instr="NUMPAGES"' in footer
        assert "&lt;script&gt;" in document
        assert 'w:fill="DCE6F1"' in document
        assert 'w:color="D9D9D9"' in document
        assert 'w:w="12240" w:h="15840"' in document
        assert "Arial" in styles


@pytest.mark.parametrize("renderer,extension", [(render_html, "html"), (render_docx, "docx"), (render_pdf, "pdf")])
def test_output_is_never_overwritten(renderer, extension, view, tmp_path):
    path = tmp_path / f"existing.{extension}"
    path.write_bytes(b"protected")
    with pytest.raises(FileExistsError):
        renderer(view, path)
    assert path.read_bytes() == b"protected"


def test_pdf_content_and_selected_appendices(view, tmp_path):
    source = tmp_path / "source.pdf"
    make_annex(source)
    before = source.read_bytes()
    view["annexes"] = [{"id": "A1", "title": "Informe de ejemplo", "source_id": "S1", "pages": [3, 1]}]
    path = tmp_path / "memory.pdf"
    result = render_pdf(view, path, {"S1": source})
    pdf = PdfReader(path)
    assert len(pdf.pages) == result["body_pages"] + 2 == result["total_pages"]
    assert result["annexes"][0]["first_page"] == result["body_pages"] + 1
    assert result["annexes"][0]["last_page"] == result["total_pages"]
    body = "\n".join(page.extract_text() for page in pdf.pages[:result["body_pages"]])
    assert "123.4567890123" in body
    assert '<script>alert("x")</script>' in body
    assert "Original page 3" in pdf.pages[-2].extract_text()
    assert "Original page 1" in pdf.pages[-1].extract_text()
    assert "Original page 2" not in "\n".join(p.extract_text() for p in pdf.pages)
    assert f"Página {result['total_pages']} de {result['total_pages']}" in pdf.pages[-1].extract_text()
    assert len(pdf.outline) == 2
    assert pdf.get_destination_page_number(pdf.outline[1]) == result["body_pages"]
    assert float(pdf.pages[-1].mediabox.height) == pytest.approx(float(PdfReader(source).pages[0].cropbox.height) + 24)
    assert source.read_bytes() == before


def test_appendix_actions_annotations_and_embedded_files_do_not_propagate(view, tmp_path):
    source = tmp_path / "active.pdf"
    base = tmp_path / "base.pdf"
    make_annex(base, 1)
    writer = PdfWriter()
    page = writer.add_page(PdfReader(base).pages[0])
    action = DictionaryObject({NameObject("/S"): NameObject("/JavaScript"), NameObject("/JS"): TextStringObject("app.alert('x')")})
    page[NameObject("/AA")] = DictionaryObject({NameObject("/O"): action})
    page[NameObject("/Annots")] = ArrayObject([DictionaryObject({NameObject("/Subtype"): NameObject("/Link"), NameObject("/A"): action})])
    writer._root_object[NameObject("/OpenAction")] = action
    writer.add_attachment("do-not-copy.txt", b"private attachment")
    with source.open("wb") as stream:
        writer.write(stream)
    view["annexes"] = [{"id": "A1", "title": "Documento", "source_id": "S1", "pages": None}]
    target = tmp_path / "clean.pdf"
    render_pdf(view, target, {"S1": source})
    result = PdfReader(target)
    assert not result.attachments
    assert "/OpenAction" not in result.trailer["/Root"]
    assert "/AA" not in result.pages[-1]
    assert not result.pages[-1].get("/Annots")
    assert b"app.alert" not in target.read_bytes()


def test_rejects_visible_form_field_without_losing_its_value(view, tmp_path):
    source = tmp_path / "form.pdf"
    canvas = Canvas(str(source))
    canvas.drawString(60, 750, "Formulario de resultados")
    canvas.acroForm.textfield(name="reaction", value="Fz = 123 kN", x=60, y=700)
    canvas.showPage()
    canvas.save()
    before = source.read_bytes()
    assert PdfReader(source).get_fields()["reaction"]["/V"] == "Fz = 123 kN"
    view["annexes"] = [{"id": "A1", "title": "Formulario", "source_id": "S1", "pages": None}]
    output = tmp_path / "out.pdf"
    with pytest.raises(RenderError, match="anotaciones con apariencia"):
        render_pdf(view, output, {"S1": source})
    assert not output.exists()
    assert source.read_bytes() == before


@pytest.mark.parametrize("subtype", ["/FreeText", "/Stamp", "/UnknownFutureType", "/Link"])
def test_rejects_visible_or_unknown_annotation_types(view, tmp_path, subtype):
    source = tmp_path / "annotation.pdf"
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    annotation = DictionaryObject({
        NameObject("/Subtype"): NameObject(subtype),
        NameObject("/Contents"): TextStringObject("Fz = 123 kN"),
    })
    if subtype == "/Link":
        annotation[NameObject("/AP")] = DictionaryObject()
    page[NameObject("/Annots")] = ArrayObject([annotation])
    with source.open("wb") as stream:
        writer.write(stream)
    view["annexes"] = [{"id": "A1", "title": "Anotación", "source_id": "S1", "pages": None}]
    with pytest.raises(RenderError, match="anotaciones con apariencia"):
        render_pdf(view, tmp_path / "out.pdf", {"S1": source})


def test_plain_external_link_is_removed_and_page_text_preserved(view, tmp_path):
    source = tmp_path / "link.pdf"
    canvas = Canvas(str(source))
    canvas.drawString(60, 700, "Evidence value 123.456 kN")
    canvas.linkURL("https://example.com", (60, 680, 250, 720), thickness=0)
    canvas.showPage()
    canvas.save()
    view["annexes"] = [{"id": "A1", "title": "Enlace", "source_id": "S1", "pages": None}]
    output = tmp_path / "out.pdf"
    render_pdf(view, output, {"S1": source})
    page = PdfReader(output).pages[-1]
    assert "Evidence value 123.456 kN" in page.extract_text()
    assert not page.get("/Annots")
    assert b"https://example.com" not in output.read_bytes()


@pytest.mark.parametrize("pages", [[0], [4], [True], [], [1, 1]])
def test_invalid_appendix_page_selection(view, tmp_path, pages):
    source = tmp_path / "source.pdf"
    make_annex(source)
    view["annexes"] = [{"id": "A1", "title": "Documento", "source_id": "S1", "pages": pages}]
    with pytest.raises(RenderError):
        render_pdf(view, tmp_path / "out.pdf", {"S1": source})


@pytest.mark.parametrize("encrypted", [False, True])
def test_rejects_malformed_and_encrypted_pdfs(view, tmp_path, encrypted):
    source = tmp_path / "source.pdf"
    if encrypted:
        writer = PdfWriter()
        writer.add_blank_page(width=300, height=400)
        writer.encrypt("password")
        with source.open("wb") as stream:
            writer.write(stream)
    else:
        source.write_bytes(b"not a pdf")
    view["annexes"] = [{"id": "A1", "title": "Documento", "source_id": "S1", "pages": None}]
    with pytest.raises(RenderError):
        render_pdf(view, tmp_path / "out.pdf", {"S1": source})


def test_repeated_table_header_and_page_count_for_long_body(view, tmp_path):
    view["sections"][0]["tables"][0]["rows"] = [[f"Magnitud {i}", str(i), "kN"] for i in range(150)]
    output = tmp_path / "long.pdf"
    metadata = render_pdf(view, output)
    pdf = PdfReader(output)
    assert len(pdf.pages) >= 3
    assert metadata["body_pages"] == metadata["total_pages"] == len(pdf.pages)
    for number, page in enumerate(pdf.pages, 1):
        text = page.extract_text()
        assert "Magnitud" in text and "Unidad" in text
        assert f"Página {number} de {len(pdf.pages)}" in text


def test_cannot_claim_engineering_approval(view, tmp_path):
    view["engineering_approval"] = True
    for renderer, suffix in ((render_html, "html"), (render_docx, "docx"), (render_pdf, "pdf")):
        with pytest.raises(RenderError, match="aprobación"):
            renderer(view, tmp_path / f"wrong.{suffix}")


def test_empty_table_is_renderable(view, tmp_path):
    view["sections"][0]["tables"][0]["rows"] = []
    render_pdf(view, tmp_path / "empty.pdf")
    assert "Resultados" in PdfReader(tmp_path / "empty.pdf").pages[0].extract_text()


def test_rotated_appendix_retains_content_without_clipping(view, tmp_path):
    base = tmp_path / "base.pdf"
    source = tmp_path / "rotated.pdf"
    make_annex(base, 1)
    writer = PdfWriter()
    page = writer.add_page(PdfReader(base).pages[0])
    page.rotate(90)
    with source.open("wb") as stream:
        writer.write(stream)
    view["annexes"] = [{"id": "A1", "title": "Documento", "source_id": "S1", "pages": None}]
    output = tmp_path / "out.pdf"
    render_pdf(view, output, {"S1": source})
    result = PdfReader(output).pages[-1]
    assert "Original page 1" in result.extract_text()
    assert float(result.mediabox.width) > float(result.mediabox.height)
