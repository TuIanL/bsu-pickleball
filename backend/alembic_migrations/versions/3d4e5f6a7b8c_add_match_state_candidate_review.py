"""persist learned candidate artifacts and review decisions

Revision ID: 3d4e5f6a7b8c
Revises: 2c3d4e5f6a7b
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3d4e5f6a7b8c"
down_revision: str | None = "2c3d4e5f6a7b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _table_exists(name: str) -> bool:
    connection = op.get_bind()
    return bool(
        connection.execute(
            sa.text("SELECT 1 FROM sqlite_master WHERE type='table' AND name=:name"),
            {"name": name},
        ).first()
    )


def upgrade() -> None:
    if not _table_exists("match_state_candidate_artifacts"):
        op.create_table(
            "match_state_candidate_artifacts",
            sa.Column("id", sa.String(80), primary_key=True),
            sa.Column("capture_take_id", sa.String(64), sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("artifact_version", sa.String(64), nullable=False),
            sa.Column("artifact_json", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("capture_take_id", "artifact_version", name="uq_candidate_artifact_version"),
        )
    if not _table_exists("match_state_candidate_reviews"):
        op.create_table(
            "match_state_candidate_reviews",
            sa.Column("capture_take_id", sa.String(64), sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"), primary_key=True),
            sa.Column("artifact_version", sa.String(64), primary_key=True),
            sa.Column("revision", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
        )
        op.create_index(
            "idx_candidate_review_take_version",
            "match_state_candidate_reviews",
            ["capture_take_id", "artifact_version"],
        )
    if not _table_exists("match_state_candidate_decisions"):
        op.create_table(
            "match_state_candidate_decisions",
            sa.Column("id", sa.String(80), primary_key=True),
            sa.Column("request_id", sa.String(128), nullable=False),
            sa.Column("capture_take_id", sa.String(64), sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("artifact_version", sa.String(64), nullable=False),
            sa.Column("candidate_id", sa.String(128), nullable=False),
            sa.Column("decision", sa.String(16), nullable=False),
            sa.Column("expected_revision", sa.Integer(), nullable=False),
            sa.Column("revision", sa.Integer(), nullable=False),
            sa.Column("original_start_ms", sa.Integer(), nullable=False),
            sa.Column("original_end_ms", sa.Integer(), nullable=False),
            sa.Column("reviewed_start_ms", sa.Integer(), nullable=False),
            sa.Column("reviewed_end_ms", sa.Integer(), nullable=False),
            sa.Column("note", sa.Text()),
            sa.Column("operation_id", sa.String(80)),
            sa.Column("output_segment_id", sa.String(80)),
            sa.Column("provenance_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("request_payload_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.UniqueConstraint("request_id", name="uq_candidate_decision_request"),
            sa.UniqueConstraint(
                "capture_take_id",
                "artifact_version",
                "candidate_id",
                name="uq_candidate_decision_candidate",
            ),
        )
        op.create_index(
            "idx_candidate_decision_take_version",
            "match_state_candidate_decisions",
            ["capture_take_id", "artifact_version"],
        )


def downgrade() -> None:
    if _table_exists("match_state_candidate_decisions"):
        op.drop_index("idx_candidate_decision_take_version", table_name="match_state_candidate_decisions")
        op.drop_table("match_state_candidate_decisions")
    if _table_exists("match_state_candidate_reviews"):
        op.drop_index("idx_candidate_review_take_version", table_name="match_state_candidate_reviews")
        op.drop_table("match_state_candidate_reviews")
    if _table_exists("match_state_candidate_artifacts"):
        op.drop_table("match_state_candidate_artifacts")
