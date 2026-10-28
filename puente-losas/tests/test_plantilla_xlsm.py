from zipfile import ZipFile

import pytest

from puente_losas.plantilla_xlsm import escribir_copia_xlsm


def plantilla(path):
    with ZipFile(path, 'w') as z:
        z.writestr('xl/workbook.xml', '''<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Datos" sheetId="1" r:id="rId1"/></sheets></workbook>''')
        z.writestr('xl/_rels/workbook.xml.rels', '''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Target="worksheets/sheet1.xml" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"/></Relationships>''')
        z.writestr('xl/worksheets/sheet1.xml', '''<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><dimension ref="A1:C1"/><sheetData><row r="1"><c r="A1" s="4"><v>1</v></c><c r="B1"><f>A1*2</f><v>2</v></c><c r="C1" t="inlineStr"><is><t>Original</t></is></c></row></sheetData></worksheet>''')
        z.writestr('xl/vbaProject.bin', b'VBA de prueba sin ejecutar')
        z.writestr('xl/styles.xml', b'estilos originales de prueba')


def test_copia_conserva_vba_estilos_y_formulas(tmp_path):
    src, dst = tmp_path/'base.xlsm', tmp_path/'salida.xlsm'
    plantilla(src)
    escribir_copia_xlsm(src, dst, {'Datos': {'A1': 3.6, 'C1': '=texto literal'}})
    with ZipFile(src) as a, ZipFile(dst) as b:
        assert a.namelist() == b.namelist()
        for name in a.namelist():
            if name != 'xl/worksheets/sheet1.xml':
                assert a.read(name) == b.read(name)
        xml = b.read('xl/worksheets/sheet1.xml').decode()
        assert '<f>A1*2</f>' in xml and 's="4"' in xml and '=texto literal' in xml


def test_no_sobrescribir_fuente_destino_o_formula(tmp_path):
    src, dst = tmp_path/'base.xlsm', tmp_path/'salida.xlsm'
    plantilla(src)
    with pytest.raises(ValueError, match='fórmula'):
        escribir_copia_xlsm(src, dst, {'Datos': {'B1': 3}})
    assert not dst.exists()
    with pytest.raises(ValueError):
        escribir_copia_xlsm(src, src, {'Datos': {'A1': 3}})
    escribir_copia_xlsm(src, dst, {'Datos': {'A1': 3}})
    with pytest.raises(FileExistsError):
        escribir_copia_xlsm(src, dst, {'Datos': {'A1': 4}})


def test_mapeo_rechaza_hoja_celda_invalida(tmp_path):
    src = tmp_path/'base.xlsm'
    plantilla(src)
    for changes in [{'Ausente': {'A1': 2}}, {'Datos': {'A0': 2}}, {'Datos': {'XFE1': 2}}]:
        with pytest.raises(ValueError):
            escribir_copia_xlsm(src, tmp_path/'salida.xlsm', changes)


def test_conserva_namespace_referido_por_mc_ignorable(tmp_path):
    src, dst = tmp_path/'base.xlsm', tmp_path/'salida.xlsm'
    plantilla(src)
    rebuilt = tmp_path/'ns.xlsm'
    with ZipFile(src) as a, ZipFile(rebuilt, 'w') as b:
        for n in a.namelist():
            data=a.read(n)
            if n=='xl/worksheets/sheet1.xml':
                data=data.replace(b'<worksheet ', b'<worksheet xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" xmlns:x14ac="http://schemas.microsoft.com/office/spreadsheetml/2009/9/ac" mc:Ignorable="x14ac" ')
            b.writestr(n,data)
    escribir_copia_xlsm(rebuilt, dst, {'Datos': {'A1': 3}})
    with ZipFile(dst) as z:
        xml=z.read('xl/worksheets/sheet1.xml')
        assert b'xmlns:x14ac=' in xml and b'Ignorable="x14ac"' in xml
