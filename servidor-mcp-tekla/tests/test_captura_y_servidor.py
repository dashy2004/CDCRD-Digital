import asyncio
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import captura  # noqa: E402

PRINCIPAL, DIALOGO, OTRA = 100, 200, 300
BOTON_SI, BOTON_NO, TEXTO = 201, 202, 203


class Win32Falso:
    """Escritorio mínimo: ventana principal de Tekla, un diálogo suyo y una ventana ajena."""

    def __init__(self):
        self.ventanas = {
            PRINCIPAL: ('Tekla Structures - modelo', (0, 0, 2000, 1000)),
            DIALOGO: ('Tekla Structures', (500, 300, 900, 500)),
            OTRA: ('Bloc de notas', (0, 0, 3000, 3000)),
        }
        self.hijos = {DIALOGO: [(BOTON_SI, 'Button', '&Yes'), (BOTON_NO, 'Button', '&No'), (TEXTO, 'Static', ' Save the model? ')]}
        self.pulsados = []
        self.al_frente = []
        self.minimizada = False
        self.cierra_al_pulsar = True

    def EnumWindows(self, visitar, extra):
        for h in list(self.ventanas):
            visitar(h, extra)

    def EnumChildWindows(self, h, visitar, extra):
        for hijo, _, _ in self.hijos.get(h, []):
            visitar(hijo, extra)

    def _hijo(self, c):
        return next(x for lista in self.hijos.values() for x in lista if x[0] == c)

    def IsWindowVisible(self, h):
        return True

    def IsWindow(self, h):
        return h in self.ventanas

    def IsIconic(self, h):
        return self.minimizada

    def ShowWindow(self, h, modo):
        self.minimizada = False

    def SetForegroundWindow(self, h):
        self.al_frente.append(h)

    def GetWindowText(self, h):
        return self.ventanas[h][0] if h in self.ventanas else self._hijo(h)[2]

    def GetWindowRect(self, h):
        return self.ventanas[h][1]

    def GetClassName(self, c):
        return self._hijo(c)[1]

    def PostMessage(self, c, mensaje, a, b):
        self.pulsados.append(c)
        if self.cierra_al_pulsar:
            self.ventanas.pop(DIALOGO, None)


@pytest.fixture
def escritorio(monkeypatch):
    falso = Win32Falso()
    monkeypatch.setitem(sys.modules, 'win32gui', falso)
    monkeypatch.setitem(sys.modules, 'win32con', types.SimpleNamespace(SW_RESTORE=9, BM_CLICK=0xF5))
    monkeypatch.setattr(captura.time, 'sleep', lambda s: None)
    return falso


def test_dialogos_lista_solo_los_de_tekla_con_texto_y_botones(escritorio):
    assert captura.dialogos() == [{'ventana': DIALOGO, 'titulo': 'Tekla Structures',
                                   'texto': 'Save the model?', 'botones': ['Yes', 'No']}]


def test_sin_ventana_de_tekla_se_explica(escritorio):
    with pytest.raises(RuntimeError, match='ETABS'):
        captura.dialogos('ETABS')


def test_pulsar_boton_pulsa_el_pedido_y_dice_si_se_cerro(escritorio):
    assert captura.pulsar_boton(DIALOGO, 'no') is True
    assert escritorio.pulsados == [BOTON_NO]


def test_pulsar_boton_inexistente_o_dialogo_que_sigue_abierto(escritorio):
    with pytest.raises(ValueError, match="'Cancel'"):
        captura.pulsar_boton(DIALOGO, 'Cancel')
    escritorio.cierra_al_pulsar = False
    assert captura.pulsar_boton(DIALOGO, 'Yes') is False


def test_capturar_guarda_la_region_de_la_ventana_principal(escritorio, monkeypatch, tmp_path):
    pedidos = []

    class Imagen:
        width, height = 1000, 500

        def save(self, archivo):
            open(archivo, 'wb').write(b'png')

    def grab(bbox, all_screens):
        pedidos.append(bbox)
        return Imagen()
    monkeypatch.setitem(sys.modules, 'PIL', types.SimpleNamespace(ImageGrab=types.SimpleNamespace(grab=grab)))
    escritorio.minimizada = True
    destino = tmp_path / 'sub' / 'vista.png'
    r = captura.capturar(str(destino), fraccion=[0.5, 0.0, 1.0, 0.5])
    assert pedidos == [(1000, 0, 2000, 500)] and destino.read_bytes() == b'png'
    assert r['ancho'] == 1000 and escritorio.al_frente == [PRINCIPAL] and not escritorio.minimizada
    with pytest.raises(ValueError, match='.png'):
        captura.capturar(str(tmp_path / 'vista.jpg'))


def test_el_servidor_registra_todas_las_herramientas(monkeypatch, tmp_path):
    pytest.importorskip('mcp')
    import server
    nombres = {h.name for h in asyncio.run(server.mcp.list_tools())}
    esperadas = {n for n in dir(server.tekla) if n.startswith('tekla_')} | {'capturar_ventana', 'tekla_dialogos', 'tekla_responder_dialogo'}
    assert nombres == esperadas
    assert '"rutas_permitidas"' in server.get_config()
    monkeypatch.setattr(server.captura, 'capturar', lambda *a: {'args': a})
    monkeypatch.setattr(server.captura, 'dialogos', lambda: ['d'])
    monkeypatch.setattr(server.captura, 'pulsar_boton', lambda v, b: (v, b))
    dentro = os.path.expandvars(r'%TEMP%\tekla-mcp-pruebas\a.png')
    assert server.capturar_ventana(dentro)['args'] == (dentro, 'Tekla Structures', 'completa', None)
    with pytest.raises(server.ErrorTekla, match='fuera de las carpetas permitidas'):
        server.capturar_ventana(r'C:\Windows\a.png')
    assert server.tekla_dialogos() == ['d'] and server.tekla_responder_dialogo(5, 'Yes') == (5, 'Yes')


def test_pulsar_boton_rechaza_una_ventana_que_no_es_un_dialogo_de_tekla(escritorio):
    with pytest.raises(ValueError, match='no es un diálogo abierto'):
        captura.pulsar_boton(OTRA, 'Yes')
    assert escritorio.pulsados == []
