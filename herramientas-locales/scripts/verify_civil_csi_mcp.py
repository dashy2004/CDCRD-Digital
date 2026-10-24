"""Read-only, sequential MCP acceptance run on explicitly named synthetic models.

Requires Python 3.11+ and mcp>=1.10,<2 in the runner. Each child runtime must
already have its server dependencies. No application/model creation or analysis.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

PRODUCTS = ("ETABS", "SAFE")
UNITS = ("in", "ft", "in", "ft", "mm", "m", "mm", "m",
         "mm", "m", "mm", "m", "cm", "cm", "cm", "cm")
TO_METRES = {"m": 1, "mm": .001, "cm": .01, "ft": .3048, "in": .0254}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def write_new(path, value):
    with Path(path).open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False, indent=2)


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def finite(value):
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
        raise ValueError("Expected a finite number")
    return float(value)


def xyz(value):
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError("Expected XYZ list with three components")
    return [finite(v) for v in value]


def label(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Empty identifier")
    return value


def absolute_file(value, suffix=None, synthetic=False):
    path = Path(value)
    if not path.is_absolute() or not path.is_file():
        raise ValueError(f"Expected existing absolute file: {path}")
    path = path.resolve(strict=True)
    if suffix and path.suffix.upper() != suffix:
        raise ValueError(f"Expected {suffix} file: {path}")
    if synthetic and not path.name.startswith("SYNTHETIC_"):
        raise ValueError("Only SYNTHETIC_* model filenames are allowed")
    return path


def validate_manifest(data):
    """Validate explicit expectations before starting any server or creating output."""
    try:
        if data["schema"] != "cdcrd.civil-csi-test/1":
            raise ValueError("Unknown manifest schema")
        tolerance = finite(data["tolerance_m"])
        if not 0 < tolerance <= .001:
            raise ValueError("tolerance_m must be in (0, 0.001]")
        label(data["site_frame"])
        label(data["vertical_datum"])
        if not re.fullmatch(r"[0-9A-Fa-f]+", data["surface_handle"]):
            raise ValueError("Invalid surface handle")
        absolute_file(data["drawing"], ".DWG", True)
        expected = data["expected_points"]
        if not isinstance(expected, dict) or not 1 <= len(expected) <= 1000:
            raise ValueError("Expected 1-1000 independent point expectations")
        for key, value in expected.items():
            label(key)
            xyz(value["site_xyz_m"])
            finite(value["terrain_z_m"])
        if set(data["models"]) != set(PRODUCTS):
            raise ValueError("Both ETABS and SAFE are required")
        for product, suffix in (("ETABS", ".EDB"), ("SAFE", ".FDB")):
            model = data["models"][product]
            absolute_file(model["path"], suffix, True)
            absolute_file(model["config"], ".JSON")
            if type(model["process_id"]) is not int or model["process_id"] <= 0:
                raise ValueError("An explicit positive process_id is required")
            label(model["source_frame"])
            units = model["expected_units_enum"]
            if (type(units) is not int or not 1 <= units <= 16
                    or model["expected_length_unit"] != UNITS[units-1]):
                raise ValueError("CSI unit enum and expected length unit disagree")
            points = model["expected_source_points"]
            if not isinstance(points, dict) or not 1 <= len(points) <= 10000:
                raise ValueError("Expected all source points, up to 10000")
            for key, value in points.items():
                label(key)
                xyz(value)
            if not set(expected).issubset(points):
                raise ValueError("Expected selected points absent from source expectations")
            config = read_json(model["config"])
            if (config["source_frame"] != model["source_frame"]
                    or config["site_frame"] != data["site_frame"]
                    or config["vertical_datum"] != data["vertical_datum"]
                    or len(config["point_ids"]) != len(expected)
                    or set(config["point_ids"]) != set(expected)):
                raise ValueError("Config frame/datum/selected IDs differ from manifest")
    except (KeyError, TypeError, IndexError) as error:
        raise ValueError(f"Incomplete or malformed manifest: {error}") from error
    return data


def parse_tool_result(result):
    """Accept structured objects or JSON text, rejecting explicit errors and ambiguity."""
    if result.get("isError"):
        raise RuntimeError(f"MCP isError: {result.get('content')}")
    values = []
    structured = result.get("structuredContent")
    if structured is not None:
        # FastMCP wraps scalar return values in {result: ...}.
        if isinstance(structured, dict) and set(structured) == {"result"}:
            structured = structured["result"]
        values.append(json.loads(structured) if isinstance(structured, str) else structured)
    for block in result.get("content", []):
        if block.get("type") == "text":
            try:
                values.append(json.loads(block["text"]))
            except (ValueError, KeyError) as error:
                raise RuntimeError("MCP returned non-JSON text") from error
    if not values or any(not isinstance(value, dict) for value in values):
        raise RuntimeError("MCP did not return a JSON object")
    if any("error" in value for value in values):
        raise RuntimeError(f"MCP JSON error: {values}")
    if any(value != values[0] for value in values[1:]):
        raise RuntimeError("MCP structured/text outputs disagree")
    return values[0]


def index_rows(rows):
    indexed = {label(row["id"]): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("Duplicate point IDs")
    return indexed


def check_snapshot(snapshot, product, spec, tolerance):
    if snapshot.get("schema") != "cdcrd.csi-points/1":
        raise ValueError("Invalid CSI snapshot schema")
    source = snapshot["source"]
    if (source["application"] != product
            or Path(source["model"]).resolve() != Path(spec["path"]).resolve()
            or source["units_enum"] != spec["expected_units_enum"]
            or snapshot["frame"] != {"id": spec["source_frame"], "axes": "Global",
                                     "length_unit": spec["expected_length_unit"]}
            or snapshot.get("model_writes") != 0):
        raise ValueError("CSI identity/units/frame/read-only assertion mismatch")
    actual = index_rows(snapshot["points"])
    expected = spec["expected_source_points"]
    if set(actual) != set(expected):
        raise ValueError("CSI source point IDs differ from independent expectations")
    factor = TO_METRES[spec["expected_length_unit"]]
    for key in actual:
        if math.dist(xyz(actual[key]["xyz"]), xyz(expected[key])) * factor > tolerance:
            raise ValueError(f"Unexpected source XYZ: {product}/{key}")


def snapshot_identity(snapshot):
    source = {k: v for k, v in snapshot["source"].items() if k != "captured_utc"}
    return source, snapshot["frame"], index_rows(snapshot["points"])


def check_result(rows, expected, tolerance, review=False):
    actual = index_rows(rows)
    if set(actual) != set(expected):
        raise ValueError("Result IDs differ from expectations")
    for key, row in actual.items():
        target = expected[key]
        if math.dist(xyz(row["site_xyz_m"]), xyz(target["site_xyz_m"])) > tolerance:
            raise ValueError(f"Unexpected site XYZ: {key}")
        if review:
            if row.get("status") != "ok":
                raise ValueError(f"Missing native elevation: {key}")
            if abs(finite(row["terrain_z_m"]) - target["terrain_z_m"]) > tolerance:
                raise ValueError(f"Unexpected terrain elevation: {key}")
            delta = target["terrain_z_m"] - target["site_xyz_m"][2]
            if abs(finite(row["terrain_minus_joint_m"]) - delta) > tolerance:
                raise ValueError(f"Unexpected terrain-joint difference: {key}")


class Runner:
    def __init__(self, repo, output, csi_python, local_python, timeout):
        self.repo, self.output = repo, output
        self.csi_python, self.local_python = csi_python, local_python
        self.timeout, self.counter = timeout, 0

    async def calls(self, server, operations, process_id=None):
        # Lazy imports leave validators/tests/--help independent from MCP installation.
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        self.counter += 1
        prefix = f"{self.counter:02d}-{server}"
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        if server == "local":
            command, args = self.local_python, ["-m", "cdcrd_local.server"]
            env.update(CDCRD_REPO_ROOT=str(self.repo),
                       PYTHONPATH=str(self.repo / "herramientas-locales" / "src"))
        else:
            folder = {"ETABS": "servidor-mcp", "SAFE": "servidor-mcp-safe",
                      "civil": "servidor-mcp-civil3d"}[server]
            command, args = self.csi_python, [str(self.repo / folder / "src" / "server.py")]
            if server in PRODUCTS:
                env[f"{server}_PROCESS_ID"] = str(process_id)
        parameters = StdioServerParameters(command=str(command), args=args, env=env,
                                           cwd=str(self.repo))
        results = []
        with (self.output / f"{prefix}-stderr.log").open("x", encoding="utf-8") as stderr:
            async with stdio_client(parameters, errlog=stderr) as (read, write):
                async with ClientSession(
                    read, write, read_timeout_seconds=timedelta(seconds=self.timeout)
                ) as session:
                    initialized = await asyncio.wait_for(session.initialize(), self.timeout)
                    write_new(self.output / f"{prefix}-initialize.json",
                              initialized.model_dump(mode="json"))
                    listed = await asyncio.wait_for(session.list_tools(), self.timeout)
                    write_new(self.output / f"{prefix}-tools.json", listed.model_dump(mode="json"))
                    available = {tool.name for tool in listed.tools}
                    for index, (name, arguments) in enumerate(operations, 1):
                        if name not in available:
                            raise RuntimeError(f"Tool absent in fresh server: {server}/{name}")
                        receipt = {"server": server, "tool": name, "arguments": arguments}
                        path = self.output / f"{prefix}-{index:02d}-{name}.json"
                        try:
                            raw = await asyncio.wait_for(
                                session.call_tool(name, arguments), self.timeout)
                            receipt["result"] = raw.model_dump(mode="json")
                        except BaseException as error:
                            receipt["exception"] = f"{type(error).__name__}: {error}"
                            write_new(path, receipt)
                            raise
                        write_new(path, receipt)
                        results.append(parse_tool_result(receipt["result"]))
        return results

    def input_name(self, name):
        return (self.output / name).relative_to(self.repo).as_posix()

    def output_name(self, name):
        return f"{self.output.name}/{name}"

    async def execute(self, manifest):
        snapshots, queries, reviews = {}, {}, {}
        tolerance = manifest["tolerance_m"]
        for product in PRODUCTS:
            spec = manifest["models"][product]
            write_new(self.output / f"{product}-config.json", read_json(spec["config"]))
            snapshots[product] = (await self.calls(product, [("get_coordinate_snapshot", {
                "expected_path": spec["path"], "frame_id": spec["source_frame"],
                "max_points": len(spec["expected_source_points"])} )], spec["process_id"]))[0]
            check_snapshot(snapshots[product], product, spec, tolerance)
            write_new(self.output / f"{product}-before.json", snapshots[product])
        for product in PRODUCTS:
            query = (await self.calls("local", [("cimentacion_preparar_consulta", {
                "snapshot_json": self.input_name(f"{product}-before.json"),
                "configuracion_json": self.input_name(f"{product}-config.json"),
                "salida_json": self.output_name(f"{product}-query.json")})]))[0]
            check_result(query["points"], manifest["expected_points"], tolerance)
            if read_json(self.output / f"{product}-query.json") != query:
                raise ValueError("MCP prepare output file differs from response")
            queries[product] = query
        for product in PRODUCTS:
            samples = (await self.calls("civil", [("muestrear_cimentaciones", {
                "consulta_json": json.dumps(queries[product], allow_nan=False),
                "dibujo_esperado": manifest["drawing"],
                "superficie_handle": manifest["surface_handle"],
                "sistema_sitio": manifest["site_frame"],
                "datum_vertical": manifest["vertical_datum"]})]))[0]
            write_new(self.output / f"{product}-samples.json", samples)
            if (Path(samples["source"]["drawing"]).resolve()
                    != Path(manifest["drawing"]).resolve()
                    or samples["source"]["surface"] != manifest["surface_handle"]
                    or samples.get("model_writes") != 0):
                raise ValueError("Civil sample source/read-only assertion mismatch")
            result = (await self.calls("local", [("cimentacion_revisar_cotas", {
                "consulta_json": self.input_name(f"{product}-query.json"),
                "muestras_json": self.input_name(f"{product}-samples.json"),
                "salida_json": self.output_name(f"{product}-review.json")})]))[0]
            if (result.get("ok") is not True or result.get("model_writes") != 0
                    or result.get("analysis_run") is not False):
                raise ValueError("Review did not pass read-only acceptance checks")
            check_result(result["rows"], manifest["expected_points"], tolerance, review=True)
            if read_json(self.output / f"{product}-review.json") != result:
                raise ValueError("MCP review output file differs from response")
            reviews[product] = index_rows(result["rows"])
        for key, etabs in reviews["ETABS"].items():
            safe = reviews["SAFE"][key]
            if (math.dist(etabs["site_xyz_m"], safe["site_xyz_m"]) > tolerance
                    or abs(etabs["terrain_z_m"] - safe["terrain_z_m"]) > tolerance):
                raise ValueError(f"ETABS/SAFE parity failed: {key}")
        for product in PRODUCTS:
            spec = manifest["models"][product]
            after = (await self.calls(product, [("get_coordinate_snapshot", {
                "expected_path": spec["path"], "frame_id": spec["source_frame"],
                "max_points": len(spec["expected_source_points"])} )], spec["process_id"]))[0]
            write_new(self.output / f"{product}-after.json", after)
            check_snapshot(after, product, spec, tolerance)
            if snapshot_identity(after) != snapshot_identity(snapshots[product]):
                raise ValueError(f"{product} points/units/identity changed during the run")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True,
                        help="Private explicit JSON manifest")
    parser.add_argument("--repo", type=Path, required=True,
                        help="Full checkout containing all servers")
    parser.add_argument("--python-csi", type=Path, required=True,
                        help="Installed CSI/Civil server Python")
    parser.add_argument("--python-local", type=Path, required=True,
                        help="Installed local server Python")
    parser.add_argument("--run-id", required=True,
                        help="New output subdirectory; never overwritten")
    parser.add_argument("--timeout", type=int, default=120,
                        help="Per-MCP-operation timeout (10-300 s)")
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}", args.run_id):
        parser.error("run-id must be 1-64 alphanumeric, underscore or hyphen characters")
    if not 10 <= args.timeout <= 300:
        parser.error("timeout must be in 10-300 seconds")
    repo = args.repo.resolve(strict=True)
    manifest = validate_manifest(read_json(absolute_file(args.manifest, ".JSON")))
    csi_python, local_python = absolute_file(args.python_csi), absolute_file(args.python_local)
    for folder, section in (("servidor-mcp", "fea"), ("servidor-mcp-safe", "safe")):
        config = read_json(repo / folder / "src" / "config.json")
        if config.get(section, {}).get("auto_start") is not False:
            raise ValueError("CSI server config must explicitly set auto_start=false")
        if section == "fea" and config[section].get("software", "").upper() != "ETABS":
            raise ValueError("FEA server must be configured as ETABS")
    output_root = repo / "herramientas-locales" / "salidas"
    if not output_root.resolve().is_relative_to(repo):
        raise ValueError("Output directory must resolve inside the checkout")
    output_root.mkdir(parents=True, exist_ok=True)
    output = output_root / args.run_id
    output.mkdir()  # Atomic refusal of an existing run: no overwrites or automatic retries.
    paths = {product: manifest["models"][product]["path"] for product in PRODUCTS}
    paths["Civil3D"] = manifest["drawing"]
    report = {"schema": "cdcrd.civil-csi-test-result/1", "status": "failed",
              "started_utc": datetime.now(timezone.utc).isoformat(),
              "model_hashes_before": {key: sha256(path) for key, path in paths.items()},
              "native_verified": False, "analysis_run": False, "model_writes_requested": 0}
    write_new(output / "manifest.json", manifest)
    try:
        runner = Runner(repo, output, csi_python, local_python, args.timeout)
        asyncio.run(runner.execute(manifest))
        report.update(status="passed", native_verified=True)
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = f"{type(error).__name__}: {error}"
    finally:
        try:
            report["model_hashes_after"] = {key: sha256(path) for key, path in paths.items()}
            report["model_files_unchanged"] = (
                report["model_hashes_after"] == report["model_hashes_before"])
            if not report["model_files_unchanged"]:
                report.update(status="failed", native_verified=False,
                              integrity_error="A model file changed during the run")
        except OSError as error:
            report.update(status="failed", native_verified=False, integrity_error=str(error))
        report["finished_utc"] = datetime.now(timezone.utc).isoformat()
        report["artifact_sha256"] = {path.name: sha256(path) for path in output.iterdir()
                                      if path.is_file()}
        write_new(output / "RESULT.json", report)
    print(json.dumps({"status": report["status"], "result": str(output / "RESULT.json"),
                      "error": report.get("error")}, ensure_ascii=False))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
