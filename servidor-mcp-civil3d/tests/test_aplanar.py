"""Pruebas offline de aplanar.lisp_aplanar (generador LISP puro)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
import aplanar  # noqa: E402


class TestLispAplanar(unittest.TestCase):
    def test_parentesis_balanceados(self):
        for bloques in (True, False):
            lisp = aplanar.lisp_aplanar(r'C:\Temp\r.json', bloques)
            dentro = 0
            en_cadena = False
            i = 0
            while i < len(lisp):
                c = lisp[i]
                if en_cadena:
                    if c == '\\':
                        i += 1
                    elif c == '"':
                        en_cadena = False
                elif c == '"':
                    en_cadena = True
                elif c == '(':
                    dentro += 1
                elif c == ')':
                    dentro -= 1
                    self.assertGreaterEqual(dentro, 0)
                i += 1
            self.assertEqual(dentro, 0, 'parentesis sin cerrar (bloques=%s)' % bloques)

    def test_ruta_reporte_con_barras_normales(self):
        lisp = aplanar.lisp_aplanar(r'C:\Users\x\r.json', True)
        self.assertIn('C:/Users/x/r.json', lisp)
        self.assertNotIn('\\U', lisp.split('open')[1][:40])

    def test_bloques_opcional(self):
        con = aplanar.lisp_aplanar('r.json', True)
        sin = aplanar.lisp_aplanar('r.json', False)
        self.assertIn('tblnext', con)
        self.assertNotIn('tblnext', sin)

    def test_excluye_vectores_de_multileader(self):
        lisp = aplanar.lisp_aplanar('r.json', True)
        self.assertIn('MULTILEADER', lisp)
        self.assertIn("'(11 12)", lisp)

    def test_no_toca_codigo_210(self):
        lisp = aplanar.lisp_aplanar('r.json', True)
        self.assertIn("'(10 11 12 13 14 15 16 17)", lisp)
        self.assertNotIn('210', lisp)

    def test_aplanar_exige_dibujo_esperado(self):
        class PuenteFalso:
            @staticmethod
            def llamar(metodo, p):
                return {'dibujo': r'C:\x\OTRO.dwg'}
        with self.assertRaises(ValueError):
            aplanar.aplanar(PuenteFalso, None, esperado='POLIDEPORTIVO')


if __name__ == '__main__':
    unittest.main()
