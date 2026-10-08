"""Inspeccion PDF y preview local de una pagina con PDFium."""

from pathlib import Path


def inspect_pdf(source: Path) -> dict:
    import pdfplumber

    with pdfplumber.open(source) as document:
        pages = [{"number": number, "width_points": page.width,
                  "height_points": page.height}
                 for number, page in enumerate(document.pages, 1)]
        first_text = (document.pages[0].extract_text() or "")[:1000] if pages else ""
    return {"pages": pages, "page_count": len(pages), "first_page_excerpt": first_text,
            "scope": "Texto/medidas PDF; no recupera dimensiones de modelo ni objetos BIM."}


def preview_pdf(source: Path, output: Path, page: int = 1, dpi: int = 120) -> dict:
    import pypdfium2 as pdfium

    if output.suffix.lower() != ".png":
        raise ValueError("La preview PDF debe tener extension .png.")
    if not 36 <= dpi <= 300:
        raise ValueError("Resolucion permitida: 36..300 DPI.")
    with pdfium.PdfDocument(source) as document:
        if not 1 <= page <= len(document):
            raise ValueError("Pagina fuera del documento (numeracion desde 1).")
        pdf_page = document[page - 1]
        width, height = pdf_page.get_size()
        if width * height * (dpi / 72) ** 2 > 50_000_000:
            pdf_page.close()
            raise ValueError("La pagina produciria mas de 50 millones de pixeles.")
        try:
            bitmap = pdf_page.render(scale=dpi / 72)
            try:
                image = bitmap.to_pil()
                output.parent.mkdir(parents=True, exist_ok=True)
                with output.open("xb") as stream:
                    identity = output.stat()
                    try:
                        image.save(stream, format="PNG")
                    except BaseException:
                        stream.close()
                        if output.exists():
                            current = output.stat()
                            if (identity.st_dev, identity.st_ino) == (
                                current.st_dev, current.st_ino
                            ):
                                output.unlink()
                        raise
                dimensions = image.size
            finally:
                bitmap.close()
        finally:
            pdf_page.close()
    return {"output": str(output), "page": page, "dpi": dpi,
            "width_pixels": dimensions[0], "height_pixels": dimensions[1]}
