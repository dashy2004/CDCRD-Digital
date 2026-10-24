import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location(
    'eps', Path(__file__).parents[1] / 'src/tools/eps_individualizar.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


def volume(box):
    return (box[3]-box[0])*(box[4]-box[1])*(box[5]-box[2])


def test_separate_cubes_remain_one_quantity_each():
    boxes = [[1, 2, 3, 1.5, 2.5, 3.15], [1.65, 2, 3, 2.15, 2.5, 3.15]]
    assert tool.piece_boxes(boxes) == boxes


def test_long_one_way_strip_is_partitioned_without_concrete_ribs_or_volume_loss():
    strip = [12.3, 7.8, 5.15, 12.8, 10.02, 5.30]
    pieces = tool.piece_boxes([strip], [.5, .5])
    assert len(pieces) == 5
    assert sum(volume(b) for b in pieces) == pytest.approx(volume(strip))
    assert all(b[:1] == strip[:1] and b[3] == strip[3] for b in pieces)
    assert pieces[0][1] == strip[1] and pieces[-1][4] == strip[4]
    assert all(a[4] == b[1] for a, b in zip(pieces[:-1], pieces[1:]))
    assert pieces[-1][4]-pieces[-1][1] == pytest.approx(.22)


def test_submillimetre_remainder_is_merged_and_kept():
    box = [0, 0, 0, .5, 1.0002, .15]
    pieces = tool.piece_boxes([box], [.5, .5])
    assert len(pieces) == 2
    assert sum(volume(b) for b in pieces) == pytest.approx(volume(box))


@pytest.mark.parametrize('boxes,max_xy', [
    ([], None), ([[0, 0, 0, 1, 1, 0]], None),
    ([[0, 0, 0, float('nan'), 1, 1]], None),
    ([[0, 0, 0, 1, 1, 1]], [0, .5]),
    ([[0, 0, 0, 1, 1, 1]], [.5, float('inf')]),
    ([[0, 0, 0, 1, 1, 1], [.9, 0, 0, 1.9, 1, 1]], None),
])
def test_invalid_or_overlapping_source_fails_closed(boxes, max_xy):
    with pytest.raises(ValueError):
        tool.piece_boxes(boxes, max_xy)


def test_piece_count_bound_prevents_oversized_batch():
    with pytest.raises(ValueError, match='Demasiadas'):
        tool.piece_boxes([[0, 0, 0, 20, 20, .15]], [.5, .5], limit=100)


def test_touching_pieces_are_accepted_without_overlap():
    assert len(tool.piece_boxes([[0, 0, 0, .5, .5, .15], [.5, 0, 0, 1, .5, .15]])) == 2


@pytest.mark.parametrize('rollback_raises', [False,True])
def test_transaction_setup_failure_rolls_back_and_disposes_even_if_rollback_fails(rollback_raises):
    calls = []
    class Transaction:
        def Start(self):
            return 'started'
        def GetStatus(self):
            return 'started'
        def GetFailureHandlingOptions(self):
            raise RuntimeError('failure options unavailable')
        def SetFailureHandlingOptions(self, options):
            pytest.fail('Setter must not run after getter failed')
        def RollBack(self):
            calls.append('rollback')
            if rollback_raises:
                raise RuntimeError('rollback failed')
            return 'rolledback'
        def Dispose(self):
            calls.append('dispose')
    db = SimpleNamespace(Transaction=lambda *args: Transaction(),
                         TransactionStatus=SimpleNamespace(Started='started', RolledBack='rolledback'))
    errors = []
    with pytest.raises(RuntimeError, match='failure options unavailable'):
        tool._start_transaction(db, None, 'sample', None, errors)
    assert calls == ['rollback','dispose']
    assert errors == (['rollback failed'] if rollback_raises else [])
