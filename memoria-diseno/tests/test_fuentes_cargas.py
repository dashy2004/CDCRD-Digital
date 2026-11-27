"""Lector del libro de cargas y espesores de losa."""
import datetime
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import armar_datos  # noqa: E402
import fuentes_cargas as fc  # noqa: E402
import fuentes_excel as fx  # noqa: E402
import fuentes_losas  # noqa: E402

HOJA_CARGAS = [
    [None, "INGENIERO", None, "   Proyecto:", None, "Otro proyecto"],
    [None, None, None, "   Fecha :", None, datetime.datetime(2025, 9, 4)],
    [None, "Cuantificación de Sobre Carga"],
    [None, "ENTREPISO"],
    [None, "  Carga Muerta", "h (m)", "d [ton/m³]", "w [ton/m²]", "qd (ton/m²)"],
    [None, "Losa de 12", 0.12, 2.4, 0.288, 0.469],
    [None, "Losa de 15", 0.15, 2.4, 0.36, 0.541],
    [],
    [None, "Pesos Propios"],
    [None, "     Mosaicos", 0.03, 2.3, 0.069],
    [None, "     Pañete ", 0.02, 2, 0.04],
    [None, "  Carga Viva"],
    [None, "     Entrepiso", None, "ql =", 0.2, "ton/m²"],
    [None, "qu= 1.2qd + 1.6ql", "ACI-318-05"],
    [None, "Descripción", "qd[ton/m²]", "ql[ton/m²]", "qu[ton/m²]"],
    [None, "Interior (h=0.12)", 0.469, 0.2, 0.8828],
    [],
    [None, "nota suelta", 1, 2, 3],
    [None, "Cuantificación de Sobre Carga"],
    [None, "TECHO"],
    [None, "Losa de 12", 0.12, 2.4, 0.288, 0.472],
    [None, "Pesos Propios"],
    [None, "     Fino", 0.08, 1.8, 0.144],
    [None, "  Carga Viva"],
    [None, "     Techo Plano", None, "ql =", 0.1],
    [None, "Descripción", "qd", "ql", "qu"],
    [None, "Techo (h=0.12)", 0.472, 0.1, 0.7264],
]

HOJA_ESPESOR = [
    ["Cant. de Losas:", None, "Fy =", 4200, "Kg/cm²"],
    ["LOSA", "Lx", "Ly", "Cond.", "K", "Ln", "b", "h [cm]", None, None, None, "bw"],
    [1, 6.85, 5.2, "2D", "N.A.", 6.85, 1.3, 0.1551, "Usar h =", 0.2, None, 0.3],
    [2, 2.3, 5.2, "1D", 10, 2.3, 2.2, 0.23, "Usar h =", 0.15, None, 0.3],
    [3, 0, 0, None, None, None, None, None, None, None, None, None],
    ["total", None],
]

HOJA_CARGA = [
    ["Cant. de Losas:", 3, "Fy =", 4200],
    ["LOSA", "Lx                (m)", "Ly                (m)", "Espesor (m)", "Espesor Eq. (m)", "Area      (m2)",
     "Q mamp    (Ton)", "Qmap     (Ton/m2)", "Q muerta     (Ton/m2)", "Q viva     (Ton/m2)", "Q ultima     (Ton/m2)"],
    [1, 6.85, 5.2, 0.2, 0.13, 35.62, 4.212, 0.1182, 0.6112, 0.2, 1.0535],
    [2, 2.3, 5.2, 0.15, 0.15, 11.96, 5.996, 0.5013, 1.0423, 0.2, 1.5708],
]


def test_sobrecarga_separa_los_bloques_y_sus_secciones():
    entrepiso, techo = fc.sobrecarga_de({"Portada": [["nada"]], "Cargas": HOJA_CARGAS})
    assert entrepiso["titulo"] == "ENTREPISO" and techo["titulo"] == "TECHO"
    assert entrepiso["espesores"] == [[0.12, 2.4, 0.288, 0.469], [0.15, 2.4, 0.36, 0.541]]
    assert entrepiso["pesos"] == [["Mosaicos", 0.03, 2.3, 0.069], ["Pañete", 0.02, 2.0, 0.04]]
    assert entrepiso["vivas"] == [["Entrepiso", 0.2]]
    assert entrepiso["resumen"] == [["Interior (h=0.12)", 0.469, 0.2, 0.8828]]      # la «nota suelta» queda fuera
    assert techo["vivas"] == [["Techo Plano", 0.1]] and techo["resumen"] == [["Techo (h=0.12)", 0.472, 0.1, 0.7264]]


def test_sobrecarga_sin_bloques_falla():
    with pytest.raises(fx.ErrorDeHoja, match="Sobre Carga"):
        fc.sobrecarga_de({"Hoja1": [["nada"]]})


def test_encabezado_trae_el_proyecto_y_la_fecha_que_declara_el_libro():
    assert fc.encabezado_de({"Cargas": HOJA_CARGAS}) == {"proyecto": "Otro proyecto", "fecha": "04/09/2025"}
    assert fc.encabezado_de({"Hoja1": [["nada"]]}) == {"proyecto": None, "fecha": None}


def test_espesores_lee_una_fila_por_losa_y_no_confunde_fy_con_la_cantidad():
    e = fc.espesores_de(HOJA_ESPESOR, "Espesor N")
    assert e["declaradas"] is None                              # la celda está vacía; 4200 es Fy
    assert list(e["losas"]) == ["1", "2"]                       # la fila de luces cero y el total se descartan
    assert e["losas"]["1"] == {"Lx": "6.85", "Ly": "5.20", "cond": "2D", "K": "N.A.", "Ln": "6.85", "hcalc": "0.16", "h": "0.20"}
    assert e["losas"]["2"]["K"] == "10.00" and e["losas"]["2"]["h"] == "0.15"


