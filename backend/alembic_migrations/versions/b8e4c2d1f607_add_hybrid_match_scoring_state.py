"""add hybrid match scoring state

Revision ID: b8e4c2d1f607
Revises: 7f3a2c1d9b4e, 9a4b2c8d3e6f
Create Date: 2026-07-20 00:00:00.000000
"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b8e4c2d1f607"
down_revision: tuple[str, str] = ("7f3a2c1d9b4e", "9a4b2c8d3e6f")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("live_coding_states", sa.Column("games_won_a", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("live_coding_states", sa.Column("games_won_b", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("live_coding_states", sa.Column("scoring_phase", sa.String(16), nullable=False, server_default="rally"))
    op.add_column("live_coding_states", sa.Column("serving_side", sa.String(8), nullable=True))
    op.add_column("live_coding_states", sa.Column("match_status", sa.String(16), nullable=False, server_default="not_started"))
    op.add_column("live_coding_states", sa.Column("match_winner", sa.String(8), nullable=True))


def downgrade() -> None:
    op.drop_column("live_coding_states", "match_winner")
    op.drop_column("live_coding_states", "match_status")
    op.drop_column("live_coding_states", "serving_side")
    op.drop_column("live_coding_states", "scoring_phase")
    op.drop_column("live_coding_states", "games_won_b")
    op.drop_column("live_coding_states", "games_won_a")
