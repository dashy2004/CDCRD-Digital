# SAFE MCP
# Cargador de configuracion. Estructura identica a servidor-mcp/src/config.py
# (fea.software fijo en "SAFE" en vez de leerse de config.json, porque este
# servidor solo habla con un producto).

import json
import logging
import os

logger = logging.getLogger('safe_mcp_server')

DEFAULTS = {
    "server": {"name": "SAFE MCP", "version": "0.1.0"},
    "safe": {
        # ProgID COM real: NO CONFIRMADO en esta sesion (sin Windows/SAFE
        # disponibles). Candidatos a probar, en orden, ver diagnose_safe.py
        # y Safe.py::_PROGID_CANDIDATES. Si diagnose_safe.py confirma cual
        # funciona en esta instalacion, fijarlo aca para saltarse el sondeo
        # en cada arranque.
        "prog_id": "",
        "helper_prog_id": "",
        "auto_start": False,
        "exe_path": "",
    },
}


class Config:
    def __init__(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
        try:
            with open(path, 'r', encoding='utf-8') as f:
                self.data = json.load(f)
            logger.info("Configuracion cargada desde %s", path)
        except Exception as e:
            logger.error("No se pudo leer config.json (%s). Usando valores por defecto.", e)
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
    def progId(self) -> str:
        return str(self.data['safe'].get('prog_id', ""))

    @property
    def helperProgId(self) -> str:
        return str(self.data['safe'].get('helper_prog_id', ""))

    @property
    def autoStart(self) -> bool:
        return bool(self.data['safe'].get('auto_start', False))

    @property
    def exePath(self) -> str:
        return str(self.data['safe'].get('exe_path', ""))


if __name__ == "__main__":
    c = Config()
    print(f"Servidor : {c.serverName} {c.serverVersion}")
    print(f"ProgID   : {c.progId or '(sin confirmar, se sondea en Safe.py)'}")
    print(f"AutoStart: {c.autoStart}")
