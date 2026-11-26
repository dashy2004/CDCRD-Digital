"""Prueba viva (requiere Tekla Structures abierto): arranca el servidor como lo hace un
cliente MCP (proceso aparte, protocolo por stdio) y llama a herramientas de solo lectura.

Uso: py tests\\vivo\\prueba_cliente_mcp.py
"""
import asyncio
import json
import os
import sys
import tempfile

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVIDOR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'src', 'server.py')


def datos(resultado) -> object:
    if resultado.isError:
        raise RuntimeError(resultado.content[0].text)
    if resultado.structuredContent is not None:
        return resultado.structuredContent.get('result', resultado.structuredContent)
    # Sin esquema de salida, FastMCP envía una lista como un bloque de texto por elemento.
    bloques = [json.loads(b.text) for b in resultado.content]
    return bloques[0] if len(bloques) == 1 else bloques


async def main() -> int:
    parametros = StdioServerParameters(command=sys.executable, args=[os.path.abspath(SERVIDOR)])
    async with stdio_client(parametros) as (lectura, escritura):
        async with ClientSession(lectura, escritura) as sesion:
            inicio = await sesion.initialize()
            herramientas = [h.name for h in (await sesion.list_tools()).tools]
            estado = datos(await sesion.call_tool('tekla_estado', {}))
            normas = datos(await sesion.call_tool('tekla_normas_tornillos', {}))
            piezas = datos(await sesion.call_tool('tekla_listar_piezas', {}))
            png = os.path.join(tempfile.gettempdir(), 'tekla-mcp-pruebas', 'cliente-mcp.png')
            captura = datos(await sesion.call_tool('capturar_ventana', {'archivo': png, 'region': 'vista'}))
            rechazo = await sesion.call_tool('tekla_despuntar', {'id_pieza': 1, 'minimo': [0, 0, 0], 'maximo': [1, 0, 1]})
    out = {'servidor': f'{inicio.serverInfo.name} {inicio.serverInfo.version}', 'herramientas': len(herramientas),
           'modelo': estado['modelo'], 'piezas_en_estado': estado['piezas'], 'piezas_listadas': len(piezas['piezas']),
           'normas_de_tornillo': len(normas), 'captura': [captura['ancho'], captura['alto']],
           'entrada_no_valida_rechazada': rechazo.isError}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    ok = (len(herramientas) >= 29 and estado['piezas'] == len(piezas['piezas']) and os.path.isfile(png) and rechazo.isError)
    print('RESULTADO:', 'OK' if ok else 'FALLA')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(asyncio.run(main()))
