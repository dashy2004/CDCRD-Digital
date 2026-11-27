"""Formato del capítulo de bloque y de fundaciones: qué se muestra, qué se omite y cómo se numera."""
import json
import os
import subprocess
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import fuentes_etabs as fe  # noqa: E402
import fuentes_excel as fx  # noqa: E402
import fuentes_safe as fs  # noqa: E402
from test_fuentes_directas import hoja, tablas_minimas  # noqa: E402
from test_fuentes_safe import tablas as tablas_safe  # noqa: E402

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_secciones_en_uso_salen_de_las_asignaciones():
    t = tablas_minimas()
    t[fe.T_PORTICO].append({"Name": "C9", "Material": "C280", "Shape": "Concrete Rectangular", "Area": "0.25",
                            "I33": "0.0052", "I22": "0.0052", "JMod": "1", "I3Mod": "0.8", "I2Mod": "0.8"})
    t[fe.T_AREA].append({"Name": "L20", "Type": "Slab", "AnalType": "Shell-Thin", "Material": "C210", "TotalThick": "0.2"})
    assert fe.etabs_de(t)["frame_en_uso"] is None                    # sin tabla de asignaciones no se filtra nada
    t[fe.T_ASIG_PORTICO] = [{"Story": "Story2", "UniqueName": "10", "AnalysisSect": "C1", "DesignSect": "C1"}]
    t[fe.T_ASIG_AREA] = [{"Story": "Story2", "UniqueName": "30", "SectProp": "L15"}]
    e = fe.etabs_de(t)
    assert e["frame_en_uso"] == ["C1"] and e["area_en_uso"] == ["L15"]


def test_cuasiestatico_trae_la_carga_viva_de_cada_uso_junto_a_su_factor():
    libro = {"Cuasiestatico": hoja({
        (0, 0): "CORTANTE BASAL",
        (1, 0): "Carga Muerta:", (1, 2): 3000.0,
        (2, 0): "Entrepisos:", (2, 1): 0.15, (2, 2): 500.0,
        (3, 0): "Común:", (3, 1): 0.25,
        (4, 0): "Techo:", (4, 1): 0.1, (4, 2): 80.0,
        (5, 0): "Carga Total de Edificio:", (5, 2): 3083.0,
        (6, 0): "V x-x =", (6, 1): 590.0, (6, 3): "V y-y =", (6, 4): 590.0,
    })}
    c = fx.cuasi_de(libro)
    assert (c["viva_entrepiso"], c["viva_comun"], c["viva_techo"]) == (500.0, None, 80.0)
    assert (c["phi_entrepiso"], c["phi_comun"], c["phi_techo"]) == (0.15, 0.25, 0.1)


