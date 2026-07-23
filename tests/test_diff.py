from __future__ import annotations

from conftest import col, snapshot, table

from driftguard.diff import diff_snapshots
from driftguard.rules import ChangeType


def _types(changes):
    return {c.type for c in changes}


def test_no_change_yields_empty_diff():
    a = snapshot(table("users", [col("id", pk=True), col("email", "TEXT", "string")]))
    b = snapshot(table("users", [col("id", pk=True), col("email", "TEXT", "string")]))
    assert diff_snapshots(a, b) == []


def test_table_added_and_removed():
    a = snapshot(table("users", [col("id")]))
    b = snapshot(table("orders", [col("id")]))
    changes = diff_snapshots(a, b)
    assert ChangeType.TABLE_ADDED in _types(changes)
    assert ChangeType.TABLE_REMOVED in _types(changes)


def test_column_added_and_removed():
    a = snapshot(table("t", [col("id"), col("old", "TEXT", "string")]))
    b = snapshot(table("t", [col("id"), col("new", "INTEGER", "integer")]))
    changes = diff_snapshots(a, b)
    # different type families -> not treated as a rename
    assert ChangeType.COLUMN_ADDED in _types(changes)
    assert ChangeType.COLUMN_REMOVED in _types(changes)


def test_rename_detection_same_family():
    a = snapshot(table("t", [col("id"), col("username", "TEXT", "string")]))
    b = snapshot(table("t", [col("id"), col("handle", "TEXT", "string")]))
    changes = diff_snapshots(a, b)
    rename = [c for c in changes if c.type is ChangeType.COLUMN_RENAMED]
    assert len(rename) == 1
    assert rename[0].before == "username"
    assert rename[0].after == "handle"
    # a rename must not also produce add+remove noise
    assert ChangeType.COLUMN_ADDED not in _types(changes)
    assert ChangeType.COLUMN_REMOVED not in _types(changes)


def test_ambiguous_rename_stays_add_remove():
    # two removed + two added of same family -> ambiguous -> no rename guess
    a = snapshot(table("t", [col("a", "TEXT", "string"), col("b", "TEXT", "string")]))
    b = snapshot(table("t", [col("c", "TEXT", "string"), col("d", "TEXT", "string")]))
    changes = diff_snapshots(a, b)
    assert ChangeType.COLUMN_RENAMED not in _types(changes)
    assert sum(c.type is ChangeType.COLUMN_ADDED for c in changes) == 2
    assert sum(c.type is ChangeType.COLUMN_REMOVED for c in changes) == 2


def test_type_change_detected():
    a = snapshot(table("t", [col("amount", "INTEGER", "integer")]))
    b = snapshot(table("t", [col("amount", "BIGINT", "integer")]))
    changes = diff_snapshots(a, b)
    assert ChangeType.COLUMN_TYPE_CHANGED in _types(changes)


def test_nullability_and_default_changes():
    a = snapshot(table("t", [col("x", "TEXT", "string", nullable=True, default="a")]))
    b = snapshot(table("t", [col("x", "TEXT", "string", nullable=False, default="b")]))
    changes = diff_snapshots(a, b)
    assert ChangeType.COLUMN_NULLABILITY_CHANGED in _types(changes)
    assert ChangeType.COLUMN_DEFAULT_CHANGED in _types(changes)


def test_primary_key_change():
    a = snapshot(table("t", [col("id"), col("email", "TEXT", "string")], primary_key=("id",)))
    b = snapshot(table("t", [col("id"), col("email", "TEXT", "string")], primary_key=("email",)))
    changes = diff_snapshots(a, b)
    assert ChangeType.PRIMARY_KEY_CHANGED in _types(changes)
