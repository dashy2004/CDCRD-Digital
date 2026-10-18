import unittest
from point_tools.verify import compare


class Compare(unittest.TestCase):
    def test_order_independent(self):
        rows = [[1, 0, 1, 2, "A"], [2, 2, 3, 4, "B"]]
        self.assertTrue(compare(rows, list(reversed(rows)))["ok"])

    def test_mismatch_is_not_hidden(self):
        expected = [[1, 0, 1, 2, "A"], [2, 2, 3, 4, "B"]]
        result = compare(expected, [[1, 0, 1, 2.1, "A "], [3, 1, 1, 1, "C"]])
        self.assertFalse(result["ok"])
        self.assertEqual(result["missing"], [2])
        self.assertEqual(result["extra"], [3])
        self.assertEqual(result["changed_descriptions"], [1])


if __name__ == "__main__":
    unittest.main()
