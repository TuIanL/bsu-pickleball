"""分析名册与分析回合上下文的持久化模型。

四张表对应三个分层事实，外加 Job 绑定：

- `rally_scoring_snapshots` —— 录制期在 `rally_start` 同事务封存的纯计分事实。
  带 `revision` + `supersedes_snapshot_id` 形成 supersede 链，`status` 区分
  effective / superseded / undone。
- `court_end_confirmations` —— 用户确认的初始 A/B 端位。Job 级确认一次，
  之后由有效 `side_change` 在投影中回放；重新确认产生新 revision，旧行转 non-effective。
- `analysis_roster_snapshots` —— Job 创建时冻结的名册（含 bootstrap 身份锚点）。
- `analysis_rally_context_sets` —— Job 创建时合成的不可变回合上下文。

历史记录缺字段时全部按 nullable 兼容读取：拿不到事实的消费者必须表达
unavailable，而不是推测。
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ScoringSnapshotStatus(enum.StrEnum):
    effective = "effective"
    superseded = "superseded"
    undone = "undone"


class RallyScoringSnapshot(Base):
    """有效 `rally_start` 的计分事实封存。

    本表 MUST NOT 引用 `AnalysisRosterSnapshot` / P1–P4 / 分析期端位。
    """

    __tablename__ = "rally_scoring_snapshots"
    __table_args__ = (
        UniqueConstraint("capture_take_id", "action_id", "revision", name="uq_scoring_snapshot_action_revision"),
        Index("idx_scoring_snapshot_take_rally", "capture_take_id", "rally_id"),
        Index("idx_scoring_snapshot_take_status", "capture_take_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    capture_take_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("capture_takes.id", ondelete="RESTRICT"), nullable=False
    )
    # 产生该快照的 start_next_rally action（action ledger 的稳定键）
    action_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # rally_start timeline event id
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 录制期 rally 区间 id（CaptureSegment.id）
    rally_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    server_team: Mapped[str | None] = mapped_column(String(8), nullable=True)
    score_a_before: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_b_before: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    games_won_a_before: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    games_won_b_before: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    scoring_phase: Mapped[str] = mapped_column(String(16), nullable=False, default="rally")
    scoring_ruleset_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    action_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_snapshot_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[ScoringSnapshotStatus] = mapped_column(
        String(16), nullable=False, default=ScoringSnapshotStatus.effective.value
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    superseded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CourtEndConfirmation(Base):
    """用户确认的初始 A/B 端位（Job 级确认一次）。

    `owner_key` 是 `capture_take_id` 或 `video:<videoId>`，让单摄上传与双摄录制
    共用同一张表；重新确认时旧行 `is_effective=False`，保留历史。
    """

    __tablename__ = "court_end_confirmations"
    __table_args__ = (
        Index("idx_court_end_owner_effective", "owner_key", "is_effective"),
        UniqueConstraint("owner_key", "revision", name="uq_court_end_owner_revision"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(128), nullable=False)
    capture_take_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # "end_a" | "end_b"：Team A 位于球场的哪一端
    team_a_end: Mapped[str] = mapped_column(String(16), nullable=False)
    confirmed_at_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_effective: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    confirmed_by: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class AnalysisRosterSnapshot(Base):
    """Job 创建时冻结的分析名册。"""

    __tablename__ = "analysis_roster_snapshots"
    __table_args__ = (
        Index("idx_roster_snapshot_owner", "owner_key", "created_at"),
        Index("idx_roster_snapshot_job", "job_id"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(128), nullable=False)
    capture_take_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    video_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unavailable")
    unavailable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    initial_team_a_end: Mapped[str | None] = mapped_column(String(16), nullable=True)
    entries_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    roster_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class AnalysisRallyContextSet(Base):
    """Job 创建时合成的不可变分析回合上下文集合。"""

    __tablename__ = "analysis_rally_context_sets"
    __table_args__ = (
        Index("idx_rally_context_job", "job_id", "version"),
        Index("idx_rally_context_owner", "owner_key"),
    )

    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    owner_key: Mapped[str] = mapped_column(String(128), nullable=False)
    job_id: Mapped[str] = mapped_column(String(128), nullable=False)
    capture_take_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="unavailable")
    unavailable_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    scoring_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    roster_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    court_end_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    context_set_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    supersedes_context_set_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(UTC))
