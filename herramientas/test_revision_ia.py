"""Pruebas de la revisión independiente del proveedor de IA, con fuentes sintéticas."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import revision_ia as revision


class RevisionIATests(unittest.TestCase):
    def setUp(self):
        carpeta = tempfile.TemporaryDirectory()
        self.addCleanup(carpeta.cleanup)
        self.base = Path(carpeta.name)
        self.entrada = self.base / "entrada.json"
        self.salida = self.base / "revision.md"

    def escribir(self, datos):
        self.entrada.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")

    def generar(self, tipo, **opciones):
        revision.generar(tipo, self.entrada, self.salida, **opciones)
        return self.salida.read_text(encoding="utf-8")

    def test_memoria_parcial_conserva_precision_y_hash_de_bytes_con_bom(self):
        texto = '{"niveles": [{"nombre":"Nivel ñ","momento":1.00000000000000000001}]}'
        raw = texto.encode("utf-8-sig")
        self.entrada.write_bytes(raw)
        doc = self.generar("memoria", origen="Ensayo A")
        for cadena in (texto, hashlib.sha256(raw).hexdigest(), "Ensayo A", "fundaciones"):
            self.assertIn(cadena, doc)
        self.assertNotIn(str(self.base), doc)
        self.assertEqual(self.entrada.read_bytes(), raw)

    def test_memoria_excluye_configuraciones_y_filas_invalidas(self):
        for invalido in ({"portada": {}, "bloques": []}, {"fundaciones": {"figuras": []}},
                         {"avisos": [42]}, {"bloques": [None]}, {"sobrecarga": {}}, {"x": 3}):
            with self.subTest(invalido=invalido):
                self.escribir(invalido)
                with self.assertRaises(ValueError):
                    self.generar("memoria")

    def test_losas_vincula_por_marca_y_conserva_recibo(self):
        self.escribir({"panos": [{"mark": "L|1", "espesor": {"h_usado_m": 0.2}}],
                       "pieper_martens": {"losas": {"L|1": {"mfx": 2, "mfy": 3, "unidades": "u/m"}}}})
        recibo = self.base / "lectura.json"
        recibo.write_bytes(b'{"panos": 1, "alcance": "Ensayo", "revision_motor": "abc"}')
        doc = self.generar("losas", recibo=recibo)
        for cadena in (r"L\|1", "0.2 | 2 | 3 | u/m", hashlib.sha256(recibo.read_bytes()).hexdigest(),
                       recibo.read_text(), "acero_pm.json"):
            self.assertIn(cadena, doc)
        self.assertIn("recibo", self.generar("losas").lower())
        recibo.write_text('{"panos":2,"alcance":"otro caso"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            self.generar("losas", recibo=recibo)

    def test_losas_exige_marcas_y_campos_sin_inventar_valores(self):
        for fila in ({"mark": "L1", "espesor": {}}, {"mark": "L2", "espesor": {"h_usado_m": 0.2}}):
            self.escribir({"panos": [fila], "pieper_martens": {"losas": {"L1": {"mfx": 2, "mfy": 2, "unidades": "u"}}}})
            with self.assertRaises(ValueError):
                self.generar("losas")

    def test_derivas_preserva_resultado_incompleto(self):
        self.escribir({"chequeos": [{"piso": None, "demanda": None, "capacidad": None, "ratio": None,
                                     "estado": "INCOMPLETO", "clausula": "Ensayo", "unidad": "m",
                                     "motivo": "Falta altura"}], "veredicto": "INCOMPLETO"})
        doc = self.generar("derivas")
        self.assertIn("Falta altura", doc)
        self.assertIn('"ratio": null', doc)
        self.escribir({"pisos": []})
        with self.assertRaises(ValueError):
            self.generar("derivas")

    def test_expediente_multidisciplinario_sin_evaluacion_automatica(self):
        filas = [{"criterio": lista + "#1", "descripcion": "Evidencia sintética", "lista": lista,
                  "numero": 1, "templateVersionId": 99, "version": "1.0", "estado": "sin_evaluar"}
                 for lista in ("CHECK-SANITARIA", "CHECK-ARQUITECTURA")]
        datos = {"resumen": {"criterios": 2, "listas": 2}, "criterios": filas}
        self.escribir(datos)
        doc = self.generar("expediente")
        for lista in ("CHECK-SANITARIA", "CHECK-ARQUITECTURA"):
            self.assertIn(f"| {lista} |", doc)
        self.assertNotIn("CUMPLE", doc)
        datos["resumen"]["criterios"] = 1
        self.escribir(datos)
        with self.assertRaises(ValueError):
            self.generar("expediente")
        datos["resumen"]["criterios"] = 2
        datos["criterios"][1] = dict(filas[0])
        self.escribir(datos)
        with self.assertRaises(ValueError):
            self.generar("expediente")

    def test_error_conserva_salida_y_rechaza_json_ambiguo(self):
        self.salida.write_bytes(b"revision anterior")
        for raw in (b'{"bloques":[],"bloques":[]}', b'{"bloques":[],"valor":NaN}', b"{no", b"\xff"):
            self.entrada.write_bytes(raw)
            with self.assertRaises(ValueError):
                self.generar("memoria")
            self.assertEqual(self.salida.read_bytes(), b"revision anterior")

    def test_protege_entradas_y_alias(self):
        self.escribir({"bloques": []})
        with self.assertRaises(ValueError):
            revision.generar("memoria", self.entrada, self.entrada)
        os.link(self.entrada, self.salida)
        with self.assertRaises(ValueError):
            self.generar("memoria")
        self.assertEqual(json.loads(self.salida.read_bytes()), {"bloques": []})
        with self.assertRaises(ValueError):
            self.generar("memoria", recibo=self.entrada)

    def test_cli_real_y_contenido_con_delimitadores(self):
        self.escribir({"avisos": ["````", "Observación de ensayo"]})
        p = subprocess.run([sys.executable, str(Path(revision.__file__)), "--tipo", "memoria",
                            "--entrada", str(self.entrada), "--salida", str(self.salida)],
                           capture_output=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("`````json", self.salida.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
