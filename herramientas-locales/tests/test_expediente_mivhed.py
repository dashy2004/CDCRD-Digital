"""Pruebas offline con dos criterios y un documento de evidencia sintéticos."""

import argparse
import copy
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cdcrd_local import expediente_mivhed as mod


class Expediente(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.dir = self.base / "esquemas"
        self.dir.mkdir()
        self.ver = 13
        self.code = "CHECK-SINTÉTICO"
        props = {}
        items = []
        for n, kind in enumerate(["boolean", "string"], 1):
            i = n + 600
            prop = {
                "type": kind,
                "title": f"Pregunta {n}",
                "x_item": {
                    "templateItemId": i,
                    "displayNumber": n,
                    "requiresNonComplianceNote": True,
                },
                "x_legal_reference_ids": [42],
                "x_basis": {},
            }
            if kind == "string":
                prop["enum"] = ["cumple", "no_cumple", "no_aplica"]
            props[f"item_{i}"] = prop
            items.append(
                {
                    "id": f"{self.code}#{n}",
                    "numero": n,
                    "itemId": i,
                    "descripcion": prop["title"],
                    "evaluacion": ["Cumple", "No Cumple", "No Aplica"],
                    "baseLegal": [{"referenceId": 42, "versionArchivada": True}],
                }
            )
        self.schema = {
            "jsonSchema": {
                "x_template": {"templateId": 8, "code": self.code, "name": "Prueba"},
                "x_template_version": {
                    "templateVersionId": 13,
                    "templateId": 8,
                    "versionNumber": "1",
                },
                "properties": props,
                "x_normative_index": {
                    "legalReferences": {
                        "42": {"referenceId": 42, "citationText": "Artículo de prueba"}
                    }
                },
            }
        }
        self.cl = {
            "templateVersionId": 13,
            "templateId": 8,
            "version": "1",
            "codigo": self.code,
            "items": items,
        }
        self.corpus = {"_meta": {"esquema": "mivhed-norm-checklists/1"}, "checklists": [self.cl]}
        self.art = self.base / "testigo.txt"
        self.art.write_text("dato")
        self.paths()

    def paths(self):
        (self.dir / "schema13.json").write_text(json.dumps(self.schema), encoding="utf8")
        (self.base / "corpus.json").write_text(json.dumps(self.corpus), encoding="utf8")

    def run_tool(self, entries=None, corpus=True):
        parser = argparse.ArgumentParser()
        mod.registrar(parser.add_subparsers(dest="command", required=True))
        args = ["expediente-mivhed", "--esquemas", str(self.dir)]
        if corpus:
            args += ["--corpus", str(self.base / "corpus.json")]
        if entries is not None:
            path = self.base / "evidencias.json"
            path.write_text(json.dumps({"evaluaciones": entries}), encoding="utf8")
            args += ["--evidencias", str(path)]
        return mod.ejecutar(parser.parse_args(args))

    def evidencia(self, n=2, respuesta="no_aplica"):
        return {
            "criterio": f"{self.code}#{n}",
            "templateVersionId": 13,
            "respuesta": respuesta,
            "justificacion": "Detalle revisado en la copia",
            "fuentes": [{"archivo": "testigo.txt", "localizador": "p. 2"}],
        }

    def test_inventario_fiel_al_esquema_y_edicion(self):
        r = self.run_tool()
        self.assertEqual(r["resumen"]["opciones_discrepantes"], 1)
        self.assertEqual(r["resumen"]["referencias_archivadas"], 2)
        self.assertEqual(r["resumen"]["sin_evaluar"], 2)
        self.assertEqual(r["criterios"][0]["opciones"], ["cumple", "no_cumple"])
        s = self.run_tool(corpus=False)
        self.assertIsNone(s["criterios"][0]["referencias"][0]["archivada"])

    def test_indice_nativo_y_enlace_archivo(self):
        entry = self.evidencia()
        r = self.run_tool([entry])
        row = r["criterios"][1]
        self.assertEqual(row["estado"], "documentada")
        self.assertEqual(row["fuentes"][0]["sha256"], hashlib.sha256(b"dato").hexdigest())
        self.assertEqual(self.run_tool([entry]), r)

    def test_respuesta_no_admitida(self):
        r = self.run_tool([self.evidencia(n=1)])
        self.assertEqual(r["resumen"]["respuestas_invalidas"], 1)
        self.assertEqual(r["criterios"][0]["estado"], "respuesta_invalida")

    def test_fuentes_nota_y_hash(self):
        entry = self.evidencia()
        for fuente in (
            [],
            [{"archivo": "ausente", "localizador": "plano 1"}],
            [{"archivo": "testigo.txt", "localizador": ""}],
            [{"archivo": "testigo.txt", "localizador": "p. 2", "sha256": "0" * 64}],
        ):
            with self.subTest(fuente=fuente):
                e = dict(entry, fuentes=fuente)
                self.assertEqual(self.run_tool([e])["resumen"]["evidencias_incompletas"], 1)
        self.assertEqual(
            self.run_tool([dict(entry, justificacion="")])["resumen"]["evidencias_incompletas"], 1
        )

    def test_id_version_duplicados_y_ruta_fuera(self):
        e = self.evidencia()
        for entries in (
            [dict(e, criterio="INEXISTENTE")],
            [dict(e, templateVersionId=0)],
            [e, e],
            [dict(e, fuentes=[{"archivo": "../x", "localizador": "p"}])],
        ):
            with self.subTest(entries=entries), self.assertRaises(ValueError):
                self.run_tool(entries)

    def test_esquema_alterado_falla_cerrado(self):
        original = copy.deepcopy(self.schema)
        for mutation in ("version", "numero", "enum", "referencias", "titulo", "id"):
            self.schema = copy.deepcopy(original)
            p = self.schema["jsonSchema"]["properties"]["item_602"]
            if mutation == "version":
                self.schema["jsonSchema"]["x_template_version"]["templateVersionId"] = 14
            elif mutation == "numero":
                p["x_item"]["displayNumber"] = 1
            elif mutation == "enum":
                p["enum"].append("quizás")
            elif mutation == "referencias":
                p["x_legal_reference_ids"] = []
            elif mutation == "titulo":
                p["title"] = "otro"
            else:
                p["x_item"]["templateItemId"] = 777
            self.paths()
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                self.run_tool()

    def test_motivo_condicional_y_nota_opcional(self):
        esquema = self.schema["jsonSchema"]
        esquema["allOf"] = [
            {
                "if": {"properties": {"item_601": {"const": False}}},
                "then": {"required": ["item_601_nc_reasons"]},
            }
        ]
        p = esquema["properties"]["item_601"]
        p["x_item"]["nonComplianceNoteRequired"] = False
        p["x_reasons"] = [{"number": "1.1", "reasonKind": "non_compliance"}]
        self.paths()
        e = dict(self.evidencia(n=1, respuesta="no_cumple"), justificacion="")
        self.assertEqual(self.run_tool([e])["criterios"][0]["estado"], "evidencia_incompleta")
        self.assertEqual(
            self.run_tool([dict(e, motivos=["1.1"])])["criterios"][0]["estado"], "documentada"
        )
        self.assertEqual(
            self.run_tool([dict(e, motivos=["1.NA1"])])["criterios"][0]["estado"],
            "evidencia_incompleta",
        )
        p["x_item"]["nonComplianceNoteRequired"] = True
        self.paths()
        self.assertEqual(
            self.run_tool([dict(e, motivos=["1.1"])])["criterios"][0]["estado"],
            "evidencia_incompleta",
        )

    def test_base_con_justificacion_sin_referencias(self):
        p = self.schema["jsonSchema"]["properties"]["item_601"]
        del p["x_legal_reference_ids"]
        p["x_basis"] = {"legalReferenceIds": [], "authorJustificationText": "Acta A"}
        self.cl["items"][0]["baseLegal"] = []
        self.paths()
        self.assertEqual(self.run_tool()["criterios"][0]["justificacion_normativa"], "Acta A")
        p["x_basis"]["authorJustificationText"] = ""
        self.paths()
        self.assertEqual(self.run_tool()["resumen"]["sin_base_legal_ni_justificacion"], 1)

    def test_cli_y_codigos_de_salida(self):
        args = [
            sys.executable,
            "-m",
            "cdcrd_local.cli",
            "expediente-mivhed",
            "--esquemas",
            str(self.dir),
            "--corpus",
            str(self.base / "corpus.json"),
        ]
        src = str(Path(__file__).resolve().parents[1] / "src")
        env = dict(os.environ, PYTHONPATH=src)

        def llamada():
            return subprocess.run(
                args,
                env=env,
                cwd=self.base,
                capture_output=True,
                encoding="utf8",
                check=False,
                timeout=30,
            )

        r = llamada()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["resumen"]["criterios"], 2)
        e = self.evidencia(n=1)
        self.run_tool([e])
        args.extend(["--evidencias", str(self.base / "evidencias.json")])
        self.assertEqual(llamada().returncode, 1)
        (self.dir / "schema13.json").unlink()
        self.assertEqual(llamada().returncode, 2)

    def test_una_huella_por_archivo_compartido(self):
        entradas = [self.evidencia(1, "cumple"), self.evidencia(2, "cumple")]
        with patch.object(mod.hashlib, "file_digest", wraps=hashlib.file_digest) as lectura:
            informe = self.run_tool(entradas)
        self.assertEqual(lectura.call_count, 1)
        self.assertEqual(informe["resumen"]["documentadas"], 2)

    def test_cambio_durante_lectura_invalida_todas_las_referencias(self):
        real = hashlib.file_digest

        def cambiar(stream, algoritmo):
            huella = real(stream, algoritmo)
            self.art.write_bytes(b"otra longitud")
            return huella

        with patch.object(mod.hashlib, "file_digest", side_effect=cambiar):
            r = self.run_tool([self.evidencia(1, "cumple"), self.evidencia(2, "cumple")])
        for fila in r["criterios"]:
            self.assertEqual(fila["estado"], "evidencia_incompleta")
            self.assertIsNone(fila["fuentes"][0]["sha256"])

    def test_cambio_despues_de_lectura_se_detecta_en_cierre(self):
        segundo = self.base / "segundo.txt"
        segundo.write_text("dos")
        e = self.evidencia(2, "cumple")
        e["fuentes"].append({"archivo": segundo.name, "localizador": "p. 3"})
        real = hashlib.file_digest

        def cambiar(stream, algoritmo):
            huella = real(stream, algoritmo)
            if Path(stream.name) == segundo:
                self.art.unlink()
            return huella

        with patch.object(mod.hashlib, "file_digest", side_effect=cambiar):
            r = self.run_tool([self.evidencia(1, "cumple"), e])
        self.assertEqual(r["resumen"]["evidencias_incompletas"], 2)
        self.assertTrue(r["criterios"][1]["fuentes"][1]["sha256"])
        self.assertIsNone(r["criterios"][0]["fuentes"][0]["sha256"])

    def test_motivos_repetidos_quedan_incompletos(self):
        prop = self.schema["jsonSchema"]["properties"]["item_601"]
        prop["x_reasons"] = [{"number": "1.1", "reasonKind": "non_compliance"}]
        self.paths()
        e = dict(self.evidencia(1, "no_cumple"), motivos=["1.1", "1.1"])
        r = self.run_tool([e])["criterios"][0]
        self.assertIn("Los motivos deben ser únicos", r["incidencias"])
        self.assertEqual(r["estado"], "evidencia_incompleta")

    def test_corpus_y_esquemas_vacios(self):
        (self.dir / "schema13.json").unlink()
        with self.assertRaises(ValueError):
            self.run_tool()
        self.corpus["checklists"] = []
        self.paths()
        with self.assertRaises(ValueError):
            self.run_tool()
