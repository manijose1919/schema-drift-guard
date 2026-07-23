<div align="center">

# DriftGuard — Schema Drift Detection & Data Contract Testing for CI/CD

**Catch breaking database schema changes in your pull requests — before they break your dashboards, pipelines, and ML models.**

[![CI](https://github.com/manijose1919/schema-drift-guard/actions/workflows/ci.yml/badge.svg)](https://github.com/manijose1919/schema-drift-guard/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.11%20|%203.12%20|%203.13-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Runtime dependencies](https://img.shields.io/badge/runtime%20deps-0-success)](#why-zero-dependencies)
[![Tests](https://img.shields.io/badge/tests-58%20passing-brightgreen)](#testing)

[Quick Start](#quick-start) · [How It Works](#how-it-works) · [CI Integration](#ci-integration) · [Waivers](#waivers-accepting-a-known-change) · [Contributing](CONTRIBUTING.md)

</div>

---

## The Problem: Silent Data Downtime

In every company with a data warehouse, **application engineers own the schema** while **data teams own the dashboards, reports, and ML features built on top of it**. Nobody owns the seam between them.

So when a backend engineer renames a column, drops a field, or tightens a constraint:

- 📉 A revenue dashboard silently shows wrong numbers
- 💥 A nightly pipeline crashes at 3 a.m.
- 🤖 An ML feature quietly corrupts and degrades a model
- 📊 A number in a board deck turns out to be wrong

Nobody finds out until **after** the damage is done. This is *data downtime*, and it is expensive.

**DriftGuard closes that gap.** It captures a versioned fingerprint of your database schema, diffs it on every pull request, classifies each change by how badly it will break downstream consumers, and **fails your CI build before the change ever merges.**

---

## Quick Start

```bash
pip install driftguard
```

```bash
driftguard init        # create .driftguard.toml
driftguard snapshot    # capture today's schema as your baseline (commit this!)
driftguard check       # in CI: exit 1 if the schema drifted in a breaking way
```

No account, no agent, no telemetry, no signup.

### Example output

```text
DriftGuard - schema drift report
========================================
[X] [BREAKING] users.email: column 'email' removed
    -> Dropping a column breaks any SELECT, view, or model that references it.
[!] [WARNING] orders.total: type NUMERIC -> INTEGER
    -> Incompatible type change (type narrowed; existing values may not fit).
[+] [SAFE] users.nickname: column 'nickname' added
    -> New nullable/defaulted column is backward compatible.
----------------------------------------
1 breaking, 1 warning, 1 safe

FAILED: drift reached severity 'breaking' (threshold 'breaking').
```

---

## How It Works

```
   Your database                DriftGuard engine              Your CI
  ┌──────────────┐            ┌──────────────────┐         ┌───────────┐
  │  Postgres /  │  reflect   │  Snapshot (JSON) │  diff   │  exit 0   │
  │  MySQL /     │ ─────────► │        +         │ ──────► │    or     │
  │  SQLite      │            │  Classifier      │         │  exit 1   │
  └──────────────┘            └──────────────────┘         └───────────┘
                                       │
                              committed to your repo
                              (reviewable in the PR diff)
```

1. **Snapshot** — reflects your live schema into a normalized, dialect-agnostic JSON document stored in your repo. Serialization is canonical, so identical schemas produce byte-identical files that diff cleanly in code review.
2. **Diff** — structurally compares live schema against the baseline: tables, columns, types, nullability, defaults, primary keys, foreign keys, indexes. It even *infers* column renames — conservatively, leaving ambiguous cases as add/remove rather than guessing wrong.
3. **Classify** — every change gets a severity and a plain-English rationale explaining the downstream blast radius.
4. **Gate** — `driftguard check` exits non-zero when drift crosses your threshold, failing the build.

### Severity model

| Severity | Meaning | Examples |
| --- | --- | --- |
| 🔴 **BREAKING** | Will break existing readers/writers | Dropped column or table, incompatible/narrowing type change, `NULL → NOT NULL`, primary key change, renamed column |
| 🟡 **WARNING** | May break some consumers | Default value changed, index or foreign key removed, new `NOT NULL` column with no default, safe type widening |
| 🟢 **SAFE** | Purely additive, backward compatible | New nullable column, new table, added index or foreign key |

---

## CI Integration

### GitHub Actions

```yaml
permissions:
  pull-requests: write   # required for the automatic PR comment

steps:
  - uses: actions/checkout@v4
  # apply your pending migrations against a service DB here, then:
  - name: DriftGuard schema check
    uses: manijose1919/schema-drift-guard@v0
    with:
      fail-on: breaking
      comment-on-pr: true    # posts the report as a PR comment
      upload-sarif: true     # feeds GitHub Code Scanning annotations
    env:
      DATABASE_URL: ${{ secrets.DATABASE_URL }}
```

### Any other CI system

Drift shows up in the dashboards your team already watches — no new tooling to adopt.

```bash
driftguard check --format junit    -o reports/drift.xml   # Jenkins, GitLab, Azure DevOps, CircleCI
driftguard check --format sarif    -o drift.sarif         # GitHub Code Scanning
driftguard check --format markdown -o comment.md          # PR comment body
driftguard check --format json     -o drift.json          # scripting / custom dashboards
```

**JUnit XML** is the one that matters most for enterprise adoption: Jenkins, GitLab CI, Azure DevOps, CircleCI and Bitbucket all ingest it natively, so schema drift appears as a failing test in the report your team already reads.

---

## Waivers: Accepting a Known Change

Sometimes a breaking change is intentional and approved. Without an escape hatch, teams disable the check entirely — the worst possible outcome. Waivers solve that safely:

```toml
[[driftguard.ignore]]
table = "legacy_*"                                          # glob supported
type = "table_removed"                                      # optional
reason = "Sunsetting legacy tables, approved in DATA-1234"   # REQUIRED
expires = "2026-12-31"                                       # optional
```

Three rules keep this honest:

1. **Nothing is hidden.** A waived change still appears in every report, marked as waived with its reason — auditors see exactly what was accepted and why.
2. **A reason is mandatory.** A waiver without justification is indistinguishable from a bug, so it's rejected at load time.
3. **Waivers expire.** Past `expires`, the waiver stops applying and is reported on stderr, forcing periodic re-review. A malformed date is treated as expired rather than granting an unlimited pass.

---

## Multiple Environments

```toml
[driftguard.env.staging]
database_url = "postgresql://app:${STAGING_DB_PASSWORD}@staging-db:5432/app"

[driftguard.env.prod]
database_url = "postgresql://app:${PROD_DB_PASSWORD}@prod-db:5432/app"
fail_on = "warning"
```

```bash
driftguard snapshot --env prod    # each environment keeps its own baseline file
driftguard check --env prod
```

---

## Why Zero Dependencies?

The DriftGuard engine has **zero required runtime dependencies** — pure Python standard library.

This is deliberate. A tool that runs inside *your* CI on *every* pull request should not add transitive packages to your lockfile, expand your supply-chain attack surface, or add seconds to every pipeline run. `pip install driftguard` completes in about a second and pulls in nothing.

Database drivers are optional extras, imported lazily — you install only what you actually connect to:

```bash
pip install driftguard                 # SQLite (stdlib), engine, CLI
pip install 'driftguard[postgres]'     # + PostgreSQL
pip install 'driftguard[mysql]'        # + MySQL / MariaDB
```

---

## CLI Reference

| Command | Purpose |
| --- | --- |
| `driftguard init` | Create a `.driftguard.toml` config file. |
| `driftguard snapshot` | Capture the live schema and store it as the baseline. |
| `driftguard check` | Diff live schema vs baseline; **exit 1** on drift at/above threshold. |
| `driftguard diff a.json b.json` | Diff two snapshot files directly (no DB connection needed). |
| `driftguard tables` | List visible tables — a fast connection/credentials smoke test. |

Common flags: `--format {text,json,junit,markdown,sarif}` · `--output FILE` · `--env NAME` · `--fail-on {safe,warning,breaking}`

### Exit codes

| Code | Meaning |
| --- | --- |
| `0` | No change at or above the configured `fail_on` severity. |
| `1` | Drift detected at or above `fail_on`. |
| `2` | Usage, configuration, or connection error. |

### Configuration

```toml
[driftguard]
# ${ENV_VAR} interpolation keeps credentials out of version control.
database_url = "postgresql://app:${DB_PASSWORD}@db.internal:5432/production"
snapshot_dir = ".driftguard/snapshots"

# Severity that fails CI: safe | warning | breaking
fail_on = "breaking"

include_tables = []
exclude_tables = ["django_migrations", "celery_taskmeta"]
```

### Use it as a library

```python
from driftguard import get_connector, diff_snapshots, classify, load

baseline = load(".driftguard/snapshots/baseline.json")
current = get_connector("postgresql://...").snapshot()

for change in classify(diff_snapshots(baseline, current)):
    print(change.severity.value, change.table, change.detail, "->", change.rationale)
```

---

## Architecture

Each module has one job, which is what makes the engine straightforward to extend and test:

| Module | Responsibility |
| --- | --- |
| `models.py` | Dialect-agnostic schema representation. No logic. |
| `connectors/` | Live database → `SchemaSnapshot`. The only dialect-aware code. |
| `diff.py` | Pure structural comparison. Knows nothing about severity. |
| `classify.py` | Severity *policy* + rationale. Knows nothing about databases. |
| `ignores.py` | Waiver matching and expiry. |
| `snapshot.py` | Canonical serialization + SHA-256 fingerprinting. |
| `report.py` | Presentation only (text/JSON/JUnit/Markdown/SARIF). |

---

## Testing

```bash
pip install -e ".[dev]"
pytest
```

**58 tests** covering the diff engine, severity classifier, waiver rules, snapshot fingerprinting, SQLite reflection, every report format, and the CLI end-to-end (including real CI exit codes against a live SQLite database).

---

## Roadmap

- [ ] Statistical/data-profile drift (row counts, null ratios, distributions)
- [ ] dbt manifest integration (map schema changes to affected models)
- [ ] Alembic / Django / Prisma migration-file awareness
- [ ] Additional warehouse connectors (Snowflake, BigQuery, Redshift)

---

## Contributing

Contributions are very welcome — especially **new database connectors**, which are self-contained and make an excellent first PR. See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE).

---

<div align="center">

**Keywords:** schema drift detection · data contract testing · database schema monitoring · data observability · breaking change detection · CI/CD database testing · data quality · PostgreSQL schema diff · JUnit schema report · data downtime prevention

</div>
