"""add formal match-state segmentation runs and segment provenance"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4e5f6a7b8c9d"
down_revision: str | None = "3d4e5f6a7b8c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Some historical deployments bootstrapped ORM metadata with ``create_all``
    # before Alembic was introduced.  In that case the new table/indexes may
    # already exist when this revision is first applied; make the revision
    # additive and idempotent instead of failing on duplicate DDL.
    if not inspector.has_table("match_state_segmentation_runs"):
        op.create_table(
            "match_state_segmentation_runs",
            sa.Column("id", sa.String(80), primary_key=True),
            sa.Column("capture_take_id", sa.String(64), sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False),
            sa.Column("planning_job_id", sa.String(128), nullable=False),
            sa.Column("status", sa.String(32), nullable=False, server_default="running"),
            sa.Column("profile", sa.String(64), nullable=False, server_default="match_default"),
            sa.Column("model_package_id", sa.String(128)), sa.Column("model_package_version", sa.String(128)),
            sa.Column("package_sha256", sa.String(64)), sa.Column("weights_sha256", sa.String(64)),
            sa.Column("decoder_sha256", sa.String(64)), sa.Column("input_fingerprint", sa.String(128)),
            sa.Column("sync_calibration_revision", sa.Integer()), sa.Column("timing_authority", sa.String(32)),
            sa.Column("artifact_path", sa.String(1024)), sa.Column("artifact_sha256", sa.String(64)),
            sa.Column("window_plan_hash", sa.String(64)), sa.Column("unknown_rate", sa.Float()),
            sa.Column("segment_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("diagnostics_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("plan_json", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("supersedes_run_id", sa.String(80)), sa.Column("started_at", sa.DateTime(), nullable=False),
            sa.Column("finished_at", sa.DateTime()),
        )

    existing_indexes = {index["name"] for index in inspector.get_indexes("match_state_segmentation_runs")}
    if "idx_segmentation_run_take_status" not in existing_indexes:
        op.create_index("idx_segmentation_run_take_status", "match_state_segmentation_runs", ["capture_take_id", "status"])
    if "idx_segmentation_run_planning_job" not in existing_indexes:
        op.create_index("idx_segmentation_run_planning_job", "match_state_segmentation_runs", ["planning_job_id"])

    segment_columns = {column["name"] for column in inspector.get_columns("capture_segments")}
    if "segmentation_run_id" not in segment_columns:
        op.add_column("capture_segments", sa.Column("segmentation_run_id", sa.String(80), nullable=True))
    segment_indexes = {index["name"] for index in inspector.get_indexes("capture_segments")}
    if "ix_capture_segments_segmentation_run_id" not in segment_indexes:
        op.create_index("ix_capture_segments_segmentation_run_id", "capture_segments", ["segmentation_run_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("capture_segments"):
        indexes = {index["name"] for index in inspector.get_indexes("capture_segments")}
        if "ix_capture_segments_segmentation_run_id" in indexes:
            op.drop_index("ix_capture_segments_segmentation_run_id", table_name="capture_segments")
        columns = {column["name"] for column in inspector.get_columns("capture_segments")}
        if "segmentation_run_id" in columns:
            # SQLite cannot directly DROP a column that participates in a
            # foreign-key constraint.  Batch mode rebuilds the table while
            # preserving its remaining columns/constraints.
            with op.batch_alter_table("capture_segments", recreate="always") as batch_op:
                batch_op.drop_column("segmentation_run_id")
    if inspector.has_table("match_state_segmentation_runs"):
        indexes = {index["name"] for index in inspector.get_indexes("match_state_segmentation_runs")}
        if "idx_segmentation_run_planning_job" in indexes:
            op.drop_index("idx_segmentation_run_planning_job", table_name="match_state_segmentation_runs")
        if "idx_segmentation_run_take_status" in indexes:
            op.drop_index("idx_segmentation_run_take_status", table_name="match_state_segmentation_runs")
        op.drop_table("match_state_segmentation_runs")
