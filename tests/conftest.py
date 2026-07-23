"""Shared test helpers for building snapshots without a live database."""

from __future__ import annotations

from driftguard.models import ColumnSchema, SchemaSnapshot, TableSchema


def col(name, data_type="INTEGER", family="integer", nullable=True, default=None, pk=False, ordinal=0):
    return ColumnSchema(
        name=name,
        data_type=data_type,
        type_family=family,
        nullable=nullable,
        default=default,
        is_primary_key=pk,
        ordinal=ordinal,
    )


def table(name, columns, primary_key=()):
    return TableSchema(
        name=name,
        columns={c.name: c for c in columns},
        primary_key=tuple(primary_key),
    )


def snapshot(*tables, dialect="sqlite", database="test"):
    return SchemaSnapshot(
        dialect=dialect,
        database=database,
        tables={t.name: t for t in tables},
    )
