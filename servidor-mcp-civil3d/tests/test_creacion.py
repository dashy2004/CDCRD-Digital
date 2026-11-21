"""Contrato de los helpers puros de creacion.py; sin CAD ni puente."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import creacion  # noqa: E402


class ParsearPunto(unittest.TestCase):
    def test_texto_simple(self):
        self.assertEqual(creacion.parsear_punto('409000,2044000'), [409000.0, 2044000.0])

    def test_json(self):
        self.assertEqual(creacion.parsear_punto('[1, 2, 3]'), [1.0, 2.0, 3.0])

    def test_lista(self):
        self.assertEqual(creacion.parsear_punto([5, 6]), [5.0, 6.0])

    def test_invalido(self):
        with self.assertRaises(ValueError):
            creacion.parsear_punto('1')
        with self.assertRaises(ValueError):
            creacion.parsear_punto('1,2,3,4')
        with self.assertRaises(ValueError):
            creacion.parsear_punto(None)


class ParsearNum(unittest.TestCase):
    def test_vacio_es_none(self):
        self.assertIsNone(creacion.parsear_num('', 'x'))
        self.assertIsNone(creacion.parsear_num(None, 'x'))

    def test_numero(self):
        self.assertEqual(creacion.parsear_num('18.5', 'x'), 18.5)
        self.assertEqual(creacion.parsear_num(10, 'x'), 10.0)

    def test_invalido(self):
        with self.assertRaises(ValueError):
            creacion.parsear_num('abc', 'x')


class ParsearHandles(unittest.TestCase):
    def test_lista(self):
        self.assertEqual(creacion.parsear_handles('7A10, 7A0A ,7A0B'), ['7A10', '7A0A', '7A0B'])

    def test_vacio(self):
        with self.assertRaises(ValueError):
            creacion.parsear_handles('  ,  ')


class ParsearEntidades(unittest.TestCase):
    def test_objeto_unico_se_vuelve_lista(self):
        datos = creacion.parsear_entidades('{"tipo":"linea","p1":[0,0],"p2":[1,1]}')
        self.assertEqual(len(datos), 1)
        self.assertEqual(datos[0]['tipo'], 'linea')

    def test_lista(self):
        datos = creacion.parsear_entidades('[{"tipo":"capa","nombre":"X"},{"tipo":"punto","punto":[0,0]}]')
        self.assertEqual([e['tipo'] for e in datos], ['capa', 'punto'])

    def test_sin_tipo(self):
        with self.assertRaises(ValueError):
            creacion.parsear_entidades('[{"nombre":"X"}]')

    def test_vacia(self):
        with self.assertRaises(ValueError):
            creacion.parsear_entidades('[]')


class SinVacios(unittest.TestCase):
    def test_filtra(self):
        self.assertEqual(creacion.sin_vacios({'a': 1, 'b': '', 'c': None, 'd': 0, 'e': False}),
                         {'a': 1, 'd': 0, 'e': False})


class Registro(unittest.TestCase):
    def test_registra_once_herramientas(self):
        nombres = []

        class McpFalso:
            def tool(self):
                def decorador(fn):
                    nombres.append(fn.__name__)
                    return fn
                return decorador

        creacion.registrar(McpFalso(), lambda *a, **k: '{}', lambda d: '{}')
        self.assertEqual(sorted(nombres), sorted([
            'crear_perfil_desde_superficie', 'crear_perfil_constante', 'crear_vista_perfil',
            'agregar_hatch_vista_perfil', 'listar_estilos', 'crear_estilo',
            'editar_estilo_display', 'purgar_estilos', 'crear_entidad',
            'borrar_objeto', 'orden_dibujo', 'crear_bloque_3d', 'crear_dibujo']))

    def test_escritura_exige_confirmar(self):
        registradas = {}

        class McpFalso:
            def tool(self):
                def decorador(fn):
                    registradas[fn.__name__] = fn
                    return fn
                return decorador

        llamadas = []
        creacion.registrar(McpFalso(), lambda *a, **k: llamadas.append(a) or '{}', lambda d: str(d))
        r = registradas['crear_perfil_desde_superficie']('A', 'S', 'P')
        self.assertIn('confirmar', r)
        self.assertEqual(llamadas, [])
        registradas['crear_perfil_desde_superficie']('A', 'S', 'P', confirmar=True)
        self.assertEqual(llamadas[0][0], 'civil.perfil_superficie')


if __name__ == '__main__':
    unittest.main()
