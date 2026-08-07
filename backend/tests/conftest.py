"""Shared pytest isolation for backend tests.

The application reads its settings while test modules are collected, so the
session-level environment is installed before collection rather than in an
autouse fixture.  Tests that need a different database can still override it
with their existing ``monkeypatch`` fixtures.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from app.core.config import Settings

_ISOLATION_ENV_KEYS = (
    "PICKLEBALL_DATA_DIR",
    "PICKLEBALL_DATABASE_PATH",
    "PICKLEBALL_UPLOADS_DIR",
    "PICKLEBALL_OUTPUTS_DIR",
    "PICKLEBALL_CALIBRATIONS_DIR",
    "PICKLEBALL_RECORDINGS_DIR",
    "PICKLEBALL_CAMERAS_DIR",
    "PICKLEBALL_TMP_DIR",
    "PICKLEBALL_MODEL_DIR",
)


def pytest_configure(config: pytest.Config) -> None:
    root = Path(tempfile.mkdtemp(prefix="pre-pickleball-pytest-"))
    config._pre_pickleball_test_root = root  # type: ignore[attr-defined]
    config._pre_pickleball_original_env = {  # type: ignore[attr-defined]
        key: os.environ.get(key) for key in _ISOLATION_ENV_KEYS
    }
    paths = {
        "PICKLEBALL_DATA_DIR": root / "data",
        "PICKLEBALL_DATABASE_PATH": root / "data" / "app.sqlite3",
        "PICKLEBALL_UPLOADS_DIR": root / "data" / "uploads",
        "PICKLEBALL_OUTPUTS_DIR": root / "data" / "outputs",
        "PICKLEBALL_CALIBRATIONS_DIR": root / "data" / "calibrations",
        "PICKLEBALL_RECORDINGS_DIR": root / "data" / "recordings",
        "PICKLEBALL_CAMERAS_DIR": root / "data" / "cameras",
        "PICKLEBALL_TMP_DIR": root / "data" / "tmp",
        "PICKLEBALL_MODEL_DIR": root / "models",
    }
    for key, value in paths.items():
        os.environ[key] = str(value)


def pytest_unconfigure(config: pytest.Config) -> None:
    original_env = getattr(config, "_pre_pickleball_original_env", {})
    for key in _ISOLATION_ENV_KEYS:
        value = original_env.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    root = getattr(config, "_pre_pickleball_test_root", None)
    if root:
        shutil.rmtree(root, ignore_errors=True)


@pytest.fixture
def isolated_settings(tmp_path: Path) -> Settings:
    """Return a complete Settings object rooted under the test temp dir."""

    data_dir = tmp_path / "data"
    return Settings(
        data_dir=data_dir,
        database_path=data_dir / "app.sqlite3",
        uploads_dir=data_dir / "uploads",
        outputs_dir=data_dir / "outputs",
        calibrations_dir=data_dir / "calibrations",
        recordings_dir=data_dir / "recordings",
        cameras_dir=data_dir / "cameras",
        tmp_dir=data_dir / "tmp",
        model_dir=tmp_path / "models",
    )


@pytest.fixture
def empty_session_factory():
    """Return a fake factory whose active CaptureTake query is explicitly empty."""

    from unittest.mock import MagicMock

    db = MagicMock(name="test_db")
    query = db.query.return_value
    query.filter.return_value.filter.return_value.order_by.return_value.first.return_value = None
    factory = MagicMock(name="test_session_factory", return_value=db)
    return factory, db


@pytest.fixture
def isolated_database(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Provide a real temporary SQLite factory for lifecycle/recovery tests."""

    from app.core import config
    from app.database import Base, get_engine, get_session_factory, init_db, reset_database_state

    database_path = tmp_path / "db" / "test.sqlite3"
    monkeypatch.setenv("PICKLEBALL_DATABASE_PATH", str(database_path))
    monkeypatch.setenv("PICKLEBALL_DATA_DIR", str(tmp_path / "data"))
    config.get_settings.cache_clear()
    reset_database_state()
    init_db()
    factory = get_session_factory()
    try:
        yield factory
    finally:
        Base.metadata.drop_all(bind=get_engine())
        reset_database_state()
        config.get_settings.cache_clear()
