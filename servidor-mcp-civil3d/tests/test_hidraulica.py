import math
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from hidraulica import calculate, critical_depth, energy_gate, manning, normal_depth, section, state


class HydraulicsTests(unittest.TestCase):
    def test_rectangular_critical_analytic(self):
        for q in (0.001, 0.7, 20):
            self.assertAlmostEqual(critical_depth(q, 2, 0), (q*q/(9.81*4))**(1/3), places=10)

    def test_triangular_critical_analytic(self):
        self.assertAlmostEqual(critical_depth(1.2, 0, 2), (2*1.2**2/(9.81*4))**0.2, places=10)

    def test_critical_minimum_energy(self):
        y = critical_depth(0.7, 0.8, 1.5)
        center = state(0.7, 0.8, 1.5, y, 0)
        self.assertAlmostEqual(center['froude'], 1)
        for factor in (0.99, 1.01):
            self.assertGreater(state(0.7, 0.8, 1.5, y*factor, 0)['specific_energy_m'], center['specific_energy_m'])

    def test_normal_discharge_residual(self):
        for b, z in ((1, 0), (0, 2), (0.8, 1.5)):
            for q in (0.01, 0.7, 25):
                y = normal_depth(q, b, z, 0.016, 0.002)
                self.assertAlmostEqual(manning(b, z, y, 0.016, 0.002), q, places=10)

    def test_manning_known_geometry(self):
        # b=2,y=1 rectangular: A=2, P=4, R=0.5.
        self.assertAlmostEqual(manning(2, 0, 1, 0.02, 0.001), 2*0.5**(2/3)*math.sqrt(0.001)/0.02)

    def test_negative_energy_rejected(self):
        self.assertEqual(energy_gate(100, 101)['status'], 'insufficient')

    def test_losses_included(self):
        self.assertAlmostEqual(energy_gate(100, 99.5, 0.8)['margin_m'], -0.3)

    def test_unknown_head_never_passes(self):
        self.assertEqual(energy_gate(None, 10)['status'], 'unverified')

    def test_positive_margin_not_route_certificate(self):
        self.assertFalse(energy_gate(100, 90)['route_verified'])

    def test_invalid_geometry(self):
        for b, z, y in ((0, 0, 1), (-1, 1, 1), (1, -1, 1), (1, 1, 0)):
            with self.assertRaises(ValueError):
                section(b, z, y)

    def test_numerical_overflow_does_not_pass(self):
        with self.assertRaises(ValueError):
            section(1e308, 1e308, 10)
        with self.assertRaises(ValueError):
            critical_depth(1e308, 1, 1)
        with self.assertRaises(ValueError):
            energy_gate(1e308, -1e308)

    def test_invalid_scalar(self):
        for value in (True, '1', None, float('nan'), float('inf'), -1, 0):
            with self.assertRaises(ValueError):
                normal_depth(value, 1, 1, 0.02, 0.001)

    def test_adverse_slope_or_roughness(self):
        for n, slope in ((0, 0.001), (-1, 0.001), (0.02, 0), (0.02, -0.01)):
            with self.assertRaises(ValueError):
                normal_depth(1, 1, 1, n, slope)

    def test_explicit_units_and_schema(self):
        request = dict(units='SI', q_m3_s=0.7, b_m=0.8, z_h_v=1.5, n_s_m13=0.016,
                       slope_m_m=0.002, bed_m=100, available_head_m=None, losses_m=0)
        self.assertEqual(calculate(request)['energy_gate']['status'], 'unverified')
        for bad in ({**request, 'units': 'ft'}, {**request, 'typo': 1}, {}):
            with self.assertRaises(ValueError):
                calculate(bad)


if __name__ == '__main__':
    unittest.main()
