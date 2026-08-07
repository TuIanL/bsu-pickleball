"""add Vidat annotation packages

Revision ID: d4e5f6a7b8c9
Revises: b8e4c2d1f607
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "b8e4c2d1f607"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vidat_annotation_packages",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "capture_take_id", sa.String(64), sa.ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("package_dir", sa.String(1024), nullable=False),
        sa.Column("manifest_json", sa.Text(), nullable=False),
        sa.Column("annotation_json", sa.Text(), nullable=False),
        sa.Column("normalized_snapshot_json", sa.Text()),
        sa.Column("imported_at", sa.DateTime()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("capture_take_id", "version", name="uq_vidat_package_take_version"),
    )
    op.create_index("ix_vidat_annotation_packages_capture_take_id", "vidat_annotation_packages", ["capture_take_id"])
    op.create_table(
        "vidat_import_previews",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "package_id",
            sa.String(64),
            sa.ForeignKey("vidat_annotation_packages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("token", sa.String(128), nullable=False, unique=True),
        sa.Column("preview_json", sa.Text(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_vidat_import_previews_package_id", "vidat_import_previews", ["package_id"])
    op.create_table(
        "vidat_import_audits",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column(
            "package_id",
            sa.String(64),
            sa.ForeignKey("vidat_annotation_packages.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "preview_id", sa.String(64), sa.ForeignKey("vidat_import_previews.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("operations_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_vidat_import_audits_package_id", "vidat_import_audits", ["package_id"])


def downgrade() -> None:
    op.drop_table("vidat_import_audits")
    op.drop_table("vidat_import_previews")
    op.drop_table("vidat_annotation_packages")
