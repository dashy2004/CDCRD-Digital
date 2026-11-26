import json
import os
import subprocess
import sys
import threading
import types

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'src'))

import tekla as modulo  # noqa: E402
from tekla import ErrorTekla, Tekla  # noqa: E402
from test_tekla import PERMITIDA, PuenteFalso, crear  # noqa: E402


# ---------- cortes ----------
def test_ajuste_y_corte_envian_el_plano_como_numeros():
    puente = PuenteFalso()
    t = crear(puente)
    t.tekla_ajustar_extremo(7, (0, 10, 0), [1, 0, 0], [0, 0, 1])
    t.tekla_cortar_plano(7, [0, 2500, 0], [0, 0, 1], [1, 0, 0])
    ajuste, corte = puente.comandos[1], puente.comandos[3]
    assert ajuste == {'op': 'ajustar_extremo', 'pieza': 7, 'origen': [0.0, 10.0, 0.0],
                      'eje_x': [1.0, 0.0, 0.0], 'eje_y': [0.0, 0.0, 1.0]}
    assert corte['op'] == 'cortar_plano' and corte['origen'] == [0.0, 2500.0, 0.0]


def test_despunte_rechaza_una_caja_sin_volumen_sin_llamar_al_puente():
    puente = PuenteFalso()
    with pytest.raises(ValueError, match='maximo > minimo'):
        crear(puente).tekla_despuntar(7, [0, 0, 0], [100, 0, 50])
    assert puente.comandos == []


def test_despunte_valido_envia_la_caja():
    puente = PuenteFalso()
    crear(puente).tekla_despuntar(7, [0, 0, 0], [100, 80, 50])
    assert puente.comandos[-1] == {'op': 'despuntar', 'pieza': 7, 'min': [0.0, 0.0, 0.0], 'max': [100.0, 80.0, 50.0]}


def test_cortar_con_pieza_rechaza_la_misma_pieza():
    with pytest.raises(ValueError, match='distinta'):
        crear(PuenteFalso()).tekla_cortar_con_pieza(5, 5)


def test_cortar_con_pieza_envia_los_dos_ids():
    puente = PuenteFalso()
    crear(puente).tekla_cortar_con_pieza(5, 6)
    assert puente.comandos[-1] == {'op': 'cortar_con_pieza', 'pieza': 5, 'pieza_cortante': 6}


# ---------- componentes ----------
def test_componente_exige_secundarias_y_envia_atributos():
    puente = PuenteFalso()
    t = crear(puente)
    with pytest.raises(ValueError, match='secundaria'):
        t.tekla_crear_componente(146, 1, [])
    t.tekla_crear_componente(146, 1, [2, 3], atributos={'tpl1': 9.5}, vector_arriba=[0, 0, 1])
    c = puente.comandos[-1]
    assert c['numero'] == 146 and c['piezas_secundarias'] == [2, 3]
    assert c['atributos'] == {'tpl1': 9.5} and c['vector_arriba'] == [0.0, 0.0, 1.0]
    assert c['archivo_atributos'] == 'standard'


def test_detalle_envia_punto_y_omite_vector_si_no_se_indica():
    puente = PuenteFalso()
    crear(puente).tekla_crear_detalle(1004, 9, [0, 3000, 0])
    c = puente.comandos[-1]
    assert c['op'] == 'detalle' and c['punto'] == [0.0, 3000.0, 0.0] and 'vector_arriba' not in c
    assert c['atributos'] == {} and c['tipo_detalle'] == 'END'


def test_detalle_con_vector_arriba():
    puente = PuenteFalso()
    crear(puente).tekla_crear_detalle(1004, 9, [0, 0, 0], vector_arriba=[1, 0, 0])
    assert puente.comandos[-1]['vector_arriba'] == [1.0, 0.0, 0.0]


