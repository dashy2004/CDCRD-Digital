import importlib.util
import json
from pathlib import Path

import pytest
from pypdf import PdfWriter

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


digitalizar, buscar = load('digitalizar'), load('buscar')


@pytest.fixture
def source(tmp_path):
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    path = tmp_path / 'source.pdf'
    writer.write(path)
    return {'id': 'TEST', 'title': 'Documento sintético', 'file': path.name,
            'pages': 1, 'sha256': digitalizar.sha256(path.read_bytes()),
            'legal_status': 'vigencia_no_evaluada'}


def test_blank_page_preserved_with_warning(tmp_path, source):
    doc = digitalizar.extract(source, tmp_path)
    page = doc['pages'][0]
    assert page['page_pdf'] == 1 and page['printed_page'] is None
    assert 'sin_texto_revisar_imagen' in page['quality_flags']
    assert not page['visually_verified']


def test_pdf_hash_is_checked(tmp_path, source):
    source['sha256'] = '0' * 64
    with pytest.raises(ValueError, match='SHA-256'):
        digitalizar.extract(source, tmp_path)


def test_path_cannot_escape_library(tmp_path, source):
    source['file'] = '../elsewhere.pdf'
    with pytest.raises(ValueError, match='dentro'):
        digitalizar.extract(source, tmp_path)


def test_page_text_and_hash():
    page = digitalizar.page_record(2, 'Sísmico\r\nValor 0.003\rFin')
    assert page['text'] == 'Sísmico\nValor 0.003\nFin'
    assert digitalizar.sha256(page['text'].encode()) == page['text_sha256']


def test_build_integrity_and_tampering(tmp_path, source):
    config = tmp_path / 'sources.json'
    digitalizar.write_json(config, {'sources': [source]})
    output = tmp_path / 'data'
    digitalizar.build(tmp_path, config, output)
    assert digitalizar.verify(output) == {'documents': 1, 'pages': 1, 'integrity': 'ok'}
    (output / 'TEST.md').write_text('changed', encoding='utf-8')
    with pytest.raises(ValueError, match='Hash'):
        digitalizar.verify(output)


def test_duplicate_sources_rejected(tmp_path, source):
    config = tmp_path / 'sources.json'
    digitalizar.write_json(config, {'sources': [source, source]})
    with pytest.raises(ValueError, match='duplicadas'):
        digitalizar.build(tmp_path, config, tmp_path / 'data')


def test_search_accent_insensitive_and_cited(tmp_path, source):
    doc = {'source': source, 'pages': [digitalizar.page_record(1, 'Análisis sísmico de estructuras')]}
    digitalizar.write_json(tmp_path / 'TEST.json', doc)
    digitalizar.write_json(tmp_path / 'manifest.json', {'documents': [
        {'id': 'TEST', 'json':'TEST.json', 'pdf_sha256': source['sha256']}]})
    result = buscar.search('analisis sismico', tmp_path)
    assert result['total_matches'] == 1
    assert result['results'][0]['page_pdf'] == 1
    assert result['results'][0]['pdf_sha256'] == source['sha256']
    assert result['results'][0]['legal_status'] == 'vigencia_no_evaluada'


@pytest.mark.parametrize('kwargs', [{'query':' '}, {'query':'x', 'limit':0}, {'query':'x', 'offset':-1}])
def test_invalid_search(kwargs):
    with pytest.raises(ValueError): buscar.search(**kwargs)
