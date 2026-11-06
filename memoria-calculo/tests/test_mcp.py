import json
import sys

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_real_stdio_tool_roundtrip(dossier_data, tmp_path):
    async def run():
        params = StdioServerParameters(command=sys.executable, args=["-m", "cdcrd_memoria.server"])
        with anyio.fail_after(30):
            async with stdio_client(params) as (read, write):  # noqa: SIM117 -- dependent session scope
                async with ClientSession(read, write) as client:
                    await client.initialize()
                    catalog = await client.list_tools()
                    assert {t.name for t in catalog.tools} == {
                        "memoria_inspeccionar_fuentes",
                        "memoria_validar_expediente",
                        "memoria_preparar",
                        "memoria_generar",
                    }
                    for name, args in [
                        ("memoria_validar_expediente", {"expediente": dossier_data}),
                        ("memoria_preparar", {"expediente": dossier_data}),
                        (
                            "memoria_inspeccionar_fuentes",
                            {"expediente": dossier_data, "base_directory": str(tmp_path)},
                        ),
                        (
                            "memoria_generar",
                            {
                                "expediente": dossier_data,
                                "base_directory": str(tmp_path),
                                "output_directory": str(tmp_path / "mcp-output"),
                                "formats": ["html"],
                            },
                        ),
                    ]:
                        result = await client.call_tool(name, args)
                        assert not result.isError, result
                        assert result.structuredContent or json.loads(result.content[0].text)
                    bad = await client.call_tool(
                        "memoria_preparar", {"expediente": dossier_data, "template_id": "wrong"}
                    )
                    assert bad.isError

    anyio.run(run)


def test_generation_keeps_event_loop_responsive(dossier_data, tmp_path, monkeypatch):
    import threading

    from cdcrd_memoria import server

    started = threading.Event()
    finished = threading.Event()

    def slow_generate(*args):
        started.set()
        if not finished.wait(timeout=5):
            raise RuntimeError("Event loop blocked while generating")
        return {"complete": True}

    monkeypatch.setattr(server, "generate", slow_generate)

    async def run():
        async with anyio.create_task_group() as group:
            group.start_soon(server.memoria_generar, dossier_data, str(tmp_path / "out"), str(tmp_path))
            with anyio.fail_after(3):
                while not started.is_set():
                    await anyio.sleep(0.01)
            finished.set()

    anyio.run(run)
