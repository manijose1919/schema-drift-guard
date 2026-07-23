"""Project configuration loaded from ``.driftguard.toml``.

TOML is parsed with the stdlib :mod:`tomllib` (Python 3.11+), keeping the free
tier dependency-free. Writing the initial config in ``init`` is done by emitting
a small hand-authored TOML template rather than pulling in a TOML *writer*.

Supports named environments so one repo can guard dev/staging/prod with the same
config file — a hard requirement once more than one team uses the tool.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .ignores import IgnoreRule
from .rules import Severity

CONFIG_FILENAME = ".driftguard.toml"
DEFAULT_SNAPSHOT_DIR = ".driftguard/snapshots"


@dataclass(slots=True)
class Config:
    # Connection URL, e.g. sqlite:///app.db or postgresql://user:pass@host/db.
    # Supports ${ENV_VAR} interpolation so secrets stay out of the repo.
    database_url: str = ""
    snapshot_dir: str = DEFAULT_SNAPSHOT_DIR
    # Fail the CI check when any change reaches this severity or higher.
    fail_on: Severity = Severity.BREAKING
    # Optional table allow/deny lists.
    include_tables: list[str] = field(default_factory=list)
    exclude_tables: list[str] = field(default_factory=list)
    # Explicitly accepted changes.
    ignore_rules: list[IgnoreRule] = field(default_factory=list)
    # Name of the active environment, if one was selected.
    environment: str | None = None

    @classmethod
    def load(cls, path: str | Path | None = None, environment: str | None = None) -> "Config":
        """Load config, optionally overlaying a named ``[driftguard.env.<name>]`` block."""
        p = Path(path) if path else Path(CONFIG_FILENAME)
        if not p.exists():
            raise FileNotFoundError(
                f"No {CONFIG_FILENAME} found. Run 'driftguard init' to create one."
            )
        # utf-8-sig tolerates a UTF-8 BOM, which Windows editors commonly add
        # and which tomllib would otherwise reject.
        data = tomllib.loads(p.read_text(encoding="utf-8-sig"))
        dg = data.get("driftguard", {})

        if environment:
            envs = dg.get("env", {})
            if environment not in envs:
                available = ", ".join(sorted(envs)) or "(none defined)"
                raise ValueError(
                    f"Environment '{environment}' is not defined in {p}. Available: {available}"
                )
            # Environment values override the top-level defaults.
            dg = {**dg, **envs[environment]}

        rules = [IgnoreRule.from_dict(r) for r in dg.get("ignore", [])]

        return cls(
            database_url=str(dg.get("database_url", "")),
            snapshot_dir=str(dg.get("snapshot_dir", DEFAULT_SNAPSHOT_DIR)),
            fail_on=Severity(str(dg.get("fail_on", "breaking"))),
            include_tables=list(dg.get("include_tables", [])),
            exclude_tables=list(dg.get("exclude_tables", [])),
            ignore_rules=rules,
            environment=environment,
        )

    def resolved_database_url(self, env: dict[str, str]) -> str:
        """Expand ${VAR} placeholders from the given environment mapping."""
        return _expand_env(self.database_url, env)

    def baseline_name(self) -> str:
        """Per-environment baseline filename so environments never collide."""
        return "baseline.json" if not self.environment else f"baseline.{self.environment}.json"


def _expand_env(value: str, env: dict[str, str]) -> str:
    import re

    def repl(match: "re.Match[str]") -> str:
        var = match.group(1)
        if var not in env:
            raise KeyError(f"Environment variable '{var}' referenced in database_url is not set.")
        return env[var]

    return re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", repl, value)


TEMPLATE = """\
# DriftGuard configuration
# Docs: https://github.com/manijose1919/schema-drift-guard

[driftguard]
# Use ${ENV_VAR} to keep credentials out of version control.
database_url = "sqlite:///app.db"
snapshot_dir = ".driftguard/snapshots"

# CI fails when a change reaches this severity or higher: safe | warning | breaking
fail_on = "breaking"

# Optionally restrict which tables are tracked.
include_tables = []
exclude_tables = []

# --- Waivers -----------------------------------------------------------------
# Explicitly accept a known change so it stops failing the build. Waived changes
# are still shown in every report, so nothing is hidden from reviewers.
#
# [[driftguard.ignore]]
# table = "legacy_*"              # glob supported
# type = "table_removed"          # optional: only this kind of change
# reason = "Sunsetting legacy tables, approved in DATA-1234"   # required
# expires = "2026-12-31"          # optional: forces periodic re-review

# --- Environments ------------------------------------------------------------
# Override any setting per environment, then use: driftguard check --env prod
#
# [driftguard.env.staging]
# database_url = "postgresql://app:${STAGING_DB_PASSWORD}@staging-db:5432/app"
#
# [driftguard.env.prod]
# database_url = "postgresql://app:${PROD_DB_PASSWORD}@prod-db:5432/app"
# fail_on = "warning"
"""
