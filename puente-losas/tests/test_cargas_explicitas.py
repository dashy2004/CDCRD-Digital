import unittest

from puente_losas.cargas import cargas_de_pano
from puente_losas.contrato import aplicar_usos, panos_desde_dict


class TestCargasExplicitas(unittest.TestCase):
    def test_peso_medido_no_modifica_espesor_de_rigidez(self):
        p = panos_desde_dict({"losas": [{"mark": "EJ1", "lx": 4, "ly": 5, "espesor": 0.25,
            "viva_tm2": 0.48, "acabados_tm2": 0.16, "peso_propio_tm2": 0.31}]})[0]
        cargas = cargas_de_pano(p)
        self.assertEqual(p.espesor, 0.25)
        self.assertEqual(cargas.peso_propio, 0.31)
        self.assertEqual(cargas.viva, 0.48)
        self.assertAlmostEqual(cargas.q_ultima, 1.2 * (0.31 + 0.16 + 0.10) + 1.6 * 0.48)

    def test_cero_explicito_y_valores_invalidos(self):
        p = panos_desde_dict({"losas": [{"mark": "EJ1", "lx": 4, "ly": 5, "espesor": 0.2}]})[0]
        self.assertEqual(cargas_de_pano(aplicar_usos([p], {"EJ1": {"viva_tm2": 0}})[0]).viva, 0)
        for bad in (-1, float("nan"), float("inf"), True, "0.4"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                aplicar_usos([p], {"EJ1": {"viva_tm2": bad}})
