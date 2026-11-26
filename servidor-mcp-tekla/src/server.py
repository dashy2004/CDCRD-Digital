# Tekla MCP - v0.2.0
# Servidor MCP para Tekla Structures. Mismo patrón que servidor-mcp-safe:
# logging antes de la configuración, log junto al script, registro por bloques.

import json
import logging
import os
import sys

SRC_DIR = os.path.dirname(os.path.abspath(__file__))
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stderr),   # stdout está reservado al protocolo MCP
        logging.FileHandler(os.path.join(SRC_DIR, 'tekla_mcp.log'), encoding='utf-8'),
    ])
logger = logging.getLogger('tekla_mcp_server')

from mcp.server.fastmcp import FastMCP          # noqa: E402
from config import Config                       # noqa: E402
from tekla import ErrorTekla, Tekla             # noqa: E402,F401
import captura                                   # noqa: E402

config = Config()
logger.info("Tekla MCP v%s. Puente: %s. Rutas de escritura: %s",
            config.serverVersion, config.exePuente, config.rutasPermitidas)

mcp = FastMCP(config.serverName, dependencies=["pillow", "pywin32"])


@mcp.resource("config://app")
def get_config() -> str:
    """Configuración activa del servidor."""
    return json.dumps(config.data, indent=2, ensure_ascii=False)


tekla = Tekla(config.exePuente, config.rutasPermitidas)

# Modelo
tekla_estado = mcp.tool()(tekla.tekla_estado)
tekla_crear_modelo = mcp.tool()(tekla.tekla_crear_modelo)
tekla_abrir_modelo = mcp.tool()(tekla.tekla_abrir_modelo)
tekla_guardar = mcp.tool()(tekla.tekla_guardar)
tekla_copiar_catalogos = mcp.tool()(tekla.tekla_copiar_catalogos)

# Geometría y uniones
tekla_definir_ejes = mcp.tool()(tekla.tekla_definir_ejes)
tekla_crear_piezas = mcp.tool()(tekla.tekla_crear_piezas)
tekla_crear_placa = mcp.tool()(tekla.tekla_crear_placa)
tekla_crear_tornillos = mcp.tool()(tekla.tekla_crear_tornillos)
tekla_crear_soldadura = mcp.tool()(tekla.tekla_crear_soldadura)

# Cortes
tekla_ajustar_extremo = mcp.tool()(tekla.tekla_ajustar_extremo)
tekla_cortar_plano = mcp.tool()(tekla.tekla_cortar_plano)
tekla_despuntar = mcp.tool()(tekla.tekla_despuntar)
tekla_cortar_con_pieza = mcp.tool()(tekla.tekla_cortar_con_pieza)

# Componentes del catálogo
tekla_crear_componente = mcp.tool()(tekla.tekla_crear_componente)
tekla_crear_detalle = mcp.tool()(tekla.tekla_crear_detalle)
tekla_catalogo_componentes = mcp.tool()(tekla.tekla_catalogo_componentes)
tekla_normas_tornillos = mcp.tool()(tekla.tekla_normas_tornillos)

# Planos
tekla_numerar = mcp.tool()(tekla.tekla_numerar)
tekla_listar_planos = mcp.tool()(tekla.tekla_listar_planos)
tekla_crear_plano = mcp.tool()(tekla.tekla_crear_plano)

# Consulta
tekla_listar_piezas = mcp.tool()(tekla.tekla_listar_piezas)
tekla_borrar = mcp.tool()(tekla.tekla_borrar)

# Vista, informes y captura
tekla_seleccionar = mcp.tool()(tekla.tekla_seleccionar)
tekla_ajustar_vista = mcp.tool()(tekla.tekla_ajustar_vista)
tekla_crear_informe = mcp.tool()(tekla.tekla_crear_informe)


@mcp.tool()
def capturar_ventana(archivo: str, titulo_contiene: str = 'Tekla Structures', region: str = 'completa',
                     fraccion: list[float] | None = None) -> dict:
    """Guarda en PNG la ventana principal cuyo título contenga `titulo_contiene` (Tekla, ETABS, SAFE…).

    `region`: completa | vista | panel | cinta (pensadas para Tekla). `fraccion` = [x0, y0, x1, y1]
    entre 0 y 1 recorta cualquier parte de la ventana. La ventana pasa al frente durante la captura.
    `archivo` debe estar dentro de las carpetas permitidas para escribir."""
    tekla.exigir_archivo_permitido(archivo)
    return captura.capturar(archivo, titulo_contiene, region, fraccion)


@mcp.tool()
def tekla_dialogos() -> list[dict]:
    """Lista los diálogos abiertos en Tekla (texto y botones). Un diálogo modal bloquea a Open API:
    por ejemplo el aviso de licencia educativa al guardar un modelo nuevo."""
    return captura.dialogos()


@mcp.tool()
def tekla_responder_dialogo(ventana: int, boton: str) -> bool:
    """Pulsa un botón («Yes», «No», «OK»…) del diálogo `ventana` devuelto por tekla_dialogos.
    Lea antes el texto del diálogo: la respuesta puede guardar o descartar cambios."""
    return captura.pulsar_boton(ventana, boton)


if __name__ == "__main__":
    logger.info("Servidor Tekla MCP listo")
    mcp.run()
