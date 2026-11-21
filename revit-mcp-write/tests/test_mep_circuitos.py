# -*- coding: utf-8 -*-
"""crear_circuitos con dobles de la API. Nada de esto corre en Revit."""
import json

import pytest

from dobles import Luminaria, Tablero, modelo_electrico
from mep import ErrorEntrada, crear_circuitos
from mep.circuitos import agrupar, incompatibilidad


def correr(doc, db, **extra):
    opciones = {"tablero": 700, "limite_va": 200.0}
    opciones.update(extra)
    resultado = crear_circuitos(db, doc, opciones)
    json.dumps(resultado)
    return resultado


def luminarias(n, **kw):
    return [Luminaria(2001 + i, **kw) for i in range(n)]


def motivos(resultado):
    return dict((f["id"], f["motivo"]) for f in resultado["sin_circuito"])


# ------------------------------------------------------------ validacion

@pytest.mark.parametrize("cambio, fragmento", [
    ({"limite_va": None}, "limite_va"),
    ({"limite_va": 0}, "limite_va"),
    ({"limite_va": "1500"}, "limite_va"),
    ({"tablero": None}, "tablero"),
    ({"tablero": 4242}, "no existe"),
    ({"tablero": "TX"}, "0 equipos"),
    ({"max_luminarias": 0}, "max_luminarias"),
    ({"luminarias": [2001, 4242]}, "inexistentes"),
    ({"categoria": "OST_Walls"}, "categoria"),
    ({"nivel": "Nivel inexistente"}, "nivel"),
    ({"confirmar": 1}, "confirmar"),
    ({"lote": 500}, "lote"),
    ({"otra": 1}, "desconocidas"),
])
def test_entrada_invalida_falla_antes_de_abrir_transaccion(cambio, fragmento):
    doc, db = modelo_electrico(luminarias(2))
    opciones = {"tablero": 700, "limite_va": 200.0}
    opciones.update(cambio)
    opciones = dict((k, v) for k, v in opciones.items() if v is not None)
    with pytest.raises(ErrorEntrada) as error:
        crear_circuitos(db, doc, opciones)
    assert fragmento in str(error.value)
    assert doc.bitacora == []


def test_tablero_sin_sistema_de_distribucion_se_rechaza():
    doc, db = modelo_electrico(luminarias(1),
                               Tablero(700, con_distribucion=False))
    with pytest.raises(ErrorEntrada) as error:
        correr(doc, db)
    assert "sistema de distribucion" in str(error.value)


def test_tablero_por_nombre_y_nombre_repetido():
    doc, db = modelo_electrico(luminarias(1))
    assert correr(doc, db, tablero="TA")["tablero"] == 700
    doc.elementos[701] = Tablero(701, "TA")
    with pytest.raises(ErrorEntrada) as error:
        correr(doc, db, tablero="TA")
    assert "2 equipos" in str(error.value)


# ------------------------------------------------------------ agrupacion

def test_agrupa_respetando_el_limite_de_va():
    doc, db = modelo_electrico(luminarias(7, carga_va=60.0))
    r = correr(doc, db, limite_va=200.0, confirmar=True)
    assert [len(c["elementos"]) for c in r["circuitos"]] == [3, 3, 1]
    assert [c["carga_va"] for c in r["circuitos"]] == [180.0, 180.0, 60.0]
    assert all(c["dentro_del_limite"] and c["tablero"] == "TA"
               for c in r["circuitos"])
    assert [c["numero"] for c in r["circuitos"]] == ["1", "2", "3"]
    assert r["sin_circuito"] == [] and r["circuitos_planeados"] == 3
    assert doc.bitacora.count("SelectPanel") == 3


def test_maximo_de_luminarias_por_circuito():
    doc, db = modelo_electrico(luminarias(5, carga_va=10.0))
    r = correr(doc, db, max_luminarias=2)
    assert [len(c["elementos"]) for c in r["circuitos"]] == [2, 2, 1]


def test_luminaria_sin_carga_queda_fuera_con_motivo():
    lote = luminarias(3)
    lote[1] = Luminaria(2002, carga_va=None)
    doc, db = modelo_electrico(lote)
    r = correr(doc, db, confirmar=True)
    assert motivos(r) == {2002: "sin_carga"}
    assert r["circuitos"][0]["elementos"] == [2001, 2003]
    assert r["circuitos"][0]["carga_va"] == 100.0


def test_las_que_no_caben_y_demas_motivos():
    lote = [Luminaria(2001, carga_va=500.0),            # sola supera el limite
            Luminaria(2002, en_circuito=True),
            Luminaria(2003, con_conector=False),
            Luminaria(2004, tension_v=277.0),           # fuera del tablero
            Luminaria(2005, polos=3, tension_v=240.0),  # tablero monofasico
            Luminaria(2006), Luminaria(2007), Luminaria(2008)]
    doc, db = modelo_electrico(lote)
    r = correr(doc, db, limite_va=100.0, max_circuitos=1, confirmar=True)
    assert motivos(r) == {
        2001: "excede_limite", 2002: "ya_en_circuito",
        2003: "sin_conector_electrico", 2004: "incompatible_con_tablero",
        2005: "incompatible_con_tablero", 2008: "supera_max_circuitos"}
    assert r["circuitos"][0]["elementos"] == [2006, 2007]


def test_tensiones_y_polos_distintos_no_comparten_circuito():
    lote = [Luminaria(2001), Luminaria(2002, polos=2, tension_v=240.0),
            Luminaria(2003)]
    doc, db = modelo_electrico(lote)
    r = correr(doc, db, limite_va=1000.0)
    assert sorted(c["elementos"] for c in r["circuitos"]) == [[2001, 2003], [2002]]


