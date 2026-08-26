"""add scoring calibration annotation packages"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "2c3d4e5f6a7b"
down_revision: str | None = "1b2c3d4e5f6a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scoring_calibration_packages",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=64), nullable=False),
        sa.Column("capture_take_id", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.String(length=96), nullable=False, server_default="scoring-calibration-annotation.v1"),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="draft"),
        sa.Column("annotator", sa.String(length=120), nullable=True),
        sa.Column("note", sa.String(length=2048), nullable=True),
        sa.Column("source_job_id", sa.String(length=64), nullable=True),
        sa.Column("source_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("quality_summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("validation_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("artifact_json", sa.Text(), nullable=True),
        sa.Column("supersedes_id", sa.String(length=64), nullable=True),
        sa.Column("locked_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["capture_take_id"], ["capture_takes.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["supersedes_id"], ["scoring_calibration_packages.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", "revision", name="uq_scoring_calibration_package_revision"),
    )
    op.create_index("ix_scoring_calibration_packages_package_id", "scoring_calibration_packages", ["package_id"])
    op.create_index("ix_scoring_calibration_packages_capture_take_id", "scoring_calibration_packages", ["capture_take_id"])
    op.create_index("ix_scoring_calibration_packages_status", "scoring_calibration_packages", ["status"])
    op.create_index("ix_scoring_calibration_packages_source_job_id", "scoring_calibration_packages", ["source_job_id"])
    op.create_index("ix_scoring_calibration_packages_supersedes_id", "scoring_calibration_packages", ["supersedes_id"])
    op.create_index("idx_scoring_calibration_take_status", "scoring_calibration_packages", ["capture_take_id", "status", "revision"])

    op.create_table(
        "scoring_calibration_annotations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("package_revision_id", sa.String(length=64), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("candidate_id", sa.String(length=128), nullable=True),
        sa.Column("event_ms", sa.Integer(), nullable=False),
        sa.Column("evidence_start_ms", sa.Integer(), nullable=False),
        sa.Column("evidence_end_ms", sa.Integer(), nullable=False),
        sa.Column("video_id", sa.String(length=128), nullable=True),
        sa.Column("rally_segment_id", sa.String(length=64), nullable=True),
        sa.Column("player_id", sa.String(length=128), nullable=True),
        sa.Column("stage", sa.String(length=32), nullable=True),
        sa.Column("opportunity_status", sa.String(length=32), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("landing_status", sa.String(length=32), nullable=True),
        sa.Column("landing_zone", sa.String(length=32), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("decision", sa.String(length=16), nullable=False, server_default="unreviewed"),
        sa.Column("revoked", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["package_revision_id"], ["scoring_calibration_packages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scoring_calibration_annotations_package_revision_id", "scoring_calibration_annotations", ["package_revision_id"])
    op.create_index("idx_scoring_calibration_annotation_package_time", "scoring_calibration_annotations", ["package_revision_id", "event_ms"])
    op.create_index("idx_scoring_calibration_annotation_candidate", "scoring_calibration_annotations", ["package_revision_id", "candidate_id"])
    op.create_index("ix_scoring_calibration_annotations_candidate_id", "scoring_calibration_annotations", ["candidate_id"])
    op.create_index("ix_scoring_calibration_annotations_rally_segment_id", "scoring_calibration_annotations", ["rally_segment_id"])

    op.create_table(
        "scoring_calibration_candidate_decisions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("package_revision_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=128), nullable=False),
        sa.Column("candidate_type", sa.String(length=32), nullable=False, server_default="shot"),
        sa.Column("source", sa.String(length=32), nullable=False, server_default="algorithm"),
        sa.Column("source_job_id", sa.String(length=64), nullable=True),
        sa.Column("candidate_snapshot_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("decision", sa.String(length=16), nullable=False, server_default="unreviewed"),
        sa.Column("annotation_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["package_revision_id"], ["scoring_calibration_packages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_revision_id", "candidate_id", name="uq_scoring_calibration_candidate_decision"),
    )
    op.create_index("ix_scoring_calibration_candidate_decisions_package_revision_id", "scoring_calibration_candidate_decisions", ["package_revision_id"])
    op.create_index("idx_scoring_calibration_candidate_decision_package", "scoring_calibration_candidate_decisions", ["package_revision_id", "decision"])
    op.create_index("ix_scoring_calibration_candidate_decisions_annotation_id", "scoring_calibration_candidate_decisions", ["annotation_id"])


def downgrade() -> None:
    op.drop_table("scoring_calibration_candidate_decisions")
    op.drop_table("scoring_calibration_annotations")
    op.drop_table("scoring_calibration_packages")
