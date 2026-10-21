import importlib.util
import json
from pathlib import Path
import socket
import sys
from unittest.mock import MagicMock, patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import puente_cliente

spec = importlib.util.spec_from_file_location('humo_v052', ROOT / 'pruebas/humo_v052.py')
humo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(humo)


def test_error_rpc_conserva_estado_y_id():
    data = {'request_id': 'abc', 'cancelada_antes_de_ejecutar': True}
    wire = json.dumps({'error': {'code': -32000, 'message': 'cancelada', 'data': data}}).encode() + b'\n'
    conn = MagicMock()
    conn.__enter__.return_value.recv.return_value = wire
    with patch.object(socket, 'create_connection', return_value=conn):
        with pytest.raises(puente_cliente.PuenteError) as exc:
            puente_cliente.llamar('gm.reparar')
    assert exc.value.codigo == -32000
    assert exc.value.datos == data


def test_timeout_transporte_no_promete_cancelacion_ni_reintenta():
    with patch.object(socket, 'create_connection', side_effect=socket.timeout) as connect:
        with pytest.raises(puente_cliente.PuenteError, match='Resultado incierto'):
            puente_cliente.llamar('cmd.run')
    assert connect.call_count == 1


def ping():
    return {'version': '0.5.6', 'comandos': True, 'escritura': True, 'timeout_ms': 5000}


def test_humo_rechaza_dibujo_ajeno(tmp_path):
    drawing = str(tmp_path / 'CDCRD_BRIDGE_SMOKE.dwg')
    with pytest.raises(RuntimeError, match='exacto'):
        humo.preflight(drawing, {'dibujo': str(tmp_path / 'Proyecto.dwg')}, ping())


def test_humo_rechaza_nombre_no_sintetico(tmp_path):
    drawing = str(tmp_path / 'Proyecto.dwg')
    with pytest.raises(RuntimeError, match='sintetico'):
        humo.preflight(drawing, {'dibujo': drawing}, ping())


def test_humo_rechaza_build_viejo(tmp_path):
    drawing = str(tmp_path / 'CDCRD_BRIDGE_SMOKE.dwg')
    with pytest.raises(RuntimeError, match='0.5.6'):
        humo.preflight(drawing, {'dibujo': drawing}, {**ping(), 'version': '0.5.5'})


def test_humo_rechaza_sobrescribir_evidencia(tmp_path):
    (tmp_path / 'receipt.json').write_text('{}')
    with patch.object(puente_cliente, 'llamar') as request:
        with pytest.raises(RuntimeError, match='vacia'):
            humo.run('CDCRD_BRIDGE_SMOKE.dwg', tmp_path)
        request.assert_not_called()


def test_servidor_mcp_conserva_detalle_timeout():
    import server
    data = {'request_id': 'abc', 'resultado_incierto': True}
    response = json.loads(server._error(server.puente.PuenteError(-32000, 'ocupado', data)))
    assert response == {'error': 'ocupado', 'codigo': -32000, 'datos': data}
