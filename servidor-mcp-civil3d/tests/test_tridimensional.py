"""Helpers puros de tridimensional.py; sin CAD."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import tridimensional as t3  # noqa: E402


class Muestreo(unittest.TestCase):
    def test_incluye_extremos(self):
        e = t3.estaciones_muestreo(0, 25, 10)
        self.assertEqual(e, [0, 10, 20, 25])

    def test_exacto(self):
        self.assertEqual(t3.estaciones_muestreo(0, 30, 10), [0, 10, 20, 30])

    def test_paso_invalido(self):
        with self.assertRaises(ValueError):
            t3.estaciones_muestreo(0, 10, 0)


class Cilindros(unittest.TestCase):
    def test_apilado_y_exageracion(self):
        s = {'x': 100, 'y': 200, 'elev': 40.0, 'estratos': [
            {'top': 0, 'base': 0.5, 'codigo': 101}, {'top': 0.5, 'base': 4, 'codigo': 205}]}
        ents = t3.cilindros_de_sondeo('S-1', s, {101: 34, 205: 12}, radio=2, exag_z=2.0)
        cil = [e for e in ents if e['tipo'] == 'cilindro']
        self.assertEqual(len(cil), 2)
        self.assertEqual(cil[0]['base'], [100, 200, 39.0])      # 40 - 0.5*2
        self.assertAlmostEqual(cil[0]['altura'], 1.0)           # (0.5-0)*2
        self.assertEqual(cil[1]['base'], [100, 200, 32.0])      # 40 - 4*2
        self.assertAlmostEqual(cil[1]['altura'], 7.0)
        self.assertEqual(cil[0]['color'], 34)
        self.assertEqual(ents[-1]['tipo'], 'mtexto')
        self.assertEqual(ents[-1]['texto'], 'S-1')


class Registro(unittest.TestCase):
    def test_tres_tools(self):
        nombres = []

        class M:
            def tool(self):
                def d(fn):
                    nombres.append(fn.__name__); return fn
                return d
        t3.registrar(M(), lambda *a, **k: '{}', lambda d: '{}')
        self.assertEqual(sorted(nombres), ['copiar_vista_perfil_a_3d', 'isometrico_sondeos_3d', 'toma_de_cerca_3d'])


if __name__ == '__main__':
    unittest.main()
