import json
from pathlib import Path
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from mcp_hidraulica import mcp


class McpTests(unittest.IsolatedAsyncioTestCase):
    async def test_discovery_and_call(self):
        tools = await mcp.list_tools()
        self.assertEqual([t.name for t in tools], ['calcular_seccion_si'])
        request = json.loads(Path(__file__).with_name('ejemplo_sintetico.json').read_text())
        result = await mcp.call_tool('calcular_seccion_si', request)
        # FastMCP returns content plus structured payload for a dict result.
        payload = result[1] if isinstance(result, tuple) else json.loads(result[0].text)
        self.assertEqual(payload['energy_gate']['status'], 'insufficient')
        self.assertFalse(payload['energy_gate']['route_verified'])
