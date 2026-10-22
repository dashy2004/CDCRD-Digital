"""Acero comercial para momentos PM (requiere motor_fea; se omite sin él)."""
import unittest

try:
    import motor_fea  # noqa: F401
    HAY_MOTOR = True
except ImportError:
    HAY_MOTOR = False

from tests.test_resultados_pm import PROYECTO, RESULTADOS


@unittest.skipUnless(HAY_MOTOR, "motor_fea (EstructurasRD) no instalado")
class TestAceroPm(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from plugin_losas.acero_pm import acero_pm_de_resultados
        cls.acero = acero_pm_de_resultados(RESULTADOS)

    def test_armados_por_losa_con_barra_comercial(self):
        losa = self.acero["losas"]["LV1"]
        self.assertEqual(losa["h_m"], 0.25)
        self.assertEqual(set(losa["armados"]), {"mfx", "mfy", "msx", "msy"})
        arm = losa["armados"]["msx"]            # 1.41 ton·m/m
        self.assertGreater(arm["as_diseno"], 0)
        self.assertTrue(arm["cumple"])
        self.assertIn("@", arm["disponer"])     # barra comercial con separación

    def test_momento_nulo_gobierna_el_minimo(self):
        arm = self.acero["losas"]["LV1"]["armados"]["msy"]   # Msy = 0
        self.assertTrue(arm["gobierna_minimo"])
        self.assertIn("@", arm["disponer"])

    def test_apoyo_balanceado_con_espesor_menor(self):
        a = self.acero["apoyos"][0]
        self.assertEqual(a["h_m"], 0.25)
        self.assertAlmostEqual(a["mu_ij"], 1.59)
        self.assertIn("@", a["armado"]["disponer"])

    def test_mas_momento_mas_acero(self):
        as_vano = self.acero["losas"]["LV1"]["armados"]["mfy"]["as_requerido"]   # 0.62
        as_apoyo = self.acero["losas"]["LV1"]["armados"]["msx"]["as_requerido"]  # 1.41
        self.assertGreater(as_apoyo, as_vano)

    def test_dto_visor_lleva_el_armado_pm(self):
        from plugin_losas.resultados_pm import dto_visor
        dto = dto_visor(PROYECTO, RESULTADOS, acero=self.acero)
        self.assertIn("@", dto.panos[0]["armado_pm"]["mfx"])
        self.assertIn("@", dto.apoyos[0]["disponer"])

    def test_sin_bloque_pm_falla(self):
        from plugin_losas.acero_pm import acero_pm_de_resultados
        with self.assertRaises(ValueError):
            acero_pm_de_resultados({"panos": []})


if __name__ == "__main__":
    unittest.main()
