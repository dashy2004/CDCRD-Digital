"""Diseño de muros de ETABS: conversión de sus tablas y subsección de la memoria."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fuentes_etabs as fe  # noqa: E402
import muros_ui  # noqa: E402
from test_formato_bloque import bloque_de_prueba, documento  # noqa: E402
from test_fuentes_directas import tablas_minimas  # noqa: E402

CORTANTE = "Design Inadequate: Shear force exceeds maximum allowed at top of pier leg"


def estacion(pila, nivel, est, dc, av="0.0015", err="No Message", sec="MH1"):
    return {"Story": nivel, "Pier": pila, "Station": est, "DesignType": "Section Designer", "PierSec": sec,
            "DCRatio": dc, "Length": "5", "Thickness": "0.25", "ShearAv": av, "BZoneL": None, "BZoneR": None,
            "WarnMsg": "No Message", "ErrMsg": err}


def tablas_con_muros():
    t = tablas_minimas()
    t[fe.T_AREA].append({"Name": "M25", "Type": "Wall", "AnalType": "Shell-Thin", "Material": "C280", "TotalThick": "0.25"})
    t[fe.T_ASIG_AREA] = [{"UniqueName": "30", "SectProp": "L15"}, {"UniqueName": "40", "SectProp": "M25"},
                         {"UniqueName": "41", "SectProp": "M25"}, {"UniqueName": "42", "SectProp": "M25"}]
    t[fe.T_PILAS] = [{"Name": n} for n in ("P1", "MH1-1", "MH2-1", "MH3")]
    t[fe.T_ASIG_PILAS] = [{"UniqueName": "40", "PierName": "MH1-1"}, {"UniqueName": "41", "PierName": "MH2-1"},
                          {"UniqueName": "43", "PierName": "MH3"}, {"UniqueName": "42", "PierName": "None"}]
    t[fe.T_MUROS] = [
        estacion("MH1-1", "Story2", "Top", "0.235"),
        estacion("MH1-1", "Story1", "Bottom", "0.407", av="0.0022", err=CORTANTE),
        estacion("MH2-1", "Story2", "Bottom", "0.995", sec="MH2",
                 err=CORTANTE + " ; Delta_ns exceeds limit"),
        estacion("MH2-1", "Story1", "Top", "0.5", sec="MH2"),
    ]
    t[fe.T_MUROS_COMBOS] = [{"ComboType": "Strength", "ComboName": "DWalS%d" % i} for i in range(1, 17)]
    t[fe.T_MUROS_PREF] = [{"Ductility": "Special Structural Wall", "SDC": "D", "R": "5", "Omega0": "2.5",
                           "Cd": "4.75", "PhiShrSeis": "0.6", "DCLimit": "0.95", "RebarMat": "A615Gr60"}]
    t["_muros"] = [{"estado": "diseñado", "codigo": "ACI 318-19", "avisos": []}]
    return t


def test_modelo_sin_pilas_no_trae_muros():
    assert fe.etabs_de(tablas_minimas())["muros"] is None


def test_envolvente_por_pila_y_lo_que_queda_sin_disenar():
    m = fe.etabs_de(tablas_con_muros())["muros"]
    assert m["estado"] == "diseñado" and m["codigo"] == "ACI 318-19"
    assert m["combinaciones"][0] == "DWalS1" and len(m["combinaciones"]) == 16
    mh1, mh2 = m["pilas"]["MH1-1"], m["pilas"]["MH2-1"]
    assert (mh1["dc"], mh1["dc_nivel"], mh1["av"], mh1["cortante"], mh1["estaciones"]) == (0.407, "Story1", 0.0022, 1, 2)
    assert mh2["dc"] == 0.995 and mh2["cortante"] == 1
    assert mh2["mensajes"] == {"Delta_ns exceeds limit": 1}         # el de cortante se cuenta aparte
    assert m["sin_diseno"] == ["MH3"]                                 # asignada pero sin resultado
    assert m["sin_asignar"] == ["P1"]
    assert m["sin_pila"] == 1                                         # el área 42 lleva «None»


def uniforme(nivel, tramo, req, act, err="No Message"):
    return {"Story": nivel, "Pier": "MH1", "Station": "Top", "DesignType": "Uniform", "ReinfPcent": req,
            "CurrPcent": act, "PierLeg": "Top Leg %d" % tramo, "Length": "1.2", "Thickness": "0.3",
            "ShearAv": "0.003", "WarnMsg": "No Message", "ErrMsg": err}


def test_diseno_uniforme_da_cuantia_y_no_relacion():
    t = tablas_con_muros()
    t[fe.T_MUROS] = [uniforme("Story1", 1, "0.25", "0.35"), uniforme("Story1", 2, "0.4", "0.35", err=CORTANTE)]
    p = fe.etabs_de(t)["muros"]["pilas"]["MH1"]
    assert (p["dc"], p["rho_req"], p["rho_act"], p["tramos"], p["tipos"]) == (None, 0.4, 0.35, 2, ["Uniform"])


def test_memoria_con_pila_uniforme(tmp_path):
    t = tablas_con_muros()
    t[fe.T_MUROS] = [uniforme("Story1", 1, "0.4", "0.35")]
    b = bloque_de_prueba()
    b["etabs"] = {**b["etabs"], "muros": fe.etabs_de(t)["muros"]}
    _, texto = documento(tmp_path, {"niveles": [], "bloques": [b]}, {"portada": {"titulo": "E", "subtitulo": "P"}})
    assert "ρ req. 0.40 % (col. 0.35 %)" in texto
    assert "MH1 (0.40 % frente a 0.35 %)" in texto


def test_cache_no_guarda_un_diseno_de_muros_fallido():
    import armar_datos
    assert armar_datos._muros_fallidos({"_muros": [{"estado": "sin diseño", "motivo": "x"}]})
    assert not armar_datos._muros_fallidos({"_muros": [{"estado": "diseñado"}]})
    assert not armar_datos._muros_fallidos({})


def test_sin_resultados_queda_el_motivo():
    t = tablas_con_muros()
    del t[fe.T_MUROS]
    t["_muros"] = [{"estado": "sin diseño", "motivo": "no apareció el menú «Design»"}]
    m = fe.etabs_de(t)["muros"]
    assert m["estado"] == "sin diseño" and "Design" in m["motivo"]


def test_subseccion_de_muros_en_la_memoria(tmp_path):
    b = bloque_de_prueba()
    b["etabs"] = {**b["etabs"], "muros": fe.etabs_de(tablas_con_muros())["muros"]}
    titulos, texto = documento(tmp_path, {"niveles": [], "bloques": [b]},
                               {"portada": {"titulo": "Edificio", "subtitulo": "Prueba"}})
    cap = next(t for _, t in titulos if t.endswith("Bloque A"))[0]
    assert ("Heading 3", "%s.7.4  Muros" % cap) in titulos
    assert "Diseño de muros por pila" in texto and "Special Structural Wall" in texto
    assert "DWalS1…DWalS16 (16)" in texto
    assert "\n22.00\n" in texto                                       # Av/s de MH1-1 en cm²/m
    assert "1 de 2" in texto
    assert "Pilas asignadas sin resultado de diseño: MH3." in texto
    assert "En 2 de 4 estaciones de muro ETABS reporta que el cortante excede" in texto
    assert "MH2-1 (0.995)" in texto                                   # sobre el límite 0.95
    assert "«Delta_ns exceeds limit»" in texto


def test_sin_diseno_la_memoria_lo_dice(tmp_path):
    b = bloque_de_prueba()
    b["etabs"] = {**b["etabs"], "muros": {"estado": "sin diseño", "motivo": "ETABS no generó la tabla",
                                          "pilas_definidas": ["P1"], "sin_pila": 0}}
    _, texto = documento(tmp_path, {"niveles": [], "bloques": [b]}, {"portada": {"titulo": "E", "subtitulo": "P"}})
    assert "No se incluye el diseño de muros: ETABS no generó la tabla." in texto


class ModeloFalso:
    """Lo mínimo de SapModel que usa _leer_muros."""

    def __init__(self, pilas=1, tablas=None):
        self.PierLabel = type("P", (), {"GetNameList": staticmethod(lambda: (pilas, ("MH1",) * pilas, 0))})()
        datos = tablas or {}

        class DB:
            @staticmethod
            def GetAvailableTables():
                return (len(datos), list(datos), 0)

            @staticmethod
            def GetTableForDisplayArray(clave, *a):
                filas = datos.get(clave, [])
                campos = list(filas[0]) if filas else []
                planos = [v for f in filas for v in f.values()]
                return (0, 0, campos, len(filas), planos, 0)
        self.DatabaseTables = DB()


def test_un_error_cualquiera_en_muros_deja_el_motivo_y_no_tumba_el_bloque(monkeypatch):
    def falla(pid):
        raise ModuleNotFoundError("No module named 'win32gui'")
    monkeypatch.setattr(muros_ui, "disenar_muros", falla)
    r = fe._leer_muros(ModeloFalso(), 1234)
    assert r["_muros"][0]["estado"] == "sin diseño" and "ModuleNotFoundError" in r["_muros"][0]["motivo"]


def test_sin_pilas_no_se_disena(monkeypatch):
    monkeypatch.setattr(muros_ui, "disenar_muros", lambda pid: pytest.fail("no debía diseñar"))
    assert fe._leer_muros(ModeloFalso(pilas=0), 1234) == {}


def test_sin_pid_queda_el_motivo():
    r = fe._leer_muros(ModeloFalso(), None)
    assert "no se identificó el proceso" in r["_muros"][0]["motivo"]


def test_tabla_vacia_no_se_da_por_disenada(monkeypatch):
    monkeypatch.setattr(muros_ui, "disenar_muros", lambda pid: [])
    monkeypatch.setattr(fe, "ESPERA_RESUMEN_MUROS", 0.0)
    r = fe._leer_muros(ModeloFalso(tablas={fe.T_MUROS + " - ACI 318-19": []}), 1234)
    assert "vino vacía" in r["_muros"][0]["motivo"]


def test_resumen_con_filas_se_lee_con_su_codigo(monkeypatch):
    monkeypatch.setattr(muros_ui, "disenar_muros", lambda pid: ["Aviso X"])
    filas = [estacion("MH1", "Story1", "Top", "0.3")]
    r = fe._leer_muros(ModeloFalso(tablas={fe.T_MUROS + " - ACI 318-19": filas}), 1234)
    assert r["_muros"][0] == {"estado": "diseñado", "codigo": "ACI 318-19", "avisos": ["Aviso X"]}
    assert r[fe.T_MUROS][0]["DCRatio"] == "0.3"


def test_pids_de_tasklist(monkeypatch):
    class R:
        stdout = '"ETABS.exe","51124","Console","1","812,000 K"\r\n"ETABS.exe","600","Console","1","1 K"\r\n'
    monkeypatch.setattr(muros_ui.subprocess, "run", lambda *a, **k: R())
    assert muros_ui.pids_etabs() == {51124, 600}
