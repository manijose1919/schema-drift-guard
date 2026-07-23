"""Connector registry.

Importing this package registers the built-in (free-tier) connectors as a side
effect. Warehouse connectors (Snowflake, BigQuery, Redshift, Databricks) are
provided by DriftGuard Pro and register themselves the same way.
"""

from __future__ import annotations

from .base import Connector, get_connector, register

# Registration side effects — order does not matter.
from . import sqlite  # noqa: E402,F401
from . import postgres  # noqa: E402,F401
from . import mysql  # noqa: E402,F401

__all__ = ["Connector", "get_connector", "register"]
