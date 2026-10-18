import csv
import tempfile
import unittest
from pathlib import Path
from point_tools.prepare import read_points, prepare


class Requests(unittest.TestCase):
    def setUp(self):
        self.config = dict(
            action="import",
            drawing="C:/demo/copy.dwg",
            expected_count=0,
            output="C:/demo/results/run1",
            name="DEMO",
        )
        self.rows = [[10, 1.0, 2.0, 3.0, "TN"]]

    def run_prepare(self, rows=None):
        return prepare(
            self.config, self.rows if rows is None else rows, "C:/tools/native.lsp"
        )

    def test_escaped_text_cannot_be_lisp(self):
        s = self.run_prepare([[10, 1.0, 2.0, 3.0, 'x") (quit) ("']])
        self.assertIn('x\\") (quit) (\\"', s)

    def test_nan_rejected(self):
        with self.assertRaises(ValueError):
            self.run_prepare([[10, float("nan"), 2.0, 3.0, "TN"]])

    def test_duplicate_numbers_rejected(self):
        with self.assertRaises(ValueError):
            self.run_prepare(self.rows * 2)

    def test_boolean_number_rejected(self):
        with self.assertRaises(ValueError):
            self.run_prepare([[True, 1, 2, 3, "TN"]])

    def test_control_character_rejected(self):
        with self.assertRaises(ValueError):
            self.run_prepare([[10, 1, 2, 3, "T\nN"]])

    def test_import_requires_empty_drawing(self):
        self.config["expected_count"] = 122
        with self.assertRaises(ValueError):
            self.run_prepare()

    def test_group_can_target_existing_points(self):
        self.config.update(action="group", expected_count=122)
        self.assertIn('"group"', self.run_prepare())

    def test_survey_description_loss_is_rejected(self):
        self.config.update(action="survey-import", survey_folder="C:/demo/survey")
        with self.assertRaises(ValueError):
            self.run_prepare([[10, 1, 2, 3, "TN "]])

    def test_relative_and_traversal_paths_rejected(self):
        for path in ["demo.dwg", "C:/demo/../original.dwg"]:
            self.config["drawing"] = path
            with self.assertRaises(ValueError):
                self.run_prepare()

    def test_csv_preserves_description(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "points.csv"
            with p.open("w", newline="") as f:
                w = csv.writer(f)
                w.writerow(
                    ["number", "easting", "northing", "elevation", "description"]
                )
                w.writerow([10, 1, 2, 3, 'TN, "a" '])
            self.assertEqual(read_points(p)[0][4], 'TN, "a" ')

    def test_wrong_coordinate_order_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "points.csv"
            p.write_text("number,northing,easting,elevation,description\n10,2,1,3,TN\n")
            with self.assertRaises(ValueError):
                read_points(p)


if __name__ == "__main__":
    unittest.main()
