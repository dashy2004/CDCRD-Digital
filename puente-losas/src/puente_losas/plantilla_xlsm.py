"""Copias de plantilla XLSM: cambiar entradas sin reescribir VBA ni otras partes.

No ejecuta macros y nunca sobrescribe fórmulas. Las entradas deben identificar
explícitamente hoja y celda; las fórmulas existentes se recalculan con Excel.
"""
from __future__ import annotations

import math
import io
import os
from pathlib import Path
import posixpath
import re
import tempfile
from xml.etree import ElementTree as ET
from zipfile import ZipFile

NS = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
ET.register_namespace('', NS)
ET.register_namespace('r', REL)


def _coord(ref):
    m = re.fullmatch(r'([A-Z]{1,3})([1-9][0-9]*)', ref)
    if not m:
        raise ValueError('Celda inválida: ' + str(ref))
    col = 0
    for c in m[1]:
        col = col * 26 + ord(c) - 64
    row = int(m[2])
    if col > 16384 or row > 1048576:
        raise ValueError('Celda fuera de Excel: ' + ref)
    return row, col


def escribir_copia_xlsm(fuente, destino, entradas):
    """Escribe copia nueva; conserva bytes de todos los miembros no editados."""
    fuente, destino = Path(fuente).resolve(), Path(destino).resolve()
    if fuente == destino:
        raise ValueError('Fuente y destino deben ser distintos')
    if destino.exists():
        raise FileExistsError(destino)
    cambios = {}
    with ZipFile(fuente) as z:
        wb = ET.fromstring(z.read('xl/workbook.xml'))
        rels = {r.get('Id'): r.get('Target') for r in ET.fromstring(z.read('xl/_rels/workbook.xml.rels'))}
        hojas = {}
        for s in wb.findall(f'{{{NS}}}sheets/{{{NS}}}sheet'):
            target = rels[s.get(f'{{{REL}}}id')]
            hojas[s.get('name')] = posixpath.normpath(target.lstrip('/') if target.startswith('/') else 'xl/' + target)
        for nombre, cells in entradas.items():
            if nombre not in hojas:
                raise ValueError('Hoja ausente: ' + nombre)
            path = hojas[nombre]
            original = z.read(path)
            # Excel's mc:Ignorable refers to namespace prefixes as text. ET would
            # drop declarations unused by element names and invalidate that list.
            namespaces = {
                prefix: uri for _, (prefix, uri) in ET.iterparse(io.BytesIO(original), events=['start-ns'])}
            for prefix, uri in namespaces.items():
                if not re.fullmatch(r'ns\d+', prefix):
                    ET.register_namespace(prefix, uri)
            root = ET.fromstring(original)
            data = root.find(f'{{{NS}}}sheetData')
            if data is None:
                raise ValueError('Hoja sin sheetData: ' + nombre)
            for ref, valor in cells.items():
                nr, nc = _coord(ref)
                row = next((r for r in data if int(r.get('r')) == nr), None)
                if row is None:
                    row = ET.Element(f'{{{NS}}}row', {'r': str(nr)})
                    index = next((i for i, r in enumerate(data) if int(r.get('r')) > nr), len(data))
                    data.insert(index, row)
                cell = next((c for c in row if c.get('r') == ref), None)
                if cell is None:
                    cell = ET.Element(f'{{{NS}}}c', {'r': ref})
                    index = next((i for i, c in enumerate(row) if _coord(c.get('r'))[1] > nc), len(row))
                    row.insert(index, cell)
                if cell.find(f'{{{NS}}}f') is not None:
                    raise ValueError('No sobrescribir fórmula: ' + nombre + '!' + ref)
                for child in list(cell):
                    cell.remove(child)
                cell.attrib.pop('t', None)
                if valor is None:
                    continue
                if isinstance(valor, bool):
                    cell.set('t', 'b')
                    ET.SubElement(cell, f'{{{NS}}}v').text = str(int(valor))
                elif isinstance(valor, (int, float)):
                    if not math.isfinite(valor):
                        raise ValueError('Número no finito: ' + ref)
                    ET.SubElement(cell, f'{{{NS}}}v').text = str(valor)
                elif isinstance(valor, str):
                    cell.set('t', 'inlineStr')
                    t = ET.SubElement(ET.SubElement(cell, f'{{{NS}}}is'), f'{{{NS}}}t')
                    t.set('{http://www.w3.org/XML/1998/namespace}space', 'preserve')
                    t.text = valor
                else:
                    raise ValueError('Tipo de entrada no soportado: ' + ref)
            dimension = root.find(f'{{{NS}}}dimension')
            if dimension is not None:
                refs = [c.get('r') for r in data for c in r if c.tag == f'{{{NS}}}c']
                if refs:
                    # Existing template ranges are retained; callers target existing cells.
                    old = dimension.get('ref', '').split(':')
                    if old and any(_coord(r)[0] > max(_coord(x)[0] for x in old) or _coord(r)[1] > max(_coord(x)[1] for x in old) for r in cells):
                        raise ValueError('Entrada fuera del rango original: ' + nombre)
            serialized = ET.tostring(root, encoding='utf-8', xml_declaration=True).decode('utf-8')
            root_start = serialized.index('<', serialized.index('?>') + 2)
            root_end = serialized.index('>', root_start)
            opening = serialized[root_start:root_end]
            from xml.sax.saxutils import quoteattr
            for prefix, uri in namespaces.items():
                declaration = 'xmlns' + (':' + prefix if prefix else '')
                if not re.search(r'\b' + re.escape(declaration) + r'=', opening):
                    opening += ' ' + declaration + '=' + quoteattr(uri)
            serialized = serialized[:root_start] + opening + serialized[root_end:]
            cambios[path] = serialized.encode('utf-8')
        destino.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=destino.stem + '-', suffix='.tmp', dir=destino.parent)
        os.close(fd)
        try:
            with ZipFile(tmp, 'w') as out:
                out.comment = z.comment
                for info in z.infolist():
                    out.writestr(info, cambios.get(info.filename, z.read(info.filename)))
            # Exclusive create avoids replacing a destination created concurrently.
            os.link(tmp, destino)
        finally:
            Path(tmp).unlink(missing_ok=True)
    return destino