def test_filtro_por_nivel():
    lote = [Luminaria(2001, nivel=10), Luminaria(2002, nivel=11)]
    doc, db = modelo_electrico(lote)
    doc.elementos[11].Name = "Nivel 2"
    r = correr(doc, db, nivel="Nivel 2")
    assert r["luminarias_total"] == 1
    assert r["circuitos"][0]["elementos"] == [2002]


def test_agrupar_es_puro_y_conserva_el_orden():
    aptas = [{"id": i, "carga_va": 40.0, "polos": 1, "tension_v": 120.0}
             for i in (5, 3, 9)]
    grupos, fuera = agrupar(aptas, 80.0)
    assert [g["elementos"] for g in grupos] == [[5, 3], [9]] and fuera == []


def test_regla_de_compatibilidad_con_el_tablero():
    d = {"fase": "ThreePhase", "linea_linea_v": (200.0, 215.0),
         "linea_tierra_v": (110.0, 130.0)}
    assert incompatibilidad(d, 1, 120.0) is None
    assert incompatibilidad(d, 3, 208.0) is None
    assert "fuera del rango" in incompatibilidad(d, 1, 208.0)
    assert "no soportado" in incompatibilidad(d, 4, 208.0)


# ------------------------------------------------------- ensayo / commit

def test_ensayo_por_defecto_revierte():
    doc, db = modelo_electrico(luminarias(4))
    r = correr(doc, db)
    assert r["ensayo"] is True and r["confirmado"] is False
    assert "Committed" not in doc.bitacora and doc.bitacora[-1] == "RolledBack"
    assert doc.circuitos == [] and len(r["circuitos"]) == 1
    assert r["circuitos"][0]["carga_va"] == 200.0  # leido antes de revertir
    assert doc.bitacora.index("Regenerate") < doc.bitacora.index("RolledBack")


def test_confirmar_hace_commit_sin_guardar():
    doc, db = modelo_electrico(luminarias(4))
    r = correr(doc, db, confirmar=True)
    assert r["confirmado"] is True and doc.bitacora[-1] == "Committed"
    assert doc.bitacora[0] == "Start:MEP - crear circuitos de iluminacion"
    assert len(doc.circuitos) == 1 and "Save" not in doc.bitacora
    assert doc.circuitos[0].tipo_pedido == "PowerCircuit"


def test_create_none_y_panel_no_asignado_son_error_de_api():
    doc, db = modelo_electrico(luminarias(2))
    doc.devuelve_none.add("ElectricalSystem.Create")
    r = correr(doc, db, confirmar=True)
    assert r["circuitos"] == []
    assert motivos(r) == {2001: "error_api", 2002: "error_api"}
    assert "devolvio None" in r["sin_circuito"][0]["detalle"]

    doc, db = modelo_electrico(luminarias(2))
    doc.devuelve_none.add("SelectPanel")  # SelectPanel no asigna nada
    r = correr(doc, db, confirmar=True)
    assert r["circuitos"] == [] and doc.circuitos == []
    assert "no quedo asignado" in r["sin_circuito"][0]["detalle"]
    assert r["errores"][0]["etapa"] == "crear_circuito"


def test_lotes_y_desde():
    doc, db = modelo_electrico(luminarias(6, carga_va=100.0))
    ensayo = correr(doc, db, lote=2)
    assert len(ensayo["circuitos"]) == 2 and ensayo["siguiente"] == 2
    assert len(correr(doc, db, lote=2, desde=2)["circuitos"]) == 1
    r1 = correr(doc, db, lote=2, confirmar=True)
    assert len(r1["circuitos"]) == 2 and r1["circuitos_planeados"] == 3
    # al confirmar, el plan siguiente es el remanente: se continua desde 0
    assert r1["siguiente"] == 0
    r2 = correr(doc, db, lote=2, confirmar=True)
    assert len(r2["circuitos"]) == 1 and r2["siguiente"] is None
    assert r2["circuitos_planeados"] == 1
    ya = [f for f in r2["sin_circuito"] if f["motivo"] == "ya_en_circuito"]
    assert len(ya) == 4 and len(doc.circuitos) == 3


def test_desde_distinto_de_cero_se_rechaza_al_confirmar():
    doc, db = modelo_electrico(luminarias(6, carga_va=100.0))
    with pytest.raises(ErrorEntrada) as error:
        correr(doc, db, lote=2, desde=2, confirmar=True)
    assert "desde=0" in str(error.value) and doc.bitacora == []


def test_circuito_que_revit_calcula_sobre_el_limite_no_se_conserva():
    doc, db = modelo_electrico(luminarias(2, carga_va=100.0))
    doc.factor_carga_revit = 1.5  # Revit suma 300 VA donde los conectores dan 200
    r = correr(doc, db, confirmar=True)
    assert r["circuitos"] == [] and len(doc.circuitos) == 0
    assert motivos(r) == {2001: "error_api", 2002: "error_api"}
    assert "supera" in r["sin_circuito"][0]["detalle"]


def test_sin_luminarias_aptas_no_abre_transaccion():
    doc, db = modelo_electrico(luminarias(2, carga_va=None))
    r = correr(doc, db, confirmar=True)
    assert r["estado"] == "sin_transaccion" and doc.bitacora == []
    assert len(r["sin_circuito"]) == 2 and r["confirmado"] is False
