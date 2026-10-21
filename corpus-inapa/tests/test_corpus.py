"""Pruebas del corpus INAPA con paginas SINTETICAS (sin PDF ni datos de proyecto)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import buscar  # noqa: E402
import extraer  # noqa: E402

ENC = ("         REGLAMENTO TECNICO PARA DISEÑO DE OBRAS E\n"
       "          INSTALACIONES HIDRO – SANITARIO DEL INAPA\n"
       "            Área: Dirección de Ingeniería\n"
       "                                                 Código: DIG -PO-001\n"
       "            Fecha de emisión:                    Página {imp} de {tot}\n"
       "                                     Versión: 01\n"
       "            4-julio-2018\n\n")

PAG1 = ENC.format(imp=1, tot=410) + "PORTADA SINTETICA\n"
PAG2 = ENC.format(imp=2, tot=413) + ("INDICE DE CONTENIDO\n"
                                     "CAPITULO I ...................................... 4\n"
                                     "TITULO II ....................................... 27\n")
PAG3 = ENC.format(imp=4, tot=413) + ("                   C AP I T U L O I\n"
                                     "          OBJETO Y CAMPO DE APLICACION\n\n"
                                     "El objeto es establecer los requisitos tecnicos para agua potable.\n")
PAG4 = ENC.format(imp=27, tot=413) + ("TITULO II\n"
                                      "SISTEMAS DE ABASTECIMIENTO DE AGUA\n\n"
                                      "CAPITULO V\n"
                                      "LINEAS DE ADUCCION, CONDUCCION E IMPULSION\n\n"
                                      "5.3.1 Velocidades\n"
                                      "La velocidad mínima en conducciones a gravedad será de 0.60 m/s.\n")
PAG5 = "Pagina sin encabezado ni numero impreso.\n"
PAGINAS = [PAG1, PAG2, PAG3, PAG4, PAG5]
META = {"documento": "Reglamento sintetico", "fuente_oficial": "https://ejemplo.invalid/reglamento.pdf",
        "fuente_local": "sintetico.pdf", "sha256_pdf": "0" * 64, "extractor": "sintetico",
        "fecha_extraccion": "2026-01-01T00:00Z"}


def corpus():
    return extraer.construir_corpus(PAGINAS, META)


class EncabezadoTests(unittest.TestCase):
    def test_parsea_codigo_version_fecha_y_pagina(self):
        e = extraer.parsear_encabezado(PAG3)
        self.assertEqual(e, {"codigo": "DIG-PO-001", "version": "01", "fecha_emision": "2018-07-04",
                             "pagina_impresa": 4, "total_impreso": 413})

    def test_total_impreso_se_lee_por_pagina_no_se_infiere(self):
        doc = corpus()
        self.assertEqual(doc["paginas"][0]["total_impreso"], 410)
        self.assertEqual(doc["paginas"][1]["total_impreso"], 413)
        self.assertEqual(doc["totales_impresos_declarados"], [410, 413])

    def test_pagina_sin_encabezado_queda_sin_numero_impreso(self):
        doc = corpus()
        self.assertIsNone(doc["paginas"][4]["pagina_impresa"])
        self.assertEqual(doc["paginas_sin_numero_impreso"], [5])

    def test_quitar_encabezado_conserva_cuerpo(self):
        cuerpo = extraer.quitar_encabezado(PAG4)
        self.assertNotIn("Código", cuerpo)
        self.assertNotIn("Página", cuerpo)
        self.assertIn("5.3.1 Velocidades", cuerpo)
        self.assertIn("0.60 m/s", cuerpo)


class EstructuraTests(unittest.TestCase):
    def test_capitulo_con_letras_separadas_por_ocr(self):
        doc = corpus()
        p = doc["paginas"][2]
        self.assertEqual(p["capitulo"], {"num": "I", "nombre": "OBJETO Y CAMPO DE APLICACION"})
        self.assertIsNone(p["titulo"])

    def test_indice_no_altera_estructura(self):
        doc = corpus()
        self.assertIsNone(doc["paginas"][1]["capitulo"])
        self.assertEqual(doc["paginas"][1]["cabeceras"], [])

    def test_titulo_reinicia_capitulo_y_seccion_se_arrastra(self):
        doc = corpus()
        p4, p5 = doc["paginas"][3], doc["paginas"][4]
        self.assertEqual(p4["titulo"]["num"], "II")
        self.assertEqual(p4["capitulo"]["num"], "V")
        self.assertEqual(p4["seccion"], {"num": "5.3.1", "nombre": "Velocidades"})
        self.assertEqual(p5["seccion"], p4["seccion"])  # arrastre a la pagina siguiente

    def test_metadatos_documento(self):
        doc = corpus()
        self.assertEqual(doc["codigo"], "DIG-PO-001")
        self.assertEqual(doc["version"], "01")
        self.assertEqual(doc["fecha_emision"], "2018-07-04")
        self.assertEqual(doc["clase"], "norma")
        self.assertFalse(doc["revision_humana"])
        self.assertEqual(doc["paginas_pdf"], 5)
        self.assertEqual(len(doc["paginas"][3]["sha256_texto"]), 64)


class BusquedaTests(unittest.TestCase):
    def test_busqueda_terminos_con_y_sin_acentos(self):
        doc = corpus()
        r = buscar.buscar("velocidad minima gravedad", doc)
        self.assertEqual([x["pagina_impresa"] for x in r["resultados"]], [27])
        r2 = buscar.buscar("velocidad mínima", doc)
        self.assertEqual(r2["resultados"][0]["pagina_pdf"], 4)
        self.assertIn("[velocidad]", r2["resultados"][0]["fragmento"].lower())
        self.assertEqual(r2["resultados"][0]["clase"], "norma")

    def test_busqueda_sin_resultado(self):
        self.assertEqual(buscar.buscar("zzz inexistente", corpus())["resultados"], [])

    def test_pagina_directa_impresa_y_pdf(self):
        doc = corpus()
        self.assertEqual(buscar.buscar("impresa:4", doc)["resultados"][0]["pagina_pdf"], 3)
        self.assertEqual(buscar.buscar("pdf:3", doc)["resultados"][0]["pagina_impresa"], 4)

    def test_filtros_titulo_capitulo(self):
        doc = corpus()
        self.assertEqual(buscar.buscar("requisitos", doc, titulo="II")["resultados"], [])
        self.assertEqual(len(buscar.buscar("velocidad", doc, titulo="ii", capitulo="V")["resultados"]), 1)

    def test_consulta_invalida(self):
        with self.assertRaises(ValueError):
            buscar.buscar("   ", corpus())
        with self.assertRaises(ValueError):
            buscar.buscar("a", corpus(), limite=0)

    def test_comillas_no_rompen_fts(self):
        self.assertEqual(buscar.buscar('"velocidad" (0.60)', corpus())["resultados"][0]["pagina_impresa"], 27)
        # 'OR' se trata como un termino mas, no como operador: sin pagina que lo contenga no hay resultado
        self.assertEqual(buscar.buscar('velocidad OR', corpus())["resultados"], [])

    def test_cita_completa(self):
        doc = corpus()
        c = buscar.buscar("impresa:27", doc)["resultados"][0]["cita"]
        for trozo in ("DIG-PO-001", "version 01", "2018-07-04", "Titulo II", "Cap. V", "seccion 5.3.1",
                      "pag. impresa 27 (PDF 4)", "https://ejemplo.invalid/reglamento.pdf", "sin revision humana"):
            self.assertIn(trozo, c)

    def test_cargar_rechaza_otro_esquema(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "x.json"
            ruta.write_text(json.dumps({"esquema": "otro/1"}), encoding="utf-8")
            with self.assertRaises(ValueError):
                buscar.cargar(ruta)


class ReferenciasTests(unittest.TestCase):
    def test_norma_requiere_pagina_existente(self):
        doc = corpus()
        with self.assertRaises(LookupError):
            buscar.referencia_norma(doc, pagina_impresa=999)
        with self.assertRaises(ValueError):
            buscar.referencia_norma(doc)

    def test_norma_requiere_fragmento_presente(self):
        doc = corpus()
        with self.assertRaises(LookupError):
            buscar.referencia_norma(doc, pagina_impresa=27, fragmento="1.20 m/s")
        r = buscar.referencia_norma(doc, pagina_impresa=27, fragmento="velocidad mínima en conducciones")
        self.assertTrue(r["normativa"])
        self.assertEqual(r["clase"], "norma")
        self.assertEqual(r["pagina_pdf"], 4)
        self.assertEqual(r["seccion"]["num"], "5.3.1")

    def test_hipotesis_nunca_es_norma(self):
        h = buscar.referencia_hipotesis("Q adoptado 0.30 m3/s", "redondeo del caudal requerido", unidades="m3/s")
        self.assertEqual(h["clase"], "hipotesis")
        self.assertFalse(h["normativa"])
        with self.assertRaises(ValueError):
            buscar.referencia_hipotesis("n = 0.012", "")

    def test_validar_referencias(self):
        doc = corpus()
        refs = [buscar.referencia_norma(doc, pagina_pdf=3),
                buscar.referencia_hipotesis("n = 0.012", "concreto liso, tabla de referencia")]
        v = buscar.validar_referencias(refs)
        self.assertTrue(v["ok"])
        self.assertEqual(v["conteo"], {"norma": 1, "hipotesis": 1})
        malas = [{"clase": "norma", "pagina_pdf": 3}, {"clase": "hipotesis", "enunciado": "x", "normativa": True}, {}]
        v2 = buscar.validar_referencias(malas)
        self.assertFalse(v2["ok"])
        self.assertEqual([e["indice"] for e in v2["errores"]], [0, 1, 2])


class ExtraccionArchivoTests(unittest.TestCase):
    def test_extraer_falla_sin_pdf(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(FileNotFoundError):
                extraer.extraer(Path(d) / "no.pdf", Path(d) / "out")


if __name__ == "__main__":
    unittest.main()
