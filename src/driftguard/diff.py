"""The diff engine: compare two :class:`SchemaSnapshot` objects.

This is the heart of DriftGuard. It produces a flat, ordered list of
:class:`Change` records describing exactly how a schema evolved from ``baseline``
to ``current``. Severity classification lives in :mod:`driftguard.classify` so
the diff stays a pure structural comparison that is trivial to unit test.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import ColumnSchema, SchemaSnapshot, TableSchema
from .rules import ChangeType, Severity


@dataclass(slots=True)
class Change:
    """One structural difference between two snapshots."""

    type: ChangeType
    table: str
    column: str | None = None
    detail: str = ""
    before: Any = None
    after: Any = None
    severity: Severity = Severity.SAFE
    rationale: str = ""
    # Set when an explicit waiver rule accepts this change. Waived changes stay
    # in the report (for auditability) but do not fail the build.
    ignored: bool = False
    ignore_reason: str = ""

    @property
    def location(self) -> str:
        """Human-readable ``table`` or ``table.column`` identifier."""
        return self.table if self.column is None else f"{self.table}.{self.column}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "table": self.table,
            "column": self.column,
            "detail": self.detail,
            "before": self.before,
            "after": self.after,
            "severity": self.severity.value,
            "rationale": self.rationale,
            "ignored": self.ignored,
            "ignore_reason": self.ignore_reason,
        }


def _detect_column_renames(
    added: dict[str, ColumnSchema],
    removed: dict[str, ColumnSchema],
) -> list[tuple[ColumnSchema, ColumnSchema]]:
    """Heuristically pair a removed column with an added one as a rename.

    A rename is *inferred* (SQL introspection cannot prove it) when exactly one
    removed and one added column share the same type family and nullability. We
    stay conservative: ambiguous cases (multiple candidates) are left as separate
    add/remove events rather than guessing wrong.
    """
    renames: list[tuple[ColumnSchema, ColumnSchema]] = []
    used_added: set[str] = set()
    for rname, rcol in list(removed.items()):
        candidates = [
            acol
            for aname, acol in added.items()
            if aname not in used_added
            and acol.type_family == rcol.type_family
            and acol.nullable == rcol.nullable
        ]
        if len(candidates) == 1:
            acol = candidates[0]
            renames.append((rcol, acol))
            used_added.add(acol.name)
    return renames


def _diff_columns(table_name: str, before: TableSchema, after: TableSchema) -> list[Change]:
    changes: list[Change] = []
    before_cols = before.columns
    after_cols = after.columns

    added = {n: c for n, c in after_cols.items() if n not in before_cols}
    removed = {n: c for n, c in before_cols.items() if n not in after_cols}

    renames = _detect_column_renames(added, removed)
    renamed_before = {r[0].name for r in renames}
    renamed_after = {r[1].name for r in renames}

    for rcol, acol in renames:
        changes.append(
            Change(
                type=ChangeType.COLUMN_RENAMED,
                table=table_name,
                column=acol.name,
                detail=f"{rcol.name} -> {acol.name}",
                before=rcol.name,
                after=acol.name,
            )
        )

    for name, col in removed.items():
        if name in renamed_before:
            continue
        changes.append(
            Change(
                type=ChangeType.COLUMN_REMOVED,
                table=table_name,
                column=name,
                detail=f"column '{name}' removed",
                before=col.to_dict(),
            )
        )

    for name, col in added.items():
        if name in renamed_after:
            continue
        changes.append(
            Change(
                type=ChangeType.COLUMN_ADDED,
                table=table_name,
                column=name,
                detail=f"column '{name}' added",
                after=col.to_dict(),
            )
        )

    # Columns present in both: compare attributes.
    for name in before_cols.keys() & after_cols.keys():
        b = before_cols[name]
        a = after_cols[name]
        if (b.data_type, b.type_family) != (a.data_type, a.type_family):
            changes.append(
                Change(
                    type=ChangeType.COLUMN_TYPE_CHANGED,
                    table=table_name,
                    column=name,
                    detail=f"type {b.data_type} -> {a.data_type}",
                    before=b.data_type,
                    after=a.data_type,
                )
            )
        if b.nullable != a.nullable:
            changes.append(
                Change(
                    type=ChangeType.COLUMN_NULLABILITY_CHANGED,
                    table=table_name,
                    column=name,
                    detail=f"nullable {b.nullable} -> {a.nullable}",
                    before=b.nullable,
                    after=a.nullable,
                )
            )
        if (b.default or None) != (a.default or None):
            changes.append(
                Change(
                    type=ChangeType.COLUMN_DEFAULT_CHANGED,
                    table=table_name,
                    column=name,
                    detail=f"default {b.default!r} -> {a.default!r}",
                    before=b.default,
                    after=a.default,
                )
            )
    return changes


def _diff_constraints(table_name: str, before: TableSchema, after: TableSchema) -> list[Change]:
    changes: list[Change] = []

    if before.primary_key != after.primary_key:
        changes.append(
            Change(
                type=ChangeType.PRIMARY_KEY_CHANGED,
                table=table_name,
                detail=f"primary key {list(before.primary_key)} -> {list(after.primary_key)}",
                before=list(before.primary_key),
                after=list(after.primary_key),
            )
        )

    b_fks, a_fks = before.foreign_keys, after.foreign_keys
    for name in b_fks.keys() - a_fks.keys():
        changes.append(
            Change(
                type=ChangeType.FOREIGN_KEY_REMOVED,
                table=table_name,
                detail=f"foreign key '{name}' removed",
                before=b_fks[name].to_dict(),
            )
        )
    for name in a_fks.keys() - b_fks.keys():
        changes.append(
            Change(
                type=ChangeType.FOREIGN_KEY_ADDED,
                table=table_name,
                detail=f"foreign key '{name}' added",
                after=a_fks[name].to_dict(),
            )
        )

    b_ix, a_ix = before.indexes, after.indexes
    for name in b_ix.keys() - a_ix.keys():
        changes.append(
            Change(
                type=ChangeType.INDEX_REMOVED,
                table=table_name,
                detail=f"index '{name}' removed",
                before=b_ix[name].to_dict(),
            )
        )
    for name in a_ix.keys() - b_ix.keys():
        changes.append(
            Change(
                type=ChangeType.INDEX_ADDED,
                table=table_name,
                detail=f"index '{name}' added",
                after=a_ix[name].to_dict(),
            )
        )
    return changes


def diff_snapshots(baseline: SchemaSnapshot, current: SchemaSnapshot) -> list[Change]:
    """Return every structural change from ``baseline`` to ``current``.

    Changes are returned unsorted here and are *not* yet classified for severity;
    callers typically pass the result to :func:`driftguard.classify.classify`.
    """
    changes: list[Change] = []

    baseline_tables = baseline.tables
    current_tables = current.tables

    for name in current_tables.keys() - baseline_tables.keys():
        changes.append(
            Change(
                type=ChangeType.TABLE_ADDED,
                table=name,
                detail=f"table '{name}' added",
                after={"columns": [c.name for c in current_tables[name].columns.values()]},
            )
        )
    for name in baseline_tables.keys() - current_tables.keys():
        changes.append(
            Change(
                type=ChangeType.TABLE_REMOVED,
                table=name,
                detail=f"table '{name}' removed",
                before={"columns": [c.name for c in baseline_tables[name].columns.values()]},
            )
        )

    for name in baseline_tables.keys() & current_tables.keys():
        b = baseline_tables[name]
        a = current_tables[name]
        changes.extend(_diff_columns(name, b, a))
        changes.extend(_diff_constraints(name, b, a))

    return changes
