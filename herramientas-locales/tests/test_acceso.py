"""Casos sintéticos para el piloto de acceso."""
import json
import unittest
from copy import deepcopy
from pathlib import Path

from cdcrd_local.acceso import comparar, revisar

CASOS = Path(__file__).resolve().parents[1] / "ejemplos" / "homologacion"


class AccesoTests(unittest.TestCase):
    def setUp(self):
        def cargar(archivo):
            return json.loads((CASOS / archivo).read_text(encoding="utf-8-sig"))
        self.reglas = cargar("criterios.json")
        self.antes = cargar("antes.json")
        self.despues = cargar("despues.json")

    def test_cambio_releido(self):
        previo = revisar(self.antes, self.reglas)
        self.assertEqual(previo["estado"], "observado")
        self.assertAlmostEqual(previo["medidas"]["desnivel_m"], 0.04)
        nuevo = revisar(self.despues, self.reglas)
        self.assertEqual(nuevo["estado"], "dentro_de_criterios")
        self.assertIsNone(nuevo.get("aprobacion"))
        self.assertEqual(comparar(self.antes, self.despues, self.reglas)["cambio"],
                         "correccion_geometrica_releida")

    def test_falla_control_bloquea_calculo(self):
        self.despues[-1]["punto_m"][2] += 1
        r = revisar(self.despues, self.reglas)
        self.assertEqual(r["estado"], "pendiente")
        self.assertNotIn("desnivel_m", r["medidas"])

    def test_no_admite_distinto_datum(self):
        self.despues[1]["marco"] = "Otro datum"
        self.assertEqual(revisar(self.despues, self.reglas)["estado"], "pendiente")

    def test_extremos_separados(self):
        self.despues[1]["punto_m"][0] += 5
        self.assertEqual(revisar(self.despues, self.reglas)["estado"], "pendiente")

    def test_rejilla_elevada(self):
        self.despues[2]["punto_m"][2] += 1
        r = revisar(self.despues, self.reglas)
        self.assertEqual(r["estado"], "observado")
        self.assertLess(r["medidas"]["pendiente_entre_extremos_pct"], 0)

    def test_roles_faltantes_o_repetidos(self):
        self.assertEqual(revisar(self.antes[:-1], self.reglas)["estado"], "pendiente")
        with self.assertRaises(ValueError):
            revisar(self.antes + self.antes[:1], self.reglas)

    def test_revision_o_elemento_incompatible(self):
        repro = deepcopy(self.antes)
        repro[1]["punto_m"] = list(self.despues[1]["punto_m"])
        with self.assertRaises(ValueError):
            comparar(self.antes, repro, self.reglas)
        self.despues[0]["elemento"] = "otro"
        with self.assertRaises(ValueError):
            comparar(self.antes, self.despues, self.reglas)

    def test_sin_falsos_cierres(self):
        self.assertNotEqual(comparar(self.despues, self.despues, self.reglas)["cambio"],
                            "correccion_geometrica_releida")
        self.antes[-1]["marco"] = "distinto"
        self.assertNotEqual(comparar(self.antes, self.despues, self.reglas)["cambio"],
                            "correccion_geometrica_releida")

    def test_dos_puntos_desplazados_no_cierran_la_incidencia(self):
        for registro in self.despues:
            registro["revision"] = "R3"
        for r in self.despues[:2]:
            r["punto_m"][0] += 1.5
        with self.assertRaisesRegex(ValueError, "emplazamiento"):
            comparar(self.antes, self.despues, self.reglas)

    def test_cambio_coherente_de_datum_no_cierra_la_incidencia(self):
        for r in self.despues[-2:]:
            r["punto_m"][2] += 2.0
            r["revision"] = "R3"
        with self.assertRaisesRegex(ValueError, "testigo"):
            comparar(self.antes, self.despues, self.reglas)

    def test_sin_valores_implicitos(self):
        with self.assertRaisesRegex(ValueError, "seis criterios"):
            revisar(self.antes, dict(self.reglas, extra="metadato"))
        with self.assertRaisesRegex(ValueError, "ocho campos"):
            revisar([dict(self.antes[0], extra="metadato")], self.reglas)
        for valor in [True, float("inf"), float("nan"), "10"]:
            with self.subTest(valor=valor), self.assertRaises(ValueError):
                self.antes[0]["punto_m"][0] = valor
                revisar(self.antes, self.reglas)
