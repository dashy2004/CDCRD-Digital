"""Cliente del puente JSON-RPC que corre dentro de Civil 3D 2027.

Una conexion por llamada: el puente es local (127.0.0.1) y las llamadas son
cortas, asi no hay estado de socket que se degrade entre herramientas.
"""

import json
import logging
import os
import socket

logger = logging.getLogger('civil3d_mcp.puente')

PUERTO = int(os.environ.get('CDCRD_C3D_PORT', '8760'))
HOST = '127.0.0.1'
TIMEOUT = float(os.environ.get('CDCRD_C3D_TIMEOUT_S', '70'))


class PuenteError(RuntimeError):
    def __init__(self, codigo, mensaje, datos=None):
        super().__init__(f'[{codigo}] {mensaje}')
        self.codigo = codigo
        self.mensaje = mensaje
        self.datos = datos


_contador = {'n': 0}


def llamar(metodo, parametros=None):
    """Envia un metodo al puente y devuelve el resultado o levanta PuenteError."""
    _contador['n'] += 1
    peticion = {
        'jsonrpc': '2.0',
        'id': _contador['n'],
        'method': metodo,
        'params': parametros or {},
    }
    datos = (json.dumps(peticion, ensure_ascii=False) + '\n').encode('utf-8')
    try:
        with socket.create_connection((HOST, PUERTO), timeout=TIMEOUT) as s:
            s.settimeout(TIMEOUT)
            s.sendall(datos)
            buf = bytearray()
            while b'\n' not in buf:
                trozo = s.recv(65536)
                if not trozo:
                    break
                buf.extend(trozo)
    except ConnectionRefusedError:
        raise PuenteError(
            'sin_puente',
            'no hay puente escuchando en 127.0.0.1:%d. Abra Civil 3D 2027; si el bundle '
            'esta instalado el puente arranca solo, y si no, escriba CDCRDMCP en la linea '
            'de comandos de Civil 3D' % PUERTO)
    except socket.timeout:
        raise PuenteError(
            'timeout',
            'el puente no respondio en %.0f s: Civil 3D suele estar en un comando, un '
            'dialogo modal o en modo edicion. Resultado incierto: no reintente escrituras; '
            'consulte diag.cola y verifique el dibujo' % TIMEOUT)

    linea = bytes(buf).split(b'\n', 1)[0].decode('utf-8', 'replace').strip()
    if not linea:
        raise PuenteError('vacio', 'el puente cerro la conexion sin responder')
    respuesta = json.loads(linea)
    if 'error' in respuesta:
        err = respuesta['error']
        raise PuenteError(err.get('code', -1), err.get('message', 'error sin mensaje'), err.get('data'))
    return respuesta.get('result')


def llamar_con_aprobacion(metodo, parametros):
    """Para metodos que escriben: pide el token ligado a estos parametros exactos.

    El puente liga el token al hash de (metodo, parametros sin token) y lo consume
    una sola vez, de modo que no se puede reutilizar con otros parametros.
    """
    parametros = dict(parametros or {})
    parametros.pop('token', None)
    aprobacion = llamar('approval.request', {'metodo': metodo, 'parametros': parametros})
    parametros['token'] = aprobacion['token']
    return llamar(metodo, parametros)
