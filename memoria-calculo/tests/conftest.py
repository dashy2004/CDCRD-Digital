import hashlib
import json

import pytest


@pytest.fixture
def dossier_data(tmp_path):
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    (inputs / "data.json").write_text(json.dumps({"height": 3.75}), encoding="utf-8")
    return {
        "schema": "cdcrd-design-memory/1",
        "project": {
            "id": "SYNTHETIC",
            "name": "Edificio de ejemplo",
            "revision": "R00",
            "description": "Datos ficticios para pruebas.",
        },
        "source_roots": ["inputs"],
        "sources": [
            {
                "id": "S1",
                "path": "inputs/data.json",
                "title": "Datos sintéticos",
                "kind": "table",
                "sha256": hashlib.sha256((inputs / "data.json").read_bytes()).hexdigest(),
            }
        ],
        "observations": [
            {
                "id": "O1",
                "label": "Altura",
                "topic": "geometry",
                "value": 3.75,
                "unit": "m",
                "source_id": "S1",
                "locator": "height",
                "acquisition": "imported",
            }
        ],
    }
