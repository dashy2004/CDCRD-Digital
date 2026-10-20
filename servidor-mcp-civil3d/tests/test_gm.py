"""MCP contract: explicit geology selection without bypassing write confirmation."""
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import gm


def tools():
    registered, calls = {}, []

    class Mcp:
        def tool(self):
            def register(fn):
                registered[fn.__name__] = fn
                return fn
            return register

    gm.registrar(Mcp(), lambda *a, **kw: calls.append((a, kw)) or '{}', json.dumps)
    return registered, calls


def test_campo_explicito_y_escritura_confirmada():
    registered, calls = tools()
    fn = registered['gm_crear_perfil_sondeos']
    fn('B', campo_geologia='GeologyCode1')
    assert not calls
    fn('B', campo_geologia='GeologyCode1', confirmar=True)
    args, kwargs = calls[0]
    assert args[1]['campo_geologia'] == 'GeologyCode1'
    assert args[1]['solo_perfil'] is False
    assert args[1]['hatch_geologia'] is False
    assert kwargs['escribe'] is True


def test_campo_vacio_delega_a_configuracion_guardada():
    registered, calls = tools()
    registered['gm_crear_perfil_sondeos']('B', confirmar=True)
    assert 'campo_geologia' not in calls[0][0][1]


def test_estilos_optativos_se_transmiten_solo_con_confirmacion():
    registered, calls = tools()
    fn = registered['gm_crear_perfil_sondeos']
    fn('B', hatch_geologia=True)
    assert not calls
    fn('B', hatch_geologia=True, confirmar=True)
    assert calls[0][0][1]['hatch_geologia'] is True


def test_superficies_simulacion_y_fondo_exigen_confirmacion():
    registered, calls = tools()
    fn = registered['gm_construir_superficies']
    fn(superficie_fondo=True, campo_geologia='GeologyCode1', simular=True)
    assert not calls
    fn(superficie_fondo=True, campo_geologia='GeologyCode1', simular=True, confirmar=True)
    args, kwargs = calls[0]
    assert args == ('gm.superficies', {'superficie_fondo': True,
                                     'campo_geologia': 'GeologyCode1', 'simular': True})
    assert kwargs['escribe'] is True


def test_superficies_campo_vacio_reutiliza_seleccion_guardada():
    registered, calls = tools()
    registered['gm_construir_superficies'](confirmar=True)
    assert calls[0][0][1] == {'superficie_fondo': False, 'simular': False}
