"""Plan de modelado 3D: sets, solape 50db mitad y mitad, nervios y bastones."""
import unittest

from plugin_losas.modelado_acero import (BARRA_COMERCIAL_M, piezas_con_solape,
                                         plan_modelado)


def _losa(mark, x0, y0, lx, ly, nivel="N1"):
    return {"mark": mark, "nivel": nivel,
            "contorno": [[x0, y0], [x0 + lx, y0], [x0 + lx, y0 + ly], [x0, y0 + ly]]}


def _proyecto(losas, origen_mm=None):
    p = {"losas": losas}
    if origen_mm:
        p["meta"] = {"traslacion_origen_mm": origen_mm}
    return p


def _resultados(marks, es_vuelo=(), apoyos=None):
    return {"panos": [{"mark": m, "es_vuelo": m in es_vuelo} for m in marks],
            "pieper_martens": {"apoyos": apoyos or []}}


class TestPiezas(unittest.TestCase):
    def test_vano_corto_una_pieza(self):
        self.assertEqual(piezas_con_solape(5.0, 0.0127, 0), [(0.0, 5.0)])

    def test_grupo_a_arranca_entero_y_solapa_50db(self):
        piezas = piezas_con_solape(12.0, 0.0127, 0)      # #4: lap = 0.635
        self.assertEqual(piezas[0], (0.0, BARRA_COMERCIAL_M))
        self.assertAlmostEqual(piezas[1][0], 9.0 - 0.635, places=6)
        self.assertEqual(piezas[-1][1], 12.0)

    def test_grupo_b_arranca_con_media_pieza(self):
        piezas = piezas_con_solape(12.0, 0.0127, 1)
        self.assertEqual(piezas[0], (0.0, 4.5))
        self.assertAlmostEqual(piezas[1][0], 4.5 - 0.635, places=6)
        self.assertEqual(piezas[-1][1], 12.0)

    def test_pieza_final_minima_estira_el_solape(self):
        # 9.1 m: la 2a pieza saldria de 0.735 m (<1.0) -> arranca en 8.1
        piezas = piezas_con_solape(9.1, 0.0127, 0)
        self.assertEqual(len(piezas), 2)
        self.assertAlmostEqual(piezas[1][0], 8.1, places=6)


