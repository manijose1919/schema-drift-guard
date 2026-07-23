"""Connector interface and URL-based registry.

Every connector turns a live database into a dialect-agnostic
:class:`SchemaSnapshot`. The free tier ships SQLite/Postgres/MySQL; the paid
tier registers additional warehouse connectors (Snowflake, BigQuery, ...) by
implementing this same interface, so the diff engine never learns dialect
specifics.
"""

from __future__ import annotations

import abc
from typing import Callable
from urllib.parse import urlparse

from ..models import SchemaSnapshot


class Connector(abc.ABC):
    """Reflect a database's schema into a normalized snapshot."""

    dialect: str = "unknown"

    def __init__(self, url: str) -> None:
        self.url = url

    @abc.abstractmethod
    def snapshot(
        self,
        include_tables: list[str] | None = None,
        exclude_tables: list[str] | None = None,
    ) -> SchemaSnapshot:
        raise NotImplementedError


_REGISTRY: dict[str, Callable[[str], Connector]] = {}


def register(scheme: str) -> Callable[[type[Connector]], type[Connector]]:
    def deco(cls: type[Connector]) -> type[Connector]:
        _REGISTRY[scheme] = cls
        return cls

    return deco


def get_connector(url: str) -> Connector:
    """Resolve a connection URL to a concrete connector instance."""
    scheme = urlparse(url).scheme.split("+")[0].lower()
    if not scheme:
        raise ValueError(f"Could not determine dialect from URL: {url!r}")
    factory = _REGISTRY.get(scheme)
    if factory is None:
        available = ", ".join(sorted(_REGISTRY)) or "(none registered)"
        raise ValueError(
            f"No connector registered for '{scheme}'. Available: {available}. "
            f"Warehouse connectors (snowflake, bigquery, redshift) are part of DriftGuard Pro."
        )
    return factory(url)


def _should_include(
    name: str, include: list[str] | None, exclude: list[str] | None
) -> bool:
    if include and name not in include:
        return False
    if exclude and name in exclude:
        return False
    return True
