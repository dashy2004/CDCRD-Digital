import unittest
from types import SimpleNamespace as N

from mep import homologacion_redes as h


class Ref:
    def __init__(self, owner, sector, domain="DomainPiping", tipo="End"):
        self.Owner = N(UniqueId=owner)
        self.Id = 1
        self.ConnectorType = tipo
        self.Domain = domain
        self.MEPSystem = N(GetTypeId=lambda: sector)
        self.AllRefs = []
        self.conectados = set()

    def IsConnectedTo(self, other):
        return other in self.conectados


class Pruebas(unittest.TestCase):
    def setUp(self):
        self.doc = N(GetElement=lambda k: N(UniqueId=k))
        self.a = Ref("a", "red_a")
        self.b = Ref("b", "red_b")
        self.a.AllRefs = [self.b]
        self.b.AllRefs = [self.a]
        self.a.conectados.add(self.b)
        self.b.conectados.add(self.a)
        self.config = {
            "tipos_red": {"red_a": "pluvial", "red_b": "sanitaria"},
            "redes_previstas": {},
        }

    def lectura(self):
        return h.leer_enlaces(self.doc, [self.a, self.b], self.config)

    def test_cruce_exige_contacto_y_dominio_fisico(self):
        r = self.lectura()
        self.assertEqual(len(r["enlaces"]), 1)
        self.assertEqual(r["enlaces"][0]["estado"], "cruce_pluvial_sanitaria")
        self.a.conectados.clear()
        self.b.conectados.clear()
        self.assertEqual(self.lectura()["enlaces"], [])
        self.a.conectados.add(self.b)
        self.b.conectados.add(self.a)
        self.b.ConnectorType = "Logical"
        self.assertEqual(self.lectura()["enlaces"], [])
        self.b.ConnectorType = "End"
        self.b.Domain = "DomainElectrical"
        self.assertEqual(self.lectura()["enlaces"], [])

    def test_faltantes_y_clasificacion_sin_inferir_de_nombres(self):
        self.config["tipos_red"] = {}
        self.assertEqual(
            self.lectura()["enlaces"][0]["estado"], "clasificacion_pendiente"
        )
        self.config["redes_previstas"] = {"a": "pluvial", "b": "sanitaria"}
        self.assertEqual(
            self.lectura()["enlaces"][0]["estado"], "cruce_pluvial_sanitaria"
        )
        self.a.AllRefs = []
        self.b.AllRefs = []
        self.assertEqual(self.lectura()["enlaces"], [])

    def test_circuitos_y_unifilar(self):
        c = N(
            UniqueId="c",
            CircuitType="Circuit",
            SystemType="PowerCircuit",
            CircuitNumber="A1",
            BaseEquipment=N(UniqueId="tab"),
            Elements=[N(UniqueId="l")],
        )
        u = [{"circuito": "c", "tablero": "otro", "cargas": ["l"], "lamina": "E-01"}]
        v = h.leer_circuitos([c], u)
        self.assertEqual(v["circuitos"][0]["diferencias"], ["tablero"])
        self.assertEqual(v["circuitos"][0]["lamina"], "E-01")
        c.BaseEquipment = None
        self.assertEqual(
            h.leer_circuitos([c], [])["circuitos"][0]["estado_tablero"], "sin_tablero"
        )
        c.CircuitType = "Spare"
        self.assertEqual(h.leer_circuitos([c], u)["unifilar_sin_circuito"], ["c"])

    def test_discrepancia_en_tipo_carga_y_equipos_sin_leer(self):
        self.config["redes_previstas"] = {"a": "sanitaria", "ausente": "sanitaria"}
        self.config["tipos_red"]["red_b"] = "pluvial"
        self.config["tipos_red"]["tipo_ausente"] = "sanitaria"
        self.config["redes_previstas"]["b"] = "sanitaria"
        r = self.lectura()
        self.assertEqual(r["elementos_previstos_no_leidos"], ["ausente"])
        self.assertEqual(r["tipos_previstos_no_leidos"], ["tipo_ausente"])
        self.assertEqual(r["enlaces"][0]["estado"], "tipo_distinto_del_previsto")
        c = N(
            UniqueId="c",
            CircuitType="Circuit",
            SystemType="PowerBalanced",
            CircuitNumber="1",
            BaseEquipment=N(UniqueId="t"),
            Elements=[],
            ApparentLoad=2,
        )
        db = N(
            UnitTypeId=N(VoltAmperes="VA"),
            UnitUtils=N(ConvertFromInternalUnits=lambda v, u: 12 * v),
        )
        r = h.leer_circuitos(
            [c],
            [{"circuito": "c", "tablero": "t", "cargas": ["l"], "lamina": "E1"}],
            db,
        )
        self.assertEqual(r["circuitos"][0]["carga_aparente_VA"], 24)
        self.assertEqual(r["circuitos"][0]["diferencias"], ["cargas"])

    def test_clasificacion_indisponible_conserva_contacto(self):
        self.doc.GetElement = lambda id: (_ for _ in ()).throw(
            ValueError("indisponible")
        )
        informe = self.lectura()
        self.assertEqual(informe["enlaces"][0]["estado"], "clasificacion_pendiente")
        self.assertEqual(informe["conectores"][0]["error_sistema"], "indisponible")

    def test_manifesto_ambiguo_o_de_otro_modelo(self):
        doc = {"documento": "ejemplo.rvt", "proyecto_uid": "modelo-1", "revision": "R1"}
        u = {"circuito": "c", "tablero": "tab", "cargas": ["l"], "lamina": "E-01"}
        base = dict(doc, unifilar=[u], redes_previstas={"a": "pluvial"}, tipos_red={})
        self.assertEqual(h.validar_config(base, doc)["unifilar"], [u])
        for dato in [
            dict(base, unifilar=[u, u]),
            dict(base, documento="otro.rvt"),
            dict(base, redes_previstas={"a": "residual"}),
            dict(base, revision="R2"),
            dict(base, unifilar=[dict(u, cargas=["l", "l"])]),
        ]:
            with self.assertRaises(ValueError):
                h.validar_config(dato, doc)
