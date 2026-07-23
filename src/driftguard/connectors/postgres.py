"""PostgreSQL connector.

The ``psycopg`` (v3) driver is imported lazily inside :meth:`snapshot` so that
users who never touch Postgres pay no import cost and hit no ImportError. Schema
is read from the standard ``information_schema`` views.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ..models import ColumnSchema, ForeignKeySchema, IndexSchema, SchemaSnapshot, TableSchema
from .base import Connector, _should_include, register


def _type_family(data_type: str) -> str:
    t = (data_type or "").lower()
    if any(k in t for k in ("int", "serial")):
        return "integer"
    if any(k in t for k in ("real", "double", "numeric", "decimal", "float")):
        return "float"
    if any(k in t for k in ("char", "text")):
        return "string"
    if any(k in t for k in ("timestamp", "date", "time")):
        return "datetime"
    if "bool" in t:
        return "boolean"
    if "json" in t:
        return "json"
    return "unknown"


@register("postgresql")
@register("postgres")
class PostgresConnector(Connector):
    dialect = "postgresql"

    def snapshot(
        self,
        include_tables: list[str] | None = None,
        exclude_tables: list[str] | None = None,
    ) -> SchemaSnapshot:
        try:
            import psycopg  # type: ignore
        except ImportError as exc:  # pragma: no cover - exercised only without driver
            raise RuntimeError(
                "PostgreSQL support requires the 'psycopg' driver. "
                "Install it with: pip install 'driftguard[postgres]'"
            ) from exc

        conn = psycopg.connect(self.url)
        try:
            return self._reflect(conn, include_tables, exclude_tables)
        finally:
            conn.close()

    def _reflect(self, conn, include_tables, exclude_tables) -> SchemaSnapshot:  # noqa: ANN001
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name"
        )
        table_names = [r[0] for r in cur.fetchall()]

        tables: dict[str, TableSchema] = {}
        for tname in table_names:
            if not _should_include(tname, include_tables, exclude_tables):
                continue
            tables[tname] = self._reflect_table(cur, tname)

        return SchemaSnapshot(
            dialect=self.dialect,
            database=conn.info.dbname,
            tables=tables,
            captured_at=datetime.now(timezone.utc).isoformat(),
        )

    def _reflect_table(self, cur, tname: str) -> TableSchema:  # noqa: ANN001
        cur.execute(
            "SELECT column_name, data_type, is_nullable, column_default, ordinal_position "
            "FROM information_schema.columns WHERE table_schema='public' AND table_name=%s "
            "ORDER BY ordinal_position",
            (tname,),
        )
        columns: dict[str, ColumnSchema] = {}
        for name, data_type, is_nullable, default, ordinal in cur.fetchall():
            columns[name] = ColumnSchema(
                name=name,
                data_type=str(data_type).upper(),
                type_family=_type_family(data_type),
                nullable=(is_nullable == "YES"),
                default=None if default is None else str(default),
                ordinal=int(ordinal),
            )

        cur.execute(
            "SELECT kcu.column_name FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name "
            "WHERE tc.table_name=%s AND tc.constraint_type='PRIMARY KEY' "
            "ORDER BY kcu.ordinal_position",
            (tname,),
        )
        primary_key = tuple(r[0] for r in cur.fetchall())
        for pk_col in primary_key:
            if pk_col in columns:
                columns[pk_col] = _with_pk(columns[pk_col])

        return TableSchema(name=tname, columns=columns, primary_key=primary_key)


def _with_pk(col: ColumnSchema) -> ColumnSchema:
    return ColumnSchema(
        name=col.name,
        data_type=col.data_type,
        type_family=col.type_family,
        nullable=col.nullable,
        default=col.default,
        is_primary_key=True,
        ordinal=col.ordinal,
        comment=col.comment,
    )
