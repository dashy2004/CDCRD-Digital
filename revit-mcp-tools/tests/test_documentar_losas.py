"""Offline guard tests; they do not replace native view/PDF verification."""
import importlib.util
from pathlib import Path

import pytest

MODULE = Path(__file__).parents[1] / 'src' / 'tools' / 'documentar_losas.py'
spec = importlib.util.spec_from_file_location('documentar_losas', MODULE)
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


@pytest.fixture
def config(tmp_path):
    return {
        'expected_path': str(tmp_path / 'copy.rvt'), 'expected_pid': 123,
        'protected_paths': [str(tmp_path / 'source.rvt')], 'floor_ids': [1, 2],
        'trial_ids': [1], 'inherited_reference_authorized': True,
        'prefix': 'CDX:TEST', 'view_prefix': 'CDX TEST ',
        'lock_identity': {'owner': 'codex', 'session': 'example', 'task': 'pilot'},
    }


def validate(p, path=None, pid=123, lock=None):
    lock = lock or dict(p['lock_identity'], state='active')
    tool._pilot_validate(p, path or p['expected_path'], pid, lock)


def test_valid_copy(config):
    validate(config)


def test_original_rejected_even_when_expected(config):
    config['expected_path'] = config['protected_paths'][0]
    with pytest.raises(ValueError, match='protegida'):
        validate(config)


def test_wrong_process(config):
    with pytest.raises(ValueError, match='PID'):
        validate(config, pid=124)


def test_other_session_and_released_lock(config):
    for changes in ({'session': 'different'}, {'state': 'released'}):
        lock = dict(config['lock_identity'], state='active')
        lock.update(changes)
        with pytest.raises(ValueError, match='Turno'):
            validate(config, lock=lock)


def test_reference_requires_explicit_authorization(config):
    config['inherited_reference_authorized'] = False
    with pytest.raises(ValueError, match='no autorizada'):
        validate(config)


@pytest.mark.parametrize('ids', [[], [1, 1]])
def test_empty_or_duplicate_ids(config, ids):
    config['floor_ids'] = ids
    with pytest.raises(ValueError, match='vacio o duplicado'):
        validate(config)


def test_trial_must_be_in_scope(config):
    config['trial_ids'] = [3]
    with pytest.raises(ValueError, match='fuera del alcance'):
        validate(config)


def test_memory_guard_cannot_be_disabled(config):
    config['min_free_mb'] = 0
    with pytest.raises(ValueError, match='memoria'):
        validate(config)


@pytest.mark.parametrize('raw,expected', [('#3 @ 0.15', '#3@15 cm'),
    ('#3 @ 0.09 (PILOTO)', '#3@9 cm'), ('10 mm @ 200', '10 mm @ 200'), ('', 'SIN DATO')])
def test_spacing_only_converts_known_explicit_syntax(raw, expected):
    assert tool._pilot_spacing(raw) == expected


def test_partition_covers_all_once():
    rows = [{'id': 1, 'cx': 1, 'cy': 1}, {'id': 2, 'cx': 5, 'cy': 1}]
    specs = [{'name': role, 'role': role, 'bounds_m': [0, 0, 6, 2]}
             for role in ('scheme', 'reinforcement')]
    assert len(tool._pilot_partition(rows, specs)['scheme']) == 2
    specs.append({'name': 'overlap', 'role': 'scheme', 'bounds_m': [0, 0, 2, 2]})
    with pytest.raises(ValueError, match='exactamente una vez'):
        tool._pilot_partition(rows, specs)


def test_partition_rejects_missing_floor():
    rows = [{'id': 1, 'cx': 1, 'cy': 1}, {'id': 2, 'cx': 5, 'cy': 1}]
    specs = [{'name': role, 'role': role, 'bounds_m': [0, 0, 2, 2]}
             for role in ('scheme', 'reinforcement')]
    with pytest.raises(ValueError, match='exactamente una vez'):
        tool._pilot_partition(rows, specs)
