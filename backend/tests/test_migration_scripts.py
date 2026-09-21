from __future__ import annotations

import json

from backend.scripts.migrate_camera_configs import migrate as migrate_cameras
from backend.scripts.migrate_candidate_reviews import migrate as migrate_candidate_reviews


def test_camera_migration_is_dry_run_by_default_and_idempotent(tmp_path):
    source = tmp_path / "legacy"
    target = tmp_path / "configured"
    source.mkdir()
    (source / "安全中文机位.json").write_text(
        json.dumps({"camera_id": "安全中文机位", "name": "A", "stream_url": "rtsp://host", "protocol": "rtsp"}),
        encoding="utf-8",
    )
    (source / "bad.json").write_text(
        json.dumps({"camera_id": "../escape", "name": "B", "stream_url": "rtsp://host", "protocol": "rtsp"}),
        encoding="utf-8",
    )
    dry = migrate_cameras(source, target, apply=False)
    assert not target.exists()
    assert dry["summary"]["copied"] == 1
    assert dry["summary"]["invalid"] == 1
    migrate_cameras(source, target, apply=True)
    assert (target / "安全中文机位.json").is_file()
    repeated = migrate_cameras(source, target, apply=True)
    assert repeated["summary"]["already_present"] == 1
    assert (source / "安全中文机位.json").is_file()


def test_candidate_migration_keeps_unverifiable_legacy_records_unbound(tmp_path):
    root = tmp_path / "candidates"
    root.mkdir()
    take_id = "legacy-take"
    artifact = {
        "schema_version": "match_state_candidate_timeline.v1",
        "capture_take_id": take_id,
        "candidate_segments": [{"candidate_id": "candidate_0001", "start_ms": 0, "end_ms": 1000}],
    }
    (root / f"{take_id}.timeline.json").write_text(json.dumps(artifact), encoding="utf-8")
    (root / f"{take_id}.reviews.json").write_text(
        json.dumps(
            {
                "schema_version": "match-state-candidate-review.v1",
                "capture_take_id": take_id,
                "history": [{"candidate_id": "candidate_0001", "decision": "accepted", "revision": 1}],
            }
        ),
        encoding="utf-8",
    )
    report = migrate_candidate_reviews(root, apply=False)
    assert report["summary"]["legacy_unbound"] == 1
    assert report["summary"]["imported"] == 0
    assert (root / f"{take_id}.reviews.json").is_file()


def test_schema_backup_upgrade_repeat_and_restore(tmp_path):
    import sqlite3
    from pathlib import Path
    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    database = tmp_path / 'legacy.sqlite3'
    backup = tmp_path / 'legacy.backup.sqlite3'
    cfg = Config(str(backend / 'alembic.ini'))
    cfg.set_main_option('script_location', str(backend / 'alembic_migrations'))
    cfg.set_main_option('sqlalchemy.url', f'sqlite:///{database}')
    # Historical releases bootstrapped pre-Alembic tables via metadata.create_all.
    # Reproduce that old schema, without any candidate tables, then upgrade it.
    from app.database import Base
    import importlib
    for model in (backend / 'app/models').glob('*.py'):
        if model.stem != '__init__':
            importlib.import_module('app.models.' + model.stem)
    from sqlalchemy import create_engine
    engine = create_engine(f'sqlite:///{database}')
    Base.metadata.create_all(engine, tables=[table for table in Base.metadata.sorted_tables
        if not table.name.startswith('match_state_candidate_')])
    engine.dispose()
    command.stamp(cfg, '2c3d4e5f6a7b')
    with sqlite3.connect(database) as source, sqlite3.connect(backup) as target:
        source.execute('CREATE TABLE migration_sentinel (value TEXT)')
        source.execute("INSERT INTO migration_sentinel VALUES ('retain original data')")
        source.commit()
        source.backup(target)
    command.upgrade(cfg, 'head')
    command.upgrade(cfg, 'head')
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '5f6a7b8c9d0e'
        assert db.execute('SELECT value FROM migration_sentinel').fetchone()[0] == 'retain original data'
    command.downgrade(cfg, '2c3d4e5f6a7b')
    with sqlite3.connect(backup) as source, sqlite3.connect(database) as target:
        source.backup(target)
    with sqlite3.connect(database) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0] == '2c3d4e5f6a7b'
        assert db.execute('SELECT value FROM migration_sentinel').fetchone()[0] == 'retain original data'
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='match_state_candidate_decisions'").fetchone()
