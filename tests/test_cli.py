from __future__ import annotations

import sqlite3

from driftguard.cli import main


def _write_config(dirpath, db_path):
    (dirpath / ".driftguard.toml").write_text(
        f'[driftguard]\ndatabase_url = "sqlite:///{db_path.as_posix()}"\n'
        'snapshot_dir = ".driftguard/snapshots"\nfail_on = "breaking"\n',
        encoding="utf-8",
    )


def _create(db_path):
    conn = sqlite3.connect(db_path)
    conn.executescript("CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT NOT NULL);")
    conn.commit()
    conn.close()


def test_init_creates_config(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    assert (tmp_path / ".driftguard.toml").exists()
    # second init without --force fails
    assert main(["init"]) == 2


def test_full_snapshot_then_clean_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "app.db"
    _create(db)
    _write_config(tmp_path, db)

    assert main(["snapshot"]) == 0
    # No change -> check passes (exit 0)
    assert main(["check"]) == 0


def test_breaking_change_fails_check(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "app.db"
    _create(db)
    _write_config(tmp_path, db)
    assert main(["snapshot"]) == 0

    # Drop the email column -> breaking
    conn = sqlite3.connect(db)
    conn.executescript("ALTER TABLE users DROP COLUMN email;")
    conn.commit()
    conn.close()

    assert main(["check"]) == 1  # EXIT_DRIFT


def test_warning_below_threshold_passes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "app.db"
    _create(db)
    _write_config(tmp_path, db)
    assert main(["snapshot"]) == 0

    # Add a nullable column -> safe; add index change etc. stays under breaking
    conn = sqlite3.connect(db)
    conn.executescript("ALTER TABLE users ADD COLUMN nickname TEXT;")
    conn.commit()
    conn.close()

    assert main(["check"]) == 0


def test_check_without_baseline_errors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db = tmp_path / "app.db"
    _create(db)
    _write_config(tmp_path, db)
    assert main(["check"]) == 2  # EXIT_ERROR: no baseline
