"""Visor Pieper-Martens: DTO desde la salida del puente y HTML con créditos."""
import json
import os
import tempfile
import unittest

from plugin_losas.resultados_pm import dto_visor, escribir_visor

# Salidas inventadas con la forma exacta que escribe el CLI de puente-losas
# (proyecto.json del export + resultados.json con bloque pieper_martens).
PROYECTO = {
    "losas": [
        {"id": "L1", "mark": "LV1", "lx": 5.0, "ly": 6.0, "z_tope": 3.0,
         "espesor": {"h_usado": 0.25},
         "contorno": [[0, 0], [5, 0], [5, 6], [0, 6]]},
        {"id": "L2", "mark": "LV2", "lx": 5.0, "ly": 6.0, "z_tope": 3.0,
         "espesor": {"h_usado": 0.25},
         "contorno": [[5, 0], [10, 0], [10, 6], [5, 6]]},
    ],
}

RESULTADOS = {
    "panos": [
        {"mark": "LV1", "uso": "entrepisos", "es_vuelo": False,
         "params": {"a": 5.0, "b": 6.0},
         "cargas_tm2": {"q_ultima": 1.234},
         "espesor": {"h_usado_m": 0.25},
         "franja_x": {"as_diseno": 310.0, "disponer": "Ø3/8\" @0.20"},
         "franja_y": {"as_diseno": 280.0, "disponer": "Ø3/8\" @0.25"},
         "franja_apoyo": {"as_diseno": 350.0, "disponer": "Ø3/8\" @0.18"}},
        {"mark": "LV2", "uso": "comun", "es_vuelo": False,
         "params": {"a": 5.0, "b": 6.0},
         "cargas_tm2": {"q_ultima": 1.544},
         "espesor": {"h_usado_m": 0.25},
         "franja_x": {"as_diseno": 420.0, "disponer": "Ø3/8\" @0.15"},
         "franja_y": {"as_diseno": 380.0, "disponer": "Ø3/8\" @0.17"},
         "franja_apoyo": {"as_diseno": 500.0, "disponer": "Ø1/2\" @0.22"}},
    ],
    "pieper_martens": {
        "metodo": "Pieper-Martens (tablas de F. Perdomo, Losas v5.21)",
        "losas": {
            "LV1": {"codigo_dl": 22, "mfx": 0.95, "mfy": 0.62, "msx": 1.41, "msy": 0.0,
                    "nota": ""},
            "LV2": {"codigo_dl": 22, "mfx": 1.19, "mfy": 0.78, "msx": 1.77, "msy": 0.0,
                    "nota": ""},
        },
        "apoyos": [
            {"losa_i": "LV1", "losa_j": "LV2", "direccion": "X",
             "mu_i": 1.41, "mu_j": 1.77, "mu_ij": 1.59, "modo": "S"},
        ],
    },
}


