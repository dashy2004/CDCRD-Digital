"""Offline behavior tests; no Autodesk assemblies, process or document required."""
import pathlib
import types
import unittest


TOOLS = pathlib.Path(__file__).resolve().parents[1] / "src" / "tools"


def obj(**kwargs):
    return types.SimpleNamespace(**kwargs)


def element(number, connectors=None, model=None):
    return obj(Id=obj(Value=number), Name="fixture", MEPModel=model,
               ConnectorManager=None if connectors is None else obj(Connectors=connectors))


class LogicalConnector:
    ConnectorType = "Logical"
    MEPSystem = None

    @property
    def IsConnected(self):
        raise AssertionError("Logical connector connectivity must never be accessed")


class BrokenConnector:
    ConnectorType = "End"
    MEPSystem = None

    @property
    def IsConnected(self):
        raise RuntimeError("Connector no longer valid")


class BrokenSystemConnector:
    ConnectorType = "End"
    IsConnected = True

    @property
    def MEPSystem(self):
        raise RuntimeError("System read failed")


class MEPTests(unittest.TestCase):
    def setUp(self):
        self.ns = {}
        for name in ("_common", "_mep", "mep_conectividad"):
            exec(compile((TOOLS / (name + ".py")).read_text(encoding="utf-8"), name, "exec"), self.ns)

    def run_tool(self, elements=None, params=None, failed_category=None):
        data = {"OST_PipeCurves": elements or []}

        class Collector:
            def __init__(self, doc):
                self.category = None

            def OfCategory(self, category):
                if category == failed_category:
                    raise RuntimeError("Collector unavailable")
                self.category = category
                return self

            def WhereElementIsNotElementType(self):
                return data.get(self.category, [])

        categories = {name: name for group in self.ns["MEP_CATEGORIES"].values() for name in group}
        db = obj(BuiltInCategory=obj(**categories), FilteredElementCollector=Collector)
        return self.ns["run"](object(), None, db, params or {})

    def test_empty_is_not_compliance_pass(self):
        result = self.run_tool()
        self.assertEqual("no_elements_in_scope", result["status"])
        self.assertFalse(result["linked_documents_included"])

    def test_counts_not_limited_by_output_cap_and_system_dedup(self):
        system = obj(Id=obj(Value=90), Name="supply")
        connectors = [obj(ConnectorType="End", MEPSystem=system, IsConnected=False),
                      obj(ConnectorType="End", MEPSystem=system, IsConnected=True)]
        result = self.run_tool([element(1, connectors), element(2, connectors)], {"max_details": 1})
        self.assertEqual(2, result["element_count"])
        self.assertEqual(1, len(result["elements"]))
        self.assertEqual(2, result["finding_counts"]["OPEN_PHYSICAL_CONNECTOR"])
        self.assertEqual(2, result["systems"][0]["observed_element_count"])
        self.assertTrue(result["details_truncated"])

    def test_logical_connectors_are_not_physically_tested(self):
        result = self.run_tool([element(1, [LogicalConnector()])])
        self.assertEqual(0, result["error_count"])
        self.assertEqual(1, result["connectors"]["logical_or_other_skipped"])

    def test_failure_is_partial_and_other_elements_continue(self):
        result = self.run_tool([element(1, [BrokenConnector()]), element(2)])
        self.assertEqual("partial", result["status"])
        self.assertEqual(2, result["element_count"])
        self.assertEqual("connector_connectivity", result["errors"][0]["stage"])
        self.assertEqual(1, result["finding_counts"]["CONNECTORS_UNAVAILABLE"])

    def test_failed_category_does_not_mean_zero_verified(self):
        result = self.run_tool(failed_category="OST_PipeCurves")
        self.assertEqual("partial", result["status"])
        row = next(row for row in result["categories"] if row["category"] == "OST_PipeCurves")
        self.assertEqual("partial", row["status"])

    def test_electrical_circuit_and_family_connector_path(self):
        system = obj(Id=obj(Value=91), Name="circuit")
        model = obj(ConnectorManager=obj(Connectors=[LogicalConnector()]),
                    GetElectricalSystems=lambda: [system])
        result = self.run_tool([element(1, model=model)])
        self.assertEqual([91], result["elements"][0]["system_ids"])
        self.assertNotIn("NO_OBSERVED_SYSTEM", result["finding_counts"])

    def test_zero_detail_limit_keeps_aggregate_errors(self):
        result = self.run_tool([element(1, [BrokenConnector()])], {"max_details": 0})
        self.assertEqual(1, result["error_count"])
        self.assertEqual([], result["errors"])
        self.assertTrue(result["details_truncated"])

    def test_invalid_filter_rejected_instead_of_returning_empty(self):
        for params in ({"disciplines": ["unknown"]}, {"disciplines": []}, {"max_details": -1}):
            with self.assertRaises(ValueError):
                self.run_tool(params=params)

    def test_inventory_does_not_access_connectivity(self):
        exec((TOOLS / "mep_inventario.py").read_text(encoding="utf-8"), self.ns)
        result = self.run_tool([element(1, [BrokenConnector()])])
        self.assertEqual("complete", result["status"])
        self.assertEqual({}, result["finding_counts"])

    def test_system_read_error_is_unknown_not_missing(self):
        result = self.run_tool([element(1, [BrokenSystemConnector()])])
        self.assertEqual("partial", result["status"])
        self.assertNotIn("NO_OBSERVED_SYSTEM", result["finding_counts"])
        row = next(row for row in result["categories"] if row["category"] == "OST_PipeCurves")
        self.assertEqual("partial", row["status"])


if __name__ == "__main__":
    unittest.main()
