"""Lógica paramétrica de aligeradas: nervios, ejes locales, topping y conexiones."""
import json
import unittest

from puente_losas.contrato import PanoLosa

from plugin_losas.aligeradas import (Conexion, conexiones, plan_pano,
                                     plan_sistema, seccion_de_pano)


def _pano(mark, lx, ly, espesor=0.25, x0=0.0, y0=0.0, **kw):
    contorno = [[x0, y0], [x0 + lx, y0], [x0 + lx, y0 + ly], [x0, y0 + ly]]
    return PanoLosa(mark=mark, nivel="N1", z_tope=3.0, lx=lx, ly=ly,
                    espesor=espesor, contorno=contorno, **kw)


class TestPlanPano(unittest.TestCase):
    def test_ribbed_1d_nervios_sobre_la_luz_corta(self):
        p = _pano("A1", 5.0, 6.5, direccion="1D")
        plan = plan_pano(p, "L25A-1D")
        self.assertEqual(plan.tipo, "Ribbed")
        self.assertEqual(plan.h_m, 0.25)
        self.assertEqual(plan.topping_m, 0.05)
        self.assertEqual(len(plan.nervios), 1)
        fam = plan.nervios[0]
        # lx=5.0 es la luz corta: los nervios corren según X y se reparten en ly=6.5
        self.assertEqual(fam.direccion, "X")
        self.assertEqual(plan.angulo_eje_local_1, 0.0)
        self.assertEqual(fam.luz_m, 5.0)
        # (6.5 - 0.20)/0.65 = 9.69 → 10 nervios centrados a 0.65 eje a eje
        self.assertEqual(fam.n, 10)
        self.assertEqual(fam.separacion_m, 0.65)
        self.assertEqual(fam.ancho_m, 0.20)
        self.assertAlmostEqual(fam.posiciones_m[0], 0.325, places=4)
        self.assertAlmostEqual(fam.posiciones_m[-1], 6.5 - 0.325, places=4)
        self.assertAlmostEqual(fam.posiciones_m[1] - fam.posiciones_m[0], 0.65, places=9)

    def test_ribbed_girado_cuando_la_luz_corta_es_y(self):
        p = _pano("A2", 6.5, 5.0, direccion="1D")
        plan = plan_pano(p, "L25A-1D")
        self.assertEqual(plan.nervios[0].direccion, "Y")
        self.assertEqual(plan.angulo_eje_local_1, 90.0)

    def test_waffle_2d_en_ambas_direcciones(self):
        p = _pano("A3", 5.0, 6.5, espesor=0.20)
        plan = plan_pano(p, "L20A-2D")
        self.assertEqual(plan.tipo, "Waffle")
        self.assertEqual({f.direccion for f in plan.nervios}, {"X", "Y"})
        self.assertIsNone(plan.angulo_eje_local_1)
        self.assertEqual(plan.nervios[0].ancho_m, 0.15)

    def test_chequeos_normativos_del_catalogo(self):
        plan = plan_pano(_pano("A4", 5.0, 6.0, direccion="1D"), "L25A-1D")
        ch = plan.chequeos
        self.assertTrue(ch["topping_ok"])                      # 0.05 >= 0.05
        self.assertAlmostEqual(ch["luz_libre_nervios_m"], 0.45)  # 0.65 - 0.20
        self.assertAlmostEqual(ch["limite_12_topping_m"], 0.60)  # 12 x 0.05
        self.assertTrue(ch["luz_libre_ok"])
        self.assertIn("CDCRD", ch["fuente"])

    def test_maciza_sin_nervios(self):
        plan = plan_pano(_pano("A5", 4.0, 5.0, espesor=0.20), "L20")
        self.assertEqual(plan.tipo, "Maciza")
        self.assertEqual(plan.nervios, ())
        self.assertIsNone(plan.topping_m)

    def test_seccion_fuera_de_biblioteca_rechazada(self):
        with self.assertRaises(ValueError):
            plan_pano(_pano("A6", 4.0, 5.0), "L30A-1D")

    def test_seccion_de_pano_sigue_la_regla_del_puente(self):
        self.assertEqual(seccion_de_pano(_pano("A7", 4.0, 5.0, espesor=0.25)), "L25A-2D")
        self.assertEqual(seccion_de_pano(_pano("A8", 2.0, 5.0, espesor=0.25)), "L25A-1D")
        self.assertEqual(seccion_de_pano(_pano("A9", 4.0, 5.0, espesor=0.15)), "L15")
        with self.assertRaises(ValueError):                    # 0.30: no inventar nervios
            seccion_de_pano(_pano("A10", 4.0, 5.0, espesor=0.30))