class TestLosas(unittest.TestCase):
    def test_2d_ambas_principales_y_la_corta_abajo(self):
        plan = plan_modelado(
            _proyecto([_losa("L00", 0, 0, 4, 5)]), _resultados(["L00"]),
            editados={"L00": {"x": "#4 @ 0.15", "y": "#3 @ 0.20"}})
        sets = plan["losas"][0]["sets"]
        self.assertEqual(len(sets), 2)
        por_eje = {s["eje"]: s for s in sets}
        sx, sy = por_eje["X"], por_eje["Y"]
        self.assertEqual((sx["clase"], sx["capa"], sx["orden"]), ("principal", "inferior", 1))
        self.assertEqual((sy["clase"], sy["capa"], sy["orden"]), ("principal", "inferior", 2))
        # X: barras de 0.025 a 3.975, repartidas en y (0.025..4.975) cada 0.15
        self.assertEqual(sx["linea"][0][0], 0.025)
        self.assertEqual(sx["linea"][1][0], 3.975)
        self.assertEqual(sx["n"], 34)             # floor(4.95/0.15)+1
        self.assertEqual(sx["paso_m"], 0.15)
        self.assertEqual(sy["n"], 20)             # floor(3.95/0.20)+1
        self.assertEqual(plan["losas"][0]["resumen"]["solapes"], 0)

    def test_1d_con_solape_en_grupos_a_y_b(self):
        plan = plan_modelado(
            _proyecto([_losa("L01", 0, 0, 4, 10)]), _resultados(["L01"]),
            editados={"L01": {"x": "#4 @ 0.15", "y": "#3 @ 0.25"}})
        sets = plan["losas"][0]["sets"]
        principales = [s for s in sets if s["clase"] == "principal"]
        temps = [s for s in sets if s["clase"] == "temperatura"]
        self.assertEqual([s["eje"] for s in principales], ["X"])
        self.assertEqual(len(temps), 4)           # 2 grupos x 2 piezas (9.95 m)
        self.assertEqual({s["grupo"] for s in temps}, {"A", "B"})
        a = [s for s in temps if s["grupo"] == "A"]
        self.assertEqual(a[0]["paso_m"], 0.5)     # 2 x 0.25
        self.assertAlmostEqual(a[0]["solape_m"], 50 * 0.009525, places=6)
        # piezas del grupo A contiguas con traslape: fin1 - ini2 = lap
        self.assertAlmostEqual(a[0]["linea"][1][1] - a[1]["linea"][0][1],
                               50 * 0.009525, places=5)
        # el grupo B empieza desfasado una separacion
        b = [s for s in temps if s["grupo"] == "B"]
        self.assertAlmostEqual(b[0]["linea"][0][0] - a[0]["linea"][0][0],
                               0.25, places=6)
        barras = plan["losas"][0]["resumen"]
        self.assertGreater(barras["solapes"], 0)

    def test_vuelo_principal_arriba(self):
        plan = plan_modelado(
            _proyecto([_losa("V1", 0, 0, 1.5, 4)]),
            _resultados(["V1"], es_vuelo={"V1"}),
            editados={"V1": {"x": "#4 @ 0.15", "y": "#3 @ 0.25"}})
        sets = plan["losas"][0]["sets"]
        self.assertTrue(all(s["capa"] == "superior" for s in sets))

    def test_aligerada_principal_por_nervio_y_temp_en_topping(self):
        aligeradas = {"panos": [{
            "mark": "L02", "seccion": "L25A-1D",
            "nervios": [{"direccion": "X", "n": 3, "separacion_m": 0.65,
                         "ancho_m": 0.20, "luz_m": 4.0,
                         "posiciones_m": [0.5, 1.15, 1.8]}]}]}
        plan = plan_modelado(
            _proyecto([_losa("L02", 10, 20, 4, 9)]), _resultados(["L02"]),
            editados={"L02": {"x": "#4 @ 0.65", "y": "#3 @ 0.25"}},
            aligeradas=aligeradas)
        losa = plan["losas"][0]
        self.assertTrue(losa["aligerada"])
        principal = [s for s in losa["sets"] if s["clase"] == "principal"][0]
        # una barra por nervio, en las posiciones del plan (y0=20 + 0.5)
        self.assertEqual(principal["n"], 3)
        self.assertEqual(principal["paso_m"], 0.65)
        self.assertEqual(principal["linea"][0][1], 20.5)
        temp = [s for s in losa["sets"] if s["clase"] == "temperatura"][0]
        self.assertEqual(temp["capa"], "superior")

    def test_seccion_y_espesor_del_payload(self):
        plan = plan_modelado(
            _proyecto([_losa("L00", 0, 0, 4, 5)]), _resultados(["L00"]),
            editados={"L00": {"x": "#4 @ 0.15", "y": "#3 @ 0.20"}},
            secciones={"secciones": {"L00": {"seccion": "L15", "espesor_m": 0.15}}})
        self.assertEqual(plan["losas"][0]["seccion"], "L15")
        self.assertEqual(plan["losas"][0]["espesor_m"], 0.15)

    def test_acero_ilegible_avisa_y_omite(self):
        plan = plan_modelado(
            _proyecto([_losa("L00", 0, 0, 4, 5)]), _resultados(["L00"]),
            editados={"L00": {"x": "#4 @ 0.15", "y": "no-se-lee"}})
        self.assertEqual(len(plan["losas"][0]["sets"]), 1)
        self.assertTrue(any("L00" in a for a in plan["avisos"]))


class TestBastones(unittest.TestCase):
    def test_baston_cruza_el_borde_l4_a_cada_lado(self):
        apoyos = [{"losa_i": "L00", "losa_j": "L01", "direccion": "X"}]
        plan = plan_modelado(
            _proyecto([_losa("L00", 0, 0, 4, 5), _losa("L01", 4, 0, 4, 5)]),
            _resultados(["L00", "L01"], apoyos=apoyos),
            editados={"L00": {"x": "#4 @ 0.15", "y": "#4 @ 0.15", "apoyo": "#4 @ 0.20"},
                      "L01": {"x": "#4 @ 0.15", "y": "#4 @ 0.15"}})
        self.assertEqual(len(plan["bastones"]), 1)
        s = plan["bastones"][0]["set"]
        self.assertEqual((s["clase"], s["capa"], s["eje"]), ("adicional", "superior", "X"))
        self.assertEqual(s["linea"][0][0], 3.0)   # borde 4.0 - 4/4
        self.assertEqual(s["linea"][1][0], 5.0)   # borde 4.0 + 4/4
        self.assertEqual(s["mark"], "L00")        # anfitriona = losa_i

    def test_origen_del_export_viaja_en_el_plan(self):
        plan = plan_modelado(
            _proyecto([_losa("L00", 0, 0, 4, 5)], origen_mm=[1000.0, 2000.0]),
            _resultados(["L00"]),
            editados={"L00": {"x": "#4 @ 0.15", "y": "#4 @ 0.15"}})
        self.assertEqual(plan["origen_m"], [1.0, 2.0])


if __name__ == "__main__":
    unittest.main()
