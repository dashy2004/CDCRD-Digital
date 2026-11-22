# -*- coding: utf-8 -*-
"""conectar_a_ramal con dobles de la API. Nada de esto corre en Revit."""
import json

import pytest

import dobles
from dobles import mm, modelo_sanitario, opciones_conectar
from mep import ErrorEntrada, conectar_a_ramal, geometria


def correr(doc, db, **extra):
    resultado = conectar_a_ramal(db, doc, opciones_conectar(**extra))
    json.dumps(resultado)  # la salida debe ser serializable
    return resultado


# ------------------------------------------------------------ validacion

@pytest.mark.parametrize("cambio, fragmento", [
    ({"pendiente": None}, "pendiente"),
    ({"pendiente": -0.01}, "pendiente"),
    ({"pendiente": 0.9}, "pendiente"),
    ({"pendiente": "2%"}, "pendiente"),
    ({"ramal": 999}, "inexistentes"),
    ({"ramal": 1001}, "no es una tuberia"),
    ({"ramal": None}, "ramal"),
    ({"tipo_tuberia": 300}, "PipeType"),
    ({"tipo_tuberia": "no existe"}, "no hay tipo"),
    ({"tipo_sistema": 200}, "PipingSystemType"),
    ({"union": "soldada"}, "union"),
    ({"lote": 0}, "lote"),
    ({"desde": 5}, "desde"),
    ({"confirmar": "si"}, "confirmar"),
    ({"categoria": "OST_Walls"}, "categoria"),
    ({"aparatos": [1001]}, "uno solo"),
    ({"categoria": None, "aparatos": [1001, 4242]}, "inexistentes"),
    ({"diametro_mm": 0}, "diametro_mm"),
    ({"inventada": 1}, "desconocidas"),
])
def test_entrada_invalida_falla_antes_de_abrir_transaccion(cambio, fragmento):
    doc, db = modelo_sanitario()
    opciones = opciones_conectar(**cambio)
    opciones = dict((k, v) for k, v in opciones.items() if v is not None)
    with pytest.raises(ErrorEntrada) as error:
        conectar_a_ramal(db, doc, opciones)
    assert fragmento in str(error.value)
    assert doc.bitacora == []


def test_nombre_de_tipo_ambiguo_se_rechaza():
    doc, db = modelo_sanitario()
    repetido = dobles.TipoTuberia(201)
    repetido.Name = "PVC sintetico"
    doc.elementos[201] = repetido
    with pytest.raises(ErrorEntrada) as error:
        correr(doc, db, tipo_tuberia="PVC sintetico")
    assert "ambiguo" in str(error.value)


def test_tipos_y_nivel_por_nombre():
    doc, db = modelo_sanitario()
    r = correr(doc, db, tipo_tuberia="PVC sintetico",
               tipo_sistema="Sanitario sintetico", nivel="Nivel 1")
    assert r["resumen"]["conectado"] == 1


def test_documento_vinculado_o_con_transaccion_abierta_se_rechaza():
    doc, db = modelo_sanitario()
    doc.IsModifiable = True
    with pytest.raises(ErrorEntrada):
        correr(doc, db)


# ------------------------------------------------------- ensayo / commit

def test_ensayo_por_defecto_revierte_y_no_confirma():
    doc, db = modelo_sanitario()
    antes = set(doc.elementos)
    r = correr(doc, db)
    assert r["ensayo"] is True and r["confirmado"] is False
    assert r["estado"] == "RolledBack" and r["ids_efimeros"] is True
    # el ensayo confirma de verdad dentro de un grupo y revierte el grupo
    assert r["commit_de_ensayo"] == "Committed" and r["ensayo_valido"] is True
    assert doc.bitacora[0] == "GroupStart" and doc.bitacora[-1] == "GroupRolledBack"
    assert doc.bitacora.index("Committed") < doc.bitacora.index("GroupRolledBack")
    assert set(doc.elementos) == antes
    # verificado dentro de la transaccion: hay datos aunque ya no hay obra
    assert r["resumen"]["conectado"] == 1 and r["sueltos"] == []
    assert doc.bitacora.index("Regenerate") < doc.bitacora.index("Committed")
    assert doc.elementos[1001].conectores[0].IsConnected is False


