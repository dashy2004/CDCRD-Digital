"""The recorder must not select the wrong application or an ambiguous CAD title."""
import importlib.util
from pathlib import Path
import unittest
import tempfile
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / "tools" / "tech" / "capturas_obs.py"
spec = importlib.util.spec_from_file_location("capturas_obs", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class WindowSelectionTest(unittest.TestCase):
    def test_exact_unique_cad_window(self):
        items = [{"itemName": "[acad.exe]: QA.dwg", "itemValue": "QA.dwg:ACAD:acad.exe"},
                 {"itemName": "[other.exe]: QA.dwg", "itemValue": "QA.dwg:OTHER:other.exe"}]
        self.assertEqual(module.select_window(items, "QA.dwg"), "QA.dwg:ACAD:acad.exe")

    def test_duplicate_or_missing_window_rejected(self):
        item = {"itemName": "QA.dwg", "itemValue": "QA.dwg:ACAD:acad.exe"}
        for items in ([], [item, item], [dict(item, itemEnabled=False)]):
            with self.subTest(items=items), self.assertRaises(ValueError):
                module.select_window(items, "QA.dwg")

    def test_empty_selector_rejected(self):
        with self.assertRaises(ValueError):
            module.select_window([], "  ")


class RecordingLifecycleTest(unittest.TestCase):
    def session(self, directory):
        session = module.CaptureSession.__new__(module.CaptureSession)
        session.directory = Path(directory)
        session.scene = "CDCRD-test-Civil3D"
        session.state = {"window": "CAD", "recordings": []}
        session.guard = Mock()
        session.idle = Mock()
        session.save_state = Mock()
        return session

    def test_delayed_start_is_polled_without_another_start(self):
        session = module.CaptureSession.__new__(module.CaptureSession)
        session.call = Mock(side_effect=[{"outputActive": False},
                                        {"outputActive": False}, {"outputActive": True}])
        with patch.object(module.time, "sleep"):
            self.assertTrue(session.wait_recording(True)["outputActive"])
        self.assertTrue(all(call.args == ("GetRecordStatus",) for call in session.call.call_args_list))

    def test_unconfirmed_start_never_runs_cad_or_stops_an_inactive_output(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.session(directory)
            session.call = Mock(return_value={"recordDirectory": directory})
            session.wait_recording = Mock(side_effect=TimeoutError("not confirmed"))
            with self.assertRaises(TimeoutError), session.recording("test"):
                self.fail("CAD action must not run before recording confirmation")
            self.assertEqual(session.state["phase"], "start_requested")
            self.assertNotIn("StopRecord", [call.args[0] for call in session.call.call_args_list])

    def test_failed_cad_action_closes_take_and_remains_failed(self):
        with tempfile.TemporaryDirectory() as directory:
            session = self.session(directory)
            output = Path(directory) / "test.mkv"
            output.write_bytes(b"fake take for lifecycle test")
            session.call = Mock(return_value={"recordDirectory": directory, "outputPath": str(output)})
            session.wait_recording = Mock()
            with self.assertRaisesRegex(ValueError, "CAD failed"), session.recording("test"):
                raise ValueError("CAD failed")
            self.assertFalse(session.state["recordings"][0]["action_completed"])
            self.assertEqual(session.state["phase"], "stopped")


if __name__ == "__main__":
    unittest.main()
