"""A native database export must not broaden the active-document guard."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / "examples" / "calle_demo" / "construir_base.py"
spec = importlib.util.spec_from_file_location("calle_base_test", SOURCE)
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)


class DocumentGuardTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name)
        base.configure(self.output, "Drawing1.dwg")

    def test_database_save_retains_original_document_guard(self):
        destination = self.output / "demo.dwg"
        with patch.object(base.b, "llamar", side_effect=[
            {"dibujo": "Drawing1.dwg"}, {"dibujo": str(destination)}
        ]), patch.object(base.b, "llamar_con_aprobacion", return_value={"guardado": str(destination)}):
            base.call("doc.save", {"ruta": str(destination)}, True)
        self.assertEqual(base.EXPECTED_DRAWING, "Drawing1.dwg")

    def test_changed_document_prevents_write(self):
        with patch.object(base.b, "llamar", return_value={"dibujo": "OTHER.dwg"}), \
                patch.object(base.b, "llamar_con_aprobacion") as write:
            with self.assertRaisesRegex(RuntimeError, "Cambio el dibujo"):
                base.call("entity.create", {"entidades": []}, True)
            write.assert_not_called()

    def test_switch_after_save_blocks_next_write(self):
        with patch.object(base.b, "llamar", side_effect=[
            {"dibujo": "Drawing1.dwg"}, {"dibujo": str(self.output / "OTHER.dwg")}
        ]), patch.object(base.b, "llamar_con_aprobacion", return_value={}):
            base.call("doc.save", {"ruta": str(self.output / "demo.dwg")}, True)
            with self.assertRaisesRegex(RuntimeError, "Cambio el dibujo"):
                base.call("entity.create", {"entidades": []}, True)
        self.assertEqual(base.EXPECTED_DRAWING, "Drawing1.dwg")


if __name__ == "__main__":
    unittest.main()
