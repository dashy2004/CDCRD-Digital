import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import captura  # noqa: E402
from config import Config  # noqa: E402
from tekla import ErrorTekla, Tekla, _dentro_de  # noqa: E402

PERMITIDA = r'C:\modelos\pruebas'


class PuenteFalso:
    def __init__(self, ruta_modelo=PERMITIDA + r'\demo', respuestas=None):
        self.ruta = ruta_modelo
        self.comandos = []
        self.respuestas = respuestas or {}

    def __call__(self, exe, comando):
        self.comandos.append(comando)
        if comando['op'] == 'estado':
            return {'ok': True, 'datos': {'ruta': self.ruta, 'modelo': 'demo.db1', 'piezas': 0}}
        return self.respuestas.get(comando['op'], {'ok': True, 'datos': True})

    def ops(self):
        return [c['op'] for c in self.comandos]


def crear(puente):
    return Tekla('TeklaPuente.exe', [PERMITIDA], ejecutar=puente)


def test_lectura_no_consulta_la_ruta_del_modelo():
    puente = PuenteFalso()
    crear(puente).tekla_listar_piezas('Viga')
    assert puente.ops() == ['listar']
    assert puente.comandos[0]['nombre'] == 'Viga'


def test_escritura_se_rechaza_fuera_de_las_rutas_permitidas():
    puente = PuenteFalso(ruta_modelo=r'C:\proyectos\cliente\modelo')
    with pytest.raises(ErrorTekla, match='fuera de las carpetas permitidas'):
        crear(puente).tekla_guardar()
    assert puente.ops() == ['estado']


def test_escritura_pasa_dentro_de_una_ruta_permitida():
    puente = PuenteFalso()
    assert crear(puente).tekla_guardar('prueba') is True
    assert puente.ops() == ['estado', 'guardar']
    assert puente.comandos[1]['comentario'] == 'prueba'


def test_carpeta_hermana_con_prefijo_comun_no_cuenta_como_permitida():
    assert _dentro_de(PERMITIDA + r'\demo', [PERMITIDA])
    assert not _dentro_de(PERMITIDA + r'-otra\demo', [PERMITIDA])


def test_crear_modelo_rechaza_carpeta_no_permitida_sin_llamar_al_puente():
    puente = PuenteFalso()
    with pytest.raises(ErrorTekla):
        crear(puente).tekla_crear_modelo(r'C:\otra', 'x')
    assert puente.comandos == []


def test_error_del_puente_se_propaga_con_su_mensaje():
    puente = PuenteFalso(respuestas={'listar': {'ok': False, 'error': 'ArgumentException: sin modelo'}})
    with pytest.raises(ErrorTekla, match='sin modelo'):
        crear(puente).tekla_listar_piezas()


def test_crear_piezas_valida_campos_y_normaliza_puntos():
    puente = PuenteFalso()
    t = crear(puente)
    with pytest.raises(ValueError, match="falta 'perfil'"):
        t.tekla_crear_piezas([{'material': 'A992', 'inicio': [0, 0, 0], 'fin': [1, 0, 0]}])
    with pytest.raises(ValueError, match=r'\[x, y, z\]'):
        t.tekla_crear_piezas([{'perfil': 'W21X44', 'material': 'A992', 'inicio': [0, 0], 'fin': [1, 0, 0]}])
    t.tekla_crear_piezas([{'perfil': 'W21X44', 'material': 'A992', 'inicio': (0, 0, 0), 'fin': [10000, 0, 200]}])
    enviado = puente.comandos[-1]['piezas'][0]
    assert enviado['inicio'] == [0.0, 0.0, 0.0] and enviado['fin'] == [10000.0, 0.0, 200.0]


def test_placa_exige_tres_puntos_y_borrar_exige_ids():
    t = crear(PuenteFalso())
    with pytest.raises(ValueError):
        t.tekla_crear_placa([[0, 0, 0], [1, 0, 0]], 'PL6.35', 'A36')
    with pytest.raises(ValueError):
        t.tekla_borrar([])


def test_tornillos_envia_separaciones_como_numeros():
    puente = PuenteFalso()
    crear(puente).tekla_crear_tornillos(10, 20, [0, 0, 0], [0, 0, 200], 'A325N', 15.875, [76.2, 76.2], [0])
    c = puente.comandos[-1]
    assert c['op'] == 'crear_tornillos' and c['separaciones_x'] == [76.2, 76.2] and c['pieza_principal'] == 10


def test_recorte_por_region_y_por_fraccion():
    caja = (0, 0, 2000, 1000)
    assert captura.recorte_de(caja, 'completa') == caja
    assert captura.recorte_de(caja, 'x', (0.5, 0.0, 1.0, 0.5)) == (1000, 0, 2000, 500)
    with pytest.raises(ValueError):
        captura.recorte_de(caja, 'inexistente')
    with pytest.raises(ValueError):
        captura.recorte_de(caja, 'x', (0.6, 0.0, 0.5, 1.0))


def test_config_usa_valores_por_defecto_y_suma_la_variable_de_entorno(tmp_path, monkeypatch):
    monkeypatch.setenv('TEKLA_MCP_RUTAS', r'D:\uno;D:\dos')
    c = Config(str(tmp_path / 'no-existe.json'))
    assert c.serverName == 'Tekla MCP'
    assert c.rutasPermitidas[-2:] == [r'D:\uno', r'D:\dos']
    assert c.exePuente.endswith(os.path.join('puente', 'TeklaPuente.exe'))
