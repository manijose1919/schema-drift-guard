"""Render classified changes in the formats corporate CI systems consume.

Formats
-------
text      Human-readable console output (default).
json      Machine-readable; stable contract for scripting and the hosted API.
junit     JUnit XML — natively ingested by Jenkins, GitLab CI, Azure DevOps,
          CircleCI and Bitbucket, so drift appears in dashboards teams already
          watch instead of requiring new tooling.
markdown  GitHub/GitLab pull-request comment body.
sarif     SARIF 2.1.0 — uploads to GitHub Code Scanning so each drift shows up
          as an inline annotation on the PR.

No third-party formatting library: a tiny ANSI helper keeps console output
readable while staying dependency-free. Colour auto-disables when output is not
a TTY or when ``NO_COLOR`` is set.
"""

from __future__ import annotations

import json
import os
import sys

# NOTE ON XML SAFETY: this module only *serializes* XML (ET.Element/ET.tostring);
# it never parses XML, and no untrusted input is ever fed to a parser here. The
# XXE / billion-laughs attacks that motivate `defusedxml` apply exclusively to
# parsing, so the stdlib serializer is safe and lets the core keep its
# zero-dependency guarantee. If a future change adds XML *parsing* of
# user-supplied data, switch that code path to defusedxml.
import xml.etree.ElementTree as ET  # noqa: S405 - serialization only, see note above

from .diff import Change
from .rules import Severity

_COLORS = {
    Severity.BREAKING: "31",  # red
    Severity.WARNING: "33",  # yellow
    Severity.SAFE: "32",  # green
}
# ASCII-only markers: CI consoles (notably Windows cp1252) cannot encode
# fancy glyphs, and a data-quality gate must never crash on its own output.
_SYMBOL = {Severity.BREAKING: "[X]", Severity.WARNING: "[!]", Severity.SAFE: "[+]"}

FORMATS = ("text", "json", "junit", "markdown", "sarif")


def _use_color() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def _c(text: str, severity: Severity) -> str:
    if not _use_color():
        return text
    return f"\033[{_COLORS[severity]}m{text}\033[0m"


def summarize(changes: list[Change]) -> dict[str, int]:
    """Counts by severity, plus how many were waived."""
    active = [c for c in changes if not c.ignored]
    return {
        "breaking": sum(c.severity is Severity.BREAKING for c in active),
        "warning": sum(c.severity is Severity.WARNING for c in active),
        "safe": sum(c.severity is Severity.SAFE for c in active),
        "ignored": sum(c.ignored for c in changes),
        "total": len(changes),
    }


# --- text -------------------------------------------------------------------

def render_text(changes: list[Change]) -> str:
    if not changes:
        return "No schema drift detected. OK"

    counts = summarize(changes)
    lines = ["DriftGuard - schema drift report", "=" * 40]

    for c in changes:
        if c.ignored:
            lines.append(f"[~] [WAIVED] {c.location}: {c.detail}")
            lines.append(f"    -> waived: {c.ignore_reason}")
            continue
        head = f"{_SYMBOL[c.severity]} [{c.severity.value.upper()}] {c.location}: {c.detail}"
        lines.append(_c(head, c.severity))
        lines.append(f"    -> {c.rationale}")

    lines.append("-" * 40)
    summary = (
        f"{counts['breaking']} breaking, {counts['warning']} warning, {counts['safe']} safe"
    )
    if counts["ignored"]:
        summary += f", {counts['ignored']} waived"
    lines.append(summary)
    return "\n".join(lines)


# --- json -------------------------------------------------------------------

def render_json(changes: list[Change]) -> str:
    return json.dumps(
        {"changes": [c.to_dict() for c in changes], "summary": summarize(changes)},
        indent=2,
    )


# --- junit ------------------------------------------------------------------

