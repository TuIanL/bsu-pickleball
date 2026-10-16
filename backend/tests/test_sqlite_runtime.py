from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from app import database, sqlite_runtime
from app.core.config import Settings
from app.services.analysis_control_plane import AnalysisControlPlane


@pytest.mark.parametrize(("is_local", "expected_mode"), [(True, "wal"), (False, "delete")])
def test_shared_sqlite_policy_sets_mode_timeout_and_synchronous(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    is_local: bool,
    expected_mode: str,
) -> None:
    monkeypatch.setattr(sqlite_runtime, "is_confirmed_local_filesystem", lambda _path: is_local)
    path = tmp_path / "store.sqlite3"
    connection = sqlite3.connect(path)
    try:
        sqlite_runtime.apply_sqlite_pragmas(connection, path)
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == expected_mode
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    finally:
        connection.close()


@pytest.mark.parametrize(("journal_mode", "expected_mode"), [("WAL", "wal"), ("DELETE", "delete")])
def test_sqlalchemy_engine_configures_every_new_connection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    journal_mode: str,
    expected_mode: str,
) -> None:
    settings = Settings(
        data_dir=tmp_path / "data",
        database_path=tmp_path / "data" / "app.sqlite3",
        outputs_dir=tmp_path / "outputs",
        uploads_dir=tmp_path / "uploads",
        calibrations_dir=tmp_path / "calibrations",
        tmp_dir=tmp_path / "tmp",
    )
    monkeypatch.setattr(database, "get_settings", lambda: settings)
    monkeypatch.setattr(database, "sqlite_journal_mode", lambda *_paths: journal_mode)
    database.reset_database_state()
    try:
        engine = database.get_engine()
        for _ in range(2):
            with engine.connect() as connection:
                assert connection.exec_driver_sql("PRAGMA journal_mode").scalar_one() == expected_mode
                assert connection.exec_driver_sql("PRAGMA busy_timeout").scalar_one() == 30000
                assert connection.exec_driver_sql("PRAGMA synchronous").scalar_one() == 1
    finally:
        database.reset_database_state()


@pytest.mark.parametrize("is_local", [True, False])
def test_control_plane_uses_same_path_aware_sqlite_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    is_local: bool,
) -> None:
    monkeypatch.setattr(sqlite_runtime, "is_confirmed_local_filesystem", lambda _path: is_local)
    path = tmp_path / "analysis_control.sqlite3"
    control_plane = AnalysisControlPlane(path)
    with control_plane._connect() as connection:
        expected_mode = "wal" if is_local else "delete"
        assert connection.execute("PRAGMA journal_mode").fetchone()[0] == expected_mode
        assert connection.execute("PRAGMA busy_timeout").fetchone()[0] == 30000
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_related_databases_share_rollback_mode_if_either_path_is_external(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    local_path = tmp_path / "app.sqlite3"
    external_path = tmp_path / "external" / "analysis_control.sqlite3"
    external_path.parent.mkdir()
    monkeypatch.setattr(
        sqlite_runtime,
        "is_confirmed_local_filesystem",
        lambda path: path != external_path,
    )

    assert sqlite_runtime.sqlite_journal_mode(local_path, external_path) == "DELETE"
    assert sqlite_runtime.sqlite_journal_mode(external_path, local_path) == "DELETE"
