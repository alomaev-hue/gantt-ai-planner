import uuid

from app.db.repo import VersionMeta
from app.services.plan_service import redo_target, undo_target

T = uuid.uuid4()
META = [
    VersionMeta(1, None),
    VersionMeta(2, None),
    VersionMeta(3, T),
    VersionMeta(4, T),
    VersionMeta(5, None),
]


def test_undo_single_version():
    assert undo_target(META, 5) == 4
    assert undo_target(META, 2) == 1


def test_undo_whole_turn_group():
    assert undo_target(META, 4) == 2


def test_undo_at_first_version_is_none():
    assert undo_target(META, 1) is None


def test_redo_skips_to_end_of_group():
    assert redo_target(META, 2) == 4
    assert redo_target(META, 4) == 5
    assert redo_target(META, 5) is None