def render_junit(changes: list[Change], *, fail_on: Severity = Severity.BREAKING) -> str:
    """JUnit XML: one test case per change.

    Changes at or above ``fail_on`` become ``<failure>`` elements; waived ones
    become ``<skipped>`` so CI dashboards show them as deliberately excluded
    rather than as passes.
    """
    counts = summarize(changes)
    suite = ET.Element(
        "testsuite",
        {
            "name": "driftguard.schema",
            "tests": str(len(changes)),
            "failures": str(
                sum(
                    1
                    for c in changes
                    if not c.ignored and c.severity.rank >= fail_on.rank
                )
            ),
            "skipped": str(counts["ignored"]),
            "errors": "0",
        },
    )

    for c in changes:
        case = ET.SubElement(
            suite,
            "testcase",
            {"classname": f"schema.{c.table}", "name": f"{c.type.value}:{c.location}"},
        )
        if c.ignored:
            ET.SubElement(case, "skipped", {"message": f"waived: {c.ignore_reason}"})
        elif c.severity.rank >= fail_on.rank:
            failure = ET.SubElement(
                case,
                "failure",
                {"type": c.severity.value, "message": c.detail},
            )
            failure.text = c.rationale
        else:
            # Passing case, but keep the detail visible in the report body.
            out = ET.SubElement(case, "system-out")
            out.text = f"[{c.severity.value}] {c.detail} -> {c.rationale}"

    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(
        suite, encoding="unicode"
    )


# --- markdown ---------------------------------------------------------------

_MD_ICON = {
    Severity.BREAKING: "🔴",
    Severity.WARNING: "🟡",
    Severity.SAFE: "🟢",
}


def render_markdown(changes: list[Change]) -> str:
    """A pull-request comment body."""
    counts = summarize(changes)

    if not changes:
        return "## ✅ DriftGuard: no schema drift detected\n"

    if counts["breaking"]:
        header = f"## 🔴 DriftGuard: {counts['breaking']} breaking schema change(s) detected"
    elif counts["warning"]:
        header = f"## 🟡 DriftGuard: {counts['warning']} schema warning(s)"
    else:
        header = "## ✅ DriftGuard: only backward-compatible changes"

    lines = [
        header,
        "",
        f"**{counts['breaking']}** breaking · **{counts['warning']}** warning · "
        f"**{counts['safe']}** safe · **{counts['ignored']}** waived",
        "",
        "| | Object | Change | Why it matters |",
        "| :-: | --- | --- | --- |",
    ]

    for c in changes:
        if c.ignored:
            lines.append(
                f"| ⚪ | `{c.location}` | {c.detail} | _Waived: {c.ignore_reason}_ |"
            )
        else:
            lines.append(
                f"| {_MD_ICON[c.severity]} | `{c.location}` | {c.detail} | {c.rationale} |"
            )

    lines += ["", "<sub>Generated by [DriftGuard](https://github.com/manijose1919/schema-drift-guard)</sub>"]
    return "\n".join(lines)


# --- sarif ------------------------------------------------------------------

_SARIF_LEVEL = {
    Severity.BREAKING: "error",
    Severity.WARNING: "warning",
    Severity.SAFE: "note",
}


def render_sarif(changes: list[Change], *, snapshot_path: str = ".driftguard/snapshots/baseline.json") -> str:
    """SARIF 2.1.0 for GitHub Code Scanning / any SARIF-aware security dashboard."""
    results = []
    for c in changes:
        if c.ignored:
            continue  # waived findings are suppressed from the security dashboard
        results.append(
            {
                "ruleId": f"driftguard/{c.type.value}",
                "level": _SARIF_LEVEL[c.severity],
                "message": {"text": f"{c.location}: {c.detail} — {c.rationale}"},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": snapshot_path},
                            "region": {"startLine": 1},
                        }
                    }
                ],
            }
        )

    rule_ids = sorted({r["ruleId"] for r in results})
    return json.dumps(
        {
            "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "DriftGuard",
                            "informationUri": "https://github.com/manijose1919/schema-drift-guard",
                            "rules": [{"id": rid} for rid in rule_ids],
                        }
                    },
                    "results": results,
                }
            ],
        },
        indent=2,
    )


# --- dispatcher -------------------------------------------------------------

def render(changes: list[Change], fmt: str, *, fail_on: Severity = Severity.BREAKING) -> str:
    if fmt == "text":
        return render_text(changes)
    if fmt == "json":
        return render_json(changes)
    if fmt == "junit":
        return render_junit(changes, fail_on=fail_on)
    if fmt == "markdown":
        return render_markdown(changes)
    if fmt == "sarif":
        return render_sarif(changes)
    raise ValueError(f"Unknown format {fmt!r}. Choose from: {', '.join(FORMATS)}")