def test_confirmar_hace_commit_y_deja_la_obra():
    doc, db = modelo_sanitario()
    r = correr(doc, db, confirmar=True)
    assert r["ensayo"] is False and r["confirmado"] is True
    assert doc.bitacora[-1] == "Committed" and "RolledBack" not in doc.bitacora
    fila = r["conexiones"][0]
    assert fila["estado"] == "conectado" and fila["union_aparato"] == "ConnectTo"
    assert len(fila["tuberias"]) == 2 and len(fila["accesorios"]) == 2
    assert all(i in doc.elementos for i in fila["tuberias"] + fila["accesorios"])
    assert doc.elementos[1001].conectores[0].IsConnected is True
    assert len(r["ramales_siguientes"]) == 2


def test_commit_que_revit_no_acepta_no_se_reporta_confirmado():
    doc, db = modelo_sanitario()
    doc.estado_commit = "RolledBack"
    r = correr(doc, db, confirmar=True)
    assert r["confirmado"] is False and r["estado"] == "RolledBack"
    assert r["ramales_siguientes"] == [100]


def test_nombre_de_transaccion_neutro_y_nunca_se_guarda():
    doc, db = modelo_sanitario(3)
    correr(doc, db, confirmar=True)
    assert doc.bitacora[0] == "Start:MEP - conectar a ramal"
    assert "Save" not in doc.bitacora


# -------------------------------------------------------------- geometria

def test_trazado_con_pendiente_bajante_y_te():
    doc, db = modelo_sanitario()
    r = correr(doc, db, confirmar=True)
    fila = r["conexiones"][0]
    bajante, horizontal = [doc.elementos[i] for i in fila["tuberias"]]
    _, _, _, a, b = bajante.creada_con
    assert a == pytest.approx((mm(2000), mm(1000), mm(600)))
    # 1 m de recorrido al 2 %: el codo queda 20 mm sobre el eje del ramal
    assert b == pytest.approx((mm(2000), mm(1000), mm(20)))
    assert horizontal.creada_con[4] == pytest.approx((mm(2000), 0.0, 0.0))
    assert horizontal.creada_con[:3] == (300, 200, 10)
    assert fila["entronque_m"] == pytest.approx([2.0, 0.0, 0.0])
    assert fila["diametro_mm"] == pytest.approx(50.0)
    assert doc.bitacora.count("BreakCurve") == 1
    assert doc.bitacora.count("NewTeeFitting") == 1


def test_diametro_distinto_usa_transicion():
    doc, db = modelo_sanitario()
    r = correr(doc, db, diametro_mm=75)
    fila = r["conexiones"][0]
    assert fila["union_aparato"] == "NewTransitionFitting"
    # Revit rechaza la transicion contra el conector del aparato: va entre
    # un tramo corto del diametro del conector y el primer tramo pedido.
    assert doc.bitacora.count("NewTransitionFitting") == 1
    assert len(fila["tuberias"]) >= 2 and fila["estado"] == "conectado"


def test_entero_admite_el_int64_de_elementid_value():
    from mep import base

    class Int64(object):
        def __int__(self):
            return 1001

    assert base.entero(Int64(), "aparatos") == 1001


def test_takeoff_que_no_refiere_al_ramal_es_suelto():
    doc, db = modelo_sanitario()
    doc.suelta.add("takeoff_sin_ramal")
    r = correr(doc, db, union="takeoff")
    assert r["conexiones"][0]["estado"] == "suelto_revertido"
    assert any("no quedo unido al ramal" in s["motivo"] for s in r["sueltos"])


def test_conector_a_la_cota_del_ramal_usa_codo_en_el_aparato():
    doc, db = modelo_sanitario(altura_mm=0.0)
    r = correr(doc, db, pendiente=0.0)
    fila = r["conexiones"][0]
    assert fila["union_aparato"] == "NewElbowFitting"
    assert len(fila["tuberias"]) == 1


def test_takeoff_no_parte_el_ramal():
    doc, db = modelo_sanitario()
    r = correr(doc, db, union="takeoff", confirmar=True)
    assert "BreakCurve" not in doc.bitacora
    assert doc.bitacora.count("NewTakeoffFitting") == 1
    assert r["ramales_siguientes"] == [100] and r["sueltos"] == []


def test_entronque_fuera_del_ramal_es_fallo_con_motivo():
    doc, db = modelo_sanitario()
    doc.elementos[1001].conectores[0].Origin = dobles.XYZ(-5.0, 3.0, 2.0)
    r = correr(doc, db)
    fila = r["conexiones"][0]
    assert fila["estado"] == "fallido" and "fuera del ramal" in fila["motivo"]
    assert r["errores"][0]["tipo"] == "ErrorTrazado"


