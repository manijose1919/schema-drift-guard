from __future__ import annotations

from conftest import col, snapshot, table

from driftguard.snapshot import fingerprint, from_json, to_json


def _sample():
    return snapshot(
        table("users", [col("id", pk=True), col("email", "TEXT", "string", ordinal=1)], primary_key=("id",)),
        table("orders", [col("id", pk=True), col("total", "REAL", "float", ordinal=1)]),
    )


def test_roundtrip_preserves_structure():
    snap = _sample()
    restored = from_json(to_json(snap))
    assert set(restored.tables) == {"users", "orders"}
    assert restored.tables["users"].columns["email"].type_family == "string"
    assert restored.tables["users"].primary_key == ("id",)


def test_serialization_is_deterministic():
    # Same schema, independently constructed -> identical JSON bytes.
    assert to_json(_sample()) == to_json(_sample())


def test_fingerprint_stable_across_metadata():
    a = _sample()
    b = _sample()
    a.captured_at = "2020-01-01T00:00:00Z"
    b.captured_at = "2099-12-31T23:59:59Z"
    a.driftguard_version = "0.1.0"
    b.driftguard_version = "9.9.9"
    assert fingerprint(a) == fingerprint(b)


def test_fingerprint_changes_on_structural_change():
    a = _sample()
    b = snapshot(table("users", [col("id", pk=True)]))
    assert fingerprint(a) != fingerprint(b)
