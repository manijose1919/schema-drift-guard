from __future__ import annotations

import sqlite3

from driftguard.connectors import get_connector
from driftguard.connectors.sqlite import SQLiteConnector


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            email TEXT NOT NULL,
            age INTEGER
        );
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER NOT NULL,
            total REAL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        );
        CREATE INDEX idx_orders_user ON orders(user_id);
        """
    )
    conn.commit()
    conn.close()


def test_registry_resolves_sqlite():
    assert isinstance(get_connector("sqlite:///x.db"), SQLiteConnector)


def test_unknown_scheme_mentions_pro():
    try:
        get_connector("snowflake://acct/db")
    except ValueError as exc:
        assert "Pro" in str(exc)
    else:
        raise AssertionError("expected ValueError for unregistered scheme")


def test_reflects_tables_columns_and_constraints(tmp_path):
    db = tmp_path / "app.db"
    _make_db(str(db))
    snap = SQLiteConnector(f"sqlite:///{db}").snapshot()

    assert set(snap.tables) == {"users", "orders"}

    users = snap.tables["users"]
    assert users.primary_key == ("id",)
    assert users.columns["email"].nullable is False
    assert users.columns["age"].nullable is True
    assert users.columns["email"].type_family == "string"

    orders = snap.tables["orders"]
    assert any(fk.referred_table == "users" for fk in orders.foreign_keys.values())
    assert any("user_id" in ix.columns for ix in orders.indexes.values())


def test_include_exclude_filters(tmp_path):
    db = tmp_path / "app.db"
    _make_db(str(db))
    conn = SQLiteConnector(f"sqlite:///{db}")
    only_users = conn.snapshot(include_tables=["users"])
    assert set(only_users.tables) == {"users"}
    no_orders = conn.snapshot(exclude_tables=["orders"])
    assert "orders" not in no_orders.tables
