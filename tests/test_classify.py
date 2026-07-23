from __future__ import annotations

from conftest import col, snapshot, table

from driftguard.classify import classify, max_severity
from driftguard.diff import diff_snapshots
from driftguard.rules import ChangeType, Severity


def _classified(a, b):
    return classify(diff_snapshots(a, b))


def _severity_of(changes, change_type):
    for c in changes:
        if c.type is change_type:
            return c.severity
    raise AssertionError(f"{change_type} not found in {[c.type for c in changes]}")


def test_dropping_column_is_breaking():
    a = snapshot(table("t", [col("id"), col("email", "TEXT", "string")]))
    b = snapshot(table("t", [col("id")]))
    changes = _classified(a, b)
    assert _severity_of(changes, ChangeType.COLUMN_REMOVED) is Severity.BREAKING


def test_adding_nullable_column_is_safe():
    a = snapshot(table("t", [col("id")]))
    b = snapshot(table("t", [col("id"), col("nickname", "TEXT", "string", nullable=True)]))
    changes = _classified(a, b)
    assert _severity_of(changes, ChangeType.COLUMN_ADDED) is Severity.SAFE


def test_adding_not_null_column_without_default_is_warning():
    a = snapshot(table("t", [col("id")]))
    b = snapshot(table("t", [col("id"), col("code", "TEXT", "string", nullable=False)]))
    changes = _classified(a, b)
    assert _severity_of(changes, ChangeType.COLUMN_ADDED) is Severity.WARNING


def test_type_widening_is_warning_not_breaking():
    a = snapshot(table("t", [col("n", "INTEGER", "integer")]))
    b = snapshot(table("t", [col("n", "BIGINT", "integer")]))
    changes = _classified(a, b)
    assert _severity_of(changes, ChangeType.COLUMN_TYPE_CHANGED) is Severity.WARNING


def test_type_narrowing_is_breaking():
    a = snapshot(table("t", [col("n", "BIGINT", "integer")]))
    b = snapshot(table("t", [col("n", "SMALLINT", "integer")]))
    changes = _classified(a, b)
    assert _severity_of(changes, ChangeType.COLUMN_TYPE_CHANGED) is Severity.BREAKING


def test_cross_family_type_change_is_breaking():
    a = snapshot(table("t", [col("v", "INTEGER", "integer")]))
    b = snapshot(table("t", [col("v", "TEXT", "string")]))
    changes = _classified(a, b)
    assert _severity_of(changes, ChangeType.COLUMN_TYPE_CHANGED) is Severity.BREAKING


def test_making_column_not_null_is_breaking():
    a = snapshot(table("t", [col("x", "TEXT", "string", nullable=True)]))
    b = snapshot(table("t", [col("x", "TEXT", "string", nullable=False)]))
    changes = _classified(a, b)
    assert _severity_of(changes, ChangeType.COLUMN_NULLABILITY_CHANGED) is Severity.BREAKING


def test_relaxing_to_nullable_is_safe():
    a = snapshot(table("t", [col("x", "TEXT", "string", nullable=False)]))
    b = snapshot(table("t", [col("x", "TEXT", "string", nullable=True)]))
    changes = _classified(a, b)
    assert _severity_of(changes, ChangeType.COLUMN_NULLABILITY_CHANGED) is Severity.SAFE


def test_results_sorted_breaking_first():
    a = snapshot(table("t", [col("id"), col("email", "TEXT", "string")]))
    b = snapshot(
        table("t", [col("id"), col("nickname", "TEXT", "string", nullable=True)])
    )
    # dropped email (breaking) + added nickname (safe)
    changes = _classified(a, b)
    assert changes[0].severity is Severity.BREAKING


def test_max_severity_empty_is_safe():
    assert max_severity([]) is Severity.SAFE


def test_severity_ordering():
    assert Severity.BREAKING > Severity.WARNING > Severity.SAFE
