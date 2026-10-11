import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from exportar import export


class EvidenceTests(unittest.TestCase):
    def test_reproducible_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = Path(__file__).with_name('ejemplo_sintetico.json')
            export(source, root/'a')
            export(source, root/'b')
            for name in ('resultado.json', 'estados.csv'):
                self.assertEqual((root/'a'/name).read_bytes(), (root/'b'/name).read_bytes())
            with self.assertRaises(FileExistsError):
                export(source, root/'a')
            data = json.loads((root/'a/resultado.json').read_text(encoding='utf-8'))
            self.assertEqual(len(data['input_sha256']), 64)
            self.assertEqual(data['energy_gate']['status'], 'insufficient')
