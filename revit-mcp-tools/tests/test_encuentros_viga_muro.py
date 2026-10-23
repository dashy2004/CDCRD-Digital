"""Offline tests of safety decisions; native Boolean/transaction QA is separate."""
import importlib.util
import pathlib
import unittest

PATH = pathlib.Path(__file__).resolve().parents[1] / 'src/tools/encuentros_viga_muro.py'
SPEC = importlib.util.spec_from_file_location('encuentros', PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class EncounterTests(unittest.TestCase):
    def identity(self, **changes):
        config = dict(expected_document='/copy.rvt', expected_pid=123,
                      protected_documents=['/original.rvt'],
                      lock=dict(owner='operator', session='session', task='task'))
        config.update(changes)
        lock = dict(owner='operator', session='session', task='task',
                    process_id=123, state='active')
        return config, lock

    def test_protected_original_rejected_even_if_expected(self):
        config, lock = self.identity(expected_document='/original.rvt')
        with self.assertRaises(ValueError):
            MODULE._wm_identity('/original.rvt', 123, config, lock)

    def test_wrong_process_document_and_operator_rejected(self):
        config, lock = self.identity()
        for path, pid in [('/other.rvt', 123), ('/copy.rvt', 999)]:
            with self.assertRaises(ValueError):
                MODULE._wm_identity(path, pid, config, lock)
        lock['owner'] = 'someone_else'
        with self.assertRaises(ValueError):
            MODULE._wm_identity('/copy.rvt', 123, config, lock)

    def test_active_owned_copy_accepted(self):
        config, lock = self.identity()
        MODULE._wm_identity('/copy.rvt', 123, config, lock)

    def test_missing_protection_and_released_lock_rejected(self):
        config, lock = self.identity(protected_documents=[])
        with self.assertRaises(ValueError):
            MODULE._wm_identity('/copy.rvt', 123, config, lock)
        config, lock = self.identity()
        lock['state'] = 'released'
        with self.assertRaises(ValueError):
            MODULE._wm_identity('/copy.rvt', 123, config, lock)

    def test_repeated_wall_rejected(self):
        for pairs in ([], [[1, 2], [1, 3]], [[1, 1]], [[-1, 2]]):
            with self.assertRaises(ValueError):
                MODULE._wm_pairs(pairs)

    def test_apply_requires_exact_join_plan(self):
        with self.assertRaises(ValueError):
            MODULE._wm_require_join_plan([[1, 2]], [], False)
        with self.assertRaises(ValueError):
            MODULE._wm_require_join_plan([], [[1, 2]], False)
        MODULE._wm_require_join_plan([[1, 2]], [], True)
        MODULE._wm_require_join_plan([[1, 2], [3, 4]], [[3, 4], [1, 2]], False)

    def test_increased_existing_overlap_is_failure(self):
        r = MODULE._wm_new_overlaps({(1, 2): 0.1}, {(1, 2): 0.2})
        self.assertEqual(r[0]['ids'], [1, 2])
        self.assertEqual(r[0]['before_ft3'], 0.1)

    def test_new_overlap_is_failure_but_smaller_or_noise_is_not(self):
        self.assertEqual(len(MODULE._wm_new_overlaps({}, {(1, 2): 0.1})), 1)
        self.assertEqual(MODULE._wm_new_overlaps({(1, 2): 0.1}, {(1, 2): 0.05}), [])
        self.assertEqual(MODULE._wm_new_overlaps({}, {(1, 2): 1e-9}), [])

    def test_numeric_noise_accepted_but_type_id_changes_rejected(self):
        self.assertTrue(MODULE._wm_close({'volume': 1.0}, {'volume': 1.0 + 1e-10}))
        self.assertFalse(MODULE._wm_close({'type': 1}, {'type': 2}))
        self.assertFalse(MODULE._wm_close({'type': 1}, {}))


if __name__ == '__main__':
    unittest.main()
