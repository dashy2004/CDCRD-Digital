"""Las recetas de perfil e isometrico se pueden repetir sin duplicar y salen coherentes; sin CAD."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import perfil_estratigrafico as pe  # noqa: E402
import tridimensional as t3  # noqa: E402


class PuenteFalso:
    """Registra las llamadas y responde lo minimo que piden las recetas."""

    def __init__(self, en_capas=None, estilos=None, superficies=None):
        self.llamadas = []
        self.en_capas = en_capas or {}
        self.estilos = estilos or []
        self.superficies = superficies or {}

    def _responder(self, metodo, p):
        if metodo == 'objects.query':
            if p.get('capa'):
                return {'objetos': [{'handle': h} for h in self.en_capas.get(p['capa'], [])]}
            return {'objetos': [{'handle': h, 'Name': s['Name']} for h, s in self.superficies.items()]}
        if metodo == 'objects.erase':
            return {'borrados': list(p['handles']), 'fallidos': {}}
        if metodo == 'estilos.listar':
            return {'estilos': list(self.estilos)}
        if metodo == 'objects.read':
            return {'valor': self.superficies[p['handle']][p['ruta']]}
        if metodo == 'entity.create':
            return {'creados': [{'tipo': e['tipo'], 'handle': 'E%d' % i} for i, e in enumerate(p['entidades'])],
                    'errores': []}
        if metodo == 'vista.exportar':
            return {'ruta': p['ruta'], 'bytes': 1}
        return {}

    def llamar(self, metodo, p=None):
        self.llamadas.append((metodo, p or {}))
        return self._responder(metodo, p or {})

    llamar_con_aprobacion = llamar

    def de(self, metodo):
        return [p for m, p in self.llamadas if m == metodo]


class Anotaciones(unittest.TestCase):
    def test_capas_del_prefijo(self):
        self.assertEqual(pe.capas_anotacion('AA'), ['AA-SOND', 'AA-TXT', 'AA-LEG'])

    def test_borra_solo_las_capas_pedidas_y_cuenta(self):
        puente = PuenteFalso(en_capas={'AA-SOND': ['1A', '1B'], 'AA-LEG': ['2A'], 'OTRA': ['9Z']})
        res = {'advertencias': []}
        n = pe.borrar_anotaciones(puente, pe.capas_anotacion('AA'), res)
        self.assertEqual(n, 3)
        borrados = [h for p in puente.de('objects.erase') for h in p['handles']]
        self.assertEqual(sorted(borrados), ['1A', '1B', '2A'])
        self.assertEqual(res['advertencias'], [])

    def test_capa_vacia_no_llama_a_borrar(self):
        puente = PuenteFalso()
        self.assertEqual(pe.borrar_anotaciones(puente, ['AA-TXT'], {'advertencias': []}), 0)
        self.assertEqual(puente.de('objects.erase'), [])

    def test_un_fallo_queda_en_advertencias(self):
        class Roto(PuenteFalso):
            def llamar(self, metodo, p=None):
                raise RuntimeError('sin puente')
        res = {'advertencias': []}
        self.assertEqual(pe.borrar_anotaciones(Roto(), ['AA-TXT'], res), 0)
        self.assertIn('borrar_AA-TXT', res['advertencias'][0])


class Bandas(unittest.TestCase):
    def test_importa_el_juego_vacio(self):
        puente = PuenteFalso(estilos=[{'familia': 'ProfileViewBandSetStyles', 'nombre': '_No Bands', 'handle': '3172'}])
        res = {'advertencias': []}
        self.assertTrue(pe.quitar_bandas(puente, 'PV1', '_No Bands', res))
        inv = puente.de('objects.invoke')[0]
        self.assertEqual((inv['handle'], inv['ruta'], inv['metodo'], inv['args']),
                         ('PV1', 'Bands', 'ImportBandSetStyle', [3172]))

    def test_sin_juego_vacio_avisa_y_no_toca_la_vista(self):
        puente = PuenteFalso(estilos=[])
        res = {'advertencias': []}
        self.assertFalse(pe.quitar_bandas(puente, 'PV1', '_No Bands', res))
        self.assertEqual(puente.de('objects.invoke'), [])
        self.assertIn('bandas', res['advertencias'][0])

    def test_handle_con_letras_va_como_texto(self):
        self.assertEqual(pe.arg_handle('76F8'), '76F8')
        self.assertEqual(pe.arg_handle('3172'), 3172)


class ExportPerfil(unittest.TestCase):
    def test_png_apaisado_por_defecto(self):
        p = pe.parametros_png({'png': 'a.png'}, 'V', 'PV1')
        self.assertEqual(p['rotacion'], '0')
        self.assertEqual(p['nombre_vista'], 'V')
        self.assertNotIn('handles', p)

    def test_respeta_la_rotacion_pedida_y_cae_a_handles(self):
        p = pe.parametros_png({'png': 'a.png', 'rotacion': 90, 'papel_png': 'X'}, None, 'PV1')
        self.assertEqual((p['rotacion'], p['papel'], p['handles']), ('90', 'X', ['PV1']))


class Cilindros(unittest.TestCase):
    S = {'x': 100, 'y': 200, 'elev': 40.0, 'estratos': [
        {'top': 0, 'base': 0.5, 'codigo': 101}, {'top': 0.5, 'base': 4, 'codigo': 205}]}

    def test_desde_cero_escala_la_cota_completa(self):
        ents = t3.cilindros_de_sondeo('S-1', self.S, {101: 34}, radio=2, exag_z=5.0, desde_cero=True)
        cil = [e for e in ents if e['tipo'] == 'cilindro']
        self.assertAlmostEqual(cil[0]['base'][2], 197.5)                     # (40-0.5)*5
        self.assertAlmostEqual(cil[0]['base'][2] + cil[0]['altura'], 200.0)  # boca en 40*5
        self.assertAlmostEqual(cil[1]['base'][2], 180.0)                     # (40-4)*5
        self.assertAlmostEqual(ents[-1]['punto'][2], 202.0)

    def test_sin_exageracion_los_dos_modos_coinciden(self):
        a = t3.cilindros_de_sondeo('S-1', self.S, {}, exag_z=1.0, desde_cero=True)
        b = t3.cilindros_de_sondeo('S-1', self.S, {}, exag_z=1.0, desde_cero=False)
        self.assertEqual(a, b)


class Exageracion(unittest.TestCase):
    def test_uno_devuelve_la_superficie_a_su_cota(self):
        self.assertEqual(t3.modo_exageracion(1.0), {'DisplayMode': 'UseSurfaceElevation'})

    def test_factor(self):
        self.assertEqual(t3.modo_exageracion(5), {'DisplayMode': 'ExaggerateElevations', 'ExaggerateElevationBy': 5.0})

    def test_export_apaisado(self):
        self.assertEqual(t3.parametros_export({'png': 'a.png'}, 'V', 'png')['rotacion'], '0')
        pdf = t3.parametros_export({'pdf': 'a.pdf', 'rotacion': 90}, 'V', 'pdf')
        self.assertEqual((pdf['rotacion'], pdf['papel']), ('90', 'A3'))
        self.assertNotIn('dispositivo', pdf)


class Isometrico(unittest.TestCase):
    def setUp(self):
        d = tempfile.mkdtemp()
        self.u, self.e = os.path.join(d, 'u.csv'), os.path.join(d, 'e.csv')
        with open(self.u, 'w', encoding='utf-8') as fh:
            fh.write('Location ID,Location Type,Easting,Northing,Ground Level,Final Depth\nS-1,CP,100,200,40.0,20.0\n')
        with open(self.e, 'w', encoding='utf-8') as fh:
            fh.write('Location ID,Depth Top,Depth Base,Legend Code,Geology Code,Description\n')
            fh.write('S-1,0,2,101,RELLENO,x\nS-1,2,20,320,CALIZA,x\n')

    def spec(self, **extra):
        base = {'prefijo': 'T', 'csv_ubicaciones': self.u, 'csv_estratigrafia': self.e, 'exageracion_z': 5,
                'estratos': [{'codigo': 101, 'nombre': 'RELLENO', 'superficie': 'SUP R', 'color_aci': 34},
                             {'codigo': 320, 'nombre': 'CALIZA', 'superficie': 'SUP C', 'color_aci': 8}],
                'exportar': {'png': 'iso.png'}}
        base.update(extra)
        return base

    def puente(self, estilo_c='EST C'):
        return PuenteFalso(
            en_capas={'T-SOND3D': ['AA', 'AB']},
            estilos=[{'familia': 'SurfaceStyles', 'nombre': 'EST R', 'handle': '10'},
                     {'familia': 'SurfaceStyles', 'nombre': 'EST C', 'handle': '1F'}],
            superficies={'S1': {'Name': 'SUP R', 'StyleName': 'EST R'},
                         'S2': {'Name': 'SUP C', 'StyleName': estilo_c}})

    def test_repetir_borra_lo_anterior_y_exagera_columnas_y_superficies_igual(self):
        puente = self.puente()
        res = t3.isometrico_sondeos(self.spec(), puente, log=lambda m: None)
        self.assertEqual(res['reemplazado'], 2)
        cil = [e for e in puente.de('entity.create')[0]['entidades'] if e['tipo'] == 'cilindro']
        self.assertAlmostEqual(cil[0]['base'][2] + cil[0]['altura'], 200.0)
        cambios = puente.de('objects.update')
        self.assertEqual({c['handle'] for c in cambios}, {'10', '1F'})
        for c in cambios:
            self.assertEqual(c['ruta'], 'TriangleStyle')
            self.assertEqual(c['props'], {'DisplayMode': 'ExaggerateElevations', 'ExaggerateElevationBy': 5.0})
        colores = {d['estilo']: d.get('color_aci') for d in puente.de('estilos.display')}
        self.assertEqual(colores, {'EST R': '34', 'EST C': '8'})
        self.assertEqual(puente.de('vista.exportar')[0]['rotacion'], '0')
        self.assertEqual(res['advertencias'], [])

    def test_sin_superficies_la_boca_queda_en_su_cota_y_no_toca_estilos(self):
        puente = self.puente()
        res = t3.isometrico_sondeos(self.spec(mostrar_superficies=False), puente, log=lambda m: None)
        cil = [e for e in puente.de('entity.create')[0]['entidades'] if e['tipo'] == 'cilindro']
        self.assertAlmostEqual(cil[0]['base'][2] + cil[0]['altura'], 40.0)
        self.assertEqual(puente.de('objects.update'), [])
        self.assertNotIn('exageracion_superficies', res)

    def test_estilo_compartido_no_recibe_dos_colores(self):
        puente = self.puente(estilo_c='EST R')
        res = t3.isometrico_sondeos(self.spec(), puente, log=lambda m: None)
        self.assertEqual(len(puente.de('estilos.display')), 1)
        self.assertTrue(any('comparte el estilo' in str(a) for a in res['advertencias']))

    def test_reemplazar_false_conserva_lo_anterior(self):
        puente = self.puente()
        res = t3.isometrico_sondeos(self.spec(reemplazar=False), puente, log=lambda m: None)
        self.assertEqual(puente.de('objects.erase'), [])
        self.assertNotIn('reemplazado', res)


if __name__ == '__main__':
    unittest.main()
