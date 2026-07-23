"""MySQL / MariaDB connector.

Uses the pure-Python ``PyMySQL`` driver, imported lazily so it is only required
when a MySQL URL is actually used.
"""

from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlparse

from ..models import ColumnSchema, SchemaSnapshot, TableSchema
from .base import Connector, _should_include, register


def _type_family(data_type: str) -> str:
    t = (data_type or "").lower()
    if "int" in t:
        return "integer"
    if any(k in t for k in ("real", "double", "float", "decimal", "numeric")):
        return "float"
    if any(k in t for k in ("char", "text", "blob")):
        return "string"
    if any(k in t for k in ("date", "time", "year")):
        return "datetime"
    if "json" in t:
        return "json"
    return "unknown"


@register("mysql")
@register("mariadb")
class MySQLConnector(Connector):
    dialect = "mysql"

    def snapshot(
        self,
        include_tables: list[str] | None = None,
        exclude_tables: list[str] | None = None,
    ) -> SchemaSnapshot:
        try:
            import pymysql  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "MySQL support requires the 'PyMySQL' driver. "
                "Install it with: pip install 'driftguard[mysql]'"
            ) from exc

        parsed = urlparse(self.url)
        db_name = parsed.path.lstrip("/")
        conn = pymysql.connect(
            host=parsed.hostname or "localhost",
            port=parsed.port or 3306,
            user=parsed.username or "root",
            password=parsed.password or "",
            database=db_name,
        )
        try:
            return self._reflect(conn, db_name, include_tables, exclude_tables)
        finally:
            conn.close()

    def _reflect(self, conn, db_name, include_tables, exclude_tables) -> SchemaSnapshot:  # noqa: ANN001
        cur = conn.cursor()
        cur.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name",
            (db_name,),
        )
        table_names = [r[0] for r in cur.fetchall()]

        tables: dict[str, TableSchema] = {}
        for tname in table_names:
            if not _should_include(tname, include_tables, exclude_tables):
                continue
            cur.execute(
                "SELECT column_name, column_type, is_nullable, column_default, "
                "ordinal_position, column_key FROM information_schema.columns "
                "WHERE table_schema=%s AND table_name=%s ORDER BY ordinal_position",
                (db_name, tname),
            )
            columns: dict[str, ColumnSchema] = {}
            primary_key: list[str] = []
            for name, col_type, is_nullable, default, ordinal, col_key in cur.fetchall():
                is_pk = col_key == "PRI"
                columns[name] = ColumnSchema(
                    name=name,
                    data_type=str(col_type).upper(),
                    type_family=_type_family(col_type),
                    nullable=(is_nullable == "YES"),
                    default=None if default is None else str(default),
                    is_primary_key=is_pk,
                    ordinal=int(ordinal),
                )
                if is_pk:
                    primary_key.append(name)
            tables[tname] = TableSchema(
                name=tname, columns=columns, primary_key=tuple(primary_key)
            )

        return SchemaSnapshot(
            dialect=self.dialect,
            database=db_name,
            tables=tables,
            captured_at=datetime.now(timezone.utc).isoformat(),
        )