def documento(tmp_path, datos, config):
    docx = pytest.importorskip("docx")
    (tmp_path / "data.json").write_text(json.dumps(datos), encoding="utf-8")
    (tmp_path / "memoria.json").write_text(json.dumps(config), encoding="utf-8")
    salida = tmp_path / "m.docx"
    r = subprocess.run([sys.executable, os.path.join(RAIZ, "generar.py"), str(tmp_path / "data.json"), "", str(salida),
                        str(tmp_path / "tmp"), str(tmp_path / "img"), str(tmp_path / "memoria.json")],
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    assert r.returncode == 0, r.stderr
    doc = docx.Document(str(salida))
    titulos = [(p.style.name, p.text) for p in doc.paragraphs if p.style.name.startswith("Heading")]
    texto = "\n".join(p.text for p in doc.paragraphs) + "\n" + "\n".join(
        c.text for t in doc.tables for fila in t.rows for c in fila.cells)
    return titulos, texto


def bloque_de_prueba():
    t = tablas_minimas()
    t[fe.T_PORTICO] += [
        {"Name": "V3070", "Material": "C280", "Shape": "Concrete Rectangular", "Area": "0.21", "I33": "0.008575",
         "I22": "0.001575", "JMod": "0.05", "I3Mod": "0.6", "I2Mod": "0.6"},
        {"Name": "V9999", "Material": "C280", "Shape": "Concrete Rectangular", "Area": "0.5", "I33": "0.01",
         "I22": "0.01", "JMod": "0.05", "I3Mod": "0.6", "I2Mod": "0.6"}]
    t[fe.T_AREA].append({"Name": "L99", "Type": "Slab", "AnalType": "Shell-Thin", "Material": "C210", "TotalThick": "0.99"})
    t[fe.T_ASIG_PORTICO] = [{"UniqueName": "10", "AnalysisSect": "C1"}, {"UniqueName": "20", "AnalysisSect": "V3070"}]
    t[fe.T_ASIG_AREA] = [{"UniqueName": "30", "SectProp": "L15"}]
    t[fe.T_VIGAS][0]["ErrMsg"] = "Shear stress due to shear force and torsion together exceeds maximum allowed."
    t[fe.T_MODAL][0].update({"SumUX": "0.8081", "SumUY": "0.9997"})
    cuasi = {"pisos": 2, "htotal": 6.95, "dx": 40.0, "dy": 18.0, "muerta": 3000.0, "viva_part": 83.0, "total": 3083.0,
             "viva_entrepiso": 500.0, "viva_comun": None, "viva_techo": 80.0,
             "phi_entrepiso": 0.15, "phi_comun": 0.25, "phi_techo": 0.1, "Ct": 0.046, "X": 0.9, "Ko": 0.07, "Ta": [0.57],
             "Tx1": 0.17, "Ty1": 0.27, "Tx": 0.17, "Ty": 0.27, "CBX": 0.19, "CBY": 0.19, "Vx": 590.0, "Vy": 590.0,
             "Vx65": 383.5, "Vy65": 383.5, "Ex": [506.39, "OK", 0.76], "texto_cargas": []}
    espectro = {"proyecto": "P", "uso": "Apartamentos", "ubicacion": "Ciudad", "pisos": 2, "h1": 3.7, "hotros": 3.25,
                "htotal": 6.95, "dx": 40.0, "dy": 18.0, "I": "IV", "Z": "2", "U": "1", "S": "C", "sistema": "Pórticos",
                "Rd": 4.0, "Rd_final": 4.0, "Rd_nota": "sin reducción", "Ss": 1.15, "S1": 0.62, "Fa": 1.0, "Fv": 1.3,
                "SDS": 7.52, "SD1": 5.27, "To": 0.14, "Ts": 0.70}
    art38 = [{"caso": "1", "filas": [{"story": 1, "rx1": 1.01, "rx2": 1.02, "ry1": 1.1, "ry2": 1.1, "ok": ["Ok"]}]}]
    return {"nombre": "Bloque A", "paginas": {}, "espectro": espectro, "tabla_espectro": [], "torsion": [], "art38": art38,
            "cuasi": cuasi, "etabs": fe.etabs_de(t)}


def test_capitulo_de_bloque_con_el_formato_pedido(tmp_path):
    titulos, texto = documento(tmp_path, {"niveles": [], "bloques": [bloque_de_prueba()]},
                               {"portada": {"titulo": "Edificio", "subtitulo": "Prueba"}})
    nombres = [t for _, t in titulos]
    cap = next(t for t in nombres if t.endswith("Bloque A"))[0]

    # subtítulos de tercer nivel numerados bajo su título de segundo nivel
    assert ("Heading 3", "%s.5.1  Niveles y masa" % cap) in titulos
    assert ("Heading 3", "%s.7.2  Vigas" % cap) in titulos
    assert not any("Mensajes del programa" in t for t in nombres)
    # torsión tomada del modelo: solo la viga en uso
    assert "Modificador de la constante de torsión J asignado en ETABS" in texto
    assert "no incluyen la hoja de reducción" not in texto
    # solo secciones asignadas
    assert "V9999" not in texto and "L99" not in texto and "V3070" in texto
    # peso sísmico detallado
    assert "Peso sísmico: cargas muertas y vivas consideradas" in texto
    assert "Carga viva de entrepisos" in texto and "75.00" in texto           # 500 × 0.15
    # Art. 38 con unidades
    assert "X, caso 1 (adim.)" in texto and "(adimensional)" in texto
    # vigas sin la columna de mensajes, y sin tabla de mensajes
    assert "Con mensaje" not in texto and "Mensajes de diseño emitidos por ETABS" not in texto
    assert "estación(es) de viga con el mensaje" in texto                      # la observación se conserva
    # participación de masa por debajo del 90 %
    assert "por debajo del 90 %: ΣUX = 80.8 %" in texto


def test_indice_sigue_en_dos_niveles():
    fuente = open(os.path.join(RAIZ, "generar.py"), encoding="utf-8").read()
    assert 'TOC \\\\o "1-2"' in fuente


def test_fundaciones_solo_propiedades_en_uso_y_combinaciones_pedidas(tmp_path):
    t = tablas_safe()
    t[fs.T_LOSAS].append({"Name": "S80", "PropType": "Stiff", "Material": "C210", "Thickness": "0.8"})
    t[fs.T_ASIG_AREA] = [{"UniqueName": "1", "SectProp": "S50"}]
    t[fs.T_COMBOS].insert(2, {"Name": "Comb2", "Type": "Linear Add", "IsAuto": "No", "LoadName": "Dead", "SF": "1"})
    t[fs.T_COMBOS][-1]["LoadName"] = "Comb2"                          # la envolvente agrupa Comb2
    t[fs.R_PRESIONES] = [{"combo": "Comb1", "n": 3, "min": -11.11, "max": -0.1},
                         {"combo": "Comb2", "n": 3, "min": -22.22, "max": -0.1}]
    datos = {"niveles": [], "bloques": [], "fundaciones": fs.fundaciones_de(t)}
    config = {"portada": {"titulo": "Otro", "subtitulo": "proyecto"},
              "fundaciones": {"texto": "", "esfuerzo_admisible_ton_m2": 25.0, "combinaciones": ["Comb2", "Envelope", "Comb77"]}}

    _, texto = documento(tmp_path, datos, config)

    assert "\nS50\n" in texto and "\nS80\n" not in texto
    assert "22.22" in texto and "11.11" not in texto                  # Comb1 no se muestra
    assert "Envolvente de Comb2" in texto
    assert "pide mostrar combinaciones que el modelo no tiene: Comb77" in texto
