# -*- coding: utf-8 -*-
"""auditar_conectores, ejecutor y compatibilidad de sintaxis."""
import ast
import json
import pathlib

import pytest

import dobles
from dobles import Aparato, Conector, Documento, Luminaria, crear_db, mm
from mep import ErrorEntrada, auditar_conectores, ejecutar

PAQUETE = pathlib.Path(__file__).resolve().parents[1] / "mep"


class ConectorLogico(Conector):
    @property
    def IsConnected(self):
        raise AssertionError("IsConnected no se consulta en conectores logicos")


def modelo():
    sistema = dobles.ns(Id=dobles.ElementId(900), Name="Sanitario 1")
    lavabo = Aparato(1, [
        Conector(0, (1, 2, 3), radio=mm(25.0)),
        Conector(1, (1, 2, 3), radio=mm(12.5), clase="DomesticColdWater",
                 conectado=True, sistema=sistema)])
    lavabo.bic = "OST_PlumbingFixtures"
    rejilla = Aparato(2, [Conector(0, (0, 0, 0), dominio="DomainHvac",
                                   clase="SupplyAir", forma="Rectangular")])
    rejilla.bic = "OST_DuctTerminal"
    luminaria = Luminaria(3)
    luminaria.conectores.append(ConectorLogico(
        1, (0, 0, 0), dominio="DomainElectrical", clase="PowerBalanced",
        tipo="Logical"))
    return Documento([lavabo, rejilla, luminaria]), crear_db()


def test_conteos_libres_y_dominios():
    doc, db = modelo()
    r = auditar_conectores(db, doc)
    json.dumps(r)
    t = r["totales"]
    assert (t["elementos"], t["conectores"], t["libres"]) == (3, 5, 3)
    assert t["elementos_con_libres"] == 3
    assert t["por_dominio"] == {"tuberia": {"total": 2, "libres": 1},
                                "ducto": {"total": 1, "libres": 1},
                                "electrico": {"total": 2, "libres": 1}}
    assert t["por_clasificacion"]["Sanitary"] == 1
    assert t["por_diametro_mm"] == {"50.00": 1, "25.00": 1}
    assert r["estado"] == "completo" and r["solo_lectura"] is True
    assert doc.bitacora == []  # ni transaccion ni regeneracion


def test_ficha_de_conector_sistema_y_diametro():
    doc, db = modelo()
    r = auditar_conectores(db, doc, ids=[1])
    libre, conectado = r["elementos"][0]["conectores"]
    assert libre["libre"] is True and libre["diametro_mm"] == 50.0
    assert libre["radio_interno_pies"] == pytest.approx(mm(25.0))
    assert libre["posicion_m"] == pytest.approx([0.3048, 0.6096, 0.9144])
    assert conectado["libre"] is False and conectado["sistema"] == "Sanitario 1"
    assert conectado["sistema_id"] == 900
    assert conectado["clasificacion"] == "DomesticColdWater"


def test_diametro_solo_en_tuberia_redonda_y_logicos_sin_estado():
    doc, db = modelo()
    r = auditar_conectores(db, doc, categorias=["OST_DuctTerminal",
                                                "OST_LightingFixtures"])
    ducto = r["elementos"][0]["conectores"][0]
    assert ducto["diametro_mm"] is None and ducto["forma"] == "Rectangular"
    logico = r["elementos"][1]["conectores"][1]
    assert logico["conectado"] is None and logico["libre"] is False


def test_error_de_lectura_deja_estado_parcial_y_registro():
    doc, db = modelo()

    class Roto(Conector):
        @property
        def IsConnected(self):
            raise RuntimeError("conector invalido")

    doc.elementos[1].conectores.append(Roto(2, (0, 0, 0)))
    r = auditar_conectores(db, doc, ids=[1])
    assert r["estado"] == "parcial" and r["elementos"][0]["estado"] == "parcial"
    assert r["errores"][0]["mensaje"] == "conector invalido"
    assert r["totales"]["conectores"] == 2


def test_limite_de_detalle_no_recorta_totales():
    doc, db = modelo()
    r = auditar_conectores(db, doc, max_elementos=1)
    assert len(r["elementos"]) == 1 and r["truncado"] is True
    assert r["totales"]["conectores"] == 5


@pytest.mark.parametrize("kw", [
    {"ids": [1], "categorias": ["OST_Sprinklers"]}, {"ids": []}, {"ids": [77]},
    {"categorias": ["Paredes"]}, {"categorias": ["OST_NoExiste"]},
    {"categorias": []}, {"max_elementos": -1}])
