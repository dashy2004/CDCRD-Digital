import unittest
from dataclasses import replace
from terrain_tools import Platform, prepare_platform, section_areas
from terrain_tools.geometry import area
from test_geometry import plane


class MeshTests(unittest.TestCase):
    def setUp(self):
        self.spec = Platform(0, 0, 12, 6, 10, 2, 24, 18)

    def test_sloped_plane_has_known_mixed_volume(self):
        triangles = [[(x, y, z + 0.05 * x) for x, y, z in t] for t in plane()]
        result = prepare_platform(triangles, self.spec)["expected"]
        self.assertAlmostEqual(result["cut_m3"], 58 / 9, places=7)
        self.assertAlmostEqual(result["fill_m3"], 58 / 9, places=7)

    def test_output_mesh_covers_domain_without_losing_faces(self):
        mesh = prepare_platform(plane(), replace(self.spec, elevation=8))
        mesh_area = sum(
            area([mesh["vertices"][i] for i in face]) for face in mesh["faces"]
        )
        self.assertAlmostEqual(mesh_area, 432, places=6)
        self.assertTrue(all(len(set(face)) == 3 for face in mesh["faces"]))

    def test_reversed_triangle_orientation_preserves_volume(self):
        mesh = prepare_platform(
            [t[::-1] for t in plane()], replace(self.spec, elevation=8)
        )
        # m=2, h=2: 72*2 + 2*18*4 + 4/3*4*8
        self.assertAlmostEqual(mesh["expected"]["cut_m3"], 992 / 3, places=6)

    def test_nonfinite_terrain_is_rejected(self):
        triangles = plane()
        triangles[0][0] = (0, 0, float("inf"))
        with self.assertRaises(ValueError):
            prepare_platform(triangles, self.spec)

    def test_excess_coverage_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "cover"):
            prepare_platform(plane() + plane(), self.spec)

    def test_section_outside_profile_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "coverage"):
            section_areas([(-1, 0), (1, 0)], [(-1, 1), (1, 1)], -2, 2)
