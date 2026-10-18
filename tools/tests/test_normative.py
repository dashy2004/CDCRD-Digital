import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location(
    "verify", Path(__file__).resolve().parents[1] / "verify_normative.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class Integrity(unittest.TestCase):
    def test_change_add_remove_and_windows_line_endings(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            (r / "datos").mkdir()
            p = r / "datos/a.json"
            p.write_bytes(b'{"value":1}\n')
            m = {"files": mod.inventory(r)}
            p.write_bytes(b'{"value":1}\r\n')
            self.assertFalse(any(mod.verify(r, m).values()))
            p.write_text('{"value":2}\n')
            self.assertEqual(mod.verify(r, m)["changed"], ["datos/a.json"])
            p.unlink()
            self.assertEqual(mod.verify(r, m)["removed"], ["datos/a.json"])
            (r / "datos/b.json").write_text("{}")
            self.assertEqual(mod.verify(r, m)["added"], ["datos/b.json"])

    def test_updating_new_manifest_does_not_change_trusted_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            r = Path(d)
            (r / "datos").mkdir()
            p = r / "datos/x.md"
            p.write_text("1")
            trusted = {"files": mod.inventory(r)}
            p.write_text("2")
            new = {"files": mod.inventory(r)}
            self.assertFalse(any(mod.verify(r, new).values()))
            self.assertTrue(mod.verify(r, trusted)["changed"])


if __name__ == "__main__":
    unittest.main()
