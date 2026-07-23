"""Assign a :class:`Severity` and human rationale to each structural change.

Kept separate from the diff so severity *policy* can evolve (and be tested)
without touching the structural comparison. Policy summary:

* BREAKING  — will break existing readers/writers (dropped column, removed
              table, incompatible type change, nullable -> not null, PK change).
* WARNING   — may break some consumers or masks intent (default change, removed
              index/FK, a new NOT NULL column with no default breaks inserts).
* SAFE      — purely additive and backward compatible (new nullable column,
              new table, added index).
"""

from __future__ import annotations

from .diff import Change
from .rules import ChangeType, Severity, TYPE_WIDENING


def _is_safe_widening(before_family: str, before_type: str, after_type: str) -> str | None:
    """Return None if this looks like a safe widen, else a reason string."""
    ladder = TYPE_WIDENING.get(before_family)
    if not ladder:
        return "type family has no defined widening path"

    def rank(type_str: str) -> int | None:
        t = type_str.lower()
        for i, member in enumerate(ladder):
            if member in t:
                return i
        return None

    b_rank = rank(before_type)
    a_rank = rank(after_type)
    if b_rank is None or a_rank is None:
        return "unrecognized type precision"
    if a_rank >= b_rank:
        return None  # widening or same width -> safe
    return "type narrowed; existing values may not fit"


def classify_change(change: Change) -> Change:
    """Mutate ``change`` in place with a severity and rationale, and return it."""
    t = change.type

    if t is ChangeType.TABLE_ADDED:
        change.severity = Severity.SAFE
        change.rationale = "New table is additive; no existing consumer depends on it."
    elif t is ChangeType.TABLE_REMOVED:
        change.severity = Severity.BREAKING
        change.rationale = "Dropping a table breaks every query, view, and job that reads it."
    elif t is ChangeType.COLUMN_ADDED:
        after = change.after or {}
        nullable = after.get("nullable", True) if isinstance(after, dict) else True
        has_default = (after.get("default") is not None) if isinstance(after, dict) else False
        if nullable or has_default:
            change.severity = Severity.SAFE
            change.rationale = "New nullable/defaulted column is backward compatible."
        else:
            change.severity = Severity.WARNING
            change.rationale = "New NOT NULL column without a default breaks existing INSERT statements."
    elif t is ChangeType.COLUMN_REMOVED:
        change.severity = Severity.BREAKING
        change.rationale = "Dropping a column breaks any SELECT, view, or model that references it."
    elif t is ChangeType.COLUMN_RENAMED:
        change.severity = Severity.BREAKING
        change.rationale = "Renamed column breaks consumers using the old name (inferred rename)."
    elif t is ChangeType.COLUMN_TYPE_CHANGED:
        # before/after here are the raw type strings; family lives on the column,
        # but we approximate using the string content.
        before_type = str(change.before or "")
        after_type = str(change.after or "")
        family = _guess_family(before_type)
        reason = _is_safe_widening(family, before_type, after_type)
        if reason is None:
            change.severity = Severity.WARNING
            change.rationale = "Type widened within family; generally safe but verify downstream casts."
        else:
            change.severity = Severity.BREAKING
            change.rationale = f"Incompatible type change ({reason})."
    elif t is ChangeType.COLUMN_NULLABILITY_CHANGED:
        if change.before is True and change.after is False:
            change.severity = Severity.BREAKING
            change.rationale = "Column became NOT NULL; existing rows/inserts with NULL will fail."
        else:
            change.severity = Severity.SAFE
            change.rationale = "Column relaxed to nullable; backward compatible."
    elif t is ChangeType.COLUMN_DEFAULT_CHANGED:
        change.severity = Severity.WARNING
        change.rationale = "Default value changed; new rows may differ from historical expectations."
    elif t is ChangeType.PRIMARY_KEY_CHANGED:
        change.severity = Severity.BREAKING
        change.rationale = "Primary key change alters row identity, joins, and upsert semantics."
    elif t is ChangeType.FOREIGN_KEY_REMOVED:
        change.severity = Severity.WARNING
        change.rationale = "Removed foreign key weakens referential guarantees consumers may rely on."
    elif t is ChangeType.FOREIGN_KEY_ADDED:
        change.severity = Severity.SAFE
        change.rationale = "Added foreign key strengthens integrity; additive."
    elif t is ChangeType.INDEX_REMOVED:
        change.severity = Severity.WARNING
        change.rationale = "Removed index may silently regress query performance downstream."
    elif t is ChangeType.INDEX_ADDED:
        change.severity = Severity.SAFE
        change.rationale = "Added index is a performance improvement; additive."
    else:
        change.severity = Severity.WARNING
        change.rationale = "Unclassified change; review manually."

    return change


def _guess_family(type_str: str) -> str:
    t = type_str.lower()
    if any(k in t for k in ("int",)):
        return "integer"
    if any(k in t for k in ("real", "float", "double", "numeric", "decimal")):
        return "float"
    if any(k in t for k in ("char", "text", "clob")):
        return "string"
    return "unknown"


def sort_changes(changes: list[Change]) -> list[Change]:
    """Order for display: actionable changes first, most severe first.

    Waived changes sink to the bottom so the top of every report is what the
    engineer actually has to deal with. Call this *after* applying waivers —
    :func:`classify` cannot know about waivers that are applied later.
    """
    return sorted(
        changes,
        key=lambda c: (c.ignored, -c.severity.rank, c.table, c.column or "", c.type.value),
    )


def classify(changes: list[Change]) -> list[Change]:
    """Classify every change and return them sorted most-severe first."""
    for c in changes:
        classify_change(c)
    return sort_changes(changes)


def max_severity(changes: list[Change], *, include_ignored: bool = False) -> Severity:
    """Highest severity present, or SAFE for an empty list.

    Waived (``ignored``) changes are excluded by default — this is the value CI
    gates on, so an accepted change must not fail the build.
    """
    relevant = changes if include_ignored else [c for c in changes if not c.ignored]
    if not relevant:
        return Severity.SAFE
    return max((c.severity for c in relevant), key=lambda s: s.rank)
