"""Portable contracts: inventory and diagnostics never activate BIM applications."""
import importlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
HEALTHY = {"ok": True, "packages": {}, "live_bim_connected": False}


def api():
    return importlib.import_module("cdcrd_local.capabilities")


class CatalogTests(unittest.TestCase):
    def test_inventory_has_stable_metadata(self):
        result = api().catalog(REPO)
        self.assertEqual(result["schema"], "cdcrd.capabilities/1")
        modules = result["modules"]
        ids = [m["id"] for m in modules]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue({"local", "normativa", "revit", "etabs", "safe",
                         "civil3d", "autocad", "terrain", "points-survey",
                         "beamng", "losas"} <= set(ids))
        for module in modules:
            for field in ("module", "operations", "inputs", "outputs", "units",
                          "documentation", "entrypoints", "version_status"):
                self.assertTrue(module[field], (module["id"], field))
            self.assertIn("version", module)
            self.assertTrue(module["source_available"], module["id"])
            for evidence in module["evidence"]:
                self.assertTrue(evidence["present"], evidence)

    def test_filter_and_returned_values_do_not_mutate_registry(self):
        result = api().catalog(REPO, "civil3d")
        self.assertEqual([m["id"] for m in result["modules"]], ["civil3d"])
        result["modules"][0]["entrypoints"].clear()
        self.assertTrue(api().catalog(REPO, "civil3d")["modules"][0]["entrypoints"])

    def test_unknown_module_and_invalid_repo_are_explicit(self):
        with self.assertRaises(ValueError):
            api().catalog(REPO, "unknown")
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                api().catalog(Path(folder))


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "datos/titulos").mkdir(parents=True)
        self.write("herramientas-locales/src/cdcrd_local/cli.py", "# synthetic\n")
        self.write("herramientas-locales/README.md", "Synthetic local tool\n")

    def write(self, name, text):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p

    def state(self, config=None, module="local"):
        with patch.object(api(), "diagnose", return_value=HEALTHY) as doctor:
            result = api().diagnose_ecosystem(self.root, module, config)
        doctor.assert_called_once_with()
        return result

    def test_reuses_doctor_without_claiming_installation_or_live_connection(self):
        with patch("socket.create_connection", side_effect=AssertionError("network")), \
             patch("subprocess.run", side_effect=AssertionError("process")):
            result = self.state()
        self.assertTrue(result["ok"])
        self.assertEqual(result["environment"], HEALTHY)
        self.assertFalse(result["live_bim_connected"])
        module = result["modules"][0]
        self.assertTrue(module["source_available"])
        self.assertIsNone(module["installed"])
        self.assertIsNone(module["configured"])
        self.assertEqual(module["live_connection"], "not_checked")
        self.assertFalse(result["configuration_checked"])

    def test_missing_sources_and_failed_dependencies_are_visible(self):
        (self.root / "herramientas-locales/src/cdcrd_local/cli.py").unlink()
        result = self.state()
        self.assertFalse(result["ok"])
        self.assertFalse(result["modules"][0]["source_available"])
        with patch.object(api(), "diagnose", return_value={"ok": False, "packages": {}}):
            self.assertFalse(api().diagnose_ecosystem(self.root, "local")["ok"])

    def test_valid_json_configuration_is_redacted(self):
        config = self.write("private.json", json.dumps({"mcpServers": {
            "cdcrd-local": {"command": "PRIVATE_COMMAND", "args": ["PRIVATE_ARG"],
                            "env": {"TOKEN": "PRIVATE_TOKEN"}},
        }}))
        result = self.state(config)
        self.assertTrue(result["configuration_checked"])
        self.assertTrue(result["modules"][0]["configured"])
        serialized = json.dumps(result)
        for secret in ("PRIVATE_COMMAND", "PRIVATE_ARG", "PRIVATE_TOKEN", "private.json"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(result["modules"][0]["live_connection"], "not_checked")

    def test_codex_toml_and_url_configuration(self):
        config = self.write("config.toml", '[mcp_servers.cdcrd-local]\nurl="https://private"\n')
        result = self.state(config)
        self.assertTrue(result["modules"][0]["configured"])
        self.assertNotIn("https://private", json.dumps(result))

    def test_missing_and_invalid_server_entries_are_distinct(self):
        for server, expected, invalid in [(None, False, False), ({}, False, True),
                                          ({"command": " "}, False, True),
                                          ({"command": 12}, False, True),
                                          ({"command": "python", "args": "bad"}, False, True),
                                          ({"command": "python", "disabled": True}, False, False)]:
            with self.subTest(server=server):
                config = self.write("config.json", json.dumps({
                    "mcpServers": {} if server is None else {"cdcrd-local": server}}))
                result = self.state(config)["modules"][0]
                self.assertEqual(result["configured"], expected)
                self.assertEqual(result["configuration_invalid"], invalid)

    def test_config_is_optional_for_modules_without_mcp(self):
        config = self.write("config.json", '{"mcpServers":{}}')
        module = self.state(config, "beamng")["modules"][0]
        self.assertIsNone(module["configured"])

    def test_explicit_missing_or_invalid_configuration_is_not_ok(self):
        for content in ['{"mcpServers":{}}', '{"mcpServers":{"cdcrd-local":{}}}']:
            with self.subTest(content=content):
                result = self.state(self.write("config.json", content))
                self.assertFalse(result["ok"])

    def test_configuration_errors_are_explicit_and_do_not_echo_contents(self):
        for name, text in [("bad.json", "PRIVATE_INVALID_JSON"),
                           ("bad.toml", "PRIVATE_INVALID_TOML"),
                           ("bad.txt", "{}"), ("wrong.json", "[]"),
                           ("empty.json", "{}"),
                           ("servers.json", '{"mcpServers":[]}')]:
            with self.subTest(name=name):
                with self.assertRaises(ValueError) as error:
                    self.state(self.write(name, text))
                self.assertNotIn("PRIVATE", str(error.exception))
        with self.assertRaises(OSError):
            self.state(self.root / "missing.json")
        huge = self.write("huge.json", " " * (1024 * 1024 + 1))
        with self.assertRaises(ValueError):
            self.state(huge)

    def test_source_version_is_metadata_not_runtime_version(self):
        path = "herramientas-locales/pyproject.toml"
        self.write(path, '[project]\nversion="9.8.7"\n')
        module = api().catalog(self.root, "local")["modules"][0]
        self.assertEqual(module["version"], "9.8.7")
        self.assertEqual(module["version_status"], "source_metadata")
        for text, status in [("broken toml!", "invalid"), ("[project]\n", "not_declared"),
                             ('[project]\nversion=42\n', "invalid")]:
            self.write(path, text)
            self.assertEqual(api().catalog(self.root, "local")["modules"][0]
                             ["version_status"], status)
        self.write(path, "x" * (1024 * 1024 + 1))
        self.assertEqual(api().catalog(self.root, "local")["modules"][0]
                         ["version_status"], "invalid")


class CLITests(unittest.TestCase):
    def run_cli(self, *args):
        return subprocess.run([sys.executable, "-m", "cdcrd_local.cli", *args],
                              env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                              capture_output=True, encoding="utf-8", timeout=30, check=False)

    def test_catalog_cli_is_json(self):
        result = self.run_cli("capacidades", "--repo", str(REPO), "--modulo", "civil3d")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["modules"][0]["id"], "civil3d")

    def test_state_cli_json_and_bad_config_exit(self):
        # Dependencies can legitimately be missing on a portable CI runner.
        result = self.run_cli("estado", "--repo", str(REPO), "--modulo", "civil3d", "--json")
        self.assertIn(result.returncode, [0, 1], result.stderr)
        self.assertFalse(json.loads(result.stdout)["live_bim_connected"])
        result = self.run_cli("estado", "--repo", str(REPO), "--config", str(REPO / "absent.json"))
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stderr)["ok"])

    def test_unknown_module_cli_fails_explicitly(self):
        result = self.run_cli("capacidades", "--repo", str(REPO), "--modulo", "unknown")
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stderr)["ok"])


if __name__ == "__main__":
    unittest.main()
