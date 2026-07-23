from __future__ import annotations

from datetime import date

import pytest
from conftest import col, snapshot, table

from driftguard.classify import classify, max_severity
from driftguard.diff import diff_snapshots
from driftguard.ignores import IgnoreRule, apply_ignores, expired_rules
from driftguard.rules import Severity


def _dropped_email():
    a = snapshot(table("users", [col("id"), col("email", "TEXT", "string")]))
    b = snapshot(table("users", [col("id")]))
    return classify(diff_snapshots(a, b))


def test_waiver_marks_change_ignored_but_keeps_it_visible():
    changes = _dropped_email()
    rules = [IgnoreRule(reason="Approved in DATA-1234", table="users", type="column_removed")]
    apply_ignores(changes, rules)

    assert len(changes) == 1, "waived changes must remain in the report"
    assert changes[0].ignored is True
    assert changes[0].ignore_reason == "Approved in DATA-1234"


def test_waiver_removes_change_from_ci_gate():
    changes = _dropped_email()
    assert max_severity(changes) is Severity.BREAKING
    apply_ignores(changes, [IgnoreRule(reason="approved", table="users")])
    assert max_severity(changes) is Severity.SAFE
    # ...but the underlying severity is untouched for auditing
    assert max_severity(changes, include_ignored=True) is Severity.BREAKING


def test_glob_matching_on_table():
    changes = _dropped_email()
    apply_ignores(changes, [IgnoreRule(reason="legacy sunset", table="us*")])
    assert changes[0].ignored is True


def test_non_matching_rule_does_not_waive():
    changes = _dropped_email()
    apply_ignores(changes, [IgnoreRule(reason="x", table="orders")])
    assert changes[0].ignored is False


def test_type_must_also_match():
    changes = _dropped_email()
    apply_ignores(changes, [IgnoreRule(reason="x", table="users", type="table_removed")])
    assert changes[0].ignored is False


def test_expired_waiver_does_not_apply():
    changes = _dropped_email()
    rule = IgnoreRule(reason="temporary", table="users", expires="2020-01-01")
    apply_ignores(changes, [rule], today=date(2026, 7, 23))
    assert changes[0].ignored is False
    assert expired_rules([rule], today=date(2026, 7, 23)) == [rule]


def test_unexpired_waiver_applies():
    changes = _dropped_email()
    rule = IgnoreRule(reason="temporary", table="users", expires="2099-01-01")
    apply_ignores(changes, [rule], today=date(2026, 7, 23))
    assert changes[0].ignored is True


def test_malformed_expiry_is_treated_as_expired():
    # Fail safe: a typo in the date must not grant an unlimited waiver.
    rule = IgnoreRule(reason="x", expires="not-a-date")
    assert rule.is_expired() is True


def test_reason_is_mandatory():
    with pytest.raises(ValueError, match="reason"):
        IgnoreRule.from_dict({"table": "users"})


def test_waived_changes_sort_last():
    a = snapshot(table("t", [col("id"), col("a", "TEXT", "string"), col("b", "TEXT", "string")]))
    b = snapshot(table("t", [col("id")]))
    changes = classify(diff_snapshots(a, b))
    apply_ignores(changes, [IgnoreRule(reason="ok", table="t", column="a")])
    changes = classify(changes)  # re-sort
    assert changes[0].ignored is False
    assert changes[-1].ignored is True
