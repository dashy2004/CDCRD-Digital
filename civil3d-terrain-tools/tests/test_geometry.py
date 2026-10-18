import unittest
from dataclasses import replace
from terrain_tools import Platform, prepare_platform, profile_at_x, section_areas


def plane(z=10, x=0, y=0):
    p = [(x - 12, y - 9, z), (x + 12, y - 9, z), (x + 12, y + 9, z), (x - 12, y + 9, z)]
    return [[p[0], p[1], p[2]], [p[0], p[2], p[3]]]


class GeometryTests(unittest.TestCase):
    def setUp(self):
        self.spec = Platform(0, 0, 12, 6, 8, 1.5, 24, 18)

    def test_known_cut_with_sloped_sides(self):
        result = prepare_platform(plane(), self.spec)["expected"]
        self.assertAlmostEqual(result["cut_m3"], 276, places=7)
        self.assertEqual(result["fill_m3"], 0)
        self.assertAlmostEqual(result["cut_area_m2"], 216, places=7)

    def test_known_fill_with_sloped_sides(self):
        result = prepare_platform(plane(), replace(self.spec, elevation=12))["expected"]
        self.assertAlmostEqual(result["fill_m3"], 276, places=7)
        self.assertEqual(result["cut_m3"], 0)

    def test_coincident_planes_do_not_duplicate_domain(self):
        r = prepare_platform(plane(), replace(self.spec, elevation=10))["expected"]
        self.assertEqual(r["cut_m3"] + r["fill_m3"], 0)
        self.assertAlmostEqual(r["domain_area_m2"], 432, places=7)

    def test_mixed_symmetric_plane(self):
        tris = [[(x, y, z + 0.05 * x) for x, y, z in t] for t in plane()]
        r = prepare_platform(tris, replace(self.spec, elevation=10))["expected"]
        self.assertGreater(r["cut_m3"], 0)
        self.assertAlmostEqual(r["cut_m3"], r["fill_m3"], places=7)

    def test_large_coordinate_translation(self):
        r = prepare_platform(
            plane(x=400000, y=2200000),
            replace(self.spec, center_x=400000, center_y=2200000),
        )
        self.assertAlmostEqual(r["expected"]["cut_m3"], 276, places=7)

    def test_requires_daylight_inside_domain(self):
        with self.assertRaisesRegex(ValueError, "Daylight"):
            prepare_platform(plane(), replace(self.spec, elevation=0))

    def test_incomplete_domain_rejected(self):
        with self.assertRaisesRegex(ValueError, "cover"):
            prepare_platform(plane()[:1], self.spec)

    def test_nonfinite_and_negative_inputs_rejected(self):
        for bad in [
            replace(self.spec, elevation=float("nan")),
            replace(self.spec, horizontal_per_vertical=0),
            replace(self.spec, width=-1),
        ]:
            with self.assertRaises(ValueError):
                prepare_platform(plane(), bad)

    def test_cut_only_preserves_lower_terrain(self):
        r = prepare_platform(
            plane(), replace(self.spec, elevation=12, mode="cut_only")
        )["expected"]
        self.assertEqual(r["cut_m3"] + r["fill_m3"], 0)

    def test_fill_only_preserves_higher_terrain(self):
        r = prepare_platform(plane(), replace(self.spec, mode="fill_only"))["expected"]
        self.assertEqual(r["cut_m3"] + r["fill_m3"], 0)

    def test_profile_intersection_and_area_sign(self):
        self.assertEqual(profile_at_x(plane(), 0), [(-9, 10), (0.0, 10.0), (9, 10)])
        r = section_areas([(-10, 0), (10, 0)], [(-10, -1), (10, 1)], -10, 10)
        self.assertAlmostEqual(r["cut_m2"], 5)
        self.assertAlmostEqual(r["fill_m2"], 5)


if __name__ == "__main__":
    unittest.main()
