"""Integra corpus, CLI Windows, verificadores reales y transporte MCP stdio."""

import json
import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import anyio
import ezdxf
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from cdcrd_local.normativa import search

REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "repo"
    for number, folder in ((1, "titulos"), (2, "vol-2")):
        destination = root / "datos" / folder
        destination.mkdir(parents=True)
        data = {
            "titulo": "Título sintético",
            "version_codigo": "CDCRD ensayo",
            "fuente_pdf": f"sintetico-vol-{number}.pdf",
            "clausulas": [{
                "id": "2.10.8.2.1.2",
                "encabezado": "Participación modal",
                "texto": f"Texto sintético volumen {number}: participación ≥ 90 %.",
                "paginas": [40 + number],
            }],
        }
        (destination / "T2.json").write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )
    return root


def run_cli(*arguments):
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0")
    return subprocess.run(
        [sys.executable, "-m", "cdcrd_local.cli", *map(str, arguments)],
        env=env, capture_output=True, encoding="utf-8", timeout=30, check=False,
    )


def test_clause_id_preserves_duplicate_volumes_and_provenance(corpus):
    result = search("2.10.8.2.1.2", corpus)
    assert result["indexed_clauses"] == 2
    assert [row["volumen"] for row in result["results"]] == [1, 2]
    for row in result["results"]:
        number = row["volumen"]
        assert row["paginas"] == [40 + number]
        assert row["version_codigo"] == "CDCRD ensayo"
        assert row["fuente_pdf"] == f"sintetico-vol-{number}.pdf"
        assert (corpus / row["source"]).is_file()
        assert row["ocurrencia"] == 0
        assert row["texto_truncado"] is False


def test_explicit_volume_disambiguates_clause_id(corpus):
    result = search("2.10.8.2.1.2", corpus, volume=2)
    assert result["indexed_clauses"] == 1
    assert len(result["results"]) == 1
    assert result["results"][0]["source"] == "datos/vol-2/T2.json"
    assert "volumen 2" in result["results"][0]["texto"]


def test_text_search_and_windows_cli_retain_unicode(corpus):
    result = search("participación", corpus, volume=1)
    assert len(result["results"]) == 1
    process = run_cli("buscar", "participación", "--repo", corpus, "--volumen", 1)
    assert process.returncode == 0, process.stderr
    cli_result = json.loads(process.stdout)
    assert cli_result == result
    assert "≥" in cli_result["results"][0]["texto"]


@pytest.mark.parametrize("sum_uy, expected_code, verdict", [
    (0.91, 0, "CUMPLE"), (0.70, 1, "NO CUMPLE"),
])
def test_cli_invokes_real_mass_participation_verifier(tmp_path, sum_uy, expected_code, verdict):
    source = tmp_path / "modos.json"
    source.write_text(json.dumps({
        "id": "PRUEBA SINTÉTICA",
        "modos": [
            {"modo": 1, "sum_ux": 0.60, "sum_uy": 0.30},
            {"modo": 2, "sum_ux": 0.92, "sum_uy": sum_uy},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    original = source.read_bytes()
    process = run_cli("verificar", "masa_modal", source, "--repo", REPO)
    assert process.returncode == expected_code, process.stderr
    result = json.loads(process.stdout)
    assert result["execution_ok"] is True
    assert result["exit_code"] == expected_code
    assert result["script"] == "herramientas/verificacion_masa_modal.py"
    assert result["result"]["veredicto"] == verdict
    assert result["result"]["id"] == "PRUEBA SINTÉTICA"
    assert [row["direccion"] for row in result["result"]["chequeos"]] == ["X", "Y"]
    assert all(
        row["clausula"] == "CDCRD T2 2.10.8.2.1.2"
        for row in result["result"]["chequeos"]
    )
    assert source.read_bytes() == original


def test_real_mcp_stdio_search_path_boundaries_and_dxf(corpus, tmp_path):
    source = corpus / "planta.json"
    source.write_text(json.dumps({
        "name": "Planta sintética MCP",
        "units": "m",
        "outlines": [{"id": "perimetro", "layer": "E-LOS",
                      "points": [[0, 0], [6, 0], [6, 4], [0, 4]]}],
        "dimensions": [{"p1": [0, 0], "p2": [6, 0], "offset": -0.6}],
        "notes": [{"text": "SINTÉTICO", "position": [0, 4.5]}],
    }, ensure_ascii=False), encoding="utf-8")
    outside = tmp_path / "fuera.json"
    outside.write_bytes(source.read_bytes())

    async def scenario():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "cdcrd_local.server"],
            env=dict(os.environ, CDCRD_REPO_ROOT=str(corpus), PYTHONIOENCODING="utf-8"),
        )
        with anyio.fail_after(35):
            async with stdio_client(parameters) as (reader, writer):
                async with ClientSession(
                    reader, writer, read_timeout_seconds=timedelta(seconds=15)
                ) as session:
                    initialized = await session.initialize()
                    assert initialized.serverInfo.name == "cdcrd-local"
                    listed = await session.list_tools()
                    assert len(listed.tools) == 10
                    assert {"cdcrd_buscar", "cad_generar_plano", "ifc_validar_ids"} <= {
                        tool.name for tool in listed.tools
                    }
                    found = await session.call_tool("cdcrd_buscar", {
                        "consulta": "2.10.8.2.1.2", "volumen": 2,
                    })
                    assert not found.isError
                    found_data = found.structuredContent or json.loads(found.content[0].text)
                    assert found_data["results"][0]["volumen"] == 2
                    rejected_input = await session.call_tool("pdf_inspeccionar", {
                        "entrada_pdf": str(outside),
                    })
                    assert rejected_input.isError
                    rejected_output = await session.call_tool("cad_generar_plano", {
                        "entrada_json": "planta.json", "salida_dxf": "../../escape.dxf",
                    })
                    assert rejected_output.isError
                    assert not (corpus / "escape.dxf").exists()
                    assert not (corpus / "herramientas-locales/salidas/rechazado.dxf").exists()
                    generated = await session.call_tool("cad_generar_plano", {
                        "entrada_json": "planta.json", "salida_dxf": "mcp.dxf",
                    })
                    assert not generated.isError, generated.content
                    output = corpus / "herramientas-locales/salidas/mcp.dxf"
                    assert output.is_file()
                    original = output.read_bytes()
                    document = ezdxf.readfile(output)
                    assert document.units == ezdxf.units.M
                    assert len(document.modelspace().query("LWPOLYLINE")) == 1
                    assert len(document.modelspace().query("DIMENSION")) == 1
                    repeated = await session.call_tool("cad_generar_plano", {
                        "entrada_json": "planta.json", "salida_dxf": "mcp.dxf",
                    })
                    assert repeated.isError
                    assert output.read_bytes() == original

    anyio.run(scenario)
