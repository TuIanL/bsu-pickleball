"""add_segment_edit_operations_and_analysis_batch

Revision ID: e1d0cca8a2e5
Revises: cc7c84e75e78
Create Date: 2026-07-10 16:02:42.013699
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa


revision: str = 'e1d0cca8a2e5'
down_revision: Union[str, None] = 'cc7c84e75e78'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    # ── ALTER capture_segments ──
    for col, type_ in [
        ("corrected_start_ms", sa.Integer()),
        ("corrected_end_ms", sa.Integer()),
        ("edit_version", sa.Integer()),
        ("corrected_at", sa.DateTime()),
        ("edit_status", sa.String(9)),
        ("superseded_by_operation_id", sa.String(64)),
        ("created_by_operation_id", sa.String(64)),
    ]:
        if not _col_exists("capture_segments", col):
            op.add_column("capture_segments", sa.Column(col, type_, nullable=True))

    # ── segment_edit_operations ──
    if not _table_exists("segment_edit_operations"):
        op.create_table(
            "segment_edit_operations",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("capture_take_id", sa.String(64), sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("operation_type", sa.String(32), nullable=False),
            sa.Column("input_segment_ids", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("output_segment_ids", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_edit_ops_take", "segment_edit_operations", ["capture_take_id"])

    # ── analysis_batches ──
    if not _table_exists("analysis_batches"):
        op.create_table(
            "analysis_batches",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("capture_take_id", sa.String(64), sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="creating"),
            sa.Column("analysis_profile", sa.String(64), nullable=False, server_default="match_default"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_batch_take", "analysis_batches", ["capture_take_id"])

    # ── analysis_batch_items ──
    if not _table_exists("analysis_batch_items"):
        op.create_table(
            "analysis_batch_items",
            sa.Column("id", sa.String(64), primary_key=True),
            sa.Column("batch_id", sa.String(64), sa.ForeignKey("analysis_batches.id", ondelete="CASCADE"), nullable=False),
            sa.Column("segment_id", sa.String(64), nullable=False),
            sa.Column("analysis_job_id", sa.String(128), nullable=True),
            sa.Column("segment_version", sa.Integer(), nullable=False),
            sa.Column("snapshot_start_ms", sa.Integer(), nullable=False),
            sa.Column("snapshot_end_ms", sa.Integer(), nullable=False),
            sa.Column("track_id", sa.String(64), nullable=False),
            sa.Column("video_id", sa.String(128), nullable=False),
            sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
        )
        op.create_index("idx_batch_item_batch", "analysis_batch_items", ["batch_id"])
        op.create_index("idx_batch_item_segment", "analysis_batch_items", ["segment_id"])


def downgrade() -> None:
    if _table_exists("analysis_batch_items"):
        op.drop_index("idx_batch_item_segment", table_name="analysis_batch_items")
        op.drop_index("idx_batch_item_batch", table_name="analysis_batch_items")
        op.drop_table("analysis_batch_items")

    if _table_exists("analysis_batches"):
        op.drop_index("idx_batch_take", table_name="analysis_batches")
        op.drop_table("analysis_batches")

    if _table_exists("segment_edit_operations"):
        op.drop_index("idx_edit_ops_take", table_name="segment_edit_operations")
        op.drop_table("segment_edit_operations")

    for col in [
        "created_by_operation_id", "superseded_by_operation_id", "edit_status",
        "corrected_at", "edit_version", "corrected_end_ms", "corrected_start_ms",
    ]:
        if _col_exists("capture_segments", col):
            op.drop_column("capture_segments", col)