class TestConexiones(unittest.TestCase):
    def test_continuidad_de_momento_cuando_los_nervios_cruzan(self):
        # Dos paños 1D lado a lado: borde vertical compartido en x=5; la luz
        # corta es X en ambos → los nervios cruzan el borde → momento.
        a = _pano("B1", 5.0, 6.5, direccion="1D")
        b = _pano("B2", 5.0, 6.5, direccion="1D", x0=5.0)
        planes = {p.mark: plan_pano(p, "L25A-1D") for p in (a, b)}
        cons = conexiones([a, b], planes)
        self.assertEqual(len(cons), 1)
        c = cons[0]
        self.assertEqual({c.losa_i, c.losa_j}, {"B1", "B2"})
        self.assertEqual(c.borde, "vertical")
        self.assertEqual(c.continuidad, "momento")
        self.assertTrue(c.topping_igual)

    def test_solo_topping_cuando_los_nervios_van_paralelos_al_borde(self):
        # Paños con luz corta según Y (nervios según Y), uno al lado del otro:
        # el borde compartido es vertical y ningún nervio lo cruza.
        a = _pano("C1", 6.0, 3.0, direccion="1D")
        b = _pano("C2", 6.0, 3.0, direccion="1D", x0=6.0)
        planes = {p.mark: plan_pano(p, "L25A-1D") for p in (a, b)}
        c = conexiones([a, b], planes)[0]
        self.assertEqual(c.continuidad, "solo topping")
        self.assertFalse(c.nervios_cruzan_i)

    def test_maciza_da_continuidad_y_topping_queda_sin_comparar(self):
        a = _pano("D1", 5.0, 6.0, espesor=0.20)
        b = _pano("D2", 5.0, 6.0, espesor=0.25, x0=5.0, direccion="1D")
        planes = {"D1": plan_pano(a, "L20"), "D2": plan_pano(b, "L25A-1D")}
        c = conexiones([a, b], planes)[0]
        self.assertEqual(c.continuidad, "momento")     # maciza + nervios que cruzan
        self.assertIsNone(c.topping_igual)
        self.assertIn("secciones distintas", c.nota)

    def test_waffle_cruza_en_ambos_sentidos(self):
        a = _pano("E1", 5.0, 6.0, espesor=0.20)
        b = _pano("E2", 5.0, 6.0, espesor=0.20, y0=6.0)   # vecino arriba: borde horizontal
        planes = {p.mark: plan_pano(p, "L20A-2D") for p in (a, b)}
        c = conexiones([a, b], planes)[0]
        self.assertEqual(c.borde, "horizontal")
        self.assertEqual(c.continuidad, "momento")

    def test_junta_sismica_no_conecta(self):
        a = _pano("F1", 5.0, 6.0, direccion="1D")
        b = _pano("F2", 5.0, 6.0, direccion="1D", x0=5.1)   # junta de 0.10 m
        planes = {p.mark: plan_pano(p, "L25A-1D") for p in (a, b)}
        self.assertEqual(conexiones([a, b], planes), [])


class TestPlanSistema(unittest.TestCase):
    def test_plan_completo_es_json_able_y_acredita_el_catalogo(self):
        panos = [_pano("G1", 5.0, 6.5, direccion="1D"),
                 _pano("G2", 5.0, 6.5, direccion="1D", x0=5.0)]
        plan = plan_sistema(panos, secciones={"G1": "L25A-1D", "G2": "L25A-1D"})
        texto = json.dumps(plan, ensure_ascii=False)
        self.assertIn("Arlette Ramírez", texto)
        self.assertEqual(len(plan["panos"]), 2)
        self.assertEqual(len(plan["conexiones"]), 1)
        self.assertEqual(plan["panos"][0]["nervios"][0]["n"], 10)
        self.assertIn("normativa", plan)


if __name__ == "__main__":
    unittest.main()
