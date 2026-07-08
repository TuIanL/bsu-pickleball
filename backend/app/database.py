"""
本地 SQLite 数据库层 —— engine、session、FastAPI dependency、启动初始化。

职责：
- 根据配置创建 SQLAlchemy engine 和 session factory
- 提供 FastAPI dependency（get_db），每个请求获取独立 session
- 应用启动时确保表已创建（create_all）
- 数据库文件默认位于 data/app.sqlite3，父目录自动创建
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, Engine
from sqlalchemy.orm import Session, sessionmaker, DeclarativeBase

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
    """Reset cached database objects; intended for tests that swap database paths."""
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
    _SessionFactory = sessionmaker(autocommit=False, autoflush=False, bind=get_engine())
    return _SessionFactory


def init_db() -> None:
    """应用启动时调用：确保所有 ORM 表存在。"""
    # 导入所有模型以触发 Base.metadata 注册
    import app.models.field_session  # noqa: F401
    import app.models.timeline_event  # noqa: F401
    engine = get_engine()
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """FastAPI dependency：每个请求生成一个新的数据库 session，请求结束后自动关闭。"""
    db = get_session_factory()()
    try:
        yield db
    finally:
        db.close()
