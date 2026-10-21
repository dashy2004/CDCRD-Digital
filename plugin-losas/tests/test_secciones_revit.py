"""Sección final por paño (fijada o reglamento) y payload para espesor_losas."""
import json
import os
import tempfile
import unittest

from puente_losas.contrato import PanoLosa

from plugin_losas.secciones_revit import (SECCION_AUTO, escribir_secciones_json,
                                          espesores_de_secciones, payload_revit,
                                          resolver_secciones)


def _pano(mark, lx, ly, espesor=0.25, x0=0.0, y0=0.0, **kw):
    contorno = [[x0, y0], [x0 + lx, y0], [x0 + lx, y0 + ly], [x0, y0 + ly]]
    return PanoLosa(mark=mark, nivel="N1", z_tope=3.0, lx=lx, ly=ly,
                    espesor=espesor, contorno=contorno, **kw)


class TestEspesores(unittest.TestCase):
    def test_espesores_del_catalogo(self):
        e = espesores_de_secciones()
        self.assertEqual(e["L12"], 0.12)
        self.assertEqual(e["L15"], 0.15)
        self.assertEqual(e["L20"], 0.20)
        self.assertEqual(e["L20A-1D"], 0.20)
        self.assertEqual(e["L20A-2D"], 0.20)
        self.assertEqual(e["L25A-1D"], 0.25)
        self.assertEqual(e["L25A-2D"], 0.25)


class TestResolver(unittest.TestCase):
    def test_fijada_manda_sobre_el_espesor_del_modelo(self):
        # el modelo trae 0.25 (placeholder) pero el panel fijó L15
        res = resolver_secciones([_pano("L00", 4.0, 5.0)], {"L00": "L15"})
        r = res["L00"]
        self.assertEqual((r.seccion, r.espesor_m, r.origen), ("L15", 0.15, "fijada"))

    def test_auto_usa_el_reglamento_no_el_espesor_del_modelo(self):
        # 2D 4x5: h = 5*(0.8+420/1400)/(36+9*1.25) = 0.116 -> 0.15 -> L15,
        # aunque el modelo diga 0.25 (Generic - 0.25)
        res = resolver_secciones([_pano("L01", 4.0, 5.0, espesor=0.25)])
        r = res["L01"]
        self.assertEqual((r.seccion, r.espesor_m, r.origen), ("L15", 0.15, "auto"))
        self.assertIn("ACI 318-19", r.criterio)

    def test_auto_literal_del_panel_cuenta_como_auto(self):
        res = resolver_secciones([_pano("L02", 4.0, 5.0)], {"L02": SECCION_AUTO})
        self.assertEqual(res["L02"].origen, "auto")

    def test_auto_grande_cae_en_aligerada_2d(self):
        # 2D 8x9: h = 9*1.1/(36+9*1.125) = 0.215 -> 0.25 -> L25A-2D
        res = resolver_secciones([_pano("L03", 8.0, 9.0)])
        r = res["L03"]
        self.assertEqual((r.seccion, r.espesor_m), ("L25A-2D", 0.25))

    def test_auto_1d_declarada_cae_en_aligerada_1d(self):
        # 1D continua 7.2 m: h = 7.2/28 = 0.257 -> 0.30: fuera de biblioteca
        # 1D continua 6.3 m: h = 6.3/28 = 0.225 -> 0.25 -> L25A-1D
        res = resolver_secciones(
            [_pano("L04", 6.3, 6.5, direccion="1D", borde="empotrado")])
        self.assertEqual(res["L04"].seccion, "L25A-1D")

    def test_vuelo_usa_l_sobre_10(self):
        # vuelo 1D 1.5 m: h = 1.5/10 = 0.15 -> L15
        res = resolver_secciones(
            [_pano("V1", 1.5, 4.0, es_vuelo=True, direccion="1D")])
        self.assertEqual(res["V1"].seccion, "L15")

    def test_fijada_fuera_de_biblioteca_detiene(self):
        with self.assertRaises(ValueError):
            resolver_secciones([_pano("L05", 4.0, 5.0)], {"L05": "L30"})

    def test_reglamento_fuera_de_biblioteca_detiene_sin_inventar(self):
        # 1D continua 7.2 m pide 0.30: no está en la biblioteca
        with self.assertRaises(ValueError):
            resolver_secciones(
                [_pano("L06", 7.2, 7.4, direccion="1D", borde="empotrado")])


class TestPayload(unittest.TestCase):
    def test_payload_asignar_y_tipos_floor(self):
        res = resolver_secciones(
            [_pano("L00", 4.0, 5.0), _pano("L01", 4.0, 5.0, x0=4.0)],
            {"L00": "L12"})
        payload = payload_revit(res)
        self.assertEqual(payload["asignar"]["L00"], "L12")
        self.assertEqual(payload["asignar"]["L01"], "L15")
        self.assertEqual(payload["tipos_floor"], {"L12": 0.12, "L15": 0.15})

    def test_escribir_json(self):
        res = resolver_secciones([_pano("L00", 4.0, 5.0)], {"L00": "L20"})
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "secciones_losas.json")
            escribir_secciones_json(res, ruta)
            with open(ruta, encoding="utf-8") as f:
                datos = json.load(f)
        self.assertEqual(datos["parametro_revit"], "Seccion_Losa")
        self.assertEqual(datos["asignar_en_revit"]["asignar"], {"L00": "L20"})
        self.assertEqual(datos["asignar_en_revit"]["tipos_floor"], {"L20": 0.20})
        self.assertEqual(datos["secciones"]["L00"]["origen"], "fijada")


if __name__ == "__main__":
    unittest.main()
