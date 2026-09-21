"""分析名册与分析回合上下文的数据契约、provenance 字段与规范化 hash。

本模块是唯一契约来源（后端 pydantic；前端 `src/types/rallyContext.ts` 是它的镜像）。
它不访问数据库，只做三层事实的建模与规范化：

1. `RallyScoringSnapshot` —— 录制期在 `rally_start` 同事务封存的**纯计分事实**，
   显式不得引用名册、P1–P4 或分析期端位。
2. `CourtEndProjection` —— 与计分 reducer 分离的端位投影，由确认的初始端位
   回放有效 `side_change` 得到。
3. `AnalysisRosterSnapshot` / `BootstrapBindingAudit` / `AnalysisRallyContextSnapshot`
   —— 分析期名册与 Job 绑定的回合上下文。

所有 hash 都通过 `canonical_hash()` 计算，保证跨进程、跨重启稳定。
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

# ── schema 版本常量（写进产物，供下游版本判定）──

RALLY_SCORING_SNAPSHOT_SCHEMA = "rally-scoring-snapshot.v1"
COURT_END_PROJECTION_SCHEMA = "court-end-projection.v1"
ANALYSIS_ROSTER_SNAPSHOT_SCHEMA = "analysis-roster-snapshot.v1"
BOOTSTRAP_BINDING_AUDIT_SCHEMA = "bootstrap-binding-audit.v1"
ANALYSIS_RALLY_CONTEXT_SCHEMA = "analysis-rally-context.v1"
ANALYSIS_RALLY_CONTEXT_SET_SCHEMA = "analysis-rally-context-set.v1"

# ── 受控词表 ──

TeamId = Literal["A", "B"]

# 场地端位：产品语义（A 端 / B 端），不是 near/far 的物理半场语义。
CourtEnd = Literal["end_a", "end_b"]

# 名册快照状态。`skipped` 与 `insufficient_candidates` 都是"用户/前置条件不足但分析照跑"，
# 下游必须读到 unavailable reason，而不是被推断出 Team A/B。
RosterSnapshotStatus = Literal["available", "skipped", "insufficient_candidates", "unavailable"]

# bootstrap anchor 到正式 canonical Player 的绑定方法。
BootstrapBindingMethod = Literal[
    "anchor_reacquire",  # 以 anchor 时空邻域重新捕获同一 canonical player
    "partial_reacquire",  # 只在部分帧上稳定关联
    "temporal_fallback",  # 仅靠时间连续性，置信度低但唯一
    "unavailable",  # 无法绑定
]

# formal window 与分析回合上下文的绑定方法，优先级由强到弱。
ContextBindingMethod = Literal[
    "direct_segment_link",  # window 的源 rally segment 直接携带 start_event_id
    "direct_start_event_link",  # window 直接携带 start_event_id
    "unique_temporal_match",  # 合法顺序 + 唯一性 + 容差内的时间匹配
    "unavailable",  # 歧义或无候选
]

CourtEndProjectionStatus = Literal["available", "unavailable"]
RallyContextStatus = Literal["available", "partial", "unavailable"]
RosterConfirmationSource = Literal["manual", "bootstrap_default", "skipped", "backfill"]

# 历史 take 缺字段时使用的稳定 unavailable reason（不得随意改写文案）。
REASON_NO_CAPTURE_TAKE = "no_capture_take_context"
REASON_INITIAL_COURT_END_NOT_CONFIRMED = "initial_court_end_not_confirmed"
REASON_ROSTER_NOT_CONFIRMED = "analysis_roster_not_confirmed"
REASON_ROSTER_SKIPPED_BY_USER = "analysis_roster_skipped_by_user"
REASON_ROSTER_INSUFFICIENT_CANDIDATES = "analysis_roster_insufficient_candidates"
REASON_NO_SCORING_SNAPSHOTS = "no_rally_scoring_snapshots"
REASON_AMBIGUOUS_TEMPORAL_MATCH = "ambiguous_temporal_match"
REASON_NO_TEMPORAL_CANDIDATE = "no_temporal_candidate"
REASON_BOOTSTRAP_BINDING_FAILED = "bootstrap_binding_failed"
REASON_BOOTSTRAP_BINDING_PARTIAL = "bootstrap_binding_partial"


# ── 规范化与 hash ──


def canonical_json(payload: Any) -> str:
    """把任意 payload 规范化为稳定 JSON（键排序、紧凑分隔符、保留中文）。"""
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def canonical_hash(payload: Any) -> str:
    """对规范化 JSON 取 sha256。所有 context hash 都必须走这里。"""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _strip_hash_fields(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if key != "context_hash" and not key.endswith("_set_hash")}


def scoring_snapshot_hash(payload: dict[str, Any]) -> str:
    """计分事实 hash：只覆盖计分事实与来源，不覆盖 supersede 链元数据。"""
    material = {
        "rally_id": payload.get("rally_id"),
        "capture_take_id": payload.get("capture_take_id"),
        "ordinal": payload.get("ordinal"),
        "server_team": payload.get("server_team"),
        "score_a_before": payload.get("score_a_before"),
        "score_b_before": payload.get("score_b_before"),
        "games_won_a_before": payload.get("games_won_a_before"),
        "games_won_b_before": payload.get("games_won_b_before"),
        "scoring_phase": payload.get("scoring_phase"),
        "scoring_ruleset_version": payload.get("scoring_ruleset_version"),
        "action_id": payload.get("action_id"),
        "event_id": payload.get("event_id"),
        "action_revision": payload.get("action_revision"),
    }
    return canonical_hash(material)


def roster_snapshot_hash(payload: dict[str, Any]) -> str:
    """名册 hash：覆盖确认条目与初始端位，不覆盖创建时间等运行期元数据。"""
    material = {
        "owner_key": payload.get("owner_key"),
        "status": payload.get("status"),
        "unavailable_reason": payload.get("unavailable_reason"),
        "initial_team_a_end": payload.get("initial_team_a_end"),
        "entries": [
            {
                "canonical_player_id": entry.get("canonical_player_id"),
                "display_name": entry.get("display_name"),
                "team_id": entry.get("team_id"),
                "source_view_id": entry.get("source_view_id"),
                "anchor_timestamp_ms": entry.get("anchor_timestamp_ms"),
                "anchor_bbox": entry.get("anchor_bbox"),
                "anchor_court_xy": entry.get("anchor_court_xy"),
                "bootstrap_run_id": entry.get("bootstrap_run_id"),
                "bootstrap_model_version": entry.get("bootstrap_model_version"),
                "bootstrap_confidence": entry.get("bootstrap_confidence"),
            }
            for entry in (payload.get("entries") or [])
        ],
    }
    return canonical_hash(material)


def court_end_hash(payload: dict[str, Any]) -> str:
    """端位投影 hash：覆盖投影状态、初始端位与全部端位窗口。"""
    material = {
        "capture_take_id": payload.get("capture_take_id"),
        "status": payload.get("status"),
        "unavailable_reason": payload.get("unavailable_reason"),
        "initial_team_a_end": payload.get("initial_team_a_end"),
        "windows": [
            {
                "effective_from_ms": window.get("effective_from_ms"),
                "team_a_end": window.get("team_a_end"),
                "team_b_end": window.get("team_b_end"),
                "source_action_id": window.get("source_action_id"),
                "source_event_id": window.get("source_event_id"),
            }
            for window in (payload.get("windows") or [])
        ],
    }
    return canonical_hash(material)


def context_hash(payload: dict[str, Any]) -> str:
    """单个分析回合上下文的 hash：由三份来源 hash 与绑定结果共同决定。"""
    material = {
        "job_id": payload.get("job_id"),
        "rally_id": payload.get("rally_id"),
        "status": payload.get("status"),
        "unavailable_reason": payload.get("unavailable_reason"),
        "scoring_hash": payload.get("scoring_hash"),
        "roster_hash": payload.get("roster_hash"),
        "court_end_hash": payload.get("court_end_hash"),
        "binding": {
            "method": (payload.get("binding") or {}).get("method"),
            "source_segment_id": (payload.get("binding") or {}).get("source_segment_id"),
            "source_start_event_id": (payload.get("binding") or {}).get("source_start_event_id"),
            "candidate_count": (payload.get("binding") or {}).get("candidate_count"),
        },
        "server_team": payload.get("server_team"),
        "score_a_before": payload.get("score_a_before"),
        "score_b_before": payload.get("score_b_before"),
        "team_a_end": payload.get("team_a_end"),
        "team_b_end": payload.get("team_b_end"),
        "team_a_players": payload.get("team_a_players"),
        "team_b_players": payload.get("team_b_players"),
    }
    return canonical_hash(material)


def context_set_hash(payload: dict[str, Any]) -> str:
    """context-set hash：Job 侧签名只消费这一个值，逐回合 context hash 参与其中。"""
    material = {
        "job_id": payload.get("job_id"),
        "capture_take_id": payload.get("capture_take_id"),
        "status": payload.get("status"),
        "unavailable_reason": payload.get("unavailable_reason"),
        "scoring_hash": payload.get("scoring_hash"),
        "roster_hash": payload.get("roster_hash"),
        "court_end_hash": payload.get("court_end_hash"),
        "rally_context_hashes": [
            {"rally_id": item.get("rally_id"), "context_hash": item.get("context_hash")}
            for item in (payload.get("rallies") or [])
        ],
    }
    return canonical_hash(material)


# ── 1. 录制期计分事实快照 ──


class RallyScoringSnapshotPayload(BaseModel):
    """有效 `rally_start` 的计分事实封存。

    关键约束：本结构 MUST NOT 携带 `AnalysisRosterSnapshot`、P1–P4、Team A/B 身份或端位。
    它只描述"这一回合以什么发球权和什么比分开始"。
    """

    schema_version: Literal["rally-scoring-snapshot.v1"] = RALLY_SCORING_SNAPSHOT_SCHEMA
    snapshot_id: str
    capture_take_id: str
    # rally_id 指向录制期创建的 rally 区间（CaptureSegment.id）
    rally_id: str
    ordinal: int
    server_team: TeamId | None = None
    score_a_before: int = 0
    score_b_before: int = 0
    games_won_a_before: int = 0
    games_won_b_before: int = 0
    scoring_phase: str = "rally"
    scoring_ruleset_version: str | None = None
    # 来源事实：产生该快照的 start_next_rally action / rally_start event / take revision
    action_id: str
    event_id: str
    action_revision: int
    start_ms: int = 0
    # supersede 链
    revision: int = 1
    supersedes_snapshot_id: str | None = None
    status: Literal["effective", "superseded", "undone"] = "effective"

    @property
    def scoring_hash(self) -> str:
        return scoring_snapshot_hash(self.model_dump(mode="json"))


# ── 2. 端位投影 ──


class CourtEndWindow(BaseModel):
    """自 `effective_from_ms` 起生效的 A/B 端位。"""

    effective_from_ms: int
    team_a_end: CourtEnd
    team_b_end: CourtEnd
    source_action_id: str | None = None
    source_event_id: str | None = None


class CourtEndDiagnostic(BaseModel):
    code: str
    detail: str = ""
    game_ordinal: int | None = None
    timestamp_ms: int | None = None


class CourtEndProjectionPayload(BaseModel):
    """独立端位投影。与 `ScoringState` 完全分离，可按 action ledger 重放。"""

    schema_version: Literal["court-end-projection.v1"] = COURT_END_PROJECTION_SCHEMA
    capture_take_id: str
    status: CourtEndProjectionStatus
    unavailable_reason: str | None = None
    initial_team_a_end: CourtEnd | None = None
    initial_confirmed_at_ms: int | None = None
    windows: list[CourtEndWindow] = Field(default_factory=list)
    diagnostics: list[CourtEndDiagnostic] = Field(default_factory=list)

    @property
    def court_end_hash(self) -> str:
        return court_end_hash(self.model_dump(mode="json"))

    def team_end_at(self, timestamp_ms: int) -> tuple[CourtEnd | None, CourtEnd | None]:
        """返回该时点的 (team_a_end, team_b_end)；投影不可用时返回 (None, None)。"""
        if self.status != "available" or not self.windows:
            return None, None
        current = self.windows[0]
        for window in self.windows:
            if window.effective_from_ms <= timestamp_ms:
                current = window
            else:
                break
        return current.team_a_end, current.team_b_end


# ── 3. 分析期名册与身份连续性 ──


class AnalysisRosterConfirmationEntry(BaseModel):
    """一条 P1–P4 确认记录，含 bootstrap 身份锚点。"""

    canonical_player_id: str
    display_name: str | None = None
    team_id: TeamId | None = None
    source_view_id: str | None = None
    anchor_timestamp_ms: int = 0
    anchor_bbox: list[float] | None = None  # image 坐标 [x1, y1, x2, y2]，单位 px
    anchor_court_xy: list[float] | None = None  # court 坐标 [x, y]，单位 ft
    bootstrap_run_id: str | None = None
    bootstrap_model_version: str | None = None
    bootstrap_confidence: float | None = None


class AnalysisRosterSnapshotPayload(BaseModel):
    """冻结后的分析名册。Job 创建后不得被后续名册编辑改写。"""

    schema_version: Literal["analysis-roster-snapshot.v1"] = ANALYSIS_ROSTER_SNAPSHOT_SCHEMA
    snapshot_id: str
    owner_key: str
    capture_take_id: str | None = None
    video_id: str | None = None
    job_id: str | None = None
    status: RosterSnapshotStatus
    unavailable_reason: str | None = None
    source: RosterConfirmationSource = "manual"
    initial_team_a_end: CourtEnd | None = None
    entries: list[AnalysisRosterConfirmationEntry] = Field(default_factory=list)
    confirmed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def roster_hash(self) -> str:
        return roster_snapshot_hash(self.model_dump(mode="json"))

    def players_for_team(self, team_id: TeamId) -> list[str]:
        return [entry.canonical_player_id for entry in self.entries if entry.team_id == team_id]


class BootstrapBindingAuditEntry(BaseModel):
    """单个 bootstrap anchor 到正式 canonical Player 的绑定结论。"""

    canonical_player_id: str
    bootstrap_run_id: str | None = None
    source_view_id: str | None = None
    anchor_timestamp_ms: int = 0
    anchor_court_xy: list[float] | None = None
    formal_canonical_player_id: str | None = None
    method: BootstrapBindingMethod = "unavailable"
    confidence: float | None = None
    confirmed: bool = False
    reason: str | None = None


class BootstrapBindingAuditPayload(BaseModel):
    schema_version: Literal["bootstrap-binding-audit.v1"] = BOOTSTRAP_BINDING_AUDIT_SCHEMA
    job_id: str
    roster_hash: str
    status: Literal["available", "partial", "unavailable"]
    unavailable_reason: str | None = None
    entries: list[BootstrapBindingAuditEntry] = Field(default_factory=list)

    def binding_hash(self) -> str:
        return canonical_hash(self.model_dump(mode="json"))


# ── 4. Job-bound 分析回合上下文 ──


class ContextBinding(BaseModel):
    """formal window 与分析回合上下文之间的绑定证据。"""

    method: ContextBindingMethod = "unavailable"
    source_segment_id: str | None = None
    source_start_event_id: str | None = None
    candidate_count: int = 0
    diagnostics: list[str] = Field(default_factory=list)


class AnalysisRallyContextRally(BaseModel):
    """一个正式回合的冻结上下文。"""

    rally_id: str
    ordinal: int
    start_ms: int
    end_ms: int | None = None
    status: RallyContextStatus
    unavailable_reason: str | None = None
    scoring_snapshot_id: str | None = None
    scoring_hash: str | None = None
    # 来源 rally_start 事件 id（录制期事实），供正式窗口按事件绑定。
    start_event_id: str | None = None
    server_team: TeamId | None = None
    score_a_before: int | None = None
    score_b_before: int | None = None
    team_a_end: CourtEnd | None = None
    team_b_end: CourtEnd | None = None
    team_a_players: list[str] = Field(default_factory=list)
    team_b_players: list[str] = Field(default_factory=list)
    binding: ContextBinding = Field(default_factory=ContextBinding)
    context_hash: str | None = None


class AnalysisRallyContextSnapshotPayload(BaseModel):
    """Job 创建时合成的不可变回合上下文。该 Job 永远只消费这一份。"""

    schema_version: Literal["analysis-rally-context.v1"] = ANALYSIS_RALLY_CONTEXT_SCHEMA
    context_set_id: str
    job_id: str
    capture_take_id: str | None = None
    status: RallyContextStatus
    unavailable_reason: str | None = None
    scoring_hash: str | None = None
    roster_hash: str | None = None
    court_end_hash: str | None = None
    rallies: list[AnalysisRallyContextRally] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)
    version: int = 1
    supersedes_context_set_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def rally_context(self, rally_id: str) -> AnalysisRallyContextRally | None:
        return next((item for item in self.rallies if item.rally_id == rally_id), None)

    def context_set_hash(self) -> str:
        return context_set_hash(self.model_dump(mode="json"))


# ── 5. bootstrap 预检（受限范围，不启动完整 Pipeline）──


class PlayerBootstrapCandidate(BaseModel):
    """bootstrap 返回的单个球员候选。"""

    canonical_player_id: str
    display_name: str | None = None
    # 候选参考帧在视频中的时间点与画面内 bbox（供人工确认时对照）
    anchor_timestamp_ms: int = 0
    anchor_bbox: list[float] | None = None
    anchor_court_xy: list[float] | None = None
    confidence: float | None = None


class PlayerBootstrapQualityDiagnostic(BaseModel):
    code: str
    detail: str = ""
    severity: Literal["info", "warning", "blocking"] = "info"


class PlayerBootstrapResult(BaseModel):
    """受限 player bootstrap 的响应契约。"""

    schema_version: Literal["player-bootstrap.v1"] = "player-bootstrap.v1"
    status: Literal["available", "insufficient_candidates", "unavailable"]
    unavailable_reason: str | None = None
    owner_key: str
    capture_take_id: str | None = None
    video_id: str | None = None
    bootstrap_run_id: str | None = None
    bootstrap_model_version: str | None = None
    reference_timestamp_ms: int = 0
    # 可直接供确认页展示的源视频参考帧（仅为只读预览，不是分析产物）。
    reference_frame_url: str | None = None
    candidates: list[PlayerBootstrapCandidate] = Field(default_factory=list)
    diagnostics: list[PlayerBootstrapQualityDiagnostic] = Field(default_factory=list)
    # 用户可跳过；跳过不影响普通分析创建。
    skippable: bool = True
    # 后端 `rally_context_enabled` 的镜像：为 false 时提交名册/端位不会冻结任何上下文，
    # 前端据此把该步骤置为"仅提示"而不是让用户误以为已经冻结。
    consumers_enabled: bool = True


class RosterConfirmationRequest(BaseModel):
    """前端在创建 Job 时提交的名册/端位确认（可为跳过）。"""

    skipped: bool = False
    initial_team_a_end: CourtEnd | None = None
    entries: list[AnalysisRosterConfirmationEntry] = Field(default_factory=list)
    bootstrap_run_id: str | None = None
    bootstrap_model_version: str | None = None
