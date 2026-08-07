"""add capture storage location fields"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7f3a2c1d9b4e"
down_revision: str | None = "e1d0cca8a2e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _col_exists(table: str, column: str) -> bool:
    rows = op.get_bind().execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def upgrade() -> None:
    # 为 capture_takes 表添加存储位置相关字段
    for column, type_ in (
        ("storage_root", sa.String(1024)),  # 存储根目录
        ("session_dir", sa.String(1024)),  # 会话目录
        ("storage_status", sa.String(32)),  # 存储状态
    ):
        if not _col_exists("capture_takes", column):
            op.add_column(
                "capture_takes",
                sa.Column(
                    column,
                    type_,
                    nullable=column != "storage_status",
                    server_default="available" if column == "storage_status" else None,
                ),
            )


def downgrade() -> None:
    # 回滚：移除存储位置字段
    for column in ("storage_status", "session_dir", "storage_root"):
        if _col_exists("capture_takes", column):
            op.drop_column("capture_takes", column)
