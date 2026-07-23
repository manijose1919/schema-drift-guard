from __future__ import annotations

import json
import xml.etree.ElementTree as ET

import pytest
from conftest import col, snapshot, table

from driftguard.classify import classify
from driftguard.diff import diff_snapshots
from driftguard.ignores import IgnoreRule, apply_ignores
from driftguard.report import (
    FORMATS,
    render,
    render_junit,
    render_markdown,
    render_sarif,
    summarize,
)
from driftguard.rules import Severity


def _mixed_changes():
    """One breaking (dropped column) + one safe (added nullable column).

    The added column deliberately uses a *different* type family from the
    dropped one; otherwise the rename heuristic correctly pairs them into a
    single COLUMN_RENAMED and there is no add/remove pair to assert on.
    """
    a = snapshot(table("users", [col("id"), col("email", "TEXT", "string")]))
    b = snapshot(table("users", [col("id"), col("age", "INTEGER", "integer", nullable=True)]))
    return classify(diff_snapshots(a, b))


def test_summarize_counts():
    counts = summarize(_mixed_changes())
    assert counts["breaking"] == 1
    assert counts["safe"] == 1
    assert counts["ignored"] == 0


def test_summarize_excludes_waived_from_severity_counts():
    changes = _mixed_changes()
    apply_ignores(changes, [IgnoreRule(reason="ok", type="column_removed")])
    counts = summarize(changes)
    assert counts["breaking"] == 0
    assert counts["ignored"] == 1


@pytest.mark.parametrize("fmt", FORMATS)
def test_every_format_renders_without_error(fmt):
    out = render(_mixed_changes(), fmt)
    assert isinstance(out, str) and out.strip()


def test_unknown_format_raises():
    with pytest.raises(ValueError, match="Unknown format"):
        render(_mixed_changes(), "yaml")


# --- JUnit ------------------------------------------------------------------

def test_junit_is_valid_xml_with_failure_for_breaking():
    xml = render_junit(_mixed_changes(), fail_on=Severity.BREAKING)
    root = ET.fromstring(xml.split("?>", 1)[1])
    assert root.tag == "testsuite"
    assert root.get("tests") == "2"
    assert root.get("failures") == "1"

    failures = root.findall(".//failure")
    assert len(failures) == 1
    assert "email" in failures[0].get("message")


def test_junit_marks_waived_changes_as_skipped():
    changes = _mixed_changes()
    apply_ignores(changes, [IgnoreRule(reason="approved DATA-1", type="column_removed")])
    xml = render_junit(changes)
    root = ET.fromstring(xml.split("?>", 1)[1])
    assert root.get("failures") == "0"
    assert root.get("skipped") == "1"
    assert "approved DATA-1" in root.find(".//skipped").get("message")


def test_junit_threshold_changes_failure_count():
    # At fail_on=safe, even the additive change becomes a failure.
    xml = render_junit(_mixed_changes(), fail_on=Severity.SAFE)
    root = ET.fromstring(xml.split("?>", 1)[1])
    assert root.get("failures") == "2"


# --- SARIF ------------------------------------------------------------------

def test_sarif_shape_and_levels():
    doc = json.loads(render_sarif(_mixed_changes()))
    assert doc["version"] == "2.1.0"
    results = doc["runs"][0]["results"]
    assert len(results) == 2
    levels = {r["level"] for r in results}
    assert "error" in levels  # breaking -> error
    assert all(r["ruleId"].startswith("driftguard/") for r in results)


def test_sarif_suppresses_waived_findings():
    changes = _mixed_changes()
    apply_ignores(changes, [IgnoreRule(reason="ok", type="column_removed")])
    doc = json.loads(render_sarif(changes))
    results = doc["runs"][0]["results"]
    assert all("email" not in r["message"]["text"] for r in results)


# --- Markdown ---------------------------------------------------------------

def test_markdown_headline_reflects_breaking_count():
    md = render_markdown(_mixed_changes())
    assert md.startswith("## 🔴 DriftGuard: 1 breaking")
    assert "`users.email`" in md
    assert "| :-: |" in md  # table renders


def test_markdown_clean_run():
    assert "no schema drift" in render_markdown([]).lower()


def test_markdown_shows_waiver_reason():
    changes = _mixed_changes()
    apply_ignores(changes, [IgnoreRule(reason="approved DATA-9", type="column_removed")])
    md = render_markdown(changes)
    assert "approved DATA-9" in md
    assert md.startswith("## ✅")  # no longer a breaking headline