def test_conector_que_apunta_al_lado_contrario_falla():
    with pytest.raises(geometria.ErrorTrazado):
        geometria.calcular_ruta((2.0, 3.0, 2.0), (0, 0, 1), (0, 0, 0),
                                (20, 0, 0), 0.02, 1.0, 0.1, 0.5, 0.001)


def test_conector_horizontal_agrega_tramo_de_salida():
    ruta = geometria.calcular_ruta((2.0, 3.0, 2.0), (1, 0, 0), (0, 0, 0),
                                   (20, 0, 0), 0.0, 1.0, 0.1, 0.5, 0.001)
    assert ruta["puntos"] == [(2.0, 3.0, 2.0), (3.0, 3.0, 2.0),
                              (3.0, 3.0, 0.0), (3.0, 0.0, 0.0)]


# ------------------------------------------------- fallos y verificacion

@pytest.mark.parametrize("llamada", ["Pipe.Create", "BreakCurve",
                                     "NewTeeFitting", "NewElbowFitting"])
def test_retorno_none_cuenta_como_fallo_y_no_deja_piezas(llamada):
    doc, db = modelo_sanitario()
    doc.devuelve_none.add(llamada)
    antes = set(doc.elementos)
    r = correr(doc, db, confirmar=True)
    fila = r["conexiones"][0]
    assert fila["estado"] == "fallido" and "devolvio None" in fila["motivo"]
    assert r["resumen"].get("conectado", 0) == 0
    assert set(doc.elementos) == antes  # la subtransaccion se revirtio
    assert r["errores"][0]["tipo"] == "ErrorApi"
    assert doc.elementos[1001].conectores[0].IsConnected is False


def test_excepcion_de_la_api_queda_registrada():
    doc, db = modelo_sanitario(2)
    doc.lanza.add("NewTeeFitting")
    r = correr(doc, db)
    assert [f["estado"] for f in r["conexiones"]] == ["fallido", "fallido"]
    assert len(r["errores"]) == 2
    assert "fallo simulado" in r["errores"][0]["mensaje"]


def test_conector_suelto_aparece_en_la_lista_y_se_revierte():
    doc, db = modelo_sanitario()
    doc.suelta.add("NewTeeFitting")
    antes = set(doc.elementos)
    r = correr(doc, db, confirmar=True)
    assert r["conexiones"][0]["estado"] == "suelto_revertido"
    roles = sorted(set(s["rol"] for s in r["sueltos"]))
    assert roles == ["accesorio", "ramal", "tramo_nuevo"]
    for suelto in r["sueltos"]:
        assert suelto["motivo"] == "IsConnected=False" and suelto["revertido"]
        assert suelto["conector"] is not None and len(suelto["posicion_m"]) == 3
        assert suelto["aparato"] == 1001
    assert set(doc.elementos) == antes
    assert r["resumen"]["sueltos"] == len(r["sueltos"]) > 0


def test_suelto_se_conserva_si_se_pide_no_revertir():
    doc, db = modelo_sanitario()
    doc.suelta.add("NewElbowFitting")
    r = correr(doc, db, confirmar=True, revertir_sueltos=False)
    fila = r["conexiones"][0]
    assert fila["estado"] == "suelto"
    assert all(s["revertido"] is False for s in r["sueltos"])
    assert all(i in doc.elementos for i in fila["tuberias"])


def test_conectores_ya_conectados_o_de_otro_sistema_se_omiten():
    doc, db = modelo_sanitario(2)
    doc.elementos[1001].conectores[0].refs.add("previo")
    doc.elementos[1002].conectores[0].PipeSystemType = "DomesticColdWater"
    r = correr(doc, db)
    motivos = [f["motivo"] for f in r["conexiones"]]
    assert motivos[0] == "conector ya conectado"
    assert "no corresponde" in motivos[1]
    assert r["resumen"] == {"omitido": 2, "sueltos": 0}
    assert "Pipe.Create" not in doc.bitacora


