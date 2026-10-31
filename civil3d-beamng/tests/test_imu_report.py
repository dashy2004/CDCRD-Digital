import copy
import importlib.util
from pathlib import Path
import unittest

import numpy as np

path=Path(__file__).resolve().parents[1]/'tools/tech/imu_report.py'
spec=importlib.util.spec_from_file_location('imu_report',path)
report=importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


class SensorQualityTests(unittest.TestCase):
    def samples(self):
        return [dict(time=10+i*.005,accRaw=[1,2,3],dirX=[1,0,0],dirY=[0,0,1],dirZ=[0,-1,0]) for i in range(20)]

    def test_clock_origin_and_rate(self):
        t,a,basis,qc=report.validate_samples(self.samples(),10)
        self.assertAlmostEqual(t[-1],.095)
        self.assertAlmostEqual(qc['rate_hz'],200)
        np.testing.assert_allclose(basis[0]@[2,3,4],[2,4,-3])

    def test_duplicate_sample_rejected(self):
        values=self.samples();values[5]=copy.deepcopy(values[4])
        with self.assertRaisesRegex(ValueError,'Duplicate'):report.validate_samples(values,10)

    def test_gap_rejected_before_smoothing(self):
        values=self.samples();del values[8]
        with self.assertRaisesRegex(ValueError,'Missing'):report.validate_samples(values,10)

    def test_invalid_sensor_basis(self):
        values=self.samples();values[7]['dirX']=[2,0,0]
        with self.assertRaisesRegex(ValueError,'basis'):report.validate_samples(values,10)

    def test_nonfinite_rejected(self):
        values=self.samples();values[3]['accRaw'][0]=float('nan')
        with self.assertRaisesRegex(ValueError,'Non-finite'):report.validate_samples(values,10)

    def test_average_preserves_constant_and_no_edge_fabrication(self):
        avg=report.centered_average(np.ones((20,3))*4)
        self.assertTrue(np.isnan(avg[:2]).all() and np.isnan(avg[-2:]).all())
        np.testing.assert_allclose(avg[2:-2],4)

    def test_average_of_vectors_can_cancel(self):
        a=np.zeros((11,3));a[4,0]=10;a[5,0]=-10
        avg=report.centered_average(a)
        self.assertEqual(float(np.linalg.norm(avg[5])),0)
        self.assertGreater(float(np.mean(np.linalg.norm(a[3:8],axis=1))),0)


if __name__=='__main__':unittest.main()
