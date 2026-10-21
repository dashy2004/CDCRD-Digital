"""Contrato de los helpers puros de vistas.py; sin CAD ni puente."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import vistas  # noqa: E402


class ParsearVentana(unittest.TestCase):
    def test_texto(self):
        self.assertEqual(vistas.parsear_ventana('0,0,10,5'), [0.0, 0.0, 10.0, 5.0])

    def test_json(self):
        self.assertEqual(vistas.parsear_ventana('[1,2,3,4]'), [1.0, 2.0, 3.0, 4.0])

    def test_vacia_es_none(self):
        self.assertIsNone(vistas.parsear_ventana(''))

    def test_invalida(self):
        with self.assertRaises(ValueError):
            vistas.parsear_ventana('1,2,3')


class ParsearDireccion(unittest.TestCase):
    def test_nombrada(self):
        self.assertEqual(vistas.parsear_direccion('SE'), 'SE')

    def test_vector(self):
        self.assertEqual(vistas.parsear_direccion('[1,-1,1]'), [1.0, -1.0, 1.0])

    def test_vacia(self):
        self.assertIsNone(vistas.parsear_direccion(''))


class Registro(unittest.TestCase):
    def test_registra_diez(self):
        nombres = []

        class McpFalso:
            def tool(self):
                def d(fn):
                    nombres.append(fn.__name__)
                    return fn
                return d

        vistas.registrar(McpFalso(), lambda *a, **k: '{}', lambda d: '{}')
        self.assertEqual(sorted(nombres), sorted([
            'listar_papeles', 'exportar_vista', 'vista_3d',
            'crear_vista_guardada', 'activar_vista',
            'crear_layout', 'leer_log_puente', 'ping_comandos', 'deshacer', 'estado_cola']))

    def test_exportar_exige_confirmar(self):
        registradas = {}

        class McpFalso:
            def tool(self):
                def d(fn):
                    registradas[fn.__name__] = fn
                    return fn
                return d

        llamadas = []
        vistas.registrar(McpFalso(), lambda *a, **k: llamadas.append((a, k)) or '{}', lambda d: str(d))
        r = registradas['exportar_vista']('C:/x.pdf')
        self.assertIn('confirmar', r)
        self.assertEqual(llamadas, [])
        registradas['exportar_vista']('C:/x.pdf', ventana='0,0,10,10', confirmar=True)
        self.assertEqual(llamadas[0][0][0], 'vista.exportar')
        self.assertEqual(llamadas[0][0][1]['ventana'], [0.0, 0.0, 10.0, 10.0])


if __name__ == '__main__':
    unittest.main()
