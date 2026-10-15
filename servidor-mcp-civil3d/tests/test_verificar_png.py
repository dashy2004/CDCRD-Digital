"""Pruebas offline de verificar_png (decodificador PNG puro)."""
import os
import struct
import sys
import unittest
import zlib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'pruebas'))
import verificar_png  # noqa: E402


def _chunk(etiqueta, datos):
    return struct.pack('>I', len(datos)) + etiqueta + datos + \
        struct.pack('>I', zlib.crc32(etiqueta + datos) & 0xFFFFFFFF)


def _png_rgb(pixeles, ancho, alto, filtro=0):
    """PNG RGB 8 bits con el filtro pedido en todas las scanlines."""
    ihdr = struct.pack('>IIBBBBB', ancho, alto, 8, 2, 0, 0, 0)
    crudo = bytearray()
    previa = [(0, 0, 0)] * ancho
    for y in range(alto):
        fila = pixeles[y * ancho:(y + 1) * ancho]
        crudo.append(filtro)
        if filtro == 0:
            for p in fila:
                crudo += bytes(p)
        elif filtro == 2:  # Up
            for x, p in enumerate(fila):
                crudo += bytes((p[c] - previa[x][c]) & 0xFF for c in range(3))
        previa = fila
    return b'\x89PNG\r\n\x1a\n' + _chunk(b'IHDR', ihdr) + \
        _chunk(b'IDAT', zlib.compress(bytes(crudo))) + _chunk(b'IEND', b'')


class TestVerificarPng(unittest.TestCase):
    def _escribir(self, datos):
        import tempfile
        f = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        f.write(datos)
        f.close()
        self.addCleanup(os.unlink, f.name)
        return f.name

    def test_histograma_sin_filtro(self):
        pix = [(255, 0, 0)] * 6 + [(0, 0, 255)] * 2
        h = verificar_png.histograma(self._escribir(_png_rgb(pix, 4, 2)))
        self.assertEqual(h[(255, 0, 0)], 6)
        self.assertEqual(h[(0, 0, 255)], 2)

    def test_histograma_filtro_up(self):
        pix = [(10, 20, 30)] * 4 + [(10, 20, 30)] * 4
        h = verificar_png.histograma(self._escribir(_png_rgb(pix, 4, 2, filtro=2)))
        self.assertEqual(h[(10, 20, 30)], 8)

    def test_fraccion_con_tolerancia(self):
        h = {(128, 128, 128): 90, (130, 126, 128): 10, (0, 0, 0): 100}
        self.assertAlmostEqual(verificar_png.fraccion_de_color(h, (128, 128, 128)), 0.5)

    def test_rechaza_no_png(self):
        with self.assertRaises(ValueError):
            verificar_png.histograma(self._escribir(b'no es png'))


if __name__ == '__main__':
    unittest.main()
