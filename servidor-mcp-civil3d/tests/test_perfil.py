"""Pruebas de perfil.py sin Civil 3D: nucleo numerico y un doble del puente.

El doble simula un alineamiento recto de 1000 m desde (1000, 2000) hacia +X, una
superficie plana inclinada z = 400 + 0.01*x_rel (x_rel = x - 1000) valida solo hasta
x_rel 950, y un perfil nativo igual a la superficie salvo en la estacion 500 (+0.20 m).
Datos sinteticos; no hay nada de un proyecto real.
"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import perfil  # noqa: E402


class PuenteDoble:
    def __init__(self):
        self.llamadas = []

    def __call__(self, metodo, parametros):
        self.llamadas.append((metodo, parametros))
        if metodo == "objects.query":
            assert isinstance(parametros["handles"], list) and isinstance(parametros["props"], list)
            if parametros["handles"] != ["AL01"]:
                return {"coincidencias": 0, "objetos": []}
            return {"coincidencias": 1, "objetos": [{"handle": "AL01", "Name": "EJE-SINTETICO",
                                                    "StartingStation": 100.0, "EndingStation": 1100.0,
                                                    "Length": 1000.0}]}
        if metodo == "objects.invoke":
            h, m, args = parametros["handle"], parametros["metodo"], parametros["args"]
            if h == "AL01" and m == "GetPointAtDist":
                return {"objetivo": h, "metodo": m, "resultado": [1000.0 + args[0], 2000.0, 0.0]}
            if h == "AL01" and m == "PointLocation":
                if args[0] > 1000.0:
                    raise RuntimeError("[-32603] PointNotOnEntityException: PointNotOnEntity")
                return {"objetivo": h, "metodo": m,
                        "resultado": {"retorno": None, "salidas": {"easting": 1000.0 + (args[0] - 100.0), "northing": 2000.0}}}
            if h == "SUP01" and m == "FindElevationAtXY":
                xr = args[0] - 1000.0
                if xr > 950:
                    raise RuntimeError("[-32602] el punto esta fuera de la superficie")
                return {"objetivo": h, "metodo": m, "resultado": 400.0 + 0.01 * xr}
            if h == "PRF01" and m == "ElevationAt":
                est = args[0]
                return {"objetivo": h, "metodo": m, "resultado": 400.0 + 0.01 * (est - 100.0) + (0.20 if est == 500.0 else 0.0)}
        raise AssertionError("llamada inesperada " + metodo + " " + repr(parametros))


class EstacionesTests(unittest.TestCase):
    def test_incluye_fin_no_multiplo(self):
        self.assertEqual(perfil.estaciones(0, 95, 20), [0, 20, 40, 60, 80, 95])

    def test_fin_multiplo_no_se_duplica(self):
        self.assertEqual(perfil.estaciones(0, 100, 20), [0, 20, 40, 60, 80, 100])

    def test_fin_no_se_redondea_hacia_arriba(self):
        # fin 21894.29268 -> ultima estacion 21894.292, nunca 21894.293
        est = perfil.estaciones(0, 21894.29268606544, 2000)
        self.assertEqual(est[-1], 21894.292)
        self.assertEqual(est[-2], 20000)
        est2 = perfil.estaciones(0, 99.9996, 50)
        self.assertEqual(est2, [0, 50, 99.999])

    def test_error_xy_no_aborta(self):
        p = PuenteDoble()
        # el doble lanza PointNotOnEntity en PointLocation si la estacion pasa de 1000
        r = perfil.muestrear(p, "AL01", "SUP01", 600.0, inicio=100.0, fin=1100.0, usar_pointlocation=True)
        self.assertEqual([m["estacion"] for m in r["muestras"]], [100, 700, 1100])
        self.assertNotIn("error_xy", r["muestras"][0])
        self.assertIn("PointNotOnEntity", r["muestras"][-1]["error_xy"])
        self.assertIsNone(r["muestras"][-1]["z_superficie"])
        self.assertEqual(r["resumen"]["con_cota"], 2)

    def test_tramo_nulo(self):
        self.assertEqual(perfil.estaciones(50, 50, 10), [50])

    def test_invalidos(self):
        for args in ((0, 10, 0), (10, 0, 5), (float("nan"), 1, 1)):
            with self.assertRaises(ValueError):
                perfil.estaciones(*args)


class CompararTests(unittest.TestCase):
    def test_estadisticas_y_fuera_de_tolerancia(self):
        m = [{"estacion": 0, "z_superficie": 10.0, "z_perfil": 10.01},
             {"estacion": 10, "z_superficie": 10.0, "z_perfil": 10.30},
             {"estacion": 20, "z_superficie": 10.0, "z_perfil": None},
             {"estacion": 30, "z_superficie": None, "z_perfil": 9.0}]
        c = perfil.comparar(m, 0.05)
        self.assertEqual(c["comparadas"], 2)
        self.assertEqual(c["max_abs_m"], 0.30)
        self.assertEqual(c["estacion_max_abs"], 10)
        self.assertEqual(c["media_m"], 0.155)
        self.assertEqual(c["fuera_tolerancia"], [{"estacion": 10, "diferencia_m": 0.30}])
        self.assertEqual(c["veredicto"], "difiere")

    def test_sin_datos(self):
        c = perfil.comparar([{"estacion": 0, "z_superficie": None, "z_perfil": None}], 0.1)
        self.assertEqual(c["veredicto"], "sin_datos")
        self.assertEqual(c["comparadas"], 0)

    def test_tolerancia_negativa(self):
        with self.assertRaises(ValueError):
            perfil.comparar([], -1)


class ResumenTests(unittest.TestCase):
    def test_pendientes(self):
        m = [{"estacion": 0, "z_superficie": 100.0}, {"estacion": 100, "z_superficie": 99.0},
             {"estacion": 200, "z_superficie": 99.5}, {"estacion": 300, "z_superficie": None}]
        r = perfil.resumen(m)
        self.assertEqual((r["muestras"], r["con_cota"], r["sin_cota"]), (4, 3, [300]))
        self.assertEqual(r["pendiente_media"], -0.0025)
        self.assertEqual(r["pendiente_max"], 0.005)
        self.assertEqual(r["pendiente_min"], -0.01)
        self.assertEqual((r["z_min_m"], r["z_max_m"]), (99.0, 100.0))


class MuestreoConDobleTests(unittest.TestCase):
    def test_muestreo_completo_con_perfil(self):
        p = PuenteDoble()
        r = perfil.muestrear(p, "AL01", "SUP01", 200.0, perfil="PRF01")
        self.assertEqual(r["alineamiento"]["nombre"], "EJE-SINTETICO")
        self.assertEqual([m["estacion"] for m in r["muestras"]], [100, 300, 500, 700, 900, 1100])
        self.assertEqual(r["muestras"][0]["x"], 1000.0)          # estacion 100 = distancia 0
        self.assertEqual(r["muestras"][0]["z_superficie"], 400.0)
        self.assertEqual(r["muestras"][2]["z_perfil"], 404.2)     # 400 + 0.01*400 + 0.20
        self.assertIsNone(r["muestras"][-1]["z_superficie"])      # fuera de la superficie
        self.assertIn("fuera de la superficie", r["muestras"][-1]["error_superficie"])
        self.assertEqual(r["resumen"]["sin_cota"], [1100])
        c = perfil.comparar(r["muestras"], 0.05)
        self.assertEqual(c["comparadas"], 5)
        self.assertEqual(c["fuera_tolerancia"], [{"estacion": 500, "diferencia_m": 0.2}])
        self.assertEqual(r["metodo_xy"], "GetPointAtDist")

    def test_recorte_inicio_fin_y_pointlocation(self):
        p = PuenteDoble()
        r = perfil.muestrear(p, "AL01", "SUP01", 50.0, inicio=0.0, fin=250.0, usar_pointlocation=True)
        self.assertEqual([m["estacion"] for m in r["muestras"]], [100, 150, 200, 250])
        self.assertEqual(r["muestras"][1]["x"], 1050.0)
        self.assertEqual(r["metodo_xy"], "PointLocation")
        self.assertTrue(any(m == "objects.invoke" and q["metodo"] == "PointLocation" and q["args"][2] is None
                            for m, q in p.llamadas))

    def test_alineamiento_inexistente(self):
        with self.assertRaises(LookupError):
            perfil.muestrear(PuenteDoble(), "NOPE", "SUP01", 10.0)

    def test_solo_lecturas(self):
        p = PuenteDoble()
        perfil.muestrear(p, "AL01", "SUP01", 500.0, perfil="PRF01")
        for metodo, q in p.llamadas:
            self.assertIn(metodo, ("objects.query", "objects.invoke"))
            self.assertNotIn("token", q)

    def test_csv(self):
        p = PuenteDoble()
        r = perfil.muestrear(p, "AL01", "SUP01", 500.0, perfil="PRF01")
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "p.csv"
            perfil.escribir_csv(r["muestras"], ruta)
            lineas = ruta.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lineas[0], "estacion,x,y,z_superficie,z_perfil,error_xy,error_superficie,error_perfil")
            self.assertEqual(len(lineas), 4)


if __name__ == "__main__":
    unittest.main()