@pytest.mark.parametrize('llamada, op', [
    (lambda t: t.tekla_catalogo_componentes('plate'), 'catalogo_componentes'),
    (lambda t: t.tekla_normas_tornillos(), 'normas_tornillos'),
    (lambda t: t.tekla_listar_planos(), 'planos'),
    (lambda t: t.tekla_estado(), 'estado'),
    (lambda t: t.tekla_seleccionar([1, 2]), 'seleccionar'),
    (lambda t: t.tekla_ajustar_vista([0, 0, 0], [1, 1, 1], ajustar_area=False), 'vista'),
    (lambda t: t.tekla_abrir_modelo(PERMITIDA + r'\demo'), 'abrir_modelo'),
])
def test_las_lecturas_no_comprueban_la_carpeta(llamada, op):
    puente = PuenteFalso(ruta_modelo=r'C:\proyectos\cliente\modelo')
    llamada(crear(puente))
    assert puente.ops() == [op]


@pytest.mark.parametrize('llamada', [
    lambda t: t.tekla_numerar(),
    lambda t: t.tekla_crear_plano(4),
    lambda t: t.tekla_despuntar(1, [0, 0, 0], [1, 1, 1]),
    lambda t: t.tekla_crear_componente(146, 1, [2]),
    lambda t: t.tekla_crear_detalle(1004, 1, [0, 0, 0]),
    lambda t: t.tekla_crear_soldadura(1, 2, 5),
    lambda t: t.tekla_crear_informe([1], 'P_Part_List', 'x.xsr'),
    lambda t: t.tekla_definir_ejes('0 1', '0 1', '0'),
    lambda t: t.tekla_borrar([1]),
])
def test_toda_escritura_se_rechaza_en_un_modelo_de_proyecto(llamada):
    puente = PuenteFalso(ruta_modelo=r'C:\proyectos\cliente\modelo')
    with pytest.raises(ErrorTekla, match='fuera de las carpetas permitidas'):
        llamada(crear(puente))
    assert puente.ops() == ['estado']


def test_plano_valida_el_tipo_y_envia_la_pieza():
    puente = PuenteFalso()
    t = crear(puente)
    with pytest.raises(ValueError, match="'pieza' o 'conjunto'"):
        t.tekla_crear_plano(4, 'general')
    t.tekla_crear_plano(4, 'conjunto')
    assert puente.comandos[-1] == {'op': 'crear_plano', 'pieza': 4, 'tipo': 'conjunto', 'archivo_atributos': 'standard'}


def test_ejes_con_origen_soldadura_doble_e_informe():
    puente = PuenteFalso()
    t = crear(puente)
    t.tekla_definir_ejes('0 1', '0 1', '0', origen=[1, 2, 3])
    assert puente.comandos[-1]['origen'] == [1.0, 2.0, 3.0]
    t.tekla_crear_soldadura(1, 2, 5, tamano_inferior=4)
    assert puente.comandos[-1]['tamano_inferior'] == 4.0
    t.tekla_crear_placa([[0, 0, 0], [1, 0, 0], [1, 1, 0]], 'PL10', 'A36')
    assert len(puente.comandos[-1]['contorno']) == 3
    with pytest.raises(ValueError, match='vacía'):
        t.tekla_crear_piezas([])


def test_estado_con_error_al_comprobar_la_ruta():
    def puente(exe, comando):
        return {'ok': False, 'error': 'Tekla Structures no está abierto'}
    with pytest.raises(ErrorTekla, match='no está abierto'):
        Tekla('x.exe', [PERMITIDA], ejecutar=puente).tekla_guardar()


# ---------- catálogos ----------
def test_copiar_catalogos_copia_los_que_existen_y_reabre(tmp_path):
    origen, modelo = tmp_path / 'entorno', tmp_path / 'modelo'
    origen.mkdir(); modelo.mkdir()
    (origen / 'screwdb.db').write_text('tornillos')
    (origen / 'otro.txt').write_text('no se copia')
    puente = PuenteFalso(ruta_modelo=str(modelo))
    r = Tekla('x.exe', [str(tmp_path)], ejecutar=puente).tekla_copiar_catalogos(str(origen))
    assert r['copiados'] == ['screwdb.db'] and (modelo / 'screwdb.db').read_text() == 'tornillos'
    assert not (modelo / 'otro.txt').exists()
    assert puente.ops()[-1] == 'abrir_modelo'


