"""add capture storage location fields"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "7f3a2c1d9b4e"
down_revision: Union[str, None] = "e1d0cca8a2e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _col_exists(table: str, column: str) -> bool:
    rows = op.get_bind().execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(row[1] == column for row in rows)


def upgrade() -> None:
    for column, type_ in (
        ("storage_root", sa.String(1024)),
        ("session_dir", sa.String(1024)),
        ("storage_status", sa.String(32)),
    ):
        if not _col_exists("capture_takes", column):
            op.add_column(
                "capture_takes",
                sa.Column(column, type_, nullable=column != "storage_status", server_default="available" if column == "storage_status" else None),
            )


def downgrade() -> None:
    for column in ("storage_status", "session_dir", "storage_root"):
        if _col_exists("capture_takes", column):
            op.drop_column("capture_takes", column)