def test_cargas_lee_por_encabezado_aunque_traiga_espacios_repetidos():
    c = fc.cargas_de(HOJA_CARGA, "Carga N")
    assert c["declaradas"] == 3 and list(c["losas"]) == ["1", "2"]
    assert c["losas"]["2"] == {"Lx": "2.30", "Ly": "5.20", "h": "0.15", "area": "11.96", "qmamp_ton": "6.00",
                              "qmamp": "0.50", "qd": "1.04", "ql": "0.20", "qu": "1.57"}


def test_hoja_sin_encabezado_o_sin_columnas_falla_con_su_nombre():
    with pytest.raises(fx.ErrorDeHoja, match="«Carga N».*LOSA"):
        fc.cargas_de([["sin", "encabezado"]], "Carga N")
    with pytest.raises(fx.ErrorDeHoja, match="q muerta|qd"):
        fc.cargas_de([["LOSA", "Lx", "Ly"], [1, 2.0, 3.0]], "Carga N")


def test_hoja_del_nivel_no_distingue_mayusculas_y_respeta_la_indicada():
    libro = {"Carga TECHO": [[1]], "Carga T": [[2]]}
    assert fc.hoja_del_nivel(libro, "Carga", "Techo")[0] == "Carga TECHO"
    assert fc.hoja_del_nivel(libro, "Carga", "Techo", "Carga T")[0] == "Carga T"
    with pytest.raises(fx.ErrorDeHoja, match="«Carga E9»"):
        fc.hoja_del_nivel(libro, "Carga", "E9")


def test_diferencias_de_luces_entre_la_hoja_y_el_listado():
    hoja = {"1": {"Lx": "6.85", "Ly": "5.20"}, "2": {"Lx": "2.30", "Ly": "5.00"}, "9": {"Lx": "1.00", "Ly": "1.00"}}
    listado = {"1": {"Lx": "6.850", "Ly": "5.200"}, "2": {"Lx": "2.300", "Ly": "5.200"}, "4": {"Lx": "3", "Ly": "3"}}
    assert fc.diferencias_de_luces(hoja, listado) == {"distintas": ["2"], "solo_hoja": ["9"], "solo_listado": ["4"]}


# ------------------------------------------------------------------ integración con el manifiesto
def libro_en_disco(tmp_path, hojas):
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for nombre, filas in hojas.items():
        ws = wb.create_sheet(nombre)
        for fila in filas:
            ws.append(fila)
    ruta = tmp_path / "cargas.xlsx"
    wb.save(ruta)
    return ruta


def nivel_falso(nombre, txt, dl=None):
    return {"nombre": nombre, "esp": {}, "carga": {}, "ax": {}, "ay": {}, "apx": [], "apy": [], "meta": {},
            "sin_leer": [], "avisos": [],
            "mom": {"1": {"Lx": "6.850", "Ly": "5.200"}, "2": {"Lx": "2.300", "Ly": "4.000"}, "3": {"Lx": "1", "Ly": "1"}}}


def test_armar_une_las_hojas_al_nivel_y_avisa_de_lo_que_no_cuadra(tmp_path, monkeypatch):
    libro_en_disco(tmp_path, {"Cargas": HOJA_CARGAS, "Espesor N1": HOJA_ESPESOR, "Carga N1": HOJA_CARGA})
    (tmp_path / "n1.TXT").write_text("", encoding="cp1252")
    monkeypatch.setattr(fuentes_losas, "nivel", nivel_falso)
    man = tmp_path / "fuentes.json"
    man.write_text(json.dumps({"niveles": [{"nombre": "N1", "txt": "n1.TXT"}], "cargas": {"libro": "cargas.xlsx"}}),
                   encoding="utf-8")

    data = armar_datos.armar(str(man))

    assert [s["titulo"] for s in data["sobrecarga"]] == ["ENTREPISO", "TECHO"]
    assert data["cargas_meta"] == {"proyecto": "Otro proyecto", "fecha": "04/09/2025", "archivo": "cargas.xlsx"}
    nv = data["niveles"][0]
    assert nv["esp"]["1"]["h"] == "0.20" and nv["carga"]["1"]["qu"] == "1.05"
    assert nv["hojas"] == {"espesor": "Espesor N1", "carga": "Carga N1"}
    avisos = "\n".join(data["avisos"])
    assert "«Carga N1» declara 3 losas y trae 2" in avisos
    assert "1 losa(s) tienen luces distintas en la hoja «Espesor N1» y en el listado de diseño: 2." in avisos
    assert "1 losa(s) están en el listado de diseño y no en la hoja «Espesor N1»: 3." in avisos


def test_armar_falla_con_mensaje_si_falta_la_hoja_de_un_nivel(tmp_path, monkeypatch):
    libro_en_disco(tmp_path, {"Cargas": HOJA_CARGAS, "Espesor N1": HOJA_ESPESOR})
    (tmp_path / "n1.TXT").write_text("", encoding="cp1252")
    monkeypatch.setattr(fuentes_losas, "nivel", nivel_falso)
    man = tmp_path / "fuentes.json"
    man.write_text(json.dumps({"niveles": [{"nombre": "N1", "txt": "n1.TXT"}], "cargas": {"libro": "cargas.xlsx"}}),
                   encoding="utf-8")

    with pytest.raises(armar_datos.ErrorDeFuentes, match="libro de cargas: ErrorDeHoja: .*«Carga N1»"):
        armar_datos.armar(str(man))