def test_copiar_catalogos_rechaza_carpeta_inexistente_o_sin_catalogos(tmp_path):
    t = Tekla('x.exe', [str(tmp_path)], ejecutar=PuenteFalso(ruta_modelo=str(tmp_path)))
    with pytest.raises(ValueError, match='No existe'):
        t.tekla_copiar_catalogos(str(tmp_path / 'nada'))
    vacia = tmp_path / 'vacia'
    vacia.mkdir()
    with pytest.raises(ValueError, match='no hay ninguno'):
        t.tekla_copiar_catalogos(str(vacia))


def test_copiar_catalogos_no_escribe_en_un_modelo_de_proyecto(tmp_path):
    origen = tmp_path / 'entorno'
    origen.mkdir()
    (origen / 'screwdb.db').write_text('x')
    proyecto = tmp_path / 'proyecto'
    proyecto.mkdir()
    t = Tekla('x.exe', [str(tmp_path / 'permitida')], ejecutar=PuenteFalso(ruta_modelo=str(proyecto)))
    with pytest.raises(ErrorTekla, match='fuera de las carpetas permitidas'):
        t.tekla_copiar_catalogos(str(origen))
    assert not (proyecto / 'screwdb.db').exists()


# ---------- modelo nuevo y diálogo de licencia ----------
def test_crear_modelo_crea_la_carpeta_y_llama_al_puente(tmp_path):
    puente = PuenteFalso()
    carpeta = tmp_path / 'nuevos'
    Tekla('x.exe', [str(tmp_path)], ejecutar=puente).tekla_crear_modelo(str(carpeta), 'm1')
    assert carpeta.is_dir() and puente.ops() == ['crear_modelo']


def test_crear_modelo_acepta_solo_el_aviso_de_licencia_educativa(tmp_path, monkeypatch):
    pulsados, respondido = [], threading.Event()

    def pulsar(ventana, boton):
        pulsados.append((ventana, boton))
        respondido.set()
        return True
    falso = types.SimpleNamespace(
        dialogos=lambda: [
            {'ventana': 1, 'texto': 'You are using an educational license. Save?', 'botones': ['Yes', 'No']},
            {'ventana': 2, 'texto': 'Delete everything?', 'botones': ['Yes', 'No']},
        ],
        pulsar_boton=pulsar)
    monkeypatch.setitem(sys.modules, 'captura', falso)
    monkeypatch.setattr(modulo.time, 'sleep', lambda s: None)

    def puente(exe, comando):
        respondido.wait(10)      # como Tekla: no vuelve hasta que alguien responde el diálogo
        return {'ok': True, 'datos': {'creado': True}}

    r = Tekla('x.exe', [str(tmp_path)], ejecutar=puente).tekla_crear_modelo(str(tmp_path), 'm2', True)
    assert r == {'creado': True}
    assert pulsados and all(p == (1, 'Yes') for p in pulsados)


# ---------- puente real (proceso) ----------
def proceso_falso(salida=b'', error=b''):
    return lambda *a, **k: subprocess.CompletedProcess(a, 0, stdout=salida, stderr=error)


def test_puente_ausente_dice_como_compilarlo(tmp_path):
    with pytest.raises(ErrorTekla, match='compilar.ps1'):
        modulo._ejecutar_puente(str(tmp_path / 'no.exe'), {'op': 'estado'})


