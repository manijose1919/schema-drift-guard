"""Enumerations and severity policy shared across the diff and classifier."""

from __future__ import annotations

from enum import Enum


class Severity(str, Enum):
    """How dangerous a change is to downstream consumers.

    Ordered so comparisons work: ``Severity.BREAKING > Severity.WARNING``.
    """

    SAFE = "safe"
    WARNING = "warning"
    BREAKING = "breaking"

    @property
    def rank(self) -> int:
        return {"safe": 0, "warning": 1, "breaking": 2}[self.value]

    def __lt__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank < other.rank

    def __le__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank <= other.rank

    # __gt__/__ge__ must be defined explicitly: because Severity subclasses str,
    # they would otherwise fall back to str's alphabetical comparison.
    def __gt__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank > other.rank

    def __ge__(self, other: object) -> bool:  # type: ignore[override]
        if not isinstance(other, Severity):
            return NotImplemented
        return self.rank >= other.rank


class ChangeType(str, Enum):
    TABLE_ADDED = "table_added"
    TABLE_REMOVED = "table_removed"
    COLUMN_ADDED = "column_added"
    COLUMN_REMOVED = "column_removed"
    COLUMN_RENAMED = "column_renamed"
    COLUMN_TYPE_CHANGED = "column_type_changed"
    COLUMN_NULLABILITY_CHANGED = "column_nullability_changed"
    COLUMN_DEFAULT_CHANGED = "column_default_changed"
    PRIMARY_KEY_CHANGED = "primary_key_changed"
    FOREIGN_KEY_ADDED = "foreign_key_added"
    FOREIGN_KEY_REMOVED = "foreign_key_removed"
    INDEX_ADDED = "index_added"
    INDEX_REMOVED = "index_removed"
    UNIQUE_CONSTRAINT_CHANGED = "unique_constraint_changed"


# Coarse type families used for compatibility reasoning. Widening within a family
# is generally safe (int -> bigint); narrowing or crossing families is breaking.
TYPE_WIDENING: dict[str, list[str]] = {
    # ordered smallest -> largest; a change to a later member is a safe widen
    "integer": ["tinyint", "smallint", "integer", "bigint"],
    "float": ["real", "float", "double"],
    "string": ["char", "varchar", "text"],
}
