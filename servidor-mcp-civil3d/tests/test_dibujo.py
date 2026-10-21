"""Contrato del generador de LISP de dibujo; puro, sin CAD ni puente."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import dibujo  # noqa: E402


class GeneradorEntidades(unittest.TestCase):
    def test_capa(self):
        s = dibujo.lisp_para_entidad({'tipo': 'capa', 'nombre': 'UBIC-LOTE', 'color': 1})
        self.assertIn('(cons 0 "LAYER")', s)
        self.assertIn('(cons 2 "UBIC-LOTE")', s)
        self.assertIn('(cons 62 1)', s)

    def test_capa_color_por_defecto_y_rango(self):
        self.assertIn('(cons 62 7)', dibujo.lisp_para_entidad({'tipo': 'capa', 'nombre': 'X'}))
        with self.assertRaises(ValueError):
            dibujo.lisp_para_entidad({'tipo': 'capa', 'nombre': 'X', 'color': 300})

    def test_linea(self):
        s = dibujo.lisp_para_entidad({'tipo': 'linea', 'capa': 'C-TOPO',
                                      'p1': [0, 0], 'p2': [10, 5]})
        self.assertIn('(cons 0 "LINE")', s)
        self.assertIn('(cons 8 "C-TOPO")', s)
        self.assertIn('(cons 10 (list 0.0000 0.0000 0.0000))', s)
        self.assertIn('(cons 11 (list 10.0000 5.0000 0.0000))', s)

    def test_polilinea_cerrada_con_ancho(self):
        s = dibujo.lisp_para_entidad({'tipo': 'polilinea', 'puntos': [[0, 0], [1, 0], [1, 1]],
                                      'cerrada': True, 'ancho': 0.5})
        self.assertIn('(cons 0 "LWPOLYLINE")', s)
        self.assertIn('(cons 90 3)', s)          # 3 vertices
        self.assertIn('(cons 70 1)', s)          # cerrada
        self.assertIn('(cons 43 0.5000)', s)     # ancho constante
        self.assertIn('(cons 10 (list 1.0000 1.0000))', s)  # vertice 2D, sin z

    def test_polilinea_abierta_por_defecto(self):
        s = dibujo.lisp_para_entidad({'tipo': 'polilinea', 'puntos': [[0, 0], [1, 1]]})
        self.assertIn('(cons 70 0)', s)
        self.assertNotIn('(cons 43', s)

    def test_polilinea_pocos_vertices(self):
        with self.assertRaises(ValueError):
            dibujo.lisp_para_entidad({'tipo': 'polilinea', 'puntos': [[0, 0]]})

    def test_texto_centrado_y_rotacion(self):
        s = dibujo.lisp_para_entidad({'tipo': 'texto', 'punto': [5, 5], 'altura': 2.5,
                                      'texto': 'N', 'centrado': True, 'rotacion': 90})
        self.assertIn('(cons 0 "TEXT")', s)
        self.assertIn('(cons 1 "N")', s)
        self.assertIn('(cons 40 2.5000)', s)
        self.assertIn('(cons 50 90.0000)', s)
        self.assertIn('(cons 72 1)', s)          # centrado
        self.assertIn('(cons 73 0)', s)

    def test_texto_escapa_comillas_y_barra(self):
        s = dibujo.lisp_para_entidad({'tipo': 'texto', 'punto': [0, 0], 'altura': 1,
                                      'texto': 'di"jo\\ok'})
        self.assertIn('(cons 1 "di\\"jo\\\\ok")', s)

    def test_texto_acentos_se_conservan(self):
        s = dibujo.lisp_para_entidad({'tipo': 'texto', 'punto': [0, 0], 'altura': 1,
                                      'texto': 'UBICACIÓN'})
        self.assertIn('UBICACIÓN', s)

    def test_circulo(self):
        s = dibujo.lisp_para_entidad({'tipo': 'circulo', 'centro': [1, 2], 'radio': 10})
        self.assertIn('(cons 0 "CIRCLE")', s)
        self.assertIn('(cons 40 10.0000)', s)

    def test_solido_cuarto_punto_por_defecto(self):
        s = dibujo.lisp_para_entidad({'tipo': 'solido', 'p1': [0, 0], 'p2': [1, 0], 'p3': [0, 1]})
        self.assertIn('(cons 0 "SOLID")', s)
        self.assertEqual(s.count('(cons 13'), 1)  # p4 = p3 si falta

    def test_punto_3d(self):
        s = dibujo.lisp_para_entidad({'tipo': 'punto', 'punto': [1, 2, 3]})
        self.assertIn('(cons 0 "POINT")', s)
        self.assertIn('(cons 10 (list 1.0000 2.0000 3.0000))', s)

    def test_alias_ingles(self):
        self.assertIn('"CIRCLE"', dibujo.lisp_para_entidad({'tipo': 'circle', 'centro': [0, 0], 'radio': 1}))

    def test_tipo_desconocido(self):
        with self.assertRaises(ValueError):
            dibujo.lisp_para_entidad({'tipo': 'espiral', 'puntos': []})

    def test_punto_invalido(self):
        with self.assertRaises(ValueError):
            dibujo.lisp_para_entidad({'tipo': 'circulo', 'centro': [1], 'radio': 1})
        with self.assertRaises(ValueError):
            dibujo.lisp_para_entidad({'tipo': 'circulo', 'centro': [1, 'x'], 'radio': 1})

    def test_no_finito(self):
        with self.assertRaises(ValueError):
            dibujo.lisp_para_entidad({'tipo': 'circulo', 'centro': [1, 2], 'radio': float('inf')})


class ListaEntidades(unittest.TestCase):
    def test_envuelve_en_progn_y_princ(self):
        s = dibujo.lisp_para_entidades([{'tipo': 'capa', 'nombre': 'A'},
                                        {'tipo': 'circulo', 'centro': [0, 0], 'radio': 1}])
        self.assertTrue(s.startswith('(progn '))
        self.assertIn('(princ "CREAR_OK")', s)
        self.assertEqual(s.count('entmakex'), 2)

    def test_acepta_un_solo_dict(self):
        s = dibujo.lisp_para_entidades({'tipo': 'punto', 'punto': [0, 0]})
        self.assertEqual(s.count('entmakex'), 1)

    def test_error_reporta_indice(self):
        with self.assertRaises(ValueError) as ctx:
            dibujo.lisp_para_entidades([{'tipo': 'punto', 'punto': [0, 0]},
                                        {'tipo': 'circulo', 'centro': [0, 0]}])
        self.assertIn('entidad #1', str(ctx.exception))

    def test_lista_vacia(self):
        with self.assertRaises(ValueError):
            dibujo.lisp_para_entidades([])


class TemporalLisp(unittest.TestCase):
    def test_escribe_y_carga(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = dibujo.escribir_lisp_temporal('(princ "hola")', tmpdir=d)
            self.assertTrue(os.path.isfile(ruta))
            self.assertEqual(Path(ruta).read_text(encoding='cp1252'), '(princ "hola")')
            self.assertEqual(dibujo.ruta_load(ruta), '(load "%s")' % ruta.replace('\\', '/'))

    def test_acentos_en_cp1252(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = dibujo.escribir_lisp_temporal('(princ "Área ñ")', tmpdir=d)
            self.assertEqual(Path(ruta).read_text(encoding='cp1252'), '(princ "Área ñ")')

    def test_borra_temporales_viejos_y_conserva_nuevo(self):
        with tempfile.TemporaryDirectory() as d:
            viejo = os.path.join(d, 'cdcrd_viejo.lsp')
            open(viejo, 'w').close()
            os.utime(viejo, (time.time() - 10000, time.time() - 10000))
            nuevo = dibujo.escribir_lisp_temporal('(princ)', tmpdir=d)
            self.assertFalse(os.path.exists(viejo))   # viejo borrado
            self.assertTrue(os.path.exists(nuevo))     # el recien creado queda

    def test_ruta_load_usa_barras_normales(self):
        self.assertEqual(dibujo.ruta_load(r'C:\tmp\a.lsp'), '(load "C:/tmp/a.lsp")')


if __name__ == '__main__':
    unittest.main()
