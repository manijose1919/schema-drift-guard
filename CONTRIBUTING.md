# Contributing to DriftGuard

Thanks for helping make schema drift a solved problem. This guide gets you productive in about five minutes.

## Ground rules

1. **The engine stays dependency-free.** DriftGuard must import nothing outside the Python standard library at runtime. Database drivers are optional extras, imported lazily inside the method that needs them. A PR adding a required runtime dependency will be asked to reconsider — a tool that runs on every pull request must not bloat anyone's lockfile.
2. **Every behavioural change needs a test.** The diff engine and the severity classifier *are* the product; untested changes to them will not be merged.
3. **Console output must be ASCII.** CI consoles (notably Windows `cp1252`) cannot encode fancy glyphs, and a data-quality gate must never crash while printing its own report. The Markdown and SARIF formats are the deliberate exceptions — they target GitHub, and the CLI writes them as UTF-8 bytes when the console can't encode them.

## Setup

```bash
git clone https://github.com/manijose1919/schema-drift-guard
cd schema-drift-guard
pip install -e ".[dev]"
pytest
```

## Adding a database connector (great first PR)

Connectors are self-contained and the highest-value contribution. Copy `src/driftguard/connectors/sqlite.py` as your template and:

1. Create `src/driftguard/connectors/<yourdb>.py`.
2. Subclass `Connector`, set `dialect`, and decorate with `@register("<url-scheme>")`.
3. Implement `snapshot()`, returning a `SchemaSnapshot`. **Import your driver lazily inside the method** and raise a helpful `RuntimeError` naming the pip extra if it is missing.
4. Write a `_type_family()` mapper so the classifier can reason about type compatibility. This is the part that matters most — it determines whether a type change is reported as a safe widening or a breaking narrowing.
5. Register it in `connectors/__init__.py` and add the extra to `pyproject.toml`.
6. Add tests. If your database can't run in CI, test the type-family mapper and any pure parsing logic directly.

## Understanding the codebase

Each module has exactly one job, which is what keeps it testable:

| Module | Responsibility |
| --- | --- |
| `models.py` | Dialect-agnostic schema representation. No logic. |
| `connectors/` | Live database → `SchemaSnapshot`. The only dialect-aware code. |
| `diff.py` | Pure structural comparison. Knows nothing about severity. |
| `classify.py` | Severity *policy* + rationale. Knows nothing about databases. |
| `ignores.py` | Waiver matching and expiry. |
| `snapshot.py` | Canonical serialization + fingerprinting. |
| `report.py` | Presentation only. |

If you find yourself adding dialect-specific logic to `diff.py`, or severity logic to a connector, the abstraction has sprung a leak — please open an issue instead.

## Changing severity classifications

Severity is a product decision, not merely a technical one: users gate deploys on it. If you believe a change is misclassified:

1. Open an issue describing the downstream breakage (or lack of it) with a concrete scenario.
2. Include the database and consumer type (view, dbt model, ORM, BI tool).

We would rather be slightly too conservative than let a breaking change through a green build.

## Pull request checklist

- [ ] `pytest` passes
- [ ] New behaviour has tests
- [ ] No new required runtime dependencies
- [ ] Console output remains ASCII
- [ ] Public functions have docstrings explaining *why*, not just *what*

## Code of Conduct

Be decent to each other. Harassment or disrespect of any kind is not welcome here.
