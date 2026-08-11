"""
本地 SQLite 数据库层 —— engine、session、FastAPI dependency、启动初始化。

职责：
- 根据配置创建 SQLAlchemy engine 和 session factory
- 提供 FastAPI dependency（get_db），每个请求获取独立 session
- 应用启动时确保表已创建（create_all）
- 数据库文件默认位于 data/app.sqlite3，父目录自动创建
"""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


# 全局 engine 和 session factory（延迟初始化）
_engine: Engine | None = None
_SessionFactory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """获取或创建 SQLAlchemy engine（单例）。"""
    global _engine
    if _engine is not None:
        return _engine

    settings = get_settings()
    db_path = settings.resolve_path(settings.database_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)

    _engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},  # SQLite 多线程访问需要
        echo=False,
    )
    return _engine


def reset_database_state() -> None:
    """重置缓存的数据库对象，用于测试中切换数据库路径。"""
    global _engine, _SessionFactory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _SessionFactory = None


def get_session_factory() -> sessionmaker[Session]:
    """获取或创建 session factory（单例）。"""
    global _SessionFactory
    if _SessionFactory is not None:
        return _SessionFactory
    engine = get_engine()
    _ensure_capture_storage_columns(engine)
    _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    return _SessionFactory


def _ensure_capture_storage_columns(engine: Engine) -> None:
    """在 Alembic 迁移运行前，为本地已有 SQLite 表补齐缺少的列。"""
    if not inspect(engine).has_table("capture_takes"):
        return
    columns = {column["name"] for column in inspect(engine).get_columns("capture_takes")}
    track_columns = (
        {column["name"] for column in inspect(engine).get_columns("capture_tracks")}
        if inspect(engine).has_table("capture_tracks")
        else set()
    )
    ffmpeg_columns = (
        {column["name"] for column in inspect(engine).get_columns("ffmpeg_registry")}
        if inspect(engine).has_table("ffmpeg_registry")
        else set()
    )
    with engine.begin() as connection:
        if "storage_root" not in columns:
            connection.execute(text("ALTER TABLE capture_takes ADD COLUMN storage_root VARCHAR(1024)"))
        if "session_dir" not in columns:
            connection.execute(text("ALTER TABLE capture_takes ADD COLUMN session_dir VARCHAR(1024)"))
        if "storage_status" not in columns:
            connection.execute(
                text("ALTER TABLE capture_takes ADD COLUMN storage_status VARCHAR(32) NOT NULL DEFAULT 'available'")
            )
        if "display_mode" not in columns:
            connection.execute(
                text("ALTER TABLE capture_takes ADD COLUMN display_mode VARCHAR(16) NOT NULL DEFAULT 'standard'")
            )
        if "slot" not in track_columns:
            connection.execute(text("ALTER TABLE capture_tracks ADD COLUMN slot VARCHAR(16) NOT NULL DEFAULT 'cam_1'"))
        if "analysis_role" not in track_columns:
            connection.execute(
                text("ALTER TABLE capture_tracks ADD COLUMN analysis_role VARCHAR(32) NOT NULL DEFAULT 'default'")
            )
        if "fragment_id" not in ffmpeg_columns:
            connection.execute(text("ALTER TABLE ffmpeg_registry ADD COLUMN fragment_id VARCHAR(64)"))
        if "return_code" not in ffmpeg_columns:
            connection.execute(text("ALTER TABLE ffmpeg_registry ADD COLUMN return_code INTEGER"))
        if "exit_reason" not in ffmpeg_columns:
            connection.execute(text("ALTER TABLE ffmpeg_registry ADD COLUMN exit_reason VARCHAR(64)"))


def _ensure_vidat_provenance_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    additions = {
        "capture_coding_actions": {
            "source": "VARCHAR(32) NOT NULL DEFAULT 'manual'",
            "annotation_package_id": "VARCHAR(64)",
            "vidat_import_audit_id": "VARCHAR(64)",
        },
        "session_timeline_events": {"annotation_package_id": "VARCHAR(64)", "vidat_import_audit_id": "VARCHAR(64)"},
        "capture_segments": {"annotation_package_id": "VARCHAR(64)", "vidat_import_audit_id": "VARCHAR(64)"},
        "vidat_import_previews": {"annotation_json": "TEXT NOT NULL DEFAULT '{}'"},
    }
    with engine.begin() as connection:
        for table, definitions in additions.items():
            if not inspector.has_table(table):
                continue
            columns = {column["name"] for column in inspector.get_columns(table)}
            for name, definition in definitions.items():
                if name not in columns:
                    connection.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}"))


