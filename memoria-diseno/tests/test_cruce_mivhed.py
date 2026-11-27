"""Cruce automático con el checklist de Estructura del MIVHED."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import cruce_mivhed as cm  # noqa: E402
import fuentes_etabs as fe  # noqa: E402
from test_formato_bloque import bloque_de_prueba, documento  # noqa: E402
from test_muros import tablas_con_muros  # noqa: E402

TITULOS = {1: "Descripción del sistema estructural.", 5: "Resistencia a la compresión del hormigón, f’c",
           7: "Norma de especificación de las barras corrugadas de acero", 11: "Acero estructural",
           18: "Dimensiones y armadura de las zapatas", 33: "Cargas de viento", 42: "Diseño de columnas",
           43: "Diseño de muros estructurales.", 46: "Diseño de cimentaciones", 99: "Ítem nuevo"}
MOTIVOS = {33: [("33.1", "No se presenta la determinación de las cargas de viento.")],
           43: [("43.1", "No se presenta el diseño de los muros."), ("43.2", "No se presenta la verificación por cortante."),
                ("43.3", "No se presenta la verificación por flexocompresión."), ("43.6", "Las armaduras no satisfacen.")]}


def checklist():
    return {"codigo": cm.CODIGO, "version": "1.0-draft", "publicadoEn": "2026-08-05T02:50:24",
            "items": [{"numero": n, "descripcion": t,
                       "motivosIncumplimiento": [{"codigo": c, "texto": x} for c, x in MOTIVOS.get(n, [])]}
                      for n, t in TITULOS.items()]}


def config():
    return {"proyecto": [["Proyecto", "Edificio Prueba"], ["Ubicación", "Punta Cana"],
                         ["Sistema estructural", "Pórticos y losas de hormigón armado"]],
            "materiales": [["Concreto", "f'c = 280 kg/cm²"], ["Barra", "fy = 4,200 kg/cm²"]],
            "normas": ["R-033 Reglamento de hormigón."],
            "fundaciones": {"esfuerzo_admisible_ton_m2": 25.0}}


def datos(muros=True):
    b = bloque_de_prueba()
    if muros:
        b["etabs"] = {**b["etabs"], **{k: v for k, v in fe.etabs_de(tablas_con_muros()).items()
                                       if k in ("muros", "area", "area_en_uso")}}
    return {"niveles": [], "bloques": [b], "fundaciones": {
        "proyecto": "Otro proyecto", "concretos": {"C210": 3059.15}, "base": {},
        "presiones": [{"combo": "Comb2", "min": -33.84, "max": -0.1}],
        "punzonado": {"n": 97, "calculados": 3, "sin_calcular": 94}}}


def por_numero(filas):
    return {f["numero"]: f for f in filas}


def test_cada_item_recibe_un_estado_conocido():
    filas = cm.cruzar(datos(), config(), checklist())
    assert [f["numero"] for f in filas] == sorted(TITULOS)
    assert all(f["estado"] in cm.ESTADOS for f in filas)
    f = por_numero(filas)
    assert f[18]["estado"] == cm.PLANOS
    assert f[99]["estado"] == cm.SIN_REVISAR and "Sin regla" in f[99]["nota"]
    assert f[1]["requisito"] == "Descripción del sistema estructural"            # sin punto final


def test_reglas_que_detectan_lo_que_falta_o_no_cuadra():
    f = por_numero(cm.cruzar(datos(), config(), checklist()))
    assert f[1]["estado"] == cm.PARCIAL and "Pórticos" in f[1]["nota"]          # pórticos frente a muros en el espectro
    assert f[5]["estado"] == cm.PARCIAL and "«C210» tiene f'c = 306" in f[5]["nota"]
    assert f[7]["estado"] == cm.PARCIAL and "A615Gr60" in f[7]["nota"]
    assert f[11]["estado"] == cm.NA
    assert f[33]["estado"] == cm.FALTA and [c for c, _ in f[33]["motivos"]] == ["33.1"]
    assert f[46]["estado"] == cm.PARCIAL and "94 de 97" in f[46]["nota"] and "33.84" in f[46]["nota"]


def test_muros_con_hallazgos_citan_sus_motivos():
    f = por_numero(cm.cruzar(datos(), config(), checklist()))[43]
    assert f["estado"] == cm.PARCIAL
    assert [c for c, _ in f["motivos"]] == ["43.1", "43.2", "43.3"]
    assert "cortante sobre el máximo en 2 de 4 estaciones" in f["nota"]


def test_muros_sin_diseno_es_falta():
    d = datos()
    d["bloques"][0]["etabs"]["muros"] = {"estado": "sin diseño", "motivo": "x"}
    f = por_numero(cm.cruzar(d, config(), checklist()))[43]
    assert f["estado"] == cm.FALTA and [c for c, _ in f["motivos"]] == ["43.1"]


def test_sin_muros_no_aplica():
    f = por_numero(cm.cruzar(datos(muros=False), config(), checklist()))[43]
    assert f["estado"] == cm.NA


def test_norma_citada_en_la_memoria():
    c = config()
    c["materiales"].append(["Norma", "ASTM A615 grado 60"])
    assert por_numero(cm.cruzar(datos(), c, checklist()))[7]["estado"] == cm.ESTA


def test_markdown_y_cli(tmp_path):
    (tmp_path / "d.json").write_text(json.dumps(datos()), encoding="utf-8")
    (tmp_path / "m.json").write_text(json.dumps(config()), encoding="utf-8")
    (tmp_path / "c.json").write_text(json.dumps({"checklists": [checklist()]}), encoding="utf-8")
    assert cm.main(["x", str(tmp_path / "d.json"), str(tmp_path / "m.json"), str(tmp_path / "c.json"),
                    str(tmp_path / "s.md")]) == 0
    md = (tmp_path / "s.md").read_text(encoding="utf-8")
    assert md.startswith("# Edificio Prueba — cruce") and "| 43 | Diseño de muros estructurales | Parcial |" in md
    assert "## Pendientes" in md


def test_checklist_sin_estructura_da_error(tmp_path):
    (tmp_path / "c.json").write_text(json.dumps({"checklists": []}), encoding="utf-8")
    try:
        cm.cargar_checklist(str(tmp_path / "c.json"))
    except cm.ErrorDeChecklist:
        return
    raise AssertionError("debía fallar")


def test_anexo_en_la_memoria(tmp_path):
    (tmp_path / "c.json").write_text(json.dumps({"checklists": [checklist()]}), encoding="utf-8")
    cfg = {**config(), "portada": {"titulo": "E", "subtitulo": "P"}, "checklist_mivhed": "c.json"}
    titulos, texto = documento(tmp_path, datos(), cfg)
    assert any("Cruce con el checklist de Estructura del MIVHED" in t for _, t in titulos)
    assert "Estado por ítem del checklist" in texto and "Motivos 43.1, 43.2, 43.3." in texto
    assert "Dimensiones y armadura de las zapatas" not in texto                # los de planos no se listan
