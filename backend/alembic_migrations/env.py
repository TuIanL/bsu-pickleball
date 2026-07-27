"""Alembic env.py —— 使用项目同步 SQLite engine 和 ORM metadata。"""

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.engine import Connection

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

from app.database import Base
import app.models.field_session  # noqa: F401
import app.models.timeline_event  # noqa: F401
import app.models.capture_take  # noqa: F401
import app.models.capture_track  # noqa: F401
import app.models.capture_coding_action  # noqa: F401
import app.models.live_coding_state  # noqa: F401
import app.models.capture_segment  # noqa: F401
import app.models.vidat_annotation  # noqa: F401

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
