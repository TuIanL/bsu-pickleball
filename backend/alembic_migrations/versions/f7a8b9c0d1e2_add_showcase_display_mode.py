"""add field session and capture take display mode snapshots

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("field_sessions", sa.Column("display_mode", sa.String(16), nullable=False, server_default="standard"))
    op.add_column("capture_takes", sa.Column("display_mode", sa.String(16), nullable=False, server_default="standard"))


def downgrade() -> None:
    op.drop_column("capture_takes", "display_mode")
    op.drop_column("field_sessions", "display_mode")
