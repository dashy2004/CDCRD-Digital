# Tekla MCP
# Cargador de configuración. Misma estructura que servidor-mcp-safe/src/config.py.

import json
import logging
import os

logger = logging.getLogger('tekla_mcp_server')
AQUI = os.path.dirname(os.path.abspath(__file__))

DEFAULTS = {
    "server": {"name": "Tekla MCP", "version": "0.2.0"},
    "tekla": {
        # Ruta del puente compilado; vacío = ..\puente\TeklaPuente.exe
        "exe_puente": "",
        # Carpetas (y subcarpetas) donde se permite crear o modificar modelos.
        "rutas_permitidas": ["%TEMP%\\tekla-mcp-pruebas"],
    },
}


class Config:
    def __init__(self, path: str = ''):
        path = path or os.path.join(AQUI, 'config.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            logger.info("Configuración cargada desde %s", path)
        except (OSError, json.JSONDecodeError) as e:
            logger.error("No se pudo leer config.json (%s). Se usan los valores por defecto.", e)
            self.data = json.loads(json.dumps(DEFAULTS))
        for section, values in DEFAULTS.items():
            self.data.setdefault(section, {})
            for k, v in values.items():
                self.data[section].setdefault(k, v)

    @property
    def serverName(self) -> str:
        return self.data['server']['name']

    @property
    def serverVersion(self) -> str:
        return self.data['server']['version']

    @property
    def exePuente(self) -> str:
        return str(self.data['tekla'].get('exe_puente') or
                   os.path.join(os.path.dirname(AQUI), 'puente', 'TeklaPuente.exe'))

    @property
    def rutasPermitidas(self) -> list[str]:
        rutas = [str(r) for r in self.data['tekla'].get('rutas_permitidas', []) if str(r).strip()]
        extra = os.environ.get('TEKLA_MCP_RUTAS', '')
        return rutas + [r for r in extra.split(';') if r.strip()]
