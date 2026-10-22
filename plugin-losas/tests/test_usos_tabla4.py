"""Tabla 4 (cargas_vivas.json): carga, ids, conversión de unidades y sets sugeridos."""
import unittest

from plugin_losas.usos_tabla4 import (KN_M2_A_T_M2, cargar_tabla4,
                                      opciones_desplegable, set_sugerido)


def _uso(tabla, grupo, nombre):
    for u in tabla.usos:
        if u.grupo == grupo and u.uso == nombre:
            return u
    raise AssertionError(f"no está {grupo}/{nombre}")


class TestCargaTabla4(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tabla = cargar_tabla4()

    def test_carga_los_45_usos_de_la_tabla(self):
        self.assertEqual(len(self.tabla.usos), 45)

    def test_ids_estables_y_unicos(self):
        ids = [u.id for u in self.tabla.usos]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn("uso-residencial-corredores-y-escaleras", ids)

    def test_fuente_declarada(self):
        self.assertEqual(self.tabla.fuente.get("tabla"), "4")

    def test_conversion_kn_a_t(self):
        gim = _uso(self.tabla, "Edificios de uso recreacional", "Gimnasios")
        self.assertAlmostEqual(gim.viva_kn_m2, 4.79)
        self.assertAlmostEqual(gim.viva_tm2, 4.79 * KN_M2_A_T_M2, places=9)
        self.assertAlmostEqual(gim.viva_tm2, 0.48845, places=4)

    def test_uso_por_regla_sin_valor(self):
        balcon = _uso(self.tabla, "Balcones y terrazas", "Balcones y terrazas")
        self.assertIsNone(balcon.viva_kn_m2)
        self.assertIsNone(balcon.viva_tm2)
        self.assertIn("1.5", balcon.regla)

    def test_opciones_desplegable_en_orden_y_con_etiqueta(self):
        ops = opciones_desplegable(self.tabla)
        self.assertEqual(len(ops), 45)
        self.assertEqual(ops[0]["grupo"], "Uso residencial")
        self.assertIn("kN/m²", ops[0]["etiqueta"])

    def test_json_invalido_rechazado(self):
        import json
        import os
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "otro.json")
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump({"parametro": "otra_cosa"}, f)
            with self.assertRaises(ValueError):
                cargar_tabla4(ruta)


class TestSetSugerido(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tabla = cargar_tabla4()

    def _sug(self, grupo, nombre):
        return set_sugerido(_uso(self.tabla, grupo, nombre))

    def test_aulas_caben_en_entrepisos(self):
        s = self._sug("Escuelas y colegios", "Aulas")        # 1.92 kN = 0.196 t/m²
        self.assertEqual(s.set_carga, "entrepisos")
        self.assertTrue(s.cubre)

    def test_oficinas_suben_a_comun(self):
        s = self._sug("Edificios para oficinas", "Oficinas")  # 2.40 kN = 0.245 > 0.20
        self.assertEqual(s.set_carga, "comun")
        self.assertTrue(s.cubre)

    def test_gimnasios_al_set_gimnasio(self):
        s = self._sug("Edificios de uso recreacional", "Gimnasios")   # 4.79 kN
        self.assertEqual(s.set_carga, "gimnasio")
        self.assertTrue(s.cubre)

    def test_escenarios_no_los_cubre_ningun_set(self):
        s = self._sug("Edificios para reuniones", "Escenarios")       # 7.18 kN
        self.assertEqual(s.set_carga, "gimnasio")
        self.assertFalse(s.cubre)
        self.assertIn("declarar carga especial", s.nota)

    def test_techos_planos_al_set_techo(self):
        s = self._sug("Techos", "Techos planos, inclinados y curvos")  # 0.96 kN
        self.assertEqual(s.set_carga, "techo")
        self.assertTrue(s.cubre)

    def test_techo_almacen_supera_el_set_techo(self):
        s = self._sug("Techos", "Techos usados para almacenamiento")   # 4.79 kN
        self.assertEqual(s.set_carga, "techo")
        self.assertFalse(s.cubre)

    def test_garajes_al_set_parqueos(self):
        s = self._sug("Garajes y estacionamientos", "Vehiculos livianos")
        self.assertEqual(s.set_carga, "parqueos")
        self.assertTrue(s.cubre)

    def test_balcones_exigen_declaracion(self):
        s = self._sug("Balcones y terrazas", "Balcones y terrazas")
        self.assertIsNone(s.set_carga)
        self.assertFalse(s.cubre)


if __name__ == "__main__":
    unittest.main()
