"""add Vidat provenance and immutable preview input

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("capture_coding_actions", sa.Column("source", sa.String(32), nullable=False, server_default="manual"))
    op.add_column("capture_coding_actions", sa.Column("annotation_package_id", sa.String(64)))
    op.add_column("capture_coding_actions", sa.Column("vidat_import_audit_id", sa.String(64)))
    op.create_index("ix_capture_coding_actions_annotation_package_id", "capture_coding_actions", ["annotation_package_id"])
    op.create_index("ix_capture_coding_actions_vidat_import_audit_id", "capture_coding_actions", ["vidat_import_audit_id"])
    op.add_column("session_timeline_events", sa.Column("annotation_package_id", sa.String(64)))
    op.add_column("session_timeline_events", sa.Column("vidat_import_audit_id", sa.String(64)))
    op.create_index("ix_session_timeline_events_annotation_package_id", "session_timeline_events", ["annotation_package_id"])
    op.create_index("ix_session_timeline_events_vidat_import_audit_id", "session_timeline_events", ["vidat_import_audit_id"])
    op.add_column("capture_segments", sa.Column("annotation_package_id", sa.String(64)))
    op.add_column("capture_segments", sa.Column("vidat_import_audit_id", sa.String(64)))
    op.create_index("ix_capture_segments_annotation_package_id", "capture_segments", ["annotation_package_id"])
    op.create_index("ix_capture_segments_vidat_import_audit_id", "capture_segments", ["vidat_import_audit_id"])
    op.add_column("vidat_import_previews", sa.Column("annotation_json", sa.Text(), nullable=False, server_default="{}"))


def downgrade() -> None:
    op.drop_column("vidat_import_previews", "annotation_json")
    op.drop_index("ix_capture_segments_vidat_import_audit_id", table_name="capture_segments")
    op.drop_index("ix_capture_segments_annotation_package_id", table_name="capture_segments")
    op.drop_column("capture_segments", "vidat_import_audit_id")
    op.drop_column("capture_segments", "annotation_package_id")
    op.drop_index("ix_session_timeline_events_vidat_import_audit_id", table_name="session_timeline_events")
    op.drop_index("ix_session_timeline_events_annotation_package_id", table_name="session_timeline_events")
    op.drop_column("session_timeline_events", "vidat_import_audit_id")
    op.drop_column("session_timeline_events", "annotation_package_id")
    op.drop_index("ix_capture_coding_actions_vidat_import_audit_id", table_name="capture_coding_actions")
    op.drop_index("ix_capture_coding_actions_annotation_package_id", table_name="capture_coding_actions")
    op.drop_column("capture_coding_actions", "vidat_import_audit_id")
    op.drop_column("capture_coding_actions", "annotation_package_id")
    op.drop_column("capture_coding_actions", "source")
