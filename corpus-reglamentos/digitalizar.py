"""Extracción trazable de textos oficiales. No interpreta fórmulas ni vigencia."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def page_record(number: int, text: str) -> dict:
    # Preserve the extraction verbatim apart from line-ending normalization.
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    flags = []
    if not text.strip():
        flags.append('sin_texto_revisar_imagen')
    elif sum(c.isalnum() for c in text) < 80:
        flags.append('texto_escaso_revisar_imagen')
    if '\ufffd' in text:
        flags.append('caracteres_no_decodificados')
    return {'page_pdf': number, 'printed_page': None, 'text': text,
            'text_sha256': sha256(text.encode('utf-8')), 'quality_flags': flags,
            'visually_verified': False}


def ocr_page(pdf, index: int) -> str:
    # Render sequentially: PDFium is not thread-safe. OCR remains local.
    with tempfile.TemporaryDirectory(prefix='cdcrd-ocr-') as folder:
        image_path = Path(folder) / 'page.png'
        page = pdf[index]
        try:
            bitmap = page.render(scale=250 / 72)
            try:
                bitmap.to_pil().save(image_path)
            finally:
                bitmap.close()
        finally:
            page.close()
        result = subprocess.run(['tesseract', str(image_path), 'stdout', '-l', 'spa+eng', '--psm', '3'],
                                check=True, capture_output=True, text=True, encoding='utf-8',
                                timeout=120, env={**os.environ, 'OMP_THREAD_LIMIT': '1'})
        return result.stdout


def extract(source: dict, library: Path, use_ocr: bool = False) -> dict:
    from pypdf import PdfReader
    path = (library / source['file']).resolve()
    if not path.is_relative_to(library.resolve()):
        raise ValueError('La fuente debe estar dentro de la biblioteca')
    if sha256(path.read_bytes()) != source['sha256']:
        raise ValueError(f"SHA-256 distinto del inventario: {source['id']}")
    reader = PdfReader(path)
    if len(reader.pages) != source['pages']:
        raise ValueError(f"Conteo de páginas distinto: {source['id']}")
    pages = []
    pdf = None
    try:
        if use_ocr:
            import pypdfium2
            pdf = pypdfium2.PdfDocument(path)
        for i, page in enumerate(reader.pages):
            native = page.extract_text() or ''
            record = page_record(i + 1, native)
            record['method'] = 'pypdf_text_layer'
            if pdf is not None and sum(c.isalnum() for c in native) < 80:
                record = page_record(i + 1, ocr_page(pdf, i))
                record['method'] = 'tesseract_spa_eng_250dpi'
                record['native_text'] = native
                record['quality_flags'].append('ocr_generado_requiere_revision')
                print(f"OCR {source['id']} página {i + 1}", flush=True)
            pages.append(record)
    finally:
        if pdf is not None:
            pdf.close()
    return {'schema': 'cdcrd-regulation/1', 'source': source,
            'extraction_method': 'pypdf text layer + optional local Tesseract OCR on sparse pages',
            'review_status': 'texto_extraido_no_validado_para_calculo',
            'pages': pages}


def render_markdown(doc: dict) -> str:
    source = doc['source']
    lines = [f"# {source['id']} — {source['title']}", '',
             '> Texto extraído automáticamente. Tablas, fórmulas, símbolos y OCR requieren cotejo con el PDF.',
             '> La numeración citada es la página del PDF (base 1), no la página impresa. Vigencia no evaluada.',
             '', f"SHA-256 del PDF: `{source['sha256']}`", '']
    if source.get('document_warning'):
        lines.extend([f"> {source['document_warning']}", ''])
    for page in doc['pages']:
        lines.extend([f"## Página PDF {page['page_pdf']}", ''])
        if page['quality_flags']:
            lines.extend(['> Revisar: ' + ', '.join(page['quality_flags']), ''])
        lines.extend([page['text'], ''])
    return '\n'.join(lines)


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def build(library: Path, sources_path: Path, output: Path, use_ocr: bool = False) -> dict:
    import pypdf
    config = json.loads(sources_path.read_text(encoding='utf-8'))
    sources = config['sources']
    if len({s['id'] for s in sources}) != len(sources) or len({s['sha256'] for s in sources}) != len(sources):
        raise ValueError('Fuentes duplicadas por ID o SHA-256')
    for source in sources:
        if not source['id'] or any(c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-' for c in source['id']):
            raise ValueError('ID de documento no válido')
    output.mkdir(parents=True, exist_ok=True)
    manifest = {'schema': 'cdcrd-regulations-manifest/1', 'pypdf_version': pypdf.__version__,
                'sources_sha256': sha256(sources_path.read_bytes()), 'documents': [],
                'review_status': 'texto_extraido_no_validado_para_calculo'}
    if use_ocr:
        import pypdfium2
        manifest['ocr'] = {'engine': subprocess.run(['tesseract', '--version'], check=True,
                           capture_output=True, text=True).stdout.splitlines()[0],
                           'pdfium': str(pypdfium2.PYPDFIUM_INFO), 'dpi': 250, 'languages': 'spa+eng'}
    for source in sources:
        doc = extract(source, library, use_ocr)
        json_path, md_path = output / (source['id'] + '.json'), output / (source['id'] + '.md')
        write_json(json_path, doc)
        md_path.write_text(render_markdown(doc), encoding='utf-8')
        row = {'id': source['id'], 'pages': len(doc['pages']), 'pdf_sha256': source['sha256'],
               'flagged_pages': [p['page_pdf'] for p in doc['pages'] if p['quality_flags']],
               'ocr_pages': [p['page_pdf'] for p in doc['pages'] if p['method'].startswith('tesseract')],
               'json': json_path.name, 'json_sha256': sha256(json_path.read_bytes()),
               'markdown': md_path.name, 'markdown_sha256': sha256(md_path.read_bytes())}
        manifest['documents'].append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    manifest['total_documents'] = len(sources)
    manifest['total_pages'] = sum(d['pages'] for d in manifest['documents'])
    write_json(output / 'manifest.json', manifest)
    return manifest


def verify(output: Path) -> dict:
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    for row in manifest['documents']:
        for key in ('json', 'markdown'):
            if sha256((output / row[key]).read_bytes()) != row[key + '_sha256']:
                raise ValueError(f"Hash de salida incorrecto: {row['id']} {key}")
        doc = json.loads((output / row['json']).read_text(encoding='utf-8'))
        if [p['page_pdf'] for p in doc['pages']] != list(range(1, row['pages'] + 1)):
            raise ValueError(f"Páginas no contiguas: {row['id']}")
        for page in doc['pages']:
            if sha256(page['text'].encode('utf-8')) != page['text_sha256']:
                raise ValueError(f"Hash de texto incorrecto: {row['id']}")
    if manifest['total_pages'] != sum(d['pages'] for d in manifest['documents']):
        raise ValueError('Total de páginas incorrecto')
    if manifest['total_documents'] != len(manifest['documents']):
        raise ValueError('Total de documentos incorrecto')
    return {'documents': manifest['total_documents'], 'pages': manifest['total_pages'], 'integrity': 'ok'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path)
    parser.add_argument('--sources', type=Path, default=Path(__file__).with_name('sources.json'))
    parser.add_argument('--output', type=Path, default=Path(__file__).with_name('data'))
    parser.add_argument('--verify', action='store_true')
    parser.add_argument('--ocr', action='store_true', help='OCR local en español/inglés de páginas con texto escaso')
    args = parser.parse_args()
    if args.verify:
        print(json.dumps(verify(args.output)))
    elif args.library:
        build(args.library, args.sources, args.output, args.ocr)
    else:
        parser.error('--library es obligatorio para extraer')


if __name__ == '__main__':
    main()