def test_advertencias_se_capturan_sin_dialogo():
    doc, db = modelo_sanitario()
    doc.fallos = [("Warning", "aviso sintetico")]
    r = correr(doc, db, confirmar=True)
    assert r["confirmado"] is True
    assert r["advertencias"] == [{"severidad": "Warning",
                                  "descripcion": "aviso sintetico",
                                  "elementos": [1]}]
    assert "DeleteWarning" in doc.bitacora


def test_error_de_revit_al_confirmar_revierte():
    doc, db = modelo_sanitario()
    doc.fallos = [("Error", "error sintetico")]
    antes = set(doc.elementos)
    r = correr(doc, db, confirmar=True)
    assert r["confirmado"] is False and r["estado"] == "RolledBack"
    assert r["advertencias"] == []
    assert r["errores"][-1] == {"etapa": "fallo_de_revit", "elemento": 1, "tipo": "Error",
                               "mensaje": "error sintetico", "elementos": [1]}
    assert set(doc.elementos) == antes


# ------------------------------------------------------------------ lotes

def test_lotes_y_desde():
    doc, db = modelo_sanitario(5)
    r1 = correr(doc, db, lote=2, confirmar=True)
    assert [f["aparato"] for f in r1["conexiones"]] == [1001, 1002]
    assert (r1["procesados"], r1["siguiente"], r1["aparatos_total"]) == (2, 2, 5)
    assert doc.bitacora.count("Start:MEP - conectar a ramal") == 1
    r2 = conectar_a_ramal(db, doc, {
        "categoria": "OST_PlumbingFixtures", "ramales": r1["ramales_siguientes"],
        "tipo_tuberia": 200, "tipo_sistema": 300, "pendiente": 0.02,
        "lote": 2, "desde": r1["siguiente"], "confirmar": True})
    assert [f["aparato"] for f in r2["conexiones"]] == [1003, 1004]
    r3 = conectar_a_ramal(db, doc, {
        "categoria": "OST_PlumbingFixtures", "ramales": r2["ramales_siguientes"],
        "tipo_tuberia": 200, "tipo_sistema": 300, "pendiente": 0.02,
        "lote": 2, "desde": r2["siguiente"], "confirmar": True})
    assert [f["aparato"] for f in r3["conexiones"]] == [1005]
    assert r3["siguiente"] is None
    assert doc.bitacora.count("Start:MEP - conectar a ramal") == 3
    assert all(doc.elementos[i].conectores[0].IsConnected
               for i in range(1001, 1006))
    assert doc.bitacora.count("BreakCurve") == 5


def test_varios_aparatos_eligen_el_tramo_de_ramal_mas_cercano():
    doc, db = modelo_sanitario(3)
    r = correr(doc, db, confirmar=True)
    ramales = [f["ramal"] for f in r["conexiones"]]
    assert ramales[0] == 100 and len(set(ramales)) == 3
    assert r["resumen"] == {"conectado": 3, "sueltos": 0}


# ------------------------------------- ensayo con Commit real y campo 'ok'

def test_ensayo_detecta_el_error_que_revit_da_al_confirmar():
    doc, db = modelo_sanitario()
    doc.fallos = [("Error", "The pipe has been modified to be in the opposite direction")]
    antes = set(doc.elementos)
    r = correr(doc, db)
    assert r["ensayo"] is True and r["confirmado"] is False
    assert r["commit_de_ensayo"] == "RolledBack" and r["ensayo_valido"] is False
    assert r["errores"][-1]["etapa"] == "fallo_de_revit"
    assert "opposite direction" in r["errores"][-1]["mensaje"]
    assert set(doc.elementos) == antes and doc.bitacora[-1] == "GroupRolledBack"


def test_ok_es_falso_si_se_pidio_confirmar_y_no_quedo_committed():
    from mep import ejecutar
    doc, db = modelo_sanitario()
    doc.fallos = [("Error", "error sintetico")]
    r = ejecutar.correr("conectar", opciones_conectar(confirmar=True), doc, db)
    assert r["ok"] is False and r["confirmado"] is False and r["errores"]
    doc, db = modelo_sanitario()
    assert ejecutar.correr("conectar", opciones_conectar(confirmar=True), doc, db)["ok"] is True


def test_ok_sigue_verdadero_en_un_ensayo_aunque_no_sea_valido():
    from mep import ejecutar
    doc, db = modelo_sanitario()
    doc.fallos = [("Error", "error sintetico")]
    r = ejecutar.correr("conectar", opciones_conectar(), doc, db)
    assert r["ok"] is True and r["ensayo_valido"] is False
