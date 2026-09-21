"""add analysis roster and rally context persistence"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5f6a7b8c9d0e"
down_revision: str | None = "4e5f6a7b8c9d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Historical deployments bootstrapped ORM metadata with ``create_all`` before
# Alembic was introduced, so the new tables may already exist when this revision
# is first applied.  Keep every statement additive and idempotent, matching the
# pattern established by ``4e5f6a7b8c9d``.
_TABLES: dict[str, tuple[sa.Column, ...]] = {
    "rally_scoring_snapshots": (
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column(
            "capture_take_id",
            sa.String(64),
            sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action_id", sa.String(64), nullable=False),
        sa.Column("event_id", sa.String(64)),
        sa.Column("rally_id", sa.String(64)),
        sa.Column("ordinal", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("server_team", sa.String(8)),
        sa.Column("score_a_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("score_b_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("games_won_a_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("games_won_b_before", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scoring_phase", sa.String(16), nullable=False, server_default="rally"),
        sa.Column("scoring_ruleset_version", sa.String(64)),
        sa.Column("action_revision", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("start_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_snapshot_id", sa.String(80)),
        sa.Column("status", sa.String(16), nullable=False, server_default="effective"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("superseded_at", sa.DateTime()),
    ),
    "court_end_confirmations": (
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("owner_key", sa.String(128), nullable=False),
        sa.Column("capture_take_id", sa.String(64)),
        sa.Column("video_id", sa.String(64)),
        sa.Column("team_a_end", sa.String(16), nullable=False),
        sa.Column("confirmed_at_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("is_effective", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("confirmed_by", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("job_id", sa.String(128)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    ),
    "analysis_roster_snapshots": (
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("owner_key", sa.String(128), nullable=False),
        sa.Column("capture_take_id", sa.String(64)),
        sa.Column("video_id", sa.String(64)),
        sa.Column("job_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False, server_default="unavailable"),
        sa.Column("unavailable_reason", sa.String(128)),
        sa.Column("source", sa.String(32), nullable=False, server_default="manual"),
        sa.Column("initial_team_a_end", sa.String(16)),
        sa.Column("entries_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("roster_hash", sa.String(64), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    ),
    "analysis_rally_context_sets": (
        sa.Column("id", sa.String(80), primary_key=True),
        sa.Column("owner_key", sa.String(128), nullable=False),
        sa.Column("job_id", sa.String(128), nullable=False),
        sa.Column("capture_take_id", sa.String(64)),
        sa.Column("status", sa.String(32), nullable=False, server_default="unavailable"),
        sa.Column("unavailable_reason", sa.String(128)),
        sa.Column("scoring_hash", sa.String(64)),
        sa.Column("roster_hash", sa.String(64)),
        sa.Column("court_end_hash", sa.String(64)),
        sa.Column("context_set_hash", sa.String(64), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("supersedes_context_set_id", sa.String(80)),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    ),
}

_INDEXES: dict[str, tuple[tuple[str, list[str]], ...]] = {
    "rally_scoring_snapshots": (
        ("uq_scoring_snapshot_action_revision", ["capture_take_id", "action_id", "revision"]),
        ("idx_scoring_snapshot_take_rally", ["capture_take_id", "rally_id"]),
        ("idx_scoring_snapshot_take_status", ["capture_take_id", "status"]),
    ),
    "court_end_confirmations": (
        ("uq_court_end_owner_revision", ["owner_key", "revision"]),
        ("idx_court_end_owner_effective", ["owner_key", "is_effective"]),
    ),
    "analysis_roster_snapshots": (
        ("idx_roster_snapshot_owner", ["owner_key", "created_at"]),
        ("idx_roster_snapshot_job", ["job_id"]),
    ),
    "analysis_rally_context_sets": (
        ("idx_rally_context_job", ["job_id", "version"]),
        ("idx_rally_context_owner", ["owner_key"]),
    ),
}

_UNIQUE_INDEXES = {"uq_scoring_snapshot_action_revision", "uq_court_end_owner_revision"}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, columns in _TABLES.items():
        if not inspector.has_table(table_name):
            op.create_table(table_name, *columns)

    for table_name, indexes in _INDEXES.items():
        if not inspector.has_table(table_name):
            continue
        existing = {index["name"] for index in inspector.get_indexes(table_name)}
        for index_name, index_columns in indexes:
            if index_name in existing:
                continue
            if index_name in _UNIQUE_INDEXES:
                op.create_index(index_name, table_name, index_columns, unique=True)
            else:
                op.create_index(index_name, table_name, index_columns)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name, indexes in _INDEXES.items():
        if not inspector.has_table(table_name):
            continue
        existing = {index["name"] for index in inspector.get_indexes(table_name)}
        for index_name, _ in indexes:
            if index_name in existing:
                op.drop_index(index_name, table_name=table_name)
    for table_name in _TABLES:
        if inspector.has_table(table_name):
            op.drop_table(table_name)
