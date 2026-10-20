"""Reject historical and inconsistent native receipts before interpreting m³."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))
from verify_demo import verify, verify_style_units, verify_units


class NativeUnitsTests(unittest.TestCase):
    def test_two_native_settings_required(self):
        for audit in (
            {"units": "Meters"},
            {"units": "Meters", "civilUnits": "Feet", "metricDrawingUnits": False},
            {"units": "Feet", "civilUnits": "Meters", "metricDrawingUnits": False},
            {"units": "Meters", "civilUnits": "Feet", "metricDrawingUnits": True},
            {"units": "Meters", "civilUnits": "Meters", "metricDrawingUnits": "true"},
        ):
            with self.subTest(audit=audit), self.assertRaisesRegex(ValueError, "Both"):
                verify({"ok": True, "result": audit})

    def test_consistent_metric_receipt(self):
        verify_units(
            {"units": "Meters", "civilUnits": "Meters", "metricDrawingUnits": True}
        )

    def test_imperial_graph_rejected_even_in_metric_drawing(self):
        axis = {"major": "<[Section View Point Offset(Uft|P2)]>",
                "minor": "<[Section View Point Offset(Uft|P2)]>",
                "title": "Offset"}
        with self.assertRaisesRegex(ValueError, "metric"):
            verify_style_units({"sectionViewStyles": [{"axes": [axis] * 5}] * 2})

    def test_missing_graph_audit_rejected(self):
        with self.assertRaisesRegex(ValueError, "audited"):
            verify_style_units({})

    def test_metric_axes_do_not_hide_imperial_station_title(self):
        axis = {"major": "<[Section View Point Offset(Um|P2)]> m",
                "minor": "<[Section View Point Offset(Um|P2)]> m",
                "title": "Offset (m)"}
        styles = [{"axes": [axis] * 5,
                   "title": "<[Section View Station(Uft|FS|P2)]>"}] * 2
        with self.assertRaisesRegex(ValueError, "station title"):
            verify_style_units({"sectionViewStyles": styles})

    def test_metric_graph(self):
        axis = {"major": "<[Section View Point Offset(Um|P2)]> m",
                "minor": "<[Section View Point Offset(Um|P2)]> m",
                "title": "Offset (m)"}
        verify_style_units({"sectionViewStyles": [{
            "axes": [axis] * 5,
            "title": "<[Section View Station(Um|FS|P2)]> m",
        }] * 2})


if __name__ == "__main__":
    unittest.main()
