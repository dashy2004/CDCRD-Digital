"""Lector de fundaciones de SAFE: conversión de tablas, sin abrir el programa."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fuentes_safe as fs  # noqa: E402


def tablas():
    return {
        "_meta": [{"version": "23.3.0", "modelo": "fundaciones.FDB"}],
        fs.T_PROYECTO: [{"ProjectName": "Otro proyecto", "ModelName": "Fundaciones de prueba"}],
        fs.T_PROGRAMA: [{"Version": "23.3.0", "ConcSlbCode": "ACI 318-19"}],
        fs.T_CONCRETOS: [{"Material": "C210", "Fc": "2100"}],
        fs.T_LOSAS: [{"Name": "S50", "PropType": "Stiff", "Material": "C210", "Thickness": "0.5"}],
        fs.T_RESORTES: [{"Name": "SOIL1", "StiffU3": "3000", "NonlinOpt3": "Compression Only"}],
        fs.T_AREAS_RESORTE: [{"UniqueName": "1", "SpringProp": "SOIL1"}, {"UniqueName": "2", "SpringProp": "SOIL1"}],
        fs.T_PATRONES: [{"Name": "~LLRF", "Type": "Other"}, {"Name": "Dead", "Type": "Dead"}],
        fs.T_CASOS: [{"Name": "Dead", "Type": "Linear Static"}],
        fs.T_COMBOS: [
            {"Name": "Comb1", "Type": "Linear Add", "IsAuto": "No", "LoadName": "Dead", "SF": "1"},
            {"Name": None, "Type": None, "IsAuto": None, "LoadName": "Live", "SF": "1"},
            {"Name": "DConS1", "Type": "Linear Add", "IsAuto": "No", "LoadName": "Dead", "SF": "1.4"},
            {"Name": "DCON1", "Type": "Linear Add", "IsAuto": "Yes", "LoadName": "Dead", "SF": "1.4"},
            {"Name": "Envelope", "Type": "Envelope", "IsAuto": "No", "LoadName": "Comb1", "SF": "1"}],
        fs.T_COMBOS_DISENO: [{"ComboType": "Strength", "ComboName": "DConS1"}],
        fs.T_BASE: [{"OutputCase": "Dead", "CaseType": "LinStatic", "FZ": "14728.39"},
                    {"OutputCase": "Comb1", "CaseType": "Combination", "FZ": "17080.1"}],
        fs.T_PUNZONADO: [{"Point": "1", "Status": "Not Calculated", "Ratio": None},
                         {"Point": "2", "Status": "OK", "Ratio": "0.81"},
                         {"Point": "3", "Status": "Fail", "Ratio": "1.12"}],
        fs.T_FRANJAS: [{"StripObject": "CSA1", "Status": "OK"}, {"StripObject": "CSA1", "Status": "OK"},
                       {"StripObject": "CSB1", "Status": "Fail"}],
        fs.R_PRESIONES: [{"combo": "Comb1", "n": 3, "min": -27.3, "max": -0.1}],
    }


def test_solo_las_combinaciones_de_servicio_del_usuario():
    assert fs.combos_de_servicio(tablas()) == ["Comb1"]


def test_resumen_de_presiones_ignora_celdas_vacias():
    filas = [{"SoilPressure": "-14.5"}, {"SoilPressure": "-20.9"}, {"SoilPressure": None}, {"SoilPressure": "0.3"}]
    assert fs.resumen_presiones(filas) == {"n": 3, "min": -20.9, "max": 0.3}
    assert fs.resumen_presiones([]) == {"n": 0, "min": None, "max": None}


def test_fundaciones_de_arma_el_contrato():
    f = fs.fundaciones_de(tablas())
    assert (f["modelo"], f["proyecto"], f["version"], f["codigo"]) == (
        "Fundaciones de prueba", "Otro proyecto", "SAFE v23.3.0", "ACI 318-19")
    assert f["concretos"] == {"C210": 2100.0}
    assert f["losas"] == [{"name": "S50", "tipo": "Stiff", "mat": "C210", "t": 0.5}]
    assert f["resortes"][0]["k"] == 3000.0 and f["areas_con_resorte"] == 2
    assert f["patrones"] == [["Dead", "Dead"]]                       # sin los patrones internos «~»
    assert f["combos"]["Comb1"] == [["Dead", 1.0], ["Live", 1.0]]    # fila de continuación
    assert f["base"] == {"Dead": 14728.39}                           # solo casos estáticos
    assert f["presiones"] == [{"combo": "Comb1", "n": 3, "min": -27.3, "max": -0.1}]
    assert f["punzonado"] == {"n": 3, "calculados": 2, "max": 1.12, "mayores_que_1": 1, "sin_calcular": 1}
    assert f["franjas"] == {"n": 2, "estaciones": 3, "estados": {"OK": 2, "Fail": 1}}


def test_sin_presiones_o_sin_losas_falla():
    t = tablas()
    t[fs.R_PRESIONES] = []
    with pytest.raises(fs.ErrorDeSafe, match="presiones"):
        fs.fundaciones_de(t)


def test_la_copia_de_trabajo_nunca_es_el_modelo_original(tmp_path):
    original = tmp_path / "modelo.FDB"
    original.write_bytes(b"x")
    with pytest.raises(fs.ErrorDeSafe, match="carpeta de trabajo"):
        fs._copiar_modelo(str(original), str(tmp_path))
    assert os.path.isfile(fs._copiar_modelo(str(original), str(tmp_path / "trabajo")))
