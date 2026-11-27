# -*- coding: utf-8 -*-
"""Sistema de distribucion del tablero: lectura, asignacion y creacion."""
import pytest

import dobles
from dobles import ElementId, Elemento, ns
from mep import ejecutar, tablero
from mep.base import ErrorEntrada

INVALIDO = "Selected distribution system type is invalid!"


class TipoTension(Elemento):
    def __init__(self, numero, nombre, real, minimo, maximo):
        Elemento.__init__(self, numero)
        self.Name, self.ActualValue = nombre, real
        self.MinValue, self.MaxValue = minimo, maximo


class Sistema(Elemento):
    def __init__(self, numero, nombre, fase, configuracion, hilos, ll, lg):
        Elemento.__init__(self, numero)
        self.Name, self.ElectricalPhase = nombre, fase
        self.ElectricalPhaseConfiguration, self.NumWires = configuracion, hilos
        self.VoltageLineToLine, self.VoltageLineToGround = ll, lg


class Ajustes(object):
    """ElectricalSetting falso: guarda lo que recibe, sin convertir, como Revit."""

    def __init__(self, doc):
        self.doc = doc
        v120 = doc.agregar(TipoTension(801, "120", 120.0, 110.0, 130.0))
        v208 = doc.agregar(TipoTension(802, "208", 208.0, 200.0, 220.0))
        v480 = doc.agregar(TipoTension(803, "480", 480.0, 460.0, 490.0))
        self.VoltageTypes = [v120, v208, v480]
        self.DistributionSysTypes = [
            doc.agregar(Sistema(811, "120/208 Wye", "ThreePhase", "Wye", 4, v208, v120)),
            doc.agregar(Sistema(812, "480 Delta", "ThreePhase", "Delta", 3, v480, None))]
        doc.deshacer[:] = []

    def _alta(self, lista, elemento):
        self.doc.agregar(elemento)
        lista.append(elemento)
        self.doc.deshacer.append(lambda: lista.remove(elemento))
        return elemento

    def AddVoltageType(self, nombre, real, minimo, maximo):
        if not self.doc.llamada("AddVoltageType"):
            return None
        return self._alta(self.VoltageTypes, TipoTension(
            self.doc.nuevo_id(), nombre, real, minimo, maximo))

    def AddDistributionSysType(self, nombre, fase, configuracion, hilos, ll, lg):
        if not self.doc.llamada("AddDistributionSysType"):
            return None
        return self._alta(self.DistributionSysTypes, Sistema(
            self.doc.nuevo_id(), nombre, fase, configuracion, hilos, ll, lg))


class ParametroSistema(object):
    """RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM de un tablero de 208 V: Set
    acepta cualquier id y Revit protesta al confirmar si no es compatible."""
    IsReadOnly = False

    def __init__(self, doc, tension_v=208.0):
        self.doc, self.tension_v, self.actual = doc, tension_v, ElementId(-1)

    def AsElementId(self):
        return self.actual

    def Set(self, element_id):
        previo, fallos = self.actual, list(self.doc.fallos)
        self.actual = element_id
        ll = self.doc.GetElement(element_id).VoltageLineToLine
        if ll is None or not ll.MinValue <= self.tension_v <= ll.MaxValue:
            self.doc.fallos.append(("Error", INVALIDO))

        def deshacer():
            self.actual = previo
            self.doc.fallos[:] = fallos
        self.doc.deshacer.append(deshacer)
        return True


@pytest.fixture()
def modelo():
    panel = dobles.Tablero(700, con_distribucion=False)
    doc, DB = dobles.modelo_electrico([], panel)
    doc.ajustes = Ajustes(doc)
    panel.parametros["RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM"] = ParametroSistema(doc)
    DB.Electrical.ElectricalSetting = ns(GetElectricalSettings=lambda d: d.ajustes)
    DB.Electrical.ElectricalPhase = dobles._Nombres()
    DB.Electrical.ElectricalPhaseConfiguration = dobles._Nombres()
    return doc, DB, panel


WYE = {"nombre": "QA 120/208", "fase": "trifasico", "configuracion": "estrella",
       "hilos": 4, "linea_linea_v": 208, "linea_tierra_v": 120}


def test_sin_sistema_ni_crear_es_lectura_y_no_abre_transaccion(modelo):
    doc, DB, _ = modelo
    r = ejecutar.correr("tablero", {"tablero": 700}, doc, DB)
    assert r["ok"] and r["lectura"] and r["estado"] == "sin_transaccion"
    assert r["sistema_anterior"] is None
    assert [s["nombre"] for s in r["sistemas_disponibles"]] == ["120/208 Wye", "480 Delta"]
    assert r["sistemas_disponibles"][0]["linea_linea"]["real_v"] == 208.0
    assert not [b for b in doc.bitacora if b.startswith("Start")]


def test_ensayo_asigna_un_sistema_existente_y_lo_revierte(modelo):
    doc, DB, panel = modelo
    r = ejecutar.correr("tablero", {"tablero": 700, "sistema": "120/208 Wye"}, doc, DB)
    assert r["ok"] and r["ensayo"] and r["ensayo_valido"] is True
    assert r["commit_de_ensayo"] == "Committed" and r["estado"] == "RolledBack"
    assert r["sistema"]["nombre"] == "120/208 Wye" and r["creado"] is False
    assert panel.get_Parameter("RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM").AsElementId().Value == -1


