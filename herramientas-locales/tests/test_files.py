"""Conversión PDF real y preservación de salidas previas."""

import pytest
from matplotlib.figure import Figure
from PIL import Image

from cdcrd_local.files import inspect_pdf, preview_pdf


@pytest.fixture
def pdf(tmp_path):
    source = tmp_path / "ejemplo.pdf"
    figure = Figure(figsize=(4, 3))
    figure.text(0.2, 0.5, "Ejemplo PDF CDCRD")
    figure.savefig(source)
    figure.clear()
    return source


def test_real_pdf_inspection_and_render(pdf, tmp_path):
    original = pdf.read_bytes()
    info = inspect_pdf(pdf)
    assert info["page_count"] == 1
    assert info["pages"][0]["width_points"] == pytest.approx(288)
    assert "Ejemplo PDF CDCRD" in info["first_page_excerpt"]
    output = tmp_path / "salidas" / "pagina.png"
    rendered = preview_pdf(pdf, output, dpi=72)
    with Image.open(output) as image:
        assert image.size == (288, 216)
    assert rendered["width_pixels"] == 288
    assert pdf.read_bytes() == original


@pytest.mark.parametrize("page,dpi,suffix", [(2, 72, ".png"), (1, 301, ".png"),
                                                (1, 72, ".jpg")])
def test_invalid_conversion_creates_no_output(pdf, tmp_path, page, dpi, suffix):
    output = tmp_path / ("invalid" + suffix)
    with pytest.raises(ValueError):
        preview_pdf(pdf, output, page, dpi)
    assert not output.exists()


def test_existing_preview_preserved(pdf, tmp_path):
    output = tmp_path / "previa.png"
    output.write_bytes(b"SALIDA ANTERIOR")
    with pytest.raises(FileExistsError):
        preview_pdf(pdf, output)
    assert output.read_bytes() == b"SALIDA ANTERIOR"


def test_failed_encoder_removes_only_new_output(pdf, tmp_path, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("fallo simulado de codificador")

    monkeypatch.setattr(Image.Image, "save", fail)
    output = tmp_path / "fallida.png"
    with pytest.raises(OSError):
        preview_pdf(pdf, output)
    assert not output.exists()
