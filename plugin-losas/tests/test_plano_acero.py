"""Trazos del armado en planta: principal, temperatura y bastones de apoyo."""
import unittest

from plugin_losas.plano_acero import (formatear_acero, partir_acero,
                                      plano_acero, trazo_de_apoyo,
                                      trazos_de_losa)

from tests.test_resultados_pm import PROYECTO, RESULTADOS

RECT_2D = [[0, 0], [5, 0], [5, 6], [0, 6]]
RECT_1D = [[0, 0], [6, 0], [6, 2.5], [0, 2.5]]     # trabaja según Y (luz corta)


class TestTrazosDeLosa(unittest.TestCase):
    def test_2d_lleva_principal_en_ambas_direcciones(self):
        trazos = trazos_de_losa(RECT_2D, False, "#3 @ 0.15", "#4 @ 0.20")
        self.assertEqual([t.clase for t in trazos], ["principal", "principal"])
        self.assertEqual(trazos[0].texto, "#3 @ 0.15")
        self.assertEqual(trazos[1].texto, "#4 @ 0.20")
        # el principal X mide 0.5·Lx con ganchos en los extremos (4 puntos)
        xs = [p[0] for p in trazos[0].puntos]
        self.assertAlmostEqual(max(xs) - min(xs), 2.5)
        self.assertEqual(len(trazos[0].puntos), 4)

    def test_1d_principal_sobre_la_luz_corta_y_temperatura(self):
        trazos = trazos_de_losa(RECT_1D, False, "#3 @ 0.25", "#4 @ 0.15")
        self.assertEqual([t.clase for t in trazos], ["principal", "temperatura"])
        principal, temp = trazos
        ys = [p[1] for p in principal.puntos]
        self.assertAlmostEqual(max(ys) - min(ys), 0.5 * 2.5)   # según Y
        self.assertEqual(principal.texto, "#4 @ 0.15")
        self.assertTrue(temp.discontinua)
        self.assertIn("(temp)", temp.texto)
        self.assertIn("#3", temp.texto)

    def test_vuelo_solo_principal(self):
        trazos = trazos_de_losa([[0, 0], [1.8, 0], [1.8, 6], [0, 6]], True,
                                "#3 @ 0.20", "")
        self.assertEqual([t.clase for t in trazos], ["principal"])


class TestTrazoDeApoyo(unittest.TestCase):
    def test_baston_cruza_el_borde_con_l4_a_cada_lado(self):
        t = trazo_de_apoyo((0, 0, 5, 6), (5, 0, 10, 6), "X", "#4 @ 0.18")
        self.assertEqual(t.clase, "adicional")
        xs = [p[0] for p in t.puntos]
        self.assertAlmostEqual(min(xs), 5 - 0.25 * 5)
        self.assertAlmostEqual(max(xs), 5 + 0.25 * 5)
        self.assertEqual(t.texto, "#4 @ 0.18")

    def test_sin_solape_no_hay_baston(self):
        self.assertIsNone(trazo_de_apoyo((0, 0, 5, 6), (5, 10, 10, 16), "X", "x"))


class TestPlanoCompleto(unittest.TestCase):
    def test_plan_desde_la_corrida_con_editados(self):
        editados = {"LV1": {"x": "#5 @ 0.10", "apoyo": "#6 @ 0.12"}}
        plan = plano_acero(PROYECTO, RESULTADOS, acero_pm=None, editados=editados)
        self.assertEqual(plan["unidades"], "m")
        self.assertEqual(plan["origen_m"], [0.0, 0.0])      # sin meta no hay traslación
        self.assertEqual(len(plan["losas"]), 2)
        lv1 = next(x for x in plan["losas"] if x["mark"] == "LV1")
        textos = [t["texto"] for t in lv1["trazos"]]
        self.assertIn("#5 @ 0.10", textos)              # el editado manda
        self.assertEqual(len(plan["apoyos"]), 1)
        self.assertEqual(plan["apoyos"][0]["trazo"]["texto"], "#6 @ 0.12")
        self.assertIn("Acero_Apoyo", plan["tabla_parametros"])

    def test_origen_trasladado_del_export(self):
        proyecto = dict(PROYECTO)
        proyecto["meta"] = {"traslacion_origen_mm": [843100.0, 459900.0]}
        plan = plano_acero(proyecto, RESULTADOS)
        self.assertEqual(plan["origen_m"], [843.1, 459.9])

    def test_sin_editados_usa_las_franjas_de_la_corrida(self):
        plan = plano_acero(PROYECTO, RESULTADOS)
        lv2 = next(x for x in plan["losas"] if x["mark"] == "LV2")
        textos = " ".join(t["texto"] for t in lv2["trazos"])
        self.assertIn("Ø3/8\" @0.15", textos)           # franja_x del fixture


class TestFormatoBarra(unittest.TestCase):
    def test_partir_mm_y_metros(self):
        self.assertEqual(partir_acero("#3 @ 150 mm"), ("#3", 0.15))
        self.assertEqual(partir_acero("#4 @ 0.20"), ("#4", 0.2))
        self.assertIsNone(partir_acero("Ø3/8\" @0.15"))
        self.assertIsNone(partir_acero(""))

    def test_formatear_y_validar(self):
        self.assertEqual(formatear_acero("#4", 0.15), "#4 @ 0.15")
        with self.assertRaises(ValueError):
            formatear_acero("#9", 0.15)
        with self.assertRaises(ValueError):
            formatear_acero("#3", 5.0)


if __name__ == "__main__":
    unittest.main()
