"""add registered video timing authority to capture tracks

Revision ID: 0a1b2c3d4e5f
Revises: f7a8b9c0d1e2
"""

import sqlalchemy as sa
from alembic import op

revision = "0a1b2c3d4e5f"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "capture_tracks",
        sa.Column("timing_authority", sa.String(length=32), nullable=False, server_default="missing"),
    )
    op.add_column("capture_tracks", sa.Column("timing_sidecar_path", sa.String(length=1024), nullable=True))
    op.add_column("capture_tracks", sa.Column("timing_failure_reason", sa.String(length=2048), nullable=True))


def downgrade() -> None:
    op.drop_column("capture_tracks", "timing_failure_reason")
    op.drop_column("capture_tracks", "timing_sidecar_path")
    op.drop_column("capture_tracks", "timing_authority")
