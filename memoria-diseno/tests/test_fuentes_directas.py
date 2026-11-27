"""Lectores directos de hojas de cálculo y de tablas de ETABS (sin abrir Excel ni ETABS)."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fuentes_etabs as fe  # noqa: E402
import fuentes_excel as fx  # noqa: E402


# ------------------------------------------------------------------ hojas de cálculo
def hoja(celdas, filas=12, cols=12):
    """Hoja vacía con las celdas dadas: {(fila, columna): valor}."""
    h = [[None] * cols for _ in range(filas)]
    for (r, c), v in celdas.items():
        h[r][c] = v
    return h


def libro_espectro():
    return {
        "Datos": hoja({(0, 0): "   Uso:", (0, 1): "Otro"}),
        "Imprimir (1)": hoja({
            (0, 3): "   Proyecto:", (0, 4): "Edificio de prueba",
            (1, 2): "   Uso:", (1, 4): "Apartamentos",
            (2, 2): "   Ubicación :", (2, 4): " Ciudad X",
            (3, 2): "   No. De Pisos :", (3, 4): 5.0,
            (4, 2): "Dirección x-x", (4, 4): 40.0,
            (5, 1): "I=", (5, 2): "IV", (5, 3): "Categoría Ocupacional",
            (6, 1): "Z=", (6, 2): 2.0, (6, 3): "Zonificación Sísmica",
            (7, 1): "Rd (final)=", (7, 2): 4.0, (7, 3): "No se le aplicó reducciones",
            (8, 1): "Fa =", (8, 2): 1.0, (9, 1): "Fv =", (9, 2): 1.3,
            (10, 1): "SDS", (10, 2): 7.521, (10, 3): "Sds= Fa x 2/3 Ss x g",
            (11, 1): "SD1", (11, 2): 5.271,
        }),
        "Imprimir (3)": hoja({
            (0, 0): "Período", (0, 1): "Aceleración", (0, 3): "Período", (0, 4): "Aceleración",
            (1, 0): 0.0, (1, 1): 0.75, (1, 3): 0.5, (1, 4): 1.88,
            (2, 0): 0.01, (2, 1): 0.83, (2, 3): 0.51, (2, 4): 1.87,
            (3, 0): "fin", (4, 0): 9.0, (4, 1): 9.0,
        }),
    }


def test_espectro_se_lee_por_rotulos_y_no_por_posicion():
    e = fx.espectro_de(libro_espectro())
    assert e["proyecto"] == "Edificio de prueba"
    assert e["uso"] == "Apartamentos"                # de la hoja que rotula SDS, no de «Datos»
    assert e["ubicacion"] == "Ciudad X"
    assert (e["pisos"], e["dx"], e["SDS"], e["SD1"], e["Fa"], e["Fv"]) == (5.0, 40.0, 7.521, 5.271, 1.0, 1.3)
    assert (e["I"], e["Z"]) == ("IV", "2")           # los enteros no salen como «2.0»
    assert (e["Rd_final"], e["Rd_nota"]) == (4.0, "No se le aplicó reducciones")
    assert e["Ss"] is None                           # rótulo ausente: None, no un error


def test_tabla_del_espectro_junta_las_columnas_y_se_detiene_en_la_primera_fila_no_numerica():
    assert fx.tabla_espectro_de(libro_espectro()) == [(0.0, 0.75), (0.01, 0.83), (0.5, 1.88), (0.51, 1.87)]


def test_espectro_sin_la_hoja_esperada_falla_con_mensaje_claro():
    with pytest.raises(fx.ErrorDeHoja, match="SDS"):
        fx.espectro_de({"Hoja1": hoja({(0, 0): "nada"})})


def test_cuasiestatico_lee_pares_y_la_fila_de_escalado():
    libro = {"Cuasiestatico": hoja({
        (0, 0): "CORTANTE BASAL",
        (1, 0): "Carga Muerta:", (1, 2): 3524.47,
        (2, 0): "Entrepisos:", (2, 1): 0.15, (2, 2): 570.65,
        (3, 0): "Carga Total de Edificio:", (3, 2): 3618.13,
        (4, 0): "Ta =", (4, 1): 0.57, (4, 3): "Ta =", (4, 4): 0.58,
        (5, 0): "V x-x =", (5, 1): 693.47, (5, 3): "V y-y =", (5, 4): 700.0,
        (6, 0): "V x-x (65%) =", (6, 1): 450.76,
        (7, 0): "Ex-x", (7, 1): 504.99, (7, 2): "OK", (7, 3): 0.8926,
        (8, 2): "Ct=", (8, 3): 0.046,
    })}
    c = fx.cuasi_de(libro)
    assert (c["muerta"], c["total"], c["phi_entrepiso"]) == (3524.47, 3618.13, 0.15)
    assert c["Ta"] == [0.57, 0.58]
    assert (c["Vx"], c["Vy"], c["Vx65"], c["Ct"]) == (693.47, 700.0, 450.76, 0.046)
    assert c["Ex"] == [504.99, "OK", 0.8926]
    assert "Ey" not in c and c["Vy65"] is None


def libro_art38():
    cab = {(1, 0): "Story", (1, 1): "Point", (1, 4): "Ratio X-X", (1, 7): "Ratio Y-Y"}
    filas = {
        (2, 0): 2.0, (2, 1): "A", (2, 4): 1.01, (2, 5): 1.02, (2, 7): 1.10, (2, 8): 1.11, (2, 9): "Ok", (2, 10): "Ok",
        (3, 1): "B", (3, 4): 9.0,
        (4, 0): 1.0, (4, 1): "A", (4, 4): 1.04, (4, 5): 1.04, (4, 7): 1.05, (4, 8): 1.06, (4, 9): "Ok",
        (5, 0): 0.0, (5, 1): "A", (5, 4): None, (5, 5): None,       # nivel 0: celdas con error en la hoja real
    }
    return {"Point Drift ": hoja({}), "Art.38(2)": hoja({**cab, **filas}), "Art.38(1)": hoja({**cab, **filas})}


def test_art38_toma_una_fila_por_nivel_y_ordena_los_casos():
    casos = fx.art38_de(libro_art38())
    assert [c["caso"] for c in casos] == ["1", "2"]
    assert [f["story"] for f in casos[0]["filas"]] == [2, 1]
    f = casos[0]["filas"][0]
    assert (f["rx1"], f["rx2"], f["ry1"], f["ry2"], f["ok"]) == (1.01, 1.02, 1.10, 1.11, ["Ok", "Ok"])


def test_art38_sin_hojas_o_sin_encabezado_falla():
    with pytest.raises(fx.ErrorDeHoja, match="Art.38"):
        fx.art38_de({"Otra": hoja({})})
    with pytest.raises(fx.ErrorDeHoja, match="encabezado"):
        fx.art38_de({"Art.38(1)": hoja({(0, 0): "sin encabezado"})})


def test_abrir_rechaza_archivo_inexistente_y_formato_desconocido(tmp_path):
    with pytest.raises(fx.ErrorDeHoja, match="no existe"):
        fx.abrir(str(tmp_path / "no.xls"))
    raro = tmp_path / "hoja.ods"
    raro.write_text("x")
    with pytest.raises(fx.ErrorDeHoja, match="no admitido"):
        fx.abrir(str(raro))


# ------------------------------------------------------------------ tablas de ETABS
def tablas_minimas():
    return {
        "_meta": [{"version": "23.3.0", "modelo": "prueba.EDB", "diseno": "recalculado"}],
        fe.T_PROYECTO: [{"ModelName": "Modelo de prueba"}],
        fe.T_PROGRAMA: [{"Version": "23.3.0", "ConcFrmCode": "ACI 318-19"}],
        fe.T_PISOS: [{"Story": "Story2", "Height": "3.25"}, {"Story": "Story1", "Height": "3.7"}],
        fe.T_MATERIALES: [{"Material": "C280", "Type": "Concrete"}, {"Material": "A615Gr60", "Type": "Rebar"}],
        fe.T_CONCRETOS: [{"Material": "C280", "Fc": "2800"}],
        fe.T_PORTICO: [{"Name": "C1", "Material": "C280", "Shape": "Concrete Rectangular", "Area": "0.16",
                        "I33": "0.002133", "I22": "0.002133", "JMod": "1", "I3Mod": "0.8", "I2Mod": "0.8"}],
        fe.T_AREA: [{"Name": "L15", "Type": "Slab", "AnalType": "Shell-Thin", "Material": "C210", "TotalThick": "0.15"}],
        fe.T_PATRONES: [{"Name": "Dead", "IsAuto": "No", "Type": "Dead", "SelfWtMult": "1", "AutoLoad": None},
                        {"Name": "Qx", "IsAuto": "No", "Type": "Seismic", "SelfWtMult": "0", "AutoLoad": "User Coefficient"}],
        fe.T_CARGAS_LOSA: [{"Name": "Comun", "LoadPattern": "Dead", "LoadValue": "0.18"},
                           {"Name": None, "LoadPattern": "Live", "LoadValue": "0.4"}],
        fe.T_FUENTE_MASA: [{"Name": "MsSrc1", "LoadPattern": "Dead", "Multiplier": "1"},
                           {"Name": "MsSrc1", "LoadPattern": "Live", "Multiplier": "0.15"}],
        fe.T_CASOS: [{"Name": "Ex", "Type": "Response Spectrum"}],
        fe.T_COMBOS: [{"Name": "DConS1", "Type": "Linear Add", "LoadName": "Dead", "SF": "1.4", "Notes": "Dead"},
                      {"Name": "DConS2", "Type": "Linear Add", "LoadName": "Dead", "SF": "1.2", "Notes": None},
                      {"Name": None, "Type": None, "LoadName": "Live", "SF": "1.6", "Notes": None}],
        fe.T_MASA: [{"Story": "Story2", "UX": "70.2", "UY": "70.2"}, {"Story": "Base", "UX": "16.3", "UY": "16.3"}],
        fe.T_SISMO_AUTO: [{"Name": "Qx", "C": "0.1", "WeightUsed": None, "BaseShear": None},
                          {"Name": "Qx(1/2)", "C": "0.1", "WeightUsed": "4498.76", "BaseShear": "449.88"}],
        fe.T_BASE: [{"OutputCase": "Dead", "StepType": None, "FX": "0", "FY": "0", "FZ": "4540.657"},
                    {"OutputCase": "Ex", "StepType": "Max", "FX": "506.39", "FY": "168.48", "FZ": "0"}],
        fe.T_DERIVAS: [{"Story": "Story2", "OutputCase": "Ex", "Direction": "X", "Drift": "0.0021"},
                       {"Story": "Story2", "OutputCase": "Ex", "Direction": "X", "Drift": "0.0034"}],
        fe.T_CORTANTES: [{"Story": "Story2", "OutputCase": "Ex", "Location": "Top", "VX": "999", "VY": "999"},
                         {"Story": "Story2", "OutputCase": "Ex", "Location": "Bottom", "VX": "-172.0", "VY": "51.8"}],
        fe.T_MODAL: [{"Mode": "1", "Period": "0.644", "UX": "0.6533", "UY": "0", "UZ": "0", "SumUX": "0.6533",
                      "SumUY": "0", "SumUZ": "0", "RX": "0", "RY": "0.41", "RZ": "0.001"}],
        fe.T_COLUMNAS: [
            {"Story": "Story2", "UniqueName": "10", "DesignSect": "C1", "PMMRatio": "0.52", "PMMCombo": "DConS1",
             "AsMin": "0.0016", "As": "0.0034", "WarnMsg": "No Message", "ErrMsg": "No Message"},
            {"Story": "Story2", "UniqueName": "10", "DesignSect": "C1", "PMMRatio": "1.27", "PMMCombo": "DConS2",
             "AsMin": "0.0016", "As": "0.0034", "WarnMsg": "Capacity ratio exceeds limit", "ErrMsg": "No Message"},
            {"Story": "Story2", "UniqueName": "11", "DesignSect": "C1", "PMMRatio": "0.40", "PMMCombo": "DConS1",
             "AsMin": "0.0016", "As": "0.0020", "WarnMsg": "No Message", "ErrMsg": "No Message"}],
        fe.T_VIGAS: [{"Story": "Story2", "UniqueName": "20", "DesignSect": "V3070", "AsTop": "0.0008", "AsBot": "0.0006",
                      "VRebar": "0.0005", "WarnMsg": "No Message", "ErrMsg": "No Message"},
                     {"Story": "Story2", "UniqueName": "20", "DesignSect": "V3070", "AsTop": "0.0015", "AsBot": "0.0005",
                      "VRebar": "0.0009", "WarnMsg": "No Message", "ErrMsg": "No Message"}],
        fe.T_NUDOS: [
            {"Story": "Story2", "UniqueName": "10", "BCMajRatio": "0.92", "BCMinRatio": "0.80", "JSMajRatio": "0.61",
             "JSMinRatio": "0.38", "WarnMsg": "No Message", "ErrMsg": "No Message"},
            {"Story": "Story2", "UniqueName": "11", "BCMajRatio": None, "BCMinRatio": "0.77", "JSMajRatio": "1.05",
             "JSMinRatio": "0.40", "WarnMsg": "No Message",
             "ErrMsg": "Beam/Column capacity ratio exceeds limitBeam/Column capacity ratio exceeds limit"},
            {"Story": "Story2", "UniqueName": "12", "BCMajRatio": None, "BCMinRatio": None, "JSMajRatio": None,
             "JSMinRatio": None, "WarnMsg": "No Message", "ErrMsg": "No Message"}],
    }


def test_etabs_definicion_y_resultados():
    e = fe.etabs_de(tablas_minimas())
    assert (e["modelo"], e["version"], e["unidad_long"]) == ("Modelo de prueba", "ETABS v23.3.0", "m")
    assert e["stories"] == [["Story2", 3.25], ["Story1", 3.7]]
    assert e["concretos"] == ["C280"] and e["fc"] == {"C280": 2800.0}
    assert e["frame"]["C1"]["mI33"] == 0.8 and e["area"][0]["t"] == 0.15
    assert e["loadsets"] == [["Comun", "Dead", 0.18], ["Comun", "Live", 0.4]]       # fila de continuación
    assert e["mass_source"] == [["Dead", 1.0], ["Live", 0.15]]
    assert e["combos"]["DConS2"]["terms"] == [["Dead", 1.2], ["Live", 1.6]]
    assert e["auto_seis"]["Qx"] == {"C": 0.1, "W": 4498.76, "V": 449.88}
    assert e["base"]["Ex"] == [{"step": "Max", "FX": 506.39, "FY": 168.48, "FZ": 0.0}]
    assert e["drift"] == {"Story2|Ex|X": 0.0034}                                    # el máximo
    assert e["shear"] == {"Story2|Ex": [172.0, 51.8]}                               # solo «Bottom», en valor absoluto
    assert e["modal"][0][:3] == [1, 0.644, 0.6533] and len(e["modal"][0]) == 11
    assert e["tiene_viento"] is False


def test_etabs_diseno_agrupa_por_nivel_y_seccion():
    e = fe.etabs_de(tablas_minimas())
    assert e["col"]["Story2|C1"] == {"n": 2, "pmm": 1.27, "combo": "DConS2", "As": 0.0034, "AsMin": 0.0016, "warn": 1}
    assert e["beam"]["Story2|V3070"] == {"n": 1, "AsTop": 0.0015, "AsBot": 0.0006, "Av": 0.0009, "err": 0}
    assert (e["n_col"], e["n_beam"], e["n_joint"]) == (2, 1, 3)


def test_etabs_nudo_que_excede_sin_valor_cuenta_como_mayor_que_uno():
    j = fe.etabs_de(tablas_minimas())["joint"]["Story2"]
    assert (j["n"], j["bc_gt1"], j["bc_sin_valor"], j["sin_bc"]) == (3, 1, 1, 1)
    assert (j["bc"], j["js"], j["js_gt1"]) == (0.92, 1.05, 1)


def test_etabs_mensaje_repetido_se_cuenta_una_vez():
    msgs = fe.etabs_de(tablas_minimas())["msgs"]
    assert msgs == {"col: Capacity ratio exceeds limit": 1, "nudo: Beam/Column capacity ratio exceeds limit": 1}


def test_etabs_detecta_patron_de_viento():
    t = tablas_minimas()
    t[fe.T_PATRONES].append({"Name": "Wx", "IsAuto": "No", "Type": "Wind", "SelfWtMult": "0", "AutoLoad": "ASCE 7-16"})
    assert fe.etabs_de(t)["tiene_viento"] is True


def test_etabs_sin_resultados_falla_diciendo_que_tablas_faltan():
    t = tablas_minimas()
    t[fe.T_BASE] = []
    del t[fe.T_MODAL]
    with pytest.raises(fe.ErrorDeEtabs, match="Base Reactions.*Modal Participating"):
        fe.etabs_de(t)


def test_la_copia_de_trabajo_nunca_es_el_modelo_original(tmp_path):
    original = tmp_path / "modelo.EDB"
    original.write_bytes(b"x")
    with pytest.raises(fe.ErrorDeEtabs, match="carpeta de trabajo"):
        fe._copiar_modelo(str(original), str(tmp_path))
    copia = fe._copiar_modelo(str(original), str(tmp_path / "trabajo"))
    assert os.path.isfile(copia) and os.path.dirname(copia) != str(tmp_path)
    with pytest.raises(fe.ErrorDeEtabs, match="no existe"):
        fe._copiar_modelo(str(tmp_path / "otro.EDB"), str(tmp_path / "t2"))
