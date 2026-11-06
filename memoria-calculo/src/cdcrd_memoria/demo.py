"""Reproducible fictitious example, generated outside the repository by the CLI."""

import hashlib
from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen.canvas import Canvas

from .pipeline import generate, parse_dossier, write_json
from .sources import OutputPackage


def create_demo(output_directory: Path) -> dict:
    with OutputPackage(output_directory, [], []) as package:
        inputs = package.path / "inputs"
        inputs.mkdir()
        write_json(
            inputs / "datos.json",
            {
                "synthetic": True,
                "height": 3.5,
                "live_load": 4.5,
                "reaction": {
                    "value": 125.123456789,
                    "component": "Fz",
                    "units": "kN",
                    "system": "Global",
                    "case": "DEMO-C1",
                    "model_revision": "R00",
                },
            },
        )
        with (inputs / "anexo.pdf").open("xb") as stream:
            canvas = Canvas(stream, pagesize=letter)
            for page in range(1, 3):
                canvas.setFont("Helvetica-Bold", 16)
                canvas.drawString(72, 710, f"Anexo ficticio - pagina original {page}")
                canvas.setFont("Helvetica", 11)
                canvas.drawString(72, 675, "Datos inventados para probar la composicion documental.")
                canvas.drawString(72, 650, "No corresponde a un proyecto ni a un calculo aprobado.")
                canvas.showPage()
            canvas.save()
        sources = [
            {
                "id": sid,
                "title": title,
                "path": f"inputs/{name}",
                "sha256": hashlib.sha256((inputs / name).read_bytes()).hexdigest(),
                "kind": kind,
            }
            for sid, title, name, kind in [
                ("DATA", "Datos ficticios", "datos.json", "table"),
                ("ANNEX", "Anexo ficticio", "anexo.pdf", "document"),
            ]
        ]
        data = {
            "schema": "cdcrd-design-memory/1",
            "project": {
                "id": "DEMO-001",
                "name": "Edificio Ejemplo",
                "revision": "R00",
                "description": "Ejemplo sintético de un pórtico. Todos los valores son inventados.",
            },
            "design_basis": {"reason": "Régimen y edición pendientes de selección por el responsable."},
            "source_roots": ["inputs"],
            "sources": sources,
            "observations": [
                {
                    "id": "O-HEIGHT",
                    "topic": "geometry",
                    "label": "Altura de nivel ficticia",
                    "value": 3.5,
                    "unit": "m",
                    "acquisition": "imported",
                    "source_id": "DATA",
                    "locator": "height",
                },
                {
                    "id": "O-LOAD",
                    "topic": "loads",
                    "label": "Carga viva ficticia",
                    "value": 4.5,
                    "unit": "kN/m2",
                    "acquisition": "imported",
                    "source_id": "DATA",
                    "locator": "live_load",
                },
                {
                    "id": "O-SOIL",
                    "topic": "geotechnical",
                    "label": "Presión admisible",
                    "value": None,
                    "unit": "kPa",
                    "acquisition": "unavailable",
                    "reason": "Estudio geotécnico no aportado",
                },
            ],
            "results": [
                {
                    "id": "R-FZ",
                    "label": "Reacción ficticia",
                    "value": 125.123456789,
                    "unit": "kN",
                    "source_id": "DATA",
                    "locator": "reaction",
                    "model_id": "MODEL-A",
                    "model_revision": "R00",
                    "load_case": "DEMO-C1",
                    "element_id": "N1",
                    "coordinate_system": "Global",
                    "axis_definition": "X e Y horizontales; Z vertical positivo",
                    "component": "Fz",
                    "component_origin": "Nudo N1; coordenadas globales (0, 0, 0) m",
                }
            ],
            "annexes": [{"id": "A-01", "title": "Anexo sintético de dos páginas", "source_id": "ANNEX"}],
        }
        write_json(package.path / "expediente.json", data)
        result = generate(
            parse_dossier(data),
            package.path / "paquete",
            package.path,
            input_path=package.path / "expediente.json",
        )
        package.complete()
    return result
