"""Real MCP subprocess/stdio contract, synthetic inputs, no CAD calls."""
import json
import sys
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path

import anyio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


class StdioTests(unittest.TestCase):
    def test_transport_schema_errors_and_recovery(self):
        async def scenario():
            params = StdioServerParameters(command=sys.executable,
                                           args=[str(ROOT/'src/mcp_hidraulica.py')])
            with tempfile.TemporaryFile(mode='w+', encoding='utf-8') as log:
                with anyio.fail_after(30):
                    async with stdio_client(params, errlog=log) as (reader, writer):
                        async with ClientSession(reader, writer, read_timeout_seconds=timedelta(seconds=10)) as session:
                            await session.initialize()
                            listed = await session.list_tools()
                            tool = next(t for t in listed.tools if t.name == 'calcular_seccion_si')
                            request = json.loads((ROOT/'tests/ejemplo_sintetico.json').read_text())
                            self.assertEqual(set(tool.inputSchema['required']), set(request))
                            result = await session.call_tool(tool.name, request)
                            self.assertFalse(result.isError)
                            payload = result.structuredContent or json.loads(result.content[0].text)
                            self.assertEqual(payload['energy_gate']['status'], 'insufficient')
                            self.assertFalse(payload['energy_gate']['route_verified'])
                            for invalid in ({**request, 'units': 'ft'},
                                            {**request, 'q_m3_s': -1},
                                            {**request, 'q_m3_s': True},
                                            {**request, 'q_m3_s': '0.7'},
                                            {k: v for k, v in request.items() if k != 'losses_m'}):
                                response = await session.call_tool(tool.name, invalid)
                                self.assertTrue(response.isError)
                            recovered = await session.call_tool(tool.name, {**request, 'available_head_m': None})
                            self.assertFalse(recovered.isError)
                            payload = recovered.structuredContent or json.loads(recovered.content[0].text)
                            self.assertEqual(payload['energy_gate']['status'], 'unverified')
        anyio.run(scenario)
