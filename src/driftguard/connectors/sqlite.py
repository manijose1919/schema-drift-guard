"""SQLite connector — stdlib only, the reference implementation.

SQLite ships with Python, so it needs no driver install. It doubles as the
worked example every other connector mirrors and as the backing store for the
engine's own test suite.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

from ..models import ColumnSchema, ForeignKeySchema, IndexSchema, SchemaSnapshot, TableSchema
from .base import Connector, _should_include, register


def _type_family(declared: str) -> str:
    t = (declared or "").lower()
    if "int" in t:
        return "integer"
    if any(k in t for k in ("real", "floa", "doub", "num", "dec")):
        return "float"
    if any(k in t for k in ("char", "clob", "text")):
        return "string"
    if "blob" in t or t == "":
        return "blob"
    if any(k in t for k in ("date", "time")):
        return "datetime"
    return "unknown"


@register("sqlite")
class SQLiteConnector(Connector):
    dialect = "sqlite"

    def _path(self) -> str:
        prefix = "sqlite:///"
        if self.url.startswith(prefix):
            raw = self.url[len(prefix):]
        else:
            raw = self.url.split("://", 1)[-1]
        return raw or ":memory:"

    def snapshot(
        self,
        include_tables: list[str] | None = None,
        exclude_tables: list[str] | None = None,
    ) -> SchemaSnapshot:
        conn = sqlite3.connect(self._path())
        try:
            return self._snapshot_conn(conn, include_tables, exclude_tables)
        finally:
            conn.close()

    def _snapshot_conn(
        self,
        conn: sqlite3.Connection,
        include_tables: list[str] | None,
        exclude_tables: list[str] | None,
    ) -> SchemaSnapshot:
        cur = conn.cursor()
        cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
        table_names = [r[0] for r in cur.fetchall()]

        tables: dict[str, TableSchema] = {}
        for tname in table_names:
            if not _should_include(tname, include_tables, exclude_tables):
                continue
            tables[tname] = self._reflect_table(cur, tname)

        return SchemaSnapshot(
            dialect=self.dialect,
            database=self._path(),
            tables=tables,
            captured_at=datetime.now(timezone.utc).isoformat(),
        )

    def _reflect_table(self, cur: sqlite3.Cursor, tname: str) -> TableSchema:
        columns: dict[str, ColumnSchema] = {}
        primary_key: list[tuple[int, str]] = []

        cur.execute(f'PRAGMA table_info("{tname}")')
        for cid, name, decl_type, notnull, dflt, pk in cur.fetchall():
            columns[name] = ColumnSchema(
                name=name,
                data_type=(decl_type or "").upper() or "BLOB",
                type_family=_type_family(decl_type),
                nullable=not bool(notnull),
                default=None if dflt is None else str(dflt),
                is_primary_key=bool(pk),
                ordinal=int(cid),
            )
            if pk:
                primary_key.append((int(pk), name))

        foreign_keys: dict[str, ForeignKeySchema] = {}
        cur.execute(f'PRAGMA foreign_key_list("{tname}")')
        # Group multi-column FKs by their id.
        fk_rows: dict[int, list[tuple]] = {}
        for row in cur.fetchall():
            fk_id, seq, ref_table, from_col, to_col = row[0], row[1], row[2], row[3], row[4]
            fk_rows.setdefault(fk_id, []).append((seq, from_col, to_col, ref_table))
        for fk_id, rows in fk_rows.items():
            rows.sort(key=lambda r: r[0])
            cols = tuple(r[1] for r in rows)
            ref_cols = tuple(r[2] for r in rows)
            ref_table = rows[0][3]
            fk_name = f"fk_{tname}_{'_'.join(cols)}"
            foreign_keys[fk_name] = ForeignKeySchema(
                name=fk_name,
                columns=cols,
                referred_table=ref_table,
                referred_columns=ref_cols,
            )

        indexes: dict[str, IndexSchema] = {}
        cur.execute(f'PRAGMA index_list("{tname}")')
        for row in cur.fetchall():
            idx_name, unique = row[1], bool(row[2])
            cur.execute(f'PRAGMA index_info("{idx_name}")')
            idx_cols = tuple(r[2] for r in sorted(cur.fetchall(), key=lambda r: r[0]))
            indexes[idx_name] = IndexSchema(name=idx_name, columns=idx_cols, unique=unique)

        return TableSchema(
            name=tname,
            columns=columns,
            primary_key=tuple(c for _, c in sorted(primary_key)),
            foreign_keys=foreign_keys,
            indexes=indexes,
        )
