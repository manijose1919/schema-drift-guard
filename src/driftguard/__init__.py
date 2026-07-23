"""DriftGuard — schema drift & data-contract testing for your CI pipeline.

Public API::

    from driftguard import get_connector, diff_snapshots, classify

    current = get_connector("sqlite:///app.db").snapshot()
    changes = classify(diff_snapshots(baseline, current))
"""

from __future__ import annotations

__version__ = "0.1.0"

from .classify import classify, classify_change, max_severity
from .connectors import get_connector
from .diff import Change, diff_snapshots
from .ignores import IgnoreRule, apply_ignores
from .report import render, summarize
from .models import (
    ColumnSchema,
    ForeignKeySchema,
    IndexSchema,
    SchemaSnapshot,
    TableSchema,
)
from .rules import ChangeType, Severity
from .snapshot import fingerprint, from_json, load, save, to_json

__all__ = [
    "__version__",
    "Change",
    "ChangeType",
    "ColumnSchema",
    "ForeignKeySchema",
    "IgnoreRule",
    "IndexSchema",
    "SchemaSnapshot",
    "Severity",
    "TableSchema",
    "apply_ignores",
    "classify",
    "classify_change",
    "diff_snapshots",
    "fingerprint",
    "render",
    "summarize",
    "from_json",
    "get_connector",
    "load",
    "max_severity",
    "save",
    "to_json",
]
