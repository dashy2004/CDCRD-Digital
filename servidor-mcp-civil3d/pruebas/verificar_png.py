"""Histograma de colores de un PNG en Python puro (sin PIL ni numpy).

Soporta los PNG que produce PublishToWeb PNG.pc3: 8 bits por canal, tipos de
color 2 (RGB), 3 (paleta) y 6 (RGBA), filtros 0-4, sin entrelazado. Es la
pieza de la suite de humo que comprueba que el perfil estratigrafico salio
con sus 4 colores de estrato.
"""
import struct
import zlib


def _desfiltrar(datos, ancho, alto, bpp):
    """Deshace los filtros por scanline del PNG; devuelve bytes crudos."""
    stride = ancho * bpp
    salida = bytearray()
    pos = 0
    previa = bytearray(stride)
    for _ in range(alto):
        filtro = datos[pos]
        linea = bytearray(datos[pos + 1:pos + 1 + stride])
        pos += 1 + stride
        if filtro == 1:                                  # Sub
            for i in range(bpp, stride):
                linea[i] = (linea[i] + linea[i - bpp]) & 0xFF
        elif filtro == 2:                                # Up
            for i in range(stride):
                linea[i] = (linea[i] + previa[i]) & 0xFF
        elif filtro == 3:                                # Average
            for i in range(stride):
                a = linea[i - bpp] if i >= bpp else 0
                linea[i] = (linea[i] + (a + previa[i]) // 2) & 0xFF
        elif filtro == 4:                                # Paeth
            for i in range(stride):
                a = linea[i - bpp] if i >= bpp else 0
                b = previa[i]
                c = previa[i - bpp] if i >= bpp else 0
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                linea[i] = (linea[i] + pr) & 0xFF
        elif filtro != 0:
            raise ValueError('filtro PNG desconocido: %d' % filtro)
        salida += linea
        previa = linea
    return bytes(salida)


def histograma(ruta):
    """Dict {(r,g,b): cantidad_de_pixeles} del PNG en `ruta`."""
    with open(ruta, 'rb') as f:
        crudo = f.read()
    if crudo[:8] != b'\x89PNG\r\n\x1a\n':
        raise ValueError('no es un PNG: ' + str(ruta))
    pos = 8
    ancho = alto = tipo = prof = None
    paleta = None
    idat = bytearray()
    while pos < len(crudo):
        (n,) = struct.unpack('>I', crudo[pos:pos + 4])
        etiqueta = crudo[pos + 4:pos + 8]
        datos = crudo[pos + 8:pos + 8 + n]
        pos += 12 + n
        if etiqueta == b'IHDR':
            ancho, alto, prof, tipo, _comp, _filt, entrelazado = struct.unpack('>IIBBBBB', datos)
            if prof != 8:
                raise ValueError('solo PNG de 8 bits por canal (este es %d)' % prof)
            if entrelazado:
                raise ValueError('PNG entrelazado no soportado')
            if tipo not in (2, 3, 6):
                raise ValueError('tipo de color %d no soportado' % tipo)
        elif etiqueta == b'PLTE':
            paleta = [tuple(datos[i:i + 3]) for i in range(0, len(datos), 3)]
        elif etiqueta == b'IDAT':
            idat += datos
        elif etiqueta == b'IEND':
            break
    bpp = {2: 3, 3: 1, 6: 4}[tipo]
    pix = _desfiltrar(zlib.decompress(bytes(idat)), ancho, alto, bpp)
    conteo = {}
    if tipo == 3:
        for i in range(0, len(pix)):
            rgb = paleta[pix[i]]
            conteo[rgb] = conteo.get(rgb, 0) + 1
    else:
        for i in range(0, len(pix), bpp):
            rgb = (pix[i], pix[i + 1], pix[i + 2])
            conteo[rgb] = conteo.get(rgb, 0) + 1
    return conteo


def fraccion_de_color(hist, rgb, tolerancia=8):
    """Fraccion [0-1] de pixeles a distancia <= tolerancia por canal de `rgb`."""
    total = sum(hist.values()) or 1
    r, g, b = rgb
    n = sum(c for (pr, pg, pb), c in hist.items()
            if abs(pr - r) <= tolerancia and abs(pg - g) <= tolerancia and abs(pb - b) <= tolerancia)
    return n / total
