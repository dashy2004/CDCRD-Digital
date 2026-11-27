"""Ciclo de vida de la instancia de ETABS/SAFE y caché de lo leído, con un `comtypes` falso."""
import json
import os
import sys
import types

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import armar_datos  # noqa: E402
import fuentes_etabs as fe  # noqa: E402
import fuentes_safe as fs  # noqa: E402
from test_fuentes_directas import tablas_minimas  # noqa: E402
from test_fuentes_safe import tablas as tablas_safe  # noqa: E402


class AppFalsa:
    """Programa falso: registra lo que se abre y si se cierra; puede fallar en un paso."""

    def __init__(self, falla_en=None):
        self.falla_en, self.abiertos, self.cerrado = falla_en, [], 0
        self.SapModel = types.SimpleNamespace(
            File=types.SimpleNamespace(OpenFile=self._abrir),
            SetPresentUnits=lambda u: 0,
            Analyze=types.SimpleNamespace(RunAnalysis=lambda: 1 if falla_en == "analisis" else 0),
            DesignConcrete=types.SimpleNamespace(StartDesign=lambda: 0),
            DesignConcreteSlab=types.SimpleNamespace(StartSlabDesign=lambda: 0),
            DatabaseTables=types.SimpleNamespace(
                GetAvailableTables=lambda: (0, [], [], [], 0),
                GetTableForDisplayArray=lambda *a: ([], 0, [], 0, [], 0),
                SetLoadCasesSelectedForDisplay=lambda x: ((), 0),
                SetLoadCombinationsSelectedForDisplay=lambda x: ((), 0)),
            GetVersion=lambda: ("0.0.0", 0.0, 0))

    def ApplicationStart(self):
        return 1 if self.falla_en == "arranque" else 0

    def _abrir(self, ruta):
        self.abiertos.append(ruta)
        return 0

    def ApplicationExit(self, guardar):
        self.cerrado += 1
        return 0


@pytest.fixture
def comtypes_falso(monkeypatch):
    def instalar(app):
        helper = types.SimpleNamespace(CreateObjectProgID=lambda pid: app)
        helper.QueryInterface = lambda interfaz: helper
        cliente = types.ModuleType("comtypes.client")
        cliente.CreateObject = lambda pid: helper
        paquete, gen, etabs = types.ModuleType("comtypes"), types.ModuleType("comtypes.gen"), types.ModuleType("comtypes.gen.ETABSv1")
        etabs.cHelper = object()
        paquete.client, paquete.gen, gen.ETABSv1 = cliente, gen, etabs
        for nombre, mod in (("comtypes", paquete), ("comtypes.client", cliente), ("comtypes.gen", gen),
                            ("comtypes.gen.ETABSv1", etabs)):
            monkeypatch.setitem(sys.modules, nombre, mod)
        return app
    return instalar


@pytest.mark.parametrize("modulo, error, ext", [(fe, fe.ErrorDeEtabs, ".EDB"), (fs, fs.ErrorDeSafe, ".FDB")])
@pytest.mark.parametrize("falla_en", ["arranque", "analisis"])
def test_el_programa_se_cierra_aunque_falle_y_el_original_no_se_abre(tmp_path, comtypes_falso, modulo, error, ext, falla_en):
    original = tmp_path / ("modelo" + ext)
    original.write_bytes(b"contenido original")
    app = comtypes_falso(AppFalsa(falla_en))

    with pytest.raises(error):
        modulo.leer_tablas(str(original), str(tmp_path / "trabajo"))

    assert app.cerrado == 1
    assert all(os.path.normcase(a) != os.path.normcase(str(original)) for a in app.abiertos)
    assert original.read_bytes() == b"contenido original"


def test_la_carpeta_de_corrida_se_vacia_entre_modelos(tmp_path):
    a, b = tmp_path / "a.EDB", tmp_path / "b.EDB"
    a.write_bytes(b"A")
    b.write_bytes(b"B")
    copia = fe._copiar_modelo(str(a), str(tmp_path / "t"))
    resto = os.path.join(os.path.dirname(copia), "resultados-de-a.Y01")
    open(resto, "w").close()

    copia_b = fe._copiar_modelo(str(b), str(tmp_path / "t"))

    assert open(copia_b, "rb").read() == b"B" and not os.path.exists(resto)


def test_deriva_negativa_cuenta_en_valor_absoluto():
    t = tablas_minimas()
    t[fe.T_DERIVAS] = [{"Story": "Story2", "OutputCase": "C", "Direction": "X", "Drift": "-0.0041"},
                       {"Story": "Story2", "OutputCase": "C", "Direction": "X", "Drift": "0.0012"}]
    assert fe.etabs_de(t)["drift"] == {"Story2|C|X": 0.0041}


def test_nudo_con_varias_filas_conserva_el_maximo_y_el_exceso():
    t = tablas_minimas()
    largo = "x" * 150 + " Beam/Column capacity ratio exceeds limit"
    t[fe.T_NUDOS] = [
        {"Story": "Story2", "UniqueName": "10", "BCMajRatio": None, "BCMinRatio": "0.70", "JSMajRatio": "1.20",
         "JSMinRatio": "0.4", "WarnMsg": "No Message", "ErrMsg": largo},
        {"Story": "Story2", "UniqueName": "10", "BCMajRatio": "0.95", "BCMinRatio": "0.60", "JSMajRatio": "0.30",
         "JSMinRatio": "0.2", "WarnMsg": "No Message", "ErrMsg": "No Message"}]
    j = fe.etabs_de(t)["joint"]["Story2"]
    assert (j["n"], j["bc"], j["js"], j["bc_gt1"], j["bc_sin_valor"], j["js_gt1"]) == (1, 0.95, 1.20, 1, 1, 1)


