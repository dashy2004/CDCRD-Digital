from dataclasses import replace
from pathlib import Path
import json

import pytest

from puente_losas.dl_io import LosaDL, SistemaDL, cargar_dl, guardar_dl
from puente_losas.losas_legacy import preparar_legacy, leer_reporte, barras_por_nervio


def sistema():
    return SistemaDL('Cubierta de prueba', .210, 4.2, 0,
                     [LosaDL(1, 40, .72, .12, 3., 4., .02, 'L01')])


TXT = '''SISTEMA DE LOSAS : Cubierta de prueba
CÁLCULO DE MOMENTOS
1 40 0.720 12.0 3.000 4.000 1.000 2.000 3.000 4.000
CALCULO DE ARMADURAS
ARMADURAS SEGÚN "X"
1 9.50 1.000 2.160 Ø3/8" @ 30 cm 2.367
ARMADURAS SEGÚN "Y"
1 8.50 2.000 0.000 As > As max
'''


def test_legacy_copia_identica_y_nombre_corto(tmp_path):
    original = tmp_path/'entrada.DL'
    guardar_dl(sistema(), str(original))
    result = preparar_legacy(original, tmp_path/'corto', marcas={1: 'L01'})
    assert result.dl.name == 'SISTEMA.DL'
    assert result.dl.read_bytes() == original.read_bytes()
    assert result.txt == result.dl.with_suffix('.TXT')
    manifest = json.loads(result.manifiesto.read_text(encoding='utf-8'))
    assert manifest['origen'] == str(original.resolve())
    assert manifest['marcas'] == {'1': 'L01'}
    assert preparar_legacy(original, tmp_path/'corto', marcas={1: 'L01'}).dl == result.dl


def test_legacy_no_sobrescribe_edicion_manual(tmp_path):
    original = tmp_path/'entrada.DL'
    guardar_dl(sistema(), str(original))
    result = preparar_legacy(original, tmp_path/'corto')
    result.dl.write_text('edicion manual', encoding='ascii')
    with pytest.raises(FileExistsError):
        preparar_legacy(original, tmp_path/'corto')


def test_writer_conserva_acentos_sin_bom_y_crlf(tmp_path):
    path = tmp_path/'prueba.DL'
    guardar_dl(replace(sistema(), nombre='Losa técnica'), str(path))
    content = path.read_bytes()
    assert b't\xe9cnica' in content and not content.startswith(b'\xef\xbb\xbf')
    assert content.count(b'\r\n') == content.count(b'\n')
    assert cargar_dl(str(path)).nombre == 'Losa técnica'


def test_reporte_conserva_armadura_y_fallo_de_seccion():
    report = leer_reporte(TXT, sistema())
    assert len(report.momentos) == 1 and len(report.armaduras) == 2
    x, y = report.armaduras
    assert x.as_cm2_m == 2.160 and x.as_provista_cm2_m == 2.367
    assert x.disponer == 'Ø3/8" @ 30 cm'
    assert y.insuficiente and y.as_cm2_m is None
    assert y.disponer == 'As > As max'
    assert barras_por_nervio(y.as_cm2_m, .65, 71) is None
    assert barras_por_nervio(x.as_cm2_m, .65, 71) == 2


def test_reporte_rechaza_otra_corrida_y_tabla_incompleta():
    with pytest.raises(ValueError, match='entrada'):
        leer_reporte(TXT.replace('0.720', '0.730'), sistema())
    with pytest.raises(ValueError, match='armaduras'):
        leer_reporte(TXT.split('ARMADURAS SEGÚN "Y"')[0], sistema())


def test_reporte_fixture_publico_completo():
    from puente_losas.dl_io import cargar_dl
    folder = Path(__file__).parent/'fixtures'
    report = leer_reporte((folder/'restaurante_2.TXT').read_text(encoding='cp1252'),
                          cargar_dl(str(folder/'restaurante_2.DL')))
    assert len(report.momentos) == 5
    assert len([a for a in report.armaduras if a.losa_j is None]) == 10
    assert len([a for a in report.armaduras if a.losa_j is not None]) == 6


def test_barras_usa_techo_decimal_y_rechaza_geometria_invalida():
    assert barras_por_nervio(2.84, .5, 71) == 2
    with pytest.raises(ValueError):
        barras_por_nervio(2.84, 0, 71)
