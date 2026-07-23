"""Serialize/deserialize snapshots and compute stable fingerprints.

Snapshots are stored as canonical JSON (sorted keys, stable ordering) so that:

1. Two identical schemas always produce byte-identical files -> clean git diffs.
2. A content fingerprint (SHA-256) can cheaply answer "did anything change?"
   without a full structural diff.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .models import SchemaSnapshot


def to_json(snapshot: SchemaSnapshot, *, indent: int | None = 2) -> str:
    """Serialize a snapshot to canonical JSON text."""
    return json.dumps(snapshot.to_dict(), indent=indent, sort_keys=True, ensure_ascii=False)


def from_json(text: str) -> SchemaSnapshot:
    return SchemaSnapshot.from_dict(json.loads(text))


def fingerprint(snapshot: SchemaSnapshot) -> str:
    """Content hash of the *structural* schema.

    Deliberately excludes volatile metadata (``captured_at``, version) so that
    re-capturing an unchanged schema yields the same fingerprint.
    """
    payload = snapshot.to_dict()
    payload.pop("captured_at", None)
    payload.pop("driftguard_version", None)
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def save(snapshot: SchemaSnapshot, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(to_json(snapshot) + "\n", encoding="utf-8")
    return p


def load(path: str | Path) -> SchemaSnapshot:
    return from_json(Path(path).read_text(encoding="utf-8"))
