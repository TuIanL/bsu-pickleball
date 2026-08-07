"""Vidat 标注包及其导入审计的持久化模型。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class VidatAnnotationPackage(Base):
    __tablename__ = "vidat_annotation_packages"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    package_dir: Mapped[str] = mapped_column(String(1024), nullable=False)
    manifest_json: Mapped[str] = mapped_column(Text, nullable=False)
    annotation_json: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_snapshot_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    imported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    __table_args__ = (UniqueConstraint("capture_take_id", "version", name="uq_vidat_package_take_version"),)


class VidatImportPreview(Base):
    __tablename__ = "vidat_import_previews"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("vidat_annotation_packages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    preview_json: Mapped[str] = mapped_column(Text, nullable=False)
    annotation_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    consumed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class VidatImportAudit(Base):
    __tablename__ = "vidat_import_audits"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    package_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("vidat_annotation_packages.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    preview_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("vidat_import_previews.id", ondelete="RESTRICT"), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    operations_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