# ------------------------------------------------------------------ caché de armar_datos
def manifiesto(tmp_path, cuerpo):
    p = tmp_path / "fuentes.json"
    p.write_text(json.dumps(cuerpo), encoding="utf-8")
    return str(p)


def test_las_tablas_de_etabs_se_reutilizan_hasta_que_el_modelo_cambia(tmp_path, monkeypatch):
    modelo = tmp_path / "bloque.EDB"
    modelo.write_bytes(b"v1")
    llamadas = []
    monkeypatch.setattr(fe, "leer_tablas", lambda m, c, d=False: llamadas.append(m) or tablas_minimas())
    man = manifiesto(tmp_path, {"bloques": [{"nombre": "Bloque A", "etabs": "bloque.EDB"}]})

    primero = armar_datos.armar(man)
    armar_datos.armar(man)
    assert len(llamadas) == 1 and primero["bloques"][0]["etabs"]["modelo"] == "Modelo de prueba"

    modelo.write_bytes(b"version 2, otro tamano")
    armar_datos.armar(man)
    assert len(llamadas) == 2


def test_cache_danada_se_trata_como_ausente(tmp_path, monkeypatch):
    (tmp_path / "bloque.EDB").write_bytes(b"v1")
    llamadas = []
    monkeypatch.setattr(fe, "leer_tablas", lambda m, c, d=False: llamadas.append(m) or tablas_minimas())
    man = manifiesto(tmp_path, {"bloques": [{"nombre": "Bloque A", "etabs": "bloque.EDB"}]})
    armar_datos.armar(man)
    carpeta = next(p for p in (tmp_path / "_trabajo").iterdir())
    (carpeta / "tablas.json").write_text("{ truncado", encoding="utf-8")

    armar_datos.armar(man)

    assert len(llamadas) == 2


def test_un_fallo_del_programa_sale_como_error_de_fuentes(tmp_path, monkeypatch):
    (tmp_path / "bloque.EDB").write_bytes(b"v1")
    (tmp_path / "f.FDB").write_bytes(b"v1")

    def falla(*a, **k):
        raise PermissionError("archivo en uso")

    monkeypatch.setattr(fe, "leer_tablas", falla)
    monkeypatch.setattr(fs, "leer_tablas", falla)
    with pytest.raises(armar_datos.ErrorDeFuentes, match="Bloque A: PermissionError"):
        armar_datos.armar(manifiesto(tmp_path, {"bloques": [{"nombre": "Bloque A", "etabs": "bloque.EDB"}]}))
    with pytest.raises(armar_datos.ErrorDeFuentes, match="fundaciones: PermissionError"):
        armar_datos.armar(manifiesto(tmp_path, {"fundaciones": {"safe": "f.FDB"}}))


def test_el_capitulo_de_fundaciones_convierte_unidades_y_compara_con_el_admisible(tmp_path):
    docx = pytest.importorskip("docx")
    import subprocess

    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    datos = {"niveles": [], "bloques": [], "fundaciones": fs.fundaciones_de(tablas_safe())}
    (tmp_path / "data.json").write_text(json.dumps(datos), encoding="utf-8")
    (tmp_path / "memoria.json").write_text(json.dumps({
        "portada": {"titulo": "Edificio", "subtitulo": "Prueba"},
        "fundaciones": {"texto": "", "esfuerzo_admisible_ton_m2": 25.0}}), encoding="utf-8")
    salida = tmp_path / "m.docx"

    r = subprocess.run([sys.executable, os.path.join(raiz, "generar.py"), str(tmp_path / "data.json"), "", str(salida),
                        str(tmp_path / "tmp"), str(tmp_path / "img"), str(tmp_path / "memoria.json")],
                       capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    assert r.returncode == 0, r.stderr
    doc = docx.Document(str(salida))
    texto = "\n".join(p.text for p in doc.paragraphs) + "\n" + "\n".join(
        c.text for t in doc.tables for fila in t.rows for c in fila.cells)
    assert "f'c = 210 kg/cm²" in texto                 # 2100 tonf/m² -> 210 kg/cm²
    assert "27.30" in texto and "2.73" in texto        # 27.3 ton/m² -> 2.73 kg/cm²
    assert "Excede" in texto
    assert "superan el esfuerzo admisible de 25.0 ton/m²" in texto
    assert "relación de punzonado mayor que 1.00" in texto
    assert "«Otro proyecto»" in texto                  # el nombre de proyecto del modelo no coincide con la portada
    assert "despegue" not in texto                     # presión máxima negativa: no hay tracción


def test_fundaciones_entran_en_data_json(tmp_path, monkeypatch):
    (tmp_path / "f.FDB").write_bytes(b"v1")
    monkeypatch.setattr(fs, "leer_tablas", lambda m, c: tablas_safe())
    data = armar_datos.armar(manifiesto(tmp_path, {"fundaciones": {"safe": "f.FDB"}}))
    assert data["fundaciones"]["presiones"][0]["combo"] == "Comb1"
