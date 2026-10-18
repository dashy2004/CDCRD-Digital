"""Búsqueda por página con referencia y advertencia de calidad."""
import argparse
import json
from pathlib import Path
import unicodedata


def normalized(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', text.casefold())
                   if not unicodedata.combining(c))


def search(query: str, data: Path | None = None, limit: int = 10, offset: int = 0) -> dict:
    if not query.strip():
        raise ValueError('Escriba una consulta no vacía')
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or offset < 0:
        raise ValueError('limit debe ser 1..100 y offset no negativo')
    data = data or Path(__file__).with_name('data')
    manifest = json.loads((data / 'manifest.json').read_text(encoding='utf-8'))
    terms = normalized(query).split()
    matches = []
    for item in manifest['documents']:
        doc = json.loads((data / item['json']).read_text(encoding='utf-8'))
        for page in doc['pages']:
            text = page['text']
            folded = normalized(text)
            if all(t in folded for t in terms):
                # Return the whole matching page to preserve immediate context;
                # pagination bounds output without silently truncating the page.
                matches.append({'document': item['id'], 'title': doc['source']['title'],
                                'page_pdf': page['page_pdf'], 'pdf_sha256': item['pdf_sha256'],
                                'quality_flags': page['quality_flags'],
                                'legal_status': doc['source']['legal_status'],
                                'document_warning': doc['source'].get('document_warning'),
                                'text': text})
    end = offset + limit
    return {'warning': 'Extracción automática; cotejar cifras, tablas y fórmulas con el PDF original.',
            'total_matches': len(matches), 'offset': offset,
            'next_offset': end if end < len(matches) else None, 'results': matches[offset:end]}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('query')
    parser.add_argument('--limit', type=int, default=10)
    parser.add_argument('--offset', type=int, default=0)
    args = parser.parse_args()
    print(json.dumps(search(args.query, limit=args.limit, offset=args.offset), ensure_ascii=False, indent=2))
