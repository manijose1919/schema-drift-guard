"""Typed, serialization-friendly models describing a database schema.

These models are intentionally built from :mod:`dataclasses` (stdlib only) rather
than a third-party validation library. The core engine ships inside users' CI
pipelines, so keeping it dependency-free means faster installs, no lockfile
churn, and a smaller supply-chain surface.

The models form a normalized, dialect-agnostic representation of a schema. A
:class:`SchemaSnapshot` is the unit that gets serialized to disk, versioned in a
repo, and diffed against another snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass(frozen=True, slots=True)
class ColumnSchema:
    """A single column, normalized across dialects.

    ``data_type`` is the raw dialect type string (e.g. ``"VARCHAR(255)"``);
    ``type_family`` is a coarse, dialect-agnostic bucket (e.g. ``"string"``) used
    by the classifier to reason about type-change compatibility.
    """

    name: str
    data_type: str
    type_family: str
    nullable: bool = True
    default: str | None = None
    is_primary_key: bool = False
    ordinal: int = 0
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ColumnSchema":
        return cls(
            name=data["name"],
            data_type=data["data_type"],
            type_family=data.get("type_family", "unknown"),
            nullable=bool(data.get("nullable", True)),
            default=data.get("default"),
            is_primary_key=bool(data.get("is_primary_key", False)),
            ordinal=int(data.get("ordinal", 0)),
            comment=data.get("comment"),
        )


@dataclass(frozen=True, slots=True)
class ForeignKeySchema:
    name: str
    columns: tuple[str, ...]
    referred_table: str
    referred_columns: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "columns": list(self.columns),
            "referred_table": self.referred_table,
            "referred_columns": list(self.referred_columns),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ForeignKeySchema":
        return cls(
            name=data["name"],
            columns=tuple(data.get("columns", [])),
            referred_table=data["referred_table"],
            referred_columns=tuple(data.get("referred_columns", [])),
        )


@dataclass(frozen=True, slots=True)
class IndexSchema:
    name: str
    columns: tuple[str, ...]
    unique: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "columns": list(self.columns), "unique": self.unique}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "IndexSchema":
        return cls(
            name=data["name"],
            columns=tuple(data.get("columns", [])),
            unique=bool(data.get("unique", False)),
        )


@dataclass(slots=True)
class TableSchema:
    name: str
    columns: dict[str, ColumnSchema] = field(default_factory=dict)
    primary_key: tuple[str, ...] = ()
    foreign_keys: dict[str, ForeignKeySchema] = field(default_factory=dict)
    indexes: dict[str, IndexSchema] = field(default_factory=dict)
    comment: str | None = None

    def to_dict(self) -> dict[str, Any]:
        # Columns are emitted as an ordinal-sorted list so serialized snapshots
        # are stable and diff cleanly in version control.
        ordered_cols = sorted(self.columns.values(), key=lambda c: (c.ordinal, c.name))
        return {
            "name": self.name,
            "columns": [c.to_dict() for c in ordered_cols],
            "primary_key": list(self.primary_key),
            "foreign_keys": [fk.to_dict() for fk in sorted(self.foreign_keys.values(), key=lambda f: f.name)],
            "indexes": [ix.to_dict() for ix in sorted(self.indexes.values(), key=lambda i: i.name)],
            "comment": self.comment,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TableSchema":
        columns = {c["name"]: ColumnSchema.from_dict(c) for c in data.get("columns", [])}
        foreign_keys = {fk["name"]: ForeignKeySchema.from_dict(fk) for fk in data.get("foreign_keys", [])}
        indexes = {ix["name"]: IndexSchema.from_dict(ix) for ix in data.get("indexes", [])}
        return cls(
            name=data["name"],
            columns=columns,
            primary_key=tuple(data.get("primary_key", [])),
            foreign_keys=foreign_keys,
            indexes=indexes,
            comment=data.get("comment"),
        )


@dataclass(slots=True)
class SchemaSnapshot:
    """A point-in-time capture of a database schema.

    This is the serialized artifact users commit to their repo (the free tier)
    or that the hosted service stores per run (the paid tier).
    """

    dialect: str
    database: str
    tables: dict[str, TableSchema] = field(default_factory=dict)
    captured_at: str | None = None
    driftguard_version: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "driftguard_version": self.driftguard_version,
            "dialect": self.dialect,
            "database": self.database,
            "captured_at": self.captured_at,
            "tables": [t.to_dict() for t in sorted(self.tables.values(), key=lambda t: t.name)],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "SchemaSnapshot":
        tables = {t["name"]: TableSchema.from_dict(t) for t in data.get("tables", [])}
        return cls(
            dialect=data.get("dialect", "unknown"),
            database=data.get("database", ""),
            tables=tables,
            captured_at=data.get("captured_at"),
            driftguard_version=data.get("driftguard_version"),
        )