def test_confirmar_crea_tensiones_en_voltios_y_deja_el_sistema(modelo):
    doc, DB, panel = modelo
    crear = dict(WYE, linea_linea_v=220, linea_tierra_v=127, nombre="QA 127/220")
    panel.parametros["RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM"].tension_v = 220.0
    r = ejecutar.correr("tablero", {"tablero": 700, "crear": crear, "confirmar": True}, doc, DB)
    assert r["ok"] and r["confirmado"] and r["estado"] == "Committed" and r["creado"]
    nuevas = dict((t.Name, t) for t in doc.ajustes.VoltageTypes)
    assert nuevas["220 V"].ActualValue == 220.0           # voltios, sin convertir
    assert (nuevas["220 V"].MinValue, nuevas["220 V"].MaxValue) == (198.0, 242.0)
    assert nuevas["127 V"].ActualValue == 127.0
    assert [n["accion"] for n in r["tensiones"]] == ["creada", "creada"]
    assert r["sistema"]["linea_linea"]["real_v"] == 220.0
    assert r["sistema"]["fase"] == "ThreePhase" and r["sistema"]["configuracion"] == "Wye"
    assert panel.get_Parameter("RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM").AsElementId().Value == r["sistema"]["id"]
    assert "Save" not in doc.bitacora


def test_crear_reutiliza_el_tipo_de_tension_que_ya_existe(modelo):
    doc, DB, _ = modelo
    r = ejecutar.correr("tablero", {"tablero": 700, "crear": WYE, "confirmar": True}, doc, DB)
    assert r["ok"] and [n["accion"] for n in r["tensiones"]] == ["reutilizada", "reutilizada"]
    assert "AddVoltageType" not in doc.bitacora
    assert len(doc.ajustes.VoltageTypes) == 3


def test_sistema_incompatible_no_confirma_y_trae_el_error_de_revit(modelo):
    doc, DB, panel = modelo
    r = ejecutar.correr("tablero", {"tablero": 700, "sistema": "480 Delta", "confirmar": True}, doc, DB)
    assert r["ok"] is False and r["confirmado"] is False and r["estado"] == "RolledBack"
    assert any(INVALIDO in str(e) for e in r["errores"])
    assert panel.get_Parameter("RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM").AsElementId().Value == -1


def test_ensayo_de_un_sistema_incompatible_dice_que_no_es_valido(modelo):
    doc, DB, _ = modelo
    r = ejecutar.correr("tablero", {"tablero": 700, "sistema": "480 Delta"}, doc, DB)
    assert r["ok"] and r["ensayo_valido"] is False and r["commit_de_ensayo"] == "RolledBack"
    assert doc.grupos_abiertos == 0


def test_un_tipo_con_el_mismo_nombre_y_otro_valor_no_se_reutiliza(modelo):
    doc, DB, panel = modelo
    # Como deja un tipo creado en unidades internas: se llama 220 V y vale otra cosa.
    doc.ajustes.VoltageTypes.append(TipoTension(820, "220 V", 2368.06, 2131.0, 2605.0))
    panel.parametros["RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM"].tension_v = 220.0
    crear = dict(WYE, nombre="QA 220", linea_linea_v=220, linea_tierra_v=None)
    r = ejecutar.correr("tablero", {"tablero": 700, "crear": crear, "confirmar": True}, doc, DB)
    assert r["ok"] and r["tensiones"][0]["tipo"] == "220 V (voltios)"
    assert r["sistema"]["linea_linea"]["real_v"] == 220.0 and r["sistema"]["linea_tierra"] is None


@pytest.mark.parametrize("opciones, texto", [
    ({"tablero": 700, "sistema": "X", "crear": WYE}, "no ambos"),
    ({"tablero": 700, "sistema": "no existe"}, "0 sistemas"),
    ({"tablero": 700, "confirmar": True}, "necesita 'sistema' o 'crear'"),
    ({"tablero": 700, "crear": dict(WYE, nombre="120/208 Wye")}, "ya existe"),
    ({"tablero": 700, "crear": dict(WYE, fase="bifasico")}, "crear.fase"),
    ({"tablero": 700, "crear": dict(WYE, configuracion="sin_definir")}, "estrella o delta"),
    ({"tablero": 700, "crear": dict(WYE, linea_linea_v=None, linea_tierra_v=None)}, "en voltios"),
    ({"tablero": 700, "crear": dict(WYE, linea_linea_v=0.5)}, "linea_linea_v"),
    ({"tablero": 700, "crear": dict(WYE, basura=1)}, "desconocidas"),
    ({"tablero": 700, "otra": 1}, "desconocidas"),
    ({"tablero": 999}, "no existe el id"),
])
def test_entradas_invalidas_no_tocan_el_modelo(modelo, opciones, texto):
    doc, DB, _ = modelo
    r = ejecutar.correr("tablero", opciones, doc, DB)
    assert r["ok"] is False and r["tipo_error"] == "entrada" and texto in r["error"]
    assert not [b for b in doc.bitacora if b.startswith("Start")]


def test_un_elemento_que_no_es_tablero_se_rechaza(modelo):
    doc, DB, panel = modelo
    del panel.parametros["RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM"]
    with pytest.raises(ErrorEntrada, match="no es un tablero"):
        tablero.validar(DB, doc, {"tablero": 700})


def test_rango_es_simetrico_en_voltios():
    assert tablero.rango(200.0, 10.0) == (180.0, 220.0)
