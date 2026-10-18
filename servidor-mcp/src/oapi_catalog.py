"""Offline discovery of CSI API signatures recovered with REA."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def _catalog() -> dict:
    return json.loads((Path(__file__).parent.parent / 'docs' / 'oapi-catalog.json').read_text(encoding='utf-8'))


def search_oapi_catalog(query: str = '', limit: int = 30, offset: int = 0) -> str:
    """Busca firmas CSI sin conectar a ETABS. No confirma soporte en el modelo.

    query: parte del nombre de interfaz o método (p. ej. JointDispl, cPropArea).
    limit: entre 1 y 100. offset: posición para continuar la consulta.
    Las firmas REF (&) requieren describe_oapi para nombres y dirección COM.
    """
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('limit debe ser un entero entre 1 y 100')
    if type(offset) is not int or offset < 0:
        raise ValueError('offset debe ser un entero no negativo')
    data = _catalog()
    terms = query.casefold().split()
    matches = [row for row in data['methods']
               if all(term in (row['interface'] + '.' + row['name']).casefold() for term in terms)]
    end = offset + limit
    return json.dumps({'artifact': data['artifact'], 'runtime_verified': False,
                       'scope': data['scope'], 'total_matches': len(matches),
                       'offset': offset, 'next_offset': end if end < len(matches) else None,
                       'methods': matches[offset:end]}, ensure_ascii=False)
