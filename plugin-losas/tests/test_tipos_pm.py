"""Tipo de losa según apoyos (código DL) y payload para el parámetro de Revit."""
import json
import os
import tempfile
import unittest

from puente_losas.contrato import PanoLosa

from plugin_losas.tipos_pm import (DESCRIPCION_CODIGO, escribir_tipos_json,
                                   payload_revit, tipos_de_panos)


def _pano(mark, lx, ly, x0=0.0, y0=0.0, espesor=0.25, **kw):
    contorno = [[x0, y0], [x0 + lx, y0], [x0 + lx, y0 + ly], [x0, y0 + ly]]
    return PanoLosa(mark=mark, nivel="N1", z_tope=3.0, lx=lx, ly=ly,
                    espesor=espesor, contorno=contorno, **kw)


class TestTiposPorApoyo(unittest.TestCase):
    def test_fila_de_tres_mas_uno_arriba(self):
        # A(0-5) B(5-10) C(10-15) en y 0-6; D encima de B (y 6-12).
        panos = [_pano("A", 5, 6), _pano("B", 5, 6, x0=5), _pano("C", 5, 6, x0=10),
                 _pano("D", 5, 6, x0=5, y0=6)]
        tipos = tipos_de_panos(panos)
        self.assertEqual(tipos["A"].codigo, 22)       # 1 vecino vertical (E)
        self.assertEqual(tipos["A"].empotrados, ("E",))
        self.assertEqual(tipos["B"].codigo, 51)       # E+W+N: 3 empotrados, simple S
        self.assertEqual(tipos["B"].empotrados, ("E", "N", "W"))
        self.assertEqual(tipos["C"].codigo, 22)
        self.assertEqual(tipos["D"].codigo, 21)       # 1 vecino horizontal (S)
        self.assertEqual(tipos["D"].empotrados, ("S",))

    def test_aislada_apoyada_y_descripciones(self):
        tipos = tipos_de_panos([_pano("SOLA", 4, 5)])
        t = tipos["SOLA"]
        self.assertEqual(t.codigo, 10)
        self.assertEqual(t.empotrados, ())
        self.assertEqual(t.descripcion, DESCRIPCION_CODIGO[10])
        self.assertEqual(t.borde_fem, "simple")
        self.assertIn("empotrados: ninguno", t.texto_param)

    def test_vuelo_no_empotra_al_vecino(self):
        panos = [_pano("V", 1.8, 6.0, x0=-1.8, es_vuelo=True, direccion="1D"),
                 _pano("A", 5, 6), _pano("B", 5, 6, x0=5)]
        tipos = tipos_de_panos(panos)
        self.assertEqual(tipos["A"].codigo, 22)       # solo B empotra; el vuelo no
        self.assertEqual(tipos["A"].empotrados, ("E",))
        self.assertEqual(tipos["V"].codigo, 72)       # vuela sobre la luz corta (X)
        self.assertTrue(tipos["V"].es_vuelo)

    def test_interior_cuatro_vecinos(self):
        panos = [_pano("CEN", 5, 6, x0=5, y0=6),
                 _pano("W", 5, 6, x0=0, y0=6), _pano("E", 5, 6, x0=10, y0=6),
                 _pano("S", 5, 6, x0=5, y0=0), _pano("N", 5, 6, x0=5, y0=12)]
        tipos = tipos_de_panos(panos)
        self.assertEqual(tipos["CEN"].codigo, 60)
        self.assertEqual(tipos["CEN"].empotrados, ("E", "N", "S", "W"))
        self.assertEqual(tipos["CEN"].borde_fem, "empotrado")

    def test_payload_y_json(self):
        panos = [_pano("A", 5, 6), _pano("B", 5, 6, x0=5)]
        tipos = tipos_de_panos(panos)
        payload = payload_revit(tipos)
        self.assertTrue(payload["A"].startswith("22 "))
        self.assertIn("empotrados: E", payload["A"])

        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "tipos_pm.json")
            escribir_tipos_json(tipos, ruta)
            with open(ruta, encoding="utf-8") as f:
                datos = json.load(f)
        self.assertEqual(datos["parametro_revit"], "Tipo_Losa_PM")
        self.assertEqual(datos["asignar_en_revit"], payload)
        self.assertEqual(datos["tipos"]["B"]["codigo"], 22)
        self.assertIn("F. Perdomo", datos["metodo"])


if __name__ == "__main__":
    unittest.main()
