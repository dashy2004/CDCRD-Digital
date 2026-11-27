"""Pruebas del lector de Losas.exe y del motor de memorias con el sistema de demostración."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
EJEMPLO = RAIZ / "ejemplo"
sys.path.insert(0, str(RAIZ))

import fuentes_losas  # noqa: E402


def correr(*args):
    # el hijo debe escribir en UTF-8 aunque la consola de quien corre las pruebas sea cp1252
    return subprocess.run([sys.executable, *map(str, args)], capture_output=True, text=True, encoding="utf-8",
                          env={**os.environ, "PYTHONIOENCODING": "utf-8"})


def test_el_listado_txt_se_lee_completo_sin_filas_perdidas():
    nivel = fuentes_losas.leer_txt(EJEMPLO / "sistema_demo_27_losas.TXT", "Demo")

    assert nivel["sin_leer"] == []
    assert len(nivel["mom"]) == 27
    assert len(nivel["ax"]) == 27
    assert len(nivel["ay"]) == 27
    assert (len(nivel["apx"]), len(nivel["apy"])) == (13, 9)


def test_el_listado_txt_conserva_encabezado_y_valores_tal_como_estan():
    nivel = fuentes_losas.leer_txt(EJEMPLO / "sistema_demo_27_losas.TXT", "Demo")

    assert nivel["meta"]["version"] == "5.20"
    assert nivel["meta"]["reglamento"] == "ACI 318-08"
    assert nivel["meta"]["fc"] == "210"
    assert nivel["meta"]["fy"] == "4.2"
    assert nivel["mom"]["1"]["Mfx"] == "1.603"
    assert nivel["ax"]["1"]["barra"].endswith("@ 15 cm")


def test_una_losa_sin_armadura_se_registra_con_raya_en_vez_de_perderse(tmp_path):
    txt = tmp_path / "s.TXT"
    txt.write_text('   ARMADURAS SEGÚN "Y"\n\n     5   16.50   0.000   0.000                        0.000\n', encoding="cp1252")

    nivel = fuentes_losas.leer_txt(txt)

    assert nivel["ay"]["5"]["barra"] == "—"
    assert nivel["sin_leer"] == []


def test_una_fila_con_formato_desconocido_queda_reportada(tmp_path):
    txt = tmp_path / "s.TXT"
    txt.write_text("   CÁLCULO DE MOMENTOS\n\n     1    40   0.720  veinte  6.850\n", encoding="cp1252")

    nivel = fuentes_losas.leer_txt(txt)

    assert nivel["mom"] == {}
    assert len(nivel["sin_leer"]) == 1


MOMENTOS = "   CÁLCULO DE MOMENTOS\n\n"
FILA_1 = "     1    40   0.720  20.0  6.850  6.650   1.280   1.358   1.987   2.108\n"


def test_el_fy_del_listado_no_se_sustituye_por_un_valor_fijo(tmp_path):
    txt = tmp_path / "s.TXT"
    txt.write_text("      Hormigón f'c : 280 Kg/cm²\n      Acero    fy  : 2.8 ton/cm²\n" + MOMENTOS + FILA_1, encoding="cp1252")

    nivel = fuentes_losas.leer_txt(txt)

    assert nivel["meta"]["fy"] == "2.8"
    assert nivel["meta"]["fc"] == "280"


def test_una_losa_repetida_no_pisa_a_la_primera_y_queda_reportada(tmp_path):
    txt = tmp_path / "s.TXT"
    txt.write_text(MOMENTOS + FILA_1 + FILA_1.replace("1.280", "9.900"), encoding="cp1252")

    nivel = fuentes_losas.leer_txt(txt)

    assert nivel["mom"]["1"]["Mfx"] == "1.280"
    assert any("repetida" in s for s in nivel["sin_leer"])


def test_un_listado_sin_momentos_legibles_genera_aviso(tmp_path):
    txt = tmp_path / "vacio.TXT"
    txt.write_text("", encoding="cp1252")

    nivel = fuentes_losas.leer_txt(txt)

    assert any("ninguna fila de momentos" in a for a in nivel["avisos"])


def test_el_encabezado_se_reconoce_aunque_el_acento_llegue_en_otra_codificacion(tmp_path):
    txt = tmp_path / "s.TXT"
    txt.write_bytes((MOMENTOS + FILA_1).encode("cp850"))

    nivel = fuentes_losas.leer_txt(txt)

    assert len(nivel["mom"]) == 1


def test_losas_del_dl_sin_resultado_en_el_listado_generan_aviso(tmp_path):
    txt = tmp_path / "s.TXT"
    txt.write_text(MOMENTOS + FILA_1, encoding="cp1252")
    dl = tmp_path / "s.DL"
    dl.write_text("Sistema\n      2       0.210      2.800        0\n"
                  "      1     40     0.720    0.200     6.850    6.650    0.025\n"
                  "      2     40     0.720    0.200     6.850    6.650    0.025\n", encoding="cp1252")

    nivel = fuentes_losas.nivel("N", txt, dl)

    assert any("sin resultado en el listado: 2" in a for a in nivel["avisos"])


def test_armar_datos_falla_con_mensaje_claro_si_falta_un_archivo(tmp_path):
    manifiesto = tmp_path / "fuentes.json"
    manifiesto.write_text(json.dumps({"niveles": [{"nombre": "N", "txt": "no-existe.TXT"}]}), encoding="utf-8")

    r = correr(RAIZ / "armar_datos.py", manifiesto, tmp_path / "data.json")

    assert r.returncode == 1
    assert "no existe el archivo" in r.stderr
    assert not (tmp_path / "data.json").exists()


def test_los_avisos_de_lectura_llegan_al_documento(tmp_path):
    docx = pytest.importorskip("docx")
    txt = tmp_path / "s.TXT"
    txt.write_text(MOMENTOS + FILA_1 + "     2    40   0.720  veinte  6.850\n", encoding="cp1252")
    manifiesto = tmp_path / "fuentes.json"
    manifiesto.write_text(json.dumps({"niveles": [{"nombre": "N", "txt": "s.TXT"}]}), encoding="utf-8")
    correr(RAIZ / "armar_datos.py", manifiesto, tmp_path / "data.json")

    r = correr(RAIZ / "generar.py", tmp_path / "data.json", "", tmp_path / "m.docx", tmp_path / "tmp", tmp_path / "img",
               tmp_path / "memoria.json")

    texto = "\n".join(p.text for p in docx.Document(str(tmp_path / "m.docx")).paragraphs)
    assert r.returncode == 0, r.stderr
    assert "Observaciones para revisión" in texto
    assert "no se pudieron leer" in texto


def test_un_nivel_calculado_por_otro_programa_no_se_atribuye_a_losas_exe(tmp_path):
    docx = pytest.importorskip("docx")
    nivel = {"nombre": "N1", "meta": {"motor": "Pieper-Martens nativo", "fc": "210", "fy": "4.2"}, "esp": {}, "carga": {},
             "mom": {"1": {"tipo": "60", "q": "1.000", "H": "20.0", "Lx": "4.000", "Ly": "5.000",
                           "Mfx": "1.000", "Mfy": "0.800", "Msx": "1.500", "Msy": "1.200"}},
             "ax": {}, "ay": {}, "apx": [], "apy": []}
    (tmp_path / "data.json").write_text(json.dumps({"niveles": [nivel]}), encoding="utf-8")

    r = correr(RAIZ / "generar.py", tmp_path / "data.json", "", tmp_path / "m.docx", tmp_path / "tmp", tmp_path / "img",
               tmp_path / "memoria.json")

    documento = docx.Document(str(tmp_path / "m.docx"))
    texto = "\n".join(p.text for p in documento.paragraphs)
    celdas = "\n".join(c.text for t in documento.tables for fila in t.rows for c in fila.cells)
    assert r.returncode == 0, r.stderr
    assert "LosasPlus (Pieper-Martens nativo)" in texto
    assert "Losas.exe" not in texto + celdas
    assert "espesor mínimo se verifica" not in texto


def test_generar_tolera_un_data_json_sin_claves_opcionales_ni_firmantes(tmp_path):
    pytest.importorskip("docx")
    (tmp_path / "data.json").write_text("{}", encoding="utf-8")
    (tmp_path / "memoria.json").write_text(json.dumps({"portada": {"titulo": "X"}, "firmas": []}), encoding="utf-8")

    r = correr(RAIZ / "generar.py", tmp_path / "data.json", "", tmp_path / "m.docx", tmp_path / "tmp", tmp_path / "img",
               tmp_path / "memoria.json")

    assert r.returncode == 0, r.stderr
    assert (tmp_path / "m.docx").exists()


def test_el_archivo_dl_entrega_materiales_y_una_fila_por_losa():
    dl = fuentes_losas.leer_dl(EJEMPLO / "sistema_demo_27_losas.DL")

    assert len(dl["losas"]) == 27
    assert dl["fc"] == pytest.approx(0.21)
    assert dl["fy"] == pytest.approx(4.2)


def test_el_nivel_combina_txt_y_dl():
    nivel = fuentes_losas.nivel("Demo", EJEMPLO / "sistema_demo_27_losas.TXT", EJEMPLO / "sistema_demo_27_losas.DL")

    assert set(nivel["esp"]) == set(nivel["mom"])
    assert nivel["esp"]["1"]["h"] == "0.25"


def test_armar_y_generar_producen_un_word_sin_datos_de_proyecto(tmp_path):
    docx = pytest.importorskip("docx")
    data, salida, cfg = tmp_path / "data.json", tmp_path / "memoria.docx", tmp_path / "memoria.json"

    r1 = correr(RAIZ / "armar_datos.py", EJEMPLO / "fuentes.json", data)
    r2 = correr(RAIZ / "generar.py", data, "", salida, tmp_path / "tmp", tmp_path / "img", cfg)

    assert r1.returncode == 0, r1.stderr
    assert r2.returncode == 0, r2.stderr
    assert json.loads(data.read_text(encoding="utf-8"))["avisos"] == []
    titulos = [p.text for p in docx.Document(str(salida)).paragraphs if p.style.name.startswith("Heading")]
    assert any("Diseño de losas" in t for t in titulos)
    assert any("Nivel Demo" in t for t in titulos)
    assert not any("Bloque" in t or "Fundaciones" in t for t in titulos)
    assert json.loads(cfg.read_text(encoding="utf-8"))["responsable"]["nombre"] == ""


def test_la_marca_de_agua_se_puede_quitar_desde_memoria_json(tmp_path):
    pytest.importorskip("docx")
    data, cfg = tmp_path / "data.json", tmp_path / "memoria.json"
    correr(RAIZ / "armar_datos.py", EJEMPLO / "fuentes.json", data)
    correr(RAIZ / "generar.py", data, "", tmp_path / "a.docx", tmp_path / "tmp", tmp_path / "img", cfg)
    config = json.loads(cfg.read_text(encoding="utf-8"))
    config["control"]["marca_de_agua"] = ""
    cfg.write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")

    r = correr(RAIZ / "generar.py", data, "", tmp_path / "b.docx", tmp_path / "tmp", tmp_path / "img", cfg)

    import zipfile
    con = "".join(zipfile.ZipFile(tmp_path / "a.docx").read(n).decode("utf-8", "ignore")
                  for n in zipfile.ZipFile(tmp_path / "a.docx").namelist() if n.startswith("word/header"))
    sin = "".join(zipfile.ZipFile(tmp_path / "b.docx").read(n).decode("utf-8", "ignore")
                  for n in zipfile.ZipFile(tmp_path / "b.docx").namelist() if n.startswith("word/header"))
    assert r.returncode == 0, r.stderr
    assert "BORRADOR" in con
    assert "BORRADOR" not in sin
