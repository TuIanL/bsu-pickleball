"""add scoring fields to live_coding_states

Revision ID: 9a4b2c8d3e6f
Revises: e1d0cca8a2e5
Create Date: 2026-07-15 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9a4b2c8d3e6f"
down_revision: str | None = "e1d0cca8a2e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("live_coding_states", sa.Column("server_team", sa.String(8), nullable=True))
    op.add_column("live_coding_states", sa.Column("score_a", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("live_coding_states", sa.Column("score_b", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("live_coding_states", sa.Column("scoring_mode", sa.String(32), nullable=False, server_default="none"))
    op.add_column("live_coding_states", sa.Column("scoring_ruleset_version", sa.String(64), nullable=True))
    op.add_column("live_coding_states", sa.Column("recent_results", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("live_coding_states", "recent_results")
    op.drop_column("live_coding_states", "scoring_ruleset_version")
    op.drop_column("live_coding_states", "scoring_mode")
    op.drop_column("live_coding_states", "score_b")
    op.drop_column("live_coding_states", "score_a")
    op.drop_column("live_coding_states", "server_team")