class TestDtoVisor(unittest.TestCase):
    def test_dto_panos_campos_y_apoyos(self):
        dto = dto_visor(PROYECTO, RESULTADOS, nombre="Ejemplo Inventado")
        self.assertEqual(dto.proyecto, "Ejemplo Inventado")
        self.assertEqual([p["mark"] for p in dto.panos], ["LV1", "LV2"])
        self.assertEqual(dto.panos[0]["contorno"][2], [5.0, 6.0])
        self.assertEqual(dto.panos[0]["codigo_dl"], 22)
        self.assertEqual(dto.panos[1]["armaduras"]["apoyo"], "Ø1/2\" @0.22")

        self.assertEqual(dto.campos["codigo_dl"]["valores"]["LV1"], 22.0)
        self.assertEqual(dto.panos[0]["trabajo"], {"tipo": "2D", "eje": None})
        mfx = dto.campos["mfx"]
        self.assertEqual(mfx.get("unidad"), "ton·m/m")
        self.assertAlmostEqual(mfx["min"], 0.95)
        self.assertAlmostEqual(mfx["max"], 1.19)
        self.assertAlmostEqual(dto.campos["as_apoyo"]["valores"]["LV2"], 500.0)
        self.assertAlmostEqual(dto.campos["q_ultima"]["valores"]["LV1"], 1.234)

        self.assertEqual(len(dto.apoyos), 1)
        self.assertAlmostEqual(dto.apoyos[0]["mu_ij"], 1.59)

    def test_direccion_de_trabajo_1d_y_vuelo(self):
        proyecto = {"losas": [
            {"id": "L1", "mark": "LV1", "lx": 2.0, "ly": 6.0,
             "contorno": [[0, 0], [2, 0], [2, 6], [0, 6]], "espesor": {"h_usado": 0.25}}]}
        panos = [dict(RESULTADOS["panos"][0], params={"a": 2.0, "b": 6.0})]
        res = {"panos": panos,
               "pieper_martens": {"losas": {"LV1": RESULTADOS["pieper_martens"]["losas"]["LV1"]},
                                  "apoyos": []}}
        dto = dto_visor(proyecto, res)
        self.assertEqual(dto.panos[0]["trabajo"], {"tipo": "1D", "eje": "X"})

        panos_v = [dict(panos[0], es_vuelo=True)]
        res_v = {"panos": panos_v, "pieper_martens": res["pieper_martens"]}
        dto_v = dto_visor(proyecto, res_v)
        self.assertEqual(dto_v.panos[0]["trabajo"], {"tipo": "vuelo", "eje": "X"})

    def test_sin_contorno_usa_el_rectangulo_de_params(self):
        proyecto = {"losas": [{"id": "L1", "mark": "LV1", "lx": 5.0, "ly": 6.0,
                               "espesor": {"h_usado": 0.25}}]}
        resultados = {"panos": RESULTADOS["panos"][:1],
                      "pieper_martens": {"losas": {"LV1": RESULTADOS["pieper_martens"]["losas"]["LV1"]},
                                         "apoyos": []}}
        dto = dto_visor(proyecto, resultados)
        self.assertEqual(dto.panos[0]["contorno"], [[0.0, 0.0], [5.0, 0.0], [5.0, 6.0], [0.0, 6.0]])

    def test_sin_bloque_pm_falla_claro(self):
        with self.assertRaises(ValueError):
            dto_visor(PROYECTO, {"panos": []})

    def test_creditos_a_perdomo_y_arlette(self):
        dto = dto_visor(PROYECTO, RESULTADOS)
        texto = " ".join(dto.creditos)
        self.assertIn("F. Perdomo", texto)
        self.assertIn("Arlette Ramírez", texto)
        self.assertIn("EstructurasRD", texto)


class TestVisorHtml(unittest.TestCase):
    def test_html_autonomo_con_datos_y_creditos(self):
        dto = dto_visor(PROYECTO, RESULTADOS, nombre="Ejemplo Inventado")
        with tempfile.TemporaryDirectory() as d:
            ruta = os.path.join(d, "visor_losas.html")
            escribir_visor(dto, ruta)
            with open(ruta, encoding="utf-8") as f:
                html = f.read()
        self.assertIn("F. Perdomo", html)
        self.assertIn("Arlette Ramírez", html)
        self.assertIn("EstructurasRD", html)
        self.assertIn("Pieper-Martens", html)
        self.assertIn("LV2", html)                      # datos embebidos
        self.assertNotIn("/*__DATOS_VISOR__*/null", html)
        self.assertNotIn("<script src", html)           # offline: sin CDN ni dependencias
        self.assertNotIn("<link", html)
        # el bloque embebido es JSON válido
        inicio = html.index("const DATOS = ") + len("const DATOS = ")
        fin = html.index(";\n", inicio)
        datos = json.loads(html[inicio:fin])
        self.assertEqual(len(datos["panos"]), 2)


if __name__ == "__main__":
    unittest.main()
