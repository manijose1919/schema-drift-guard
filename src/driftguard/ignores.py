"""Waiver ("ignore") rules — acknowledged, approved schema changes.

Real teams need an escape hatch: a table is being deliberately sunset, a column
rename was coordinated with every consumer, a migration was signed off in a
ticket. Without waivers, teams disable the check entirely — which is the worst
possible outcome.

Design principles:

1. **Never silently drop a change.** A waived change is still reported, marked
   ``ignored`` with the reason. Auditors can see exactly what was waived and why.
2. **Waivers expire.** An ``expires`` date forces periodic re-review so a
   temporary exception does not become permanent blindness.
3. **A reason is mandatory.** A waiver without justification is just a bug.
"""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from datetime import date

from .diff import Change


@dataclass(slots=True)
class IgnoreRule:
    """Matches changes that a team has explicitly accepted.

    Every specified field must match for the rule to apply (logical AND).
    Omitted fields match anything. ``table`` and ``column`` support glob
    patterns via :mod:`fnmatch`.
    """

    reason: str
    table: str | None = None
    column: str | None = None
    type: str | None = None
    expires: str | None = None  # ISO date, e.g. "2026-12-31"

    def is_expired(self, today: date | None = None) -> bool:
        if not self.expires:
            return False
        try:
            return date.fromisoformat(self.expires) < (today or date.today())
        except ValueError:
            # A malformed date must not silently disable the waiver's expiry;
            # treat it as expired so the change resurfaces for review.
            return True

    def matches(self, change: Change) -> bool:
        if self.table is not None and not fnmatch.fnmatch(change.table, self.table):
            return False
        if self.column is not None:
            if change.column is None or not fnmatch.fnmatch(change.column, self.column):
                return False
        if self.type is not None and change.type.value != self.type:
            return False
        return True

    @classmethod
    def from_dict(cls, data: dict) -> "IgnoreRule":
        reason = str(data.get("reason", "")).strip()
        if not reason:
            raise ValueError(
                "Every [[driftguard.ignore]] rule requires a 'reason'. "
                "An unexplained waiver is indistinguishable from a bug."
            )
        return cls(
            reason=reason,
            table=data.get("table"),
            column=data.get("column"),
            type=data.get("type"),
            expires=data.get("expires"),
        )


def apply_ignores(
    changes: list[Change],
    rules: list[IgnoreRule],
    today: date | None = None,
) -> list[Change]:
    """Mark changes matched by an active (non-expired) waiver as ignored.

    Mutates and returns the same list — waived changes stay in the report so
    they remain visible and auditable.
    """
    active = [r for r in rules if not r.is_expired(today)]
    for change in changes:
        for rule in active:
            if rule.matches(change):
                change.ignored = True
                change.ignore_reason = rule.reason
                break
    return changes


def expired_rules(rules: list[IgnoreRule], today: date | None = None) -> list[IgnoreRule]:
    """Waivers that have lapsed — surfaced as a warning so they get re-reviewed."""
    return [r for r in rules if r.is_expired(today)]
