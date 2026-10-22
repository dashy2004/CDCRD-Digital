"""CLI del plugin: los tres subcomandos de punta a punta con datos inventados."""
import json
import os
import tempfile
import unittest

from plugin_losas.cli import main

from tests.test_extraccion import EXPORT_INVENTADO, ID_AULAS
from tests.test_resultados_pm import PROYECTO, RESULTADOS


def _escribir(d, carpeta, nombre):
    ruta = os.path.join(carpeta, nombre)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    return ruta


class TestCli(unittest.TestCase):
    def test_tabla_desde_export_revit(self):
        with tempfile.TemporaryDirectory() as d:
            proyecto = _escribir(EXPORT_INVENTADO, d, "proyecto.json")
            marcados = _escribir({"LE1": ID_AULAS}, d, "marcados.json")
            salida = os.path.join(d, "salidas")
            rc = main(["tabla", "--proyecto", proyecto, "--usos-marcados", marcados,
                       "--salida", salida, "--nombre", "Ejemplo Inventado"])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(os.path.join(salida, "tabla_losas.xlsx")))
            with open(os.path.join(salida, "usos.json"), encoding="utf-8") as f:
                usos = json.load(f)
            self.assertEqual(usos["LE1"], {"uso": "entrepisos"})
            self.assertTrue(os.path.isfile(os.path.join(salida, "avisos.txt")))

    def test_tabla_desde_dxf(self):
        from tests.test_acad_dxf import FIXTURE
        with tempfile.TemporaryDirectory() as d:
            dxf = os.path.join(d, "plano.dxf")
            with open(dxf, "w", encoding="cp1252") as f:
                f.write(FIXTURE)
            salida = os.path.join(d, "salidas")
            rc = main(["tabla", "--dxf", dxf, "--capa", "LOSAS", "--espesor", "0.20",
                       "--salida", salida])
            self.assertEqual(rc, 0)
            with open(os.path.join(salida, "losas_acad.json"), encoding="utf-8") as f:
                export = json.load(f)
            self.assertEqual(len(export["losas"]), 3)

    def test_aligeradas(self):
        with tempfile.TemporaryDirectory() as d:
            proyecto = _escribir(EXPORT_INVENTADO, d, "proyecto.json")
            salida = os.path.join(d, "salidas")
            rc = main(["aligeradas", "--proyecto", proyecto, "--salida", salida,
                       "--usos", _escribir({"LE6": {"direccion": "1D"}}, d, "usos.json")])
            self.assertEqual(rc, 0)
            with open(os.path.join(salida, "plan_aligeradas.json"), encoding="utf-8") as f:
                plan = json.load(f)
            self.assertEqual(len(plan["panos"]), 3)
            self.assertTrue(any(c["continuidad"] for c in plan["conexiones"]))

    def test_visor(self):
        with tempfile.TemporaryDirectory() as d:
            proyecto = _escribir(PROYECTO, d, "proyecto.json")
            resultados = _escribir(RESULTADOS, d, "resultados.json")
            salida = os.path.join(d, "salidas")
            rc = main(["visor", "--proyecto", proyecto, "--resultados", resultados,
                       "--salida", salida, "--nombre", "Ejemplo Inventado"])
            self.assertEqual(rc, 0)
            with open(os.path.join(salida, "visor_losas.html"), encoding="utf-8") as f:
                html = f.read()
            self.assertIn("F. Perdomo", html)

    def test_visor_filtrado_por_nivel(self):
        proyecto_niveles = dict(PROYECTO)
        proyecto_niveles["losas"] = [dict(l, nivel="N1 +3.00") for l in PROYECTO["losas"]]
        with tempfile.TemporaryDirectory() as d:
            proyecto = _escribir(proyecto_niveles, d, "proyecto.json")
            resultados = _escribir(RESULTADOS, d, "resultados.json")
            rc = main(["visor", "--proyecto", proyecto, "--resultados", resultados,
                       "--salida", os.path.join(d, "s1"), "--nivel", "N1 +3.00"])
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.isfile(os.path.join(d, "s1", "visor_losas.html")))
            rc = main(["visor", "--proyecto", proyecto, "--resultados", resultados,
                       "--salida", os.path.join(d, "s2"), "--nivel", "NO-EXISTE"])
            self.assertEqual(rc, 1)

    def test_tipos_por_apoyo(self):
        with tempfile.TemporaryDirectory() as d:
            proyecto = _escribir(EXPORT_INVENTADO, d, "proyecto.json")
            usos = _escribir({"LE6": {"es_vuelo": True, "direccion": "1D"}}, d, "usos.json")
            salida = os.path.join(d, "salidas")
            rc = main(["tipos", "--proyecto", proyecto, "--usos", usos, "--salida", salida])
            self.assertEqual(rc, 0)
            with open(os.path.join(salida, "tipos_pm.json"), encoding="utf-8") as f:
                datos = json.load(f)
            self.assertEqual(datos["tipos"]["LE1"]["codigo"], 22)   # el vuelo no empotra
            self.assertEqual(datos["tipos"]["LE6"]["codigo"], 72)
            self.assertIn("LE2", datos["asignar_en_revit"])

    def test_secciones_fijadas_y_reglamento(self):
        with tempfile.TemporaryDirectory() as d:
            proyecto = _escribir(EXPORT_INVENTADO, d, "proyecto.json")
            fijadas = _escribir({"LE1": "L20"}, d, "secciones.json")
            salida = os.path.join(d, "salidas")
            rc = main(["secciones", "--proyecto", proyecto,
                       "--secciones", fijadas, "--salida", salida])
            self.assertEqual(rc, 0)
            with open(os.path.join(salida, "secciones_losas.json"), encoding="utf-8") as f:
                datos = json.load(f)
            self.assertEqual(datos["secciones"]["LE1"]["origen"], "fijada")
            payload = datos["asignar_en_revit"]
            self.assertEqual(payload["asignar"]["LE1"], "L20")
            self.assertEqual(payload["tipos_floor"]["L20"], 0.20)
            # las no fijadas salen del reglamento
            otras = [m for m in payload["asignar"] if m != "LE1"]
            self.assertTrue(otras)
            for m in otras:
                self.assertEqual(datos["secciones"][m]["origen"], "auto")

    def test_modelado_acero_3d(self):
        with tempfile.TemporaryDirectory() as d:
            proyecto = _escribir(PROYECTO, d, "proyecto.json")
            resultados = _escribir(RESULTADOS, d, "resultados.json")
            editados = _escribir({"LV1": {"x": "#3 @ 0.20", "y": "#3 @ 0.25",
                                          "apoyo": "#3 @ 0.18"},
                                  "LV2": {"x": "#3 @ 0.15", "y": "#3 @ 0.17"}},
                                 d, "editados.json")
            salida = os.path.join(d, "salidas")
            rc = main(["modelado", "--proyecto", proyecto, "--resultados", resultados,
                       "--editados", editados, "--salida", salida])
            self.assertEqual(rc, 0)
            with open(os.path.join(salida, "plan_modelado.json"), encoding="utf-8") as f:
                plan = json.load(f)
            self.assertEqual(len(plan["losas"]), 2)
            self.assertEqual(len(plan["bastones"]), 1)
            self.assertTrue(all(x["resumen"]["sets"] > 0 for x in plan["losas"]))
            self.assertIn("50", plan["criterio_solape"])

    def test_usos_para_el_lisp(self):
        with tempfile.TemporaryDirectory() as d:
            rc = main(["usos", "--salida", d])
            self.assertEqual(rc, 0)
            with open(os.path.join(d, "usos_tabla4.txt"), encoding="utf-8") as f:
                lineas = f.read().splitlines()
            self.assertEqual(len(lineas), 45)
            n, uso_id, etiqueta = lineas[0].split("\t")
            self.assertEqual(n, "1")
            self.assertTrue(uso_id.startswith("uso-residencial"))
            self.assertIn("kN/m²", etiqueta)

    def test_error_limpio(self):
        rc = main(["tabla", "--proyecto", "no-existe.json", "--salida", "x"])
        self.assertEqual(rc, 1)


if __name__ == "__main__":
    unittest.main()
