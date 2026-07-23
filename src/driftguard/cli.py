"""Command-line interface (argparse — stdlib only).

Commands
--------
init       Create a .driftguard.toml in the current directory.
snapshot   Capture the current schema and save it as the baseline.
check      Diff the live schema against the baseline and fail CI on drift.
diff       Diff two snapshot files directly (no live connection).
tables     List the tables DriftGuard can see (connection smoke test).

Exit codes (designed for CI gating)
-----------------------------------
0  success — no change at or above the configured ``fail_on`` severity.
1  drift detected at or above ``fail_on``.
2  usage / configuration / connection error.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .classify import classify, max_severity, sort_changes
from .config import CONFIG_FILENAME, TEMPLATE, Config
from .connectors import get_connector
from .diff import diff_snapshots
from .ignores import apply_ignores, expired_rules
from .report import FORMATS, render
from .rules import Severity
from .snapshot import load, save

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_ERROR = 2


def _baseline_path(cfg: Config) -> Path:
    return Path(cfg.snapshot_dir) / cfg.baseline_name()


def _capture(cfg: Config):
    url = cfg.resolved_database_url(dict(os.environ))
    connector = get_connector(url)
    return connector.snapshot(
        include_tables=cfg.include_tables or None,
        exclude_tables=cfg.exclude_tables or None,
    )


def _emit(text: str, output: str | None) -> None:
    """Write a report to stdout or a file (for CI artifact upload)."""
    if output:
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
        print(f"Wrote report to {path}")
        return

    try:
        print(text)
    except UnicodeEncodeError:
        # The markdown/SARIF formats legitimately contain non-ASCII (emoji are
        # meaningful in a GitHub PR comment), but legacy consoles such as
        # Windows cp1252 cannot encode them. Write UTF-8 bytes directly rather
        # than crashing or silently producing nothing.
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace") + b"\n")
        sys.stdout.buffer.flush()


def _warn_expired(cfg: Config) -> None:
    for rule in expired_rules(cfg.ignore_rules):
        print(
            f"warning: waiver expired on {rule.expires} "
            f"(table={rule.table}, type={rule.type}): {rule.reason}",
            file=sys.stderr,
        )


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(CONFIG_FILENAME)
    if path.exists() and not args.force:
        print(f"{CONFIG_FILENAME} already exists (use --force to overwrite).", file=sys.stderr)
        return EXIT_ERROR
    path.write_text(TEMPLATE, encoding="utf-8")
    print(f"Created {CONFIG_FILENAME}. Edit database_url, then run: driftguard snapshot")
    return EXIT_OK


def cmd_snapshot(args: argparse.Namespace) -> int:
    cfg = Config.load(args.config, args.env)
    snap = _capture(cfg)
    snap.driftguard_version = __version__
    out = _baseline_path(cfg)
    save(snap, out)
    print(f"Saved baseline snapshot ({len(snap.tables)} tables) to {out}")
    return EXIT_OK


def cmd_tables(args: argparse.Namespace) -> int:
    """Connection smoke test — verifies credentials and shows what is visible."""
    cfg = Config.load(args.config, args.env)
    snap = _capture(cfg)
    print(f"Connected to {snap.dialect} database '{snap.database}'")
    if not snap.tables:
        print("No tables visible. Check your credentials and include/exclude filters.")
        return EXIT_OK
    for name in sorted(snap.tables):
        table = snap.tables[name]
        print(f"  {name} ({len(table.columns)} columns)")
    print(f"\n{len(snap.tables)} table(s) tracked.")
    return EXIT_OK


def cmd_check(args: argparse.Namespace) -> int:
    cfg = Config.load(args.config, args.env)
    if args.fail_on:
        cfg.fail_on = Severity(args.fail_on)

    baseline_path = _baseline_path(cfg)
    if not baseline_path.exists():
        # Each environment keeps its own baseline, so a missing one usually
        # means the user has not snapshotted *this* environment yet.
        hint = f"driftguard snapshot --env {cfg.environment}" if cfg.environment else "driftguard snapshot"
        print(f"No baseline at {baseline_path}. Run '{hint}' first.", file=sys.stderr)
        return EXIT_ERROR

    _warn_expired(cfg)

    baseline = load(baseline_path)
    current = _capture(cfg)
    changes = classify(diff_snapshots(baseline, current))
    # Re-sort after waivers are applied so waived entries sink to the bottom.
    changes = sort_changes(apply_ignores(changes, cfg.ignore_rules))

    _emit(render(changes, args.format, fail_on=cfg.fail_on), args.output)

    # Gate on actionable changes only: if every finding is waived there is
    # nothing to fail on, even when fail_on is set to 'safe'.
    actionable = [c for c in changes if not c.ignored]
    top = max_severity(changes)  # already excludes waived changes
    if actionable and top.rank >= cfg.fail_on.rank:
        if args.format == "text" and not args.output:
            print(
                f"\nFAILED: drift reached severity '{top.value}' "
                f"(threshold '{cfg.fail_on.value}').",
                file=sys.stderr,
            )
        return EXIT_DRIFT
    return EXIT_OK


def cmd_diff(args: argparse.Namespace) -> int:
    baseline = load(args.baseline)
    current = load(args.current)
    changes = classify(diff_snapshots(baseline, current))
    _emit(render(changes, args.format), args.output)
    return EXIT_OK


def _add_format_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-f",
        "--format",
        choices=FORMATS,
        default="text",
        help="report format (junit/sarif/markdown integrate with CI dashboards)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="write the report to a file instead of stdout (for CI artifacts)",
    )
    # Deprecated alias kept so existing pipelines using --json keep working.
    parser.add_argument("--json", action="store_true", help=argparse.SUPPRESS)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="driftguard",
        description="Schema drift & data-contract testing for your CI pipeline.",
    )
    parser.add_argument("--version", action="version", version=f"driftguard {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_init = sub.add_parser("init", help="create a .driftguard.toml config")
    p_init.add_argument("--force", action="store_true", help="overwrite existing config")
    p_init.set_defaults(func=cmd_init)

    p_snap = sub.add_parser("snapshot", help="capture the current schema as baseline")
    p_snap.add_argument("-c", "--config", default=None, help="path to config file")
    p_snap.add_argument("-e", "--env", default=None, help="named environment to use")
    p_snap.set_defaults(func=cmd_snapshot)

    p_tables = sub.add_parser("tables", help="list visible tables (connection smoke test)")
    p_tables.add_argument("-c", "--config", default=None, help="path to config file")
    p_tables.add_argument("-e", "--env", default=None, help="named environment to use")
    p_tables.set_defaults(func=cmd_tables)

    p_check = sub.add_parser("check", help="diff live schema vs baseline; fail CI on drift")
    p_check.add_argument("-c", "--config", default=None, help="path to config file")
    p_check.add_argument("-e", "--env", default=None, help="named environment to use")
    p_check.add_argument(
        "--fail-on",
        choices=[s.value for s in Severity],
        default=None,
        help="override severity threshold that fails the check",
    )
    _add_format_args(p_check)
    p_check.set_defaults(func=cmd_check)

    p_diff = sub.add_parser("diff", help="diff two snapshot files directly")
    p_diff.add_argument("baseline", help="baseline snapshot JSON file")
    p_diff.add_argument("current", help="current snapshot JSON file")
    _add_format_args(p_diff)
    p_diff.set_defaults(func=cmd_diff)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    # Back-compat: --json is now --format json.
    if getattr(args, "json", False):
        args.format = "json"
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError, KeyError, RuntimeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR


if __name__ == "__main__":
    raise SystemExit(main())
