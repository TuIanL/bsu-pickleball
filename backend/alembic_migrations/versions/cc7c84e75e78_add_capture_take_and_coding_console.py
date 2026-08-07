"""add_capture_take_and_coding_console

Revision ID: cc7c84e75e78
Revises:
Create Date: 2026-07-10 15:02:07.679199
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "cc7c84e75e78"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(
        sa.text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
        {"name": name},
    )
    return result.fetchone() is not None


def _col_exists(table: str, col: str) -> bool:
    conn = op.get_bind()
    result = conn.execute(sa.text(f"PRAGMA table_info({table})"))
    return any(row[1] == col for row in result.fetchall())


def upgrade() -> None:
    # 创建拍摄片段表
    if not _table_exists("capture_takes"):
        op.create_table(
            "capture_takes",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("field_session_id", sa.String(64), sa.ForeignKey("field_sessions.id"), nullable=False),
            sa.Column("capture_mode", sa.String(6), nullable=False),
            sa.Column("source_session_type", sa.String(14), nullable=False),
            sa.Column("source_session_id", sa.String(128), nullable=False),
            sa.Column("status", sa.String(9), nullable=False, server_default="recording"),
            sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("ended_at", sa.DateTime(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("archived_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("source_session_type", "source_session_id", name="uq_take_source"),
            sa.CheckConstraint("duration_ms IS NULL OR duration_ms >= 0", name="ck_take_duration_nonneg"),
            sa.CheckConstraint("revision >= 0", name="ck_take_revision_nonneg"),
        )
        # 拍摄片段索引
        op.create_index("idx_take_field_session", "capture_takes", ["field_session_id", "started_at"])
        op.create_index("idx_take_status", "capture_takes", ["status"])
        op.create_index(op.f("ix_capture_takes_field_session_id"), "capture_takes", ["field_session_id"], unique=False)

    # 创建拍摄轨道表
    if not _table_exists("capture_tracks"):
        op.create_table(
            "capture_tracks",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column(
                "capture_take_id", sa.String(64), sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
            ),
            sa.Column("camera_id", sa.String(128), nullable=False),
            sa.Column("role", sa.String(9), nullable=False),
            sa.Column("video_id", sa.String(128), nullable=True),
            sa.Column("offset_ms", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("offset_source", sa.String(9), nullable=False, server_default="assumed"),
            sa.Column("sync_quality", sa.String(8), nullable=False, server_default="unknown"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("capture_take_id", "role", name="uq_track_take_role"),
        )
        op.create_index("idx_track_take", "capture_tracks", ["capture_take_id"])

    # 创建编码操作表
    if not _table_exists("capture_coding_actions"):
        op.create_table(
            "capture_coding_actions",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column(
                "capture_take_id", sa.String(64), sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
            ),
            sa.Column("client_action_id", sa.String(128), nullable=False),
            sa.Column("action_type", sa.String(64), nullable=False),
            sa.Column("timestamp_ms", sa.Integer(), nullable=False),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("request_hash", sa.String(128), nullable=False),
            sa.Column("status", sa.String(8), nullable=False, server_default="executed"),
            sa.Column("revision_before", sa.Integer(), nullable=False),
            sa.Column("revision_after", sa.Integer(), nullable=True),
            sa.Column("result_json", sa.Text(), nullable=True),
            sa.Column("error_code", sa.String(64), nullable=True),
            sa.Column("reverses_action_id", sa.String(64), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("capture_take_id", "client_action_id", name="uq_coding_client_action"),
        )
        op.create_index("idx_coding_take_revision", "capture_coding_actions", ["capture_take_id", "revision_before"])

    # 创建实时编码状态表
    if not _table_exists("live_coding_states"):
        op.create_table(
            "live_coding_states",
            sa.Column(
                "capture_take_id",
                sa.String(64),
                sa.ForeignKey("capture_takes.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("set_ordinal", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("game_ordinal", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("rally_ordinal", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("non_play", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("current_set_segment_id", sa.String(64), nullable=True),
            sa.Column("current_game_segment_id", sa.String(64), nullable=True),
            sa.Column("current_rally_segment_id", sa.String(64), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )

    # 创建片段表
    if not _table_exists("capture_segments"):
        op.create_table(
            "capture_segments",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column(
                "capture_take_id", sa.String(64), sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
            ),
            sa.Column("segment_type", sa.String(6), nullable=False),
            sa.Column(
                "parent_segment_id",
                sa.String(64),
                sa.ForeignKey("capture_segments.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("ordinal", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("label", sa.String(256), nullable=False, server_default=""),
            sa.Column("start_event_id", sa.String(64), nullable=True),
            sa.Column("end_event_id", sa.String(64), nullable=True),
            sa.Column("start_ms", sa.Integer(), nullable=False),
            sa.Column("end_ms", sa.Integer(), nullable=True),
            sa.Column("status", sa.String(9), nullable=False, server_default="open"),
            sa.Column("close_reason", sa.String(64), nullable=True),
            sa.Column("source", sa.String(9), nullable=False, server_default="manual"),
            sa.Column("is_highlight", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint("end_ms IS NULL OR end_ms >= start_ms", name="ck_segment_end_after_start"),
        )
        op.create_index("idx_segment_take_type", "capture_segments", ["capture_take_id", "segment_type", "start_ms"])
        op.create_index("idx_segment_parent", "capture_segments", ["parent_segment_id"])

    # 为时间线事件表添加拍摄片段关联
    if not _col_exists("session_timeline_events", "capture_take_id"):
        op.add_column("session_timeline_events", sa.Column("capture_take_id", sa.String(length=64), nullable=True))
        op.create_index(
            op.f("ix_session_timeline_events_capture_take_id"),
            "session_timeline_events",
            ["capture_take_id"],
            unique=False,
        )

    # 为时间线事件表添加撤销标记
    if not _col_exists("session_timeline_events", "is_undone"):
        op.add_column(
            "session_timeline_events", sa.Column("is_undone", sa.Boolean(), nullable=False, server_default=sa.text("0"))
        )


def downgrade() -> None:
    # 回滚：移除时间线事件新增字段
    if _col_exists("session_timeline_events", "is_undone"):
        op.drop_column("session_timeline_events", "is_undone")
    if _col_exists("session_timeline_events", "capture_take_id"):
        op.drop_index(op.f("ix_session_timeline_events_capture_take_id"), table_name="session_timeline_events")
        op.drop_column("session_timeline_events", "capture_take_id")

    # 回滚：按依赖顺序删除所有新建表
    for table in [
        "capture_segments",
        "live_coding_states",
        "capture_coding_actions",
        "capture_tracks",
        "capture_takes",
    ]:
        if _table_exists(table):
            op.drop_table(table)