def test_puente_devuelve_el_json_del_proceso(tmp_path, monkeypatch):
    exe = tmp_path / 'p.exe'
    exe.write_bytes(b'')
    monkeypatch.setattr(modulo.subprocess, 'run', proceso_falso(json.dumps({'ok': True, 'datos': 'ñ'}).encode('utf-8')))
    assert modulo._ejecutar_puente(str(exe), {'op': 'estado'}) == {'ok': True, 'datos': 'ñ'}


def test_puente_sin_salida_o_con_salida_no_json(tmp_path, monkeypatch):
    exe = tmp_path / 'p.exe'
    exe.write_bytes(b'')
    monkeypatch.setattr(modulo.subprocess, 'run', proceso_falso(b'', b'fallo de carga'))
    with pytest.raises(ErrorTekla, match='fallo de carga'):
        modulo._ejecutar_puente(str(exe), {'op': 'estado'})
    monkeypatch.setattr(modulo.subprocess, 'run', proceso_falso(b'no es json'))
    with pytest.raises(ErrorTekla, match='no válida'):
        modulo._ejecutar_puente(str(exe), {'op': 'estado'})


def test_tiempo_agotado_informa_del_dialogo_abierto(tmp_path, monkeypatch):
    exe = tmp_path / 'p.exe'
    exe.write_bytes(b'')

    def agotar(*a, **k):
        raise subprocess.TimeoutExpired('p.exe', 1)
    monkeypatch.setattr(modulo.subprocess, 'run', agotar)
    monkeypatch.setitem(sys.modules, 'captura', types.SimpleNamespace(
        dialogos=lambda: [{'ventana': 1, 'texto': 'Save changes?', 'botones': ['Yes', 'No']}]))
    with pytest.raises(ErrorTekla, match=r'«Save changes\?» \[Yes, No\]'):
        modulo._ejecutar_puente(str(exe), {'op': 'guardar'})


def test_aviso_de_dialogos_sin_dialogo_y_con_fallo_de_deteccion(monkeypatch):
    monkeypatch.setitem(sys.modules, 'captura', types.SimpleNamespace(dialogos=lambda: []))
    assert 'ningún diálogo' in modulo._aviso_dialogos()

    def romper():
        raise RuntimeError('sin ventana')
    monkeypatch.setitem(sys.modules, 'captura', types.SimpleNamespace(dialogos=romper))
    assert 'No se pudo comprobar' in modulo._aviso_dialogos()


# ---------- archivos de salida ----------
def test_informe_relativo_va_a_la_carpeta_del_modelo_y_absoluto_fuera_se_rechaza():
    puente = PuenteFalso()
    t = crear(puente)
    assert t.tekla_crear_informe([1], 'P_Part_List', 'lista.xsr') is True
    assert puente.comandos[-1]['archivo'] == 'lista.xsr'
    with pytest.raises(ErrorTekla, match='fuera de las carpetas permitidas'):
        t.tekla_crear_informe([1], 'P_Part_List', r'C:\Users\Public\x.bat')
    with pytest.raises(ErrorTekla, match='fuera de las carpetas permitidas'):
        t.tekla_crear_informe([1], 'P_Part_List', r'..\..\..\fuera.xsr')
    assert puente.ops().count('informe') == 1


def test_una_ruta_permitida_vacia_no_permite_nada():
    assert not modulo._dentro_de(os.getcwd(), ['', '  '])


def test_fallo_al_mirar_dialogos_no_tapa_el_resultado_del_puente(tmp_path, monkeypatch):
    listo = threading.Event()

    def romper():
        listo.set()
        raise RuntimeError('sin ventana de Tekla')
    monkeypatch.setitem(sys.modules, 'captura', types.SimpleNamespace(dialogos=romper))
    monkeypatch.setattr(modulo.time, 'sleep', lambda s: None)

    def puente(exe, comando):
        listo.wait(10)
        return {'ok': True, 'datos': {'creado': True}}
    r = Tekla('x.exe', [str(tmp_path)], ejecutar=puente).tekla_crear_modelo(str(tmp_path), 'm3', True)
    assert r == {'creado': True}
