"""A scripted incident must follow CAD stations in both travel directions."""
import importlib.util
from pathlib import Path
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/tech/film_events.py'
spec = importlib.util.spec_from_file_location('film_events', SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RoadAxisTest(unittest.TestCase):
    def axis(self):
        return module.RoadAxis({'alignment': {
            'nodes_abs_m': [[100,200,10,7],[100,220,12,7],[100,240,14,7]],
            'station_m': [0,20,40]}}, [90,190,10])

    def test_right_offset_and_absolute_to_local_height(self):
        axis = self.axis()
        position, _ = axis.point(10, 1.5, .5)
        self.assertEqual(position, (11.5,20,1.5))
        self.assertAlmostEqual(axis.station(position),10)

    def test_oncoming_script_time_increases_while_station_decreases(self):
        script = self.axis().script(30,10,5,-1.7)
        self.assertEqual(script[0]['t'],0)
        self.assertEqual(script[-1]['t'],4)
        self.assertGreater(script[0]['y'],script[-1]['y'])
        self.assertTrue(all(a['t'] < b['t'] for a,b in zip(script,script[1:])))

    def test_evasive_script_changes_lane(self):
        script = self.axis().script(0,40,8,offsets=[[0,1.7],[20,-1.7],[40,-1.7]])
        self.assertAlmostEqual(script[0]['x'],11.7)
        self.assertAlmostEqual(script[-1]['x'],8.3)

    def test_invalid_travel_and_station_rejected(self):
        axis=self.axis()
        with self.assertRaises(ValueError):axis.point(41)
        with self.assertRaises(ValueError):axis.script(0,40,0)
        with self.assertRaises(ValueError):axis.script(20,20,8)

    def test_duplicate_axis_points_rejected(self):
        with self.assertRaises(ValueError):
            module.RoadAxis({'alignment':{'nodes_abs_m':[[0,0,0,7],[0,0,0,7]],
                                         'station_m':[0,1]}},[0,0,0])

    def test_crossing_path_uses_cad_origin_and_distance_timing(self):
        pos, rot, script = module.vehicle_motion(self.axis(), {
            'path_abs_m': [[100,220,12],[110,220,12],[110,240,12]],
            'speed': 5, 'lift': .4})
        self.assertEqual(pos, (10,30,2.4))
        self.assertAlmostEqual(rot[2], -2**-.5)
        self.assertEqual([p['t'] for p in script], [0,2,6])
        self.assertEqual(script[-1]['y'], 50)

    def test_invalid_crossing_paths_fail_before_connecting(self):
        for points, speed in [([[0,0,0],[0,0,1]],5),
                              ([[0,0,0],[1,0,float('nan')]],5),
                              ([[0,0,0],[1,0,0]],0),
                              ([[0,0,0],[1,0,0]],5),
                              ([[0,0],[1,0]],5)]:
            with self.subTest(points=points, speed=speed), self.assertRaises(ValueError):
                module.vehicle_motion(self.axis(), {'path_abs_m':points,'speed':speed})

    def test_heading_faces_route_instead_of_driving_in_reverse(self):
        import math
        for start, end, expected in [(0,40,(0,1)),(40,0,(0,-1))]:
            _, q, _ = module.vehicle_motion(self.axis(), {'start':start,'end':end,'speed':5})
            yaw = 2 * math.atan2(q[2], q[3])
            self.assertAlmostEqual(-math.sin(yaw), expected[0])
            self.assertAlmostEqual(-math.cos(yaw), expected[1])