def test_entrada_invalida(kw):
    doc, db = modelo()
    with pytest.raises(ErrorEntrada):
        auditar_conectores(db, doc, **kw)


# --------------------------------------------------------------- ejecutor

def test_correr_despacha_y_nunca_lanza():
    doc, db = modelo()
    assert ejecutar.correr("conectores", {"ids": [1]}, doc, db)["ok"] is True
    malo = ejecutar.correr("conectar", {"pendiente": 0.01}, doc, db)
    assert malo["ok"] is False and malo["tipo_error"] == "entrada"
    otro = ejecutar.correr("borrar_todo", {}, doc, db)
    assert otro["ok"] is False and "desconocida" in otro["error"]
    assert ejecutar.correr("conectores", {"x": 1}, doc, db)["ok"] is False
    interno = ejecutar.correr("conectores", {}, object(), db)
    assert interno["ok"] is False and interno["tipo_error"] == "interno"


def test_correr_conectar_y_circuitos_en_ensayo():
    doc, db = dobles.modelo_sanitario()
    r = ejecutar.correr("conectar", dobles.opciones_conectar(), doc, db)
    assert r["ok"] is True and r["ensayo"] is True
    doc, db = dobles.modelo_electrico([Luminaria(2001)])
    r = ejecutar.correr("circuitos", {"tablero": 700, "limite_va": 100}, doc, db)
    assert r["ok"] is True and r["confirmado"] is False


def test_resolver_documento():
    doc, _ = modelo()
    otro = Documento()
    otro.Title, otro.PathName = "segundo_plano", "c:/sintetico/segundo.rvt"
    vinculo = Documento()
    vinculo.Title, vinculo.IsLinked = "vinculo", True
    doc.Application = dobles.ns(Documents=[doc, otro, vinculo])
    assert ejecutar.resolver_documento(doc, None) is doc
    assert ejecutar.resolver_documento(doc, "segundo_plano") is otro
    assert ejecutar.resolver_documento(doc, "C:/Sintetico/Segundo.rvt") is otro
    for mala in ("vinculo", "no abierto", "", 5):
        with pytest.raises(ErrorEntrada):
            ejecutar.resolver_documento(doc, mala)


def test_recargar_descarta_los_modulos_del_paquete():
    import sys
    guardados = dict((n, m) for n, m in sys.modules.items()
                     if n == "mep" or n.startswith("mep."))
    try:
        assert "mep.trazado" in ejecutar.recargar()
        assert "mep" not in sys.modules
    finally:
        sys.modules.update(guardados)


# ----------------------------------------------------- reglas del paquete

PROHIBIDOS = tuple(getattr(ast, n) for n in (
    "JoinedStr", "NamedExpr", "Match", "AnnAssign", "AsyncFunctionDef",
    "Await", "MatMult") if hasattr(ast, n))


@pytest.mark.parametrize("ruta", sorted(PAQUETE.glob("*.py")),
                         ids=lambda r: r.name)
def test_sintaxis_apta_para_ironpython_34_y_reglas_del_encargo(ruta):
    texto = ruta.read_text(encoding="utf-8")
    arbol = ast.parse(texto)
    for nodo in ast.walk(arbol):
        assert not isinstance(nodo, PROHIBIDOS), "%s: %s linea %d" % (
            ruta.name, type(nodo).__name__, nodo.lineno)
        if isinstance(nodo, (ast.List, ast.Tuple, ast.Set, ast.Call)):
            hijos = getattr(nodo, "elts", None) or getattr(nodo, "args", [])
            assert sum(isinstance(h, ast.Starred) for h in hijos) <= (
                1 if isinstance(nodo, ast.Call) else 0)
        if isinstance(nodo, ast.FunctionDef):
            assert not nodo.args.kwonlyargs and nodo.returns is None
            assert nodo.end_lineno - nodo.lineno < 50, nodo.name
        if isinstance(nodo, ast.ExceptHandler):
            solo_pass = all(isinstance(s, ast.Pass) for s in nodo.body)
            assert not solo_pass, "except vacio en %s:%d" % (ruta.name, nodo.lineno)
        if isinstance(nodo, ast.Attribute):
            assert nodo.attr not in ("Save", "SaveAs", "IntegerValue"), (
                "%s usa %s" % (ruta.name, nodo.attr))
    assert "dataclass" not in texto and "import typing" not in texto
    assert "Autodesk" not in "".join(
        l for l in texto.splitlines() if l.startswith(("import", "from")))
