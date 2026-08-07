# FEA MCP - fix
# Cargador de configuracion.

import json
import logging
import os

logger = logging.getLogger('fea_mcp_server')

DEFAULTS = {
    "server": {"name": "FEA MCP", "version": "1.1.0"},
    "fea": {"software": "ETABS", "version": "22.0",
            "auto_start": False, "exe_path": ""},
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

        # Rellenar claves faltantes para tolerar config.json antiguos.
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
    def feaName(self) -> str:
        return str(self.data['fea']['software']).upper()

    @property
    def feaVersion(self) -> str:
        # El original hacia float(version) -> ValueError con "21.1.0" o "v22".
        raw = str(self.data['fea']['version'])
        try:
            return f"{float(raw):.1f}"
        except ValueError:
            logger.warning("Version '%s' no numerica; se usa tal cual.", raw)
            return raw

    @property
    def autoStart(self) -> bool:
        return bool(self.data['fea'].get('auto_start', False))

    @property
    def exePath(self) -> str:
        return str(self.data['fea'].get('exe_path', ""))


if __name__ == "__main__":
    c = Config()
    print(f"Servidor : {c.serverName} {c.serverVersion}")
    print(f"Software : {c.feaName} {c.feaVersion}")
    print(f"AutoStart: {c.autoStart}")
