"""add Vidat version metadata, lineage and active projection"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "1b2c3d4e5f6a"
down_revision = "0a1b2c3d4e5f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vidat_annotation_packages", sa.Column("name", sa.String(160), nullable=True))
    op.add_column("vidat_annotation_packages", sa.Column("owner", sa.String(120), nullable=True))
    op.add_column("vidat_annotation_packages", sa.Column("note", sa.String(2048), nullable=True))
    op.add_column("vidat_annotation_packages", sa.Column("source_package_id", sa.String(64), nullable=True))
    op.add_column(
        "vidat_annotation_packages",
        sa.Column("provenance", sa.String(16), nullable=True, server_default="generated"),
    )
    op.add_column("vidat_annotation_packages", sa.Column("deleted_at", sa.DateTime(), nullable=True))
    op.create_index(
        "ix_vidat_annotation_packages_source_package_id",
        "vidat_annotation_packages",
        ["source_package_id"],
    )
    op.create_index("ix_vidat_annotation_packages_deleted_at", "vidat_annotation_packages", ["deleted_at"])

    op.add_column("vidat_import_audits", sa.Column("result_package_id", sa.String(64), nullable=True))
    op.create_index("ix_vidat_import_audits_result_package_id", "vidat_import_audits", ["result_package_id"])

    op.add_column("live_coding_states", sa.Column("active_vidat_package_id", sa.String(64), nullable=True))
    op.create_index("ix_live_coding_states_active_vidat_package_id", "live_coding_states", ["active_vidat_package_id"])


def downgrade() -> None:
    op.drop_index("ix_live_coding_states_active_vidat_package_id", table_name="live_coding_states")
    op.drop_column("live_coding_states", "active_vidat_package_id")
    op.drop_index("ix_vidat_import_audits_result_package_id", table_name="vidat_import_audits")
    op.drop_column("vidat_import_audits", "result_package_id")
    op.drop_index("ix_vidat_annotation_packages_deleted_at", table_name="vidat_annotation_packages")
    op.drop_index("ix_vidat_annotation_packages_source_package_id", table_name="vidat_annotation_packages")
    op.drop_column("vidat_annotation_packages", "deleted_at")
    op.drop_column("vidat_annotation_packages", "provenance")
    op.drop_column("vidat_annotation_packages", "source_package_id")
    op.drop_column("vidat_annotation_packages", "note")
    op.drop_column("vidat_annotation_packages", "owner")
    op.drop_column("vidat_annotation_packages", "name")
