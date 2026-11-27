# -*- coding: utf-8 -*-
"""Las herramientas MCP solo arman el cuerpo y llaman al endpoint."""
import importlib.util
import pathlib

import pytest

pytest.importorskip("mcp")

RUTA = pathlib.Path(__file__).resolve().parents[1] / "src" / "server.py"


@pytest.fixture()
def servidor(monkeypatch):
    spec = importlib.util.spec_from_file_location("servidor_revit_write", RUTA)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    llamadas = []
    monkeypatch.setattr(modulo, "_go", lambda ruta, metodo="GET", payload=None:
                        llamadas.append((ruta, metodo, payload)) or {"ok": True})
    modulo.llamadas = llamadas
    return modulo


def test_conectar_es_ensayo_por_defecto_y_no_envia_nulos(servidor):
    servidor.revit_mep_conectar(tipo_tuberia=200, tipo_sistema="Sanitario",
                                pendiente=0.02, ramal=100,
                                categoria="OST_Sprinklers")
    ruta, metodo, cuerpo = servidor.llamadas[0]
    assert (ruta, metodo) == ("/mep/conectar", "POST")
    assert cuerpo["confirmar"] is False and cuerpo["lote"] == 25
    assert "ramales" not in cuerpo and "documento" not in cuerpo


def test_circuitos_exige_limite_y_conectores_es_post(servidor):
    with pytest.raises(TypeError):
        servidor.revit_mep_circuitos(tablero=700)
    servidor.revit_mep_circuitos(tablero="TA", limite_va=1500.0, confirmar=True)
    servidor.revit_mep_conectores(ids=[1], documento="otro")
    assert servidor.llamadas[0][2] == {
        "tablero": "TA", "limite_va": 1500.0, "lote": 25, "desde": 0,
        "confirmar": True}
    assert servidor.llamadas[1] == ("/mep/conectores", "POST",
                                    {"ids": [1], "documento": "otro"})

def test_tablero_sin_sistema_es_lectura_y_no_envia_nulos(servidor):
    servidor.revit_mep_tablero(tablero="TA")
    servidor.revit_mep_tablero(tablero=700, sistema="120/208 Wye", confirmar=True)
    assert servidor.llamadas[0] == ("/mep/tablero", "POST",
                                    {"tablero": "TA", "confirmar": False})
    assert servidor.llamadas[1][2] == {"tablero": 700, "sistema": "120/208 Wye",
                                       "confirmar": True}
