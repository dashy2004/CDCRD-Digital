"""Adapter failures must remain explicit; source data is passed without a shell."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cdcrd_local.interchange import validate_beamng


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        (self.root / "datos/titulos").mkdir(parents=True)
        self.validator = self.root / "civil3d-beamng/cdcrd_beamng/validation.py"
        self.validator.parent.mkdir(parents=True)
        self.validator.write_text("# synthetic adapter fixture", encoding="utf-8")

    def response(self, stdout=None, code=0):
        report = {"schema": "cdcrd.interchange-validation/1", "ok": code == 0}
        return subprocess.CompletedProcess([], code, json.dumps(report) if stdout is None else stdout, "")

    def test_paths_are_resolved_before_changing_directory_and_names_are_literal(self):
        with patch("cdcrd_local.interchange.subprocess.run", return_value=self.response()) as run, \
             patch.dict(os.environ, {"PYTHONPATH": "SHOULD_NOT_INFLUENCE_CONVERTER"}):
            result = validate_beamng(self.root, snapshot=Path("input.json"),
                                     terrain_surface="literal; no shell", road_guide=None)
        self.assertTrue(result["ok"])
        command = run.call_args.args[0]
        self.assertIn(str(Path("input.json").resolve()), command)
        self.assertIn("literal; no shell", command)
        self.assertNotIn("--road-guide", command)
        self.assertNotIn("PYTHONPATH", run.call_args.kwargs["env"])
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs["cwd"], self.root / "civil3d-beamng")

    def test_missing_validator_and_unknown_options_fail_before_execution(self):
        with patch("cdcrd_local.interchange.subprocess.run") as run:
            with self.assertRaises(ValueError):
                validate_beamng(self.root, unknown="bad")
            self.validator.unlink()
            with self.assertRaises(ValueError):
                validate_beamng(self.root)
        run.assert_not_called()

    def test_invalid_json_and_inconsistent_exit_status_are_not_success(self):
        for response in [self.response("not JSON"), self.response("[]"),
                         self.response('{"schema":"wrong","ok":true}'),
                         self.response('{"schema":"cdcrd.interchange-validation/1","ok":1}'),
                         self.response(code=2)]:
            with self.subTest(response=response):
                with patch("cdcrd_local.interchange.subprocess.run", return_value=response):
                    with self.assertRaises(RuntimeError):
                        validate_beamng(self.root)

    def test_source_rejection_is_returned_as_failure_and_timeout_propagates(self):
        with patch("cdcrd_local.interchange.subprocess.run", return_value=self.response(code=1)):
            self.assertFalse(validate_beamng(self.root)["ok"])
        with patch("cdcrd_local.interchange.subprocess.run",
                   side_effect=subprocess.TimeoutExpired("synthetic", 60)):
            with self.assertRaises(subprocess.TimeoutExpired):
                validate_beamng(self.root)