def init_db() -> None:
    """应用启动时调用：确保所有 ORM 表存在。"""
    # 导入所有模型以触发 Base.metadata 注册
    import app.models.analysis_batch  # noqa: F401
    import app.models.camera_lease  # noqa: F401
    import app.models.capture_coding_action  # noqa: F401
    import app.models.capture_segment  # noqa: F401
    import app.models.capture_take  # noqa: F401
    import app.models.capture_track  # noqa: F401
    import app.models.ffmpeg_registry  # noqa: F401
    import app.models.field_session  # noqa: F401
    import app.models.live_coding_state  # noqa: F401
    import app.models.media_fragment  # noqa: F401
    import app.models.segment_edit_operation  # noqa: F401
    import app.models.timeline_event  # noqa: F401
    import app.models.track_finalization  # noqa: F401
    import app.models.track_timeline_span  # noqa: F401
    import app.models.vidat_annotation  # noqa: F401

    engine = get_engine()
    Base.metadata.create_all(bind=engine)
    _ensure_capture_storage_columns(engine)
    field_session_columns = {column["name"] for column in inspect(engine).get_columns("field_sessions")}
    with engine.begin() as connection:
        if "display_mode" not in field_session_columns:
            connection.execute(
                text("ALTER TABLE field_sessions ADD COLUMN display_mode VARCHAR(16) NOT NULL DEFAULT 'standard'")
            )
    _ensure_vidat_provenance_columns(engine)
    # SQLite 的 create_all 不会为已有表追加列；保持本地历史数据库可用。
    lcs_columns = {column["name"] for column in inspect(engine).get_columns("live_coding_states")}
    with engine.begin() as connection:
        if "match_phase" not in lcs_columns:
            connection.execute(
                text("ALTER TABLE live_coding_states ADD COLUMN match_phase VARCHAR(32) NOT NULL DEFAULT 'idle'")
            )
        if "intermission_kind" not in lcs_columns:
            connection.execute(text("ALTER TABLE live_coding_states ADD COLUMN intermission_kind VARCHAR(32)"))
        if "server_team" not in lcs_columns:
            connection.execute(text("ALTER TABLE live_coding_states ADD COLUMN server_team VARCHAR(8)"))
        if "score_a" not in lcs_columns:
            connection.execute(text("ALTER TABLE live_coding_states ADD COLUMN score_a INTEGER NOT NULL DEFAULT 0"))
        if "score_b" not in lcs_columns:
            connection.execute(text("ALTER TABLE live_coding_states ADD COLUMN score_b INTEGER NOT NULL DEFAULT 0"))
        if "scoring_mode" not in lcs_columns:
            connection.execute(
                text("ALTER TABLE live_coding_states ADD COLUMN scoring_mode VARCHAR(32) NOT NULL DEFAULT 'none'")
            )
        if "scoring_ruleset_version" not in lcs_columns:
            connection.execute(text("ALTER TABLE live_coding_states ADD COLUMN scoring_ruleset_version VARCHAR(64)"))
        if "recent_results" not in lcs_columns:
            connection.execute(
                text("ALTER TABLE live_coding_states ADD COLUMN recent_results TEXT NOT NULL DEFAULT '[]'")
            )
        if "games_won_a" not in lcs_columns:
            connection.execute(text("ALTER TABLE live_coding_states ADD COLUMN games_won_a INTEGER NOT NULL DEFAULT 0"))
        if "games_won_b" not in lcs_columns:
            connection.execute(text("ALTER TABLE live_coding_states ADD COLUMN games_won_b INTEGER NOT NULL DEFAULT 0"))
        if "scoring_phase" not in lcs_columns:
            connection.execute(
                text("ALTER TABLE live_coding_states ADD COLUMN scoring_phase VARCHAR(16) NOT NULL DEFAULT 'rally'")
            )
        if "serving_side" not in lcs_columns:
            connection.execute(text("ALTER TABLE live_coding_states ADD COLUMN serving_side VARCHAR(8)"))
        if "match_status" not in lcs_columns:
            connection.execute(
                text(
                    "ALTER TABLE live_coding_states ADD COLUMN match_status VARCHAR(16) NOT NULL DEFAULT 'not_started'"
                )
            )
        if "match_winner" not in lcs_columns:
            connection.execute(text("ALTER TABLE live_coding_states ADD COLUMN match_winner VARCHAR(8)"))


def get_db() -> Session:
    """FastAPI dependency：每个请求生成一个新的数据库 session，请求结束后自动关闭。"""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
