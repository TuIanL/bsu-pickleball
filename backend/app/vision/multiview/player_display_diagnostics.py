"""player-display-diagnostics.v1 —— 逐球员逐 stage 显示漏斗正式产物契约。

joint_tracking_v2 模式下，对每个 `(roster confirmed player, available view,
canonical tick)` 生成一行紧凑显示诊断，回答"该球员此刻为何这样显示 / 为何不显示"。

v1 漏斗边界（评审收敛）：
- 起点 = post-tracker/post-lock eligible detection（`ViewFrameResult.frame_detections`
  是 `PlayerLockManager` 产出 `eligible_track_ids` 后才构建的检测框，非 raw YOLO）；
- raw detector / ROI filter / tracker / lock rejection 归因不属于本产物；
- 分层断裂状态独立记录：`eligible_detection_present / position_present /
  court_position_present / projection_status / projection_confidence /
  formal_observation_emitted`（前两项必须可区分）；
- expected region 只来自 pre-tick global prediction（无 hindsight bias），
  非 `available` 时 `eligible_detections_in_expected_gate` 为 `null` 而非 `0`；
- 产物不依赖 `joint_debug_trace`，`debugTraceEnabled=false` 时仍生成；
- 产物 `player_id` 直接为 canonical `Player_N`（artifact 层不暴露 global id）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from math import isfinite
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from app.vision.multiview.court_frame import CourtOrientation, canonical_to_local

logger = logging.getLogger(__name__)

PLAYER_DISPLAY_DIAGNOSTICS_SCHEMA = "player-display-diagnostics.v1"

ExpectedRegionStatus = Literal[
    "available",
    "prediction_unavailable",
    "uncertainty_too_high",
    "target_geometry_unavailable",
]


@dataclass(frozen=True)
class ExpectedPlayerRegion:
    """pre-tick prediction 投影的 expected region（guidance 与 diagnostics 共享）。"""

    status: ExpectedRegionStatus
    expected_image_position: tuple[float, float] | None = None
    roi: tuple[float, float, float, float] | None = None  # (x1, y1, x2, y2)
    radius_px: float | None = None


def build_expected_player_region(
    *,
    predicted_canonical_position: tuple[float, float] | None,
    uncertainty_ft: float | None,
    orientation: CourtOrientation | None,
    inverse_homography: Any,
    frame_width: int | None,
    frame_height: int | None,
    policy: Any,
    max_uncertainty_ft: float | None = None,
) -> ExpectedPlayerRegion:
    """构建 expected player region（guidance 与 diagnostics 共用同一 ROI 规则）。

    ROI 半径：`base_roi_margin_px + uncertainty × uncertainty_to_px_scale`，
    cap `max_roi_margin_px`（与 guidance 现有规则一致，抽取为共享纯函数）。

    仅当预测位置、geometry 均可用且 uncertainty 未超限时返回 `available`；
    否则返回对应 `status`（调用方据此把计数置为 `null` 而非 `0`）。
    """
    if predicted_canonical_position is None:
        return ExpectedPlayerRegion(status="prediction_unavailable")
    uncertainty = uncertainty_ft if uncertainty_ft is not None else 0.0
    limit = max_uncertainty_ft if max_uncertainty_ft is not None else getattr(policy, "max_uncertainty_ft", 8.0)
    if uncertainty > limit:
        return ExpectedPlayerRegion(status="uncertainty_too_high")
    if orientation is None or inverse_homography is None or not frame_width or not frame_height:
        return ExpectedPlayerRegion(status="target_geometry_unavailable")

    from app.vision.multiview.guidance import court_to_image_single

    px, py = predicted_canonical_position
    lx, ly = canonical_to_local(px, py, orientation)
    ix, iy = court_to_image_single((lx, ly), inverse_homography)
    base_margin = float(getattr(policy, "base_roi_margin_px", 40.0))
    px_scale = float(getattr(policy, "uncertainty_to_px_scale", 12.0))
    max_margin = float(getattr(policy, "max_roi_margin_px", 160.0))
    r_px = min(base_margin + uncertainty * px_scale, max_margin)
    x1 = max(0.0, ix - r_px)
    y1 = max(0.0, iy - r_px)
    x2 = min(float(frame_width), ix + r_px)
    y2 = min(float(frame_height), iy + r_px)
    return ExpectedPlayerRegion(
        status="available",
        expected_image_position=(ix, iy),
        roi=(x1, y1, x2, y2),
        radius_px=r_px,
    )


class PlayerDisplayDiagnosticsRow(BaseModel):
    """一个 `(canonical_tick, player_id, view_id)` 的显示漏斗行。"""

    canonical_tick: int = Field(ge=0)
    timestamp_ms: float = Field(ge=0)
    player_id: str = Field(min_length=1)  # canonical Player_N（artifact 层）
    view_id: str = Field(min_length=1)
    frame_status: str = "unavailable"
    # expected region（pre-tick prediction 投影）
    expected_region_status: ExpectedRegionStatus = "prediction_unavailable"
    expected_image_position: list[float] | None = Field(default=None, min_length=2, max_length=2)
    # 落在 expected region 门内的 eligible detection 数量；region 不可用时为 null（非 0）
    eligible_detections_in_expected_gate: int | None = Field(default=None, ge=0)
    # 分层断裂状态（独立记录，MUST NOT 合并）
    eligible_detection_present: bool = False
    position_present: bool = False
    court_position_present: bool = False
    projection_status: str | None = None
    projection_confidence: float | None = Field(default=None, ge=0, le=1)
    formal_observation_emitted: bool = False
    formal_local_observation: bool = False
    local_player_id: str | None = None
    tracking_status: str | None = None
    # association
    global_associated: bool = False
    association_reason: str | None = None
    # binding
    binding_visibility: str | None = None
    # 连续 available global-view miss 计数（fast path 触发依据；缺省 0）
    available_miss_streak: int = Field(default=0, ge=0)
    # guidance（只读 GuidanceDecision）
    guidance_status: str | None = None  # generated | not_eligible | None
    guidance_skip_reason: str | None = None
    guidance_trigger_source: str | None = None  # visibility_age | available_miss | None
    # same-tick usable-candidate recovery（B-Phase-2）
    pre_association_status: str | None = None  # candidate_found | projection_failed | ambiguous | not_assessed
    same_tick_guidance_status: str | None = None  # generated | not_generated_no_cross_candidate | not_needed_observed | geometry_unavailable
    # fix-multiview-cam1-bootstrap-4player D4：reference 槽位身份冲突显式观测
    # （两个 global 抢同一 (view_id, view_player_id)；缺省 false 兼容旧产物）
    roster_conflict: bool = False

    @field_validator("expected_image_position")
    @classmethod
    def _validate_point(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        point = [float(item) for item in value]
        if not all(isfinite(item) for item in point):
            raise ValueError("expected_image_position must contain only finite values")
        return point


class PlayerDisplayDiagnosticsArtifact(BaseModel):
    """player-display-diagnostics.v1 正式产物。"""

    schema_version: Literal["player-display-diagnostics.v1"] = PLAYER_DISPLAY_DIAGNOSTICS_SCHEMA
    job_id: str
    video_id: str | None = None
    reference_view_id: str
    status: Literal["available", "unavailable", "failed"] = "available"
    detail: str = ""
    rows: list[PlayerDisplayDiagnosticsRow] = Field(default_factory=list)


def validate_player_display_diagnostics(payload: object) -> None:
    """校验契约 payload；不合法抛 ValueError。"""
    if not isinstance(payload, dict):
        raise ValueError("player display diagnostics must be an object")
    if payload.get("schema_version") != PLAYER_DISPLAY_DIAGNOSTICS_SCHEMA:
        raise ValueError(f"expected {PLAYER_DISPLAY_DIAGNOSTICS_SCHEMA}")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ValueError("player display diagnostics rows must be a list")
    seen: set[tuple[int, str, str]] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"diagnostics row {index} must be an object")
        player_id = str(row.get("player_id", ""))
        if not (player_id.startswith("Player_") and player_id[len("Player_"):].isdigit()):
            raise ValueError(f"diagnostics row {index} player_id {player_id!r} must be canonical Player_N")
        key = (int(row.get("canonical_tick", -1)), player_id, str(row.get("view_id", "")))
        if key in seen:
            raise ValueError(
                f"diagnostics row {index} duplicate (tick, player, view) {key!r} "
                "(同一 tick 同一 Player_N 同一 view 最多一行)"
            )
        seen.add(key)
        # expected region 不可用 => 计数必须为 null（MUST NOT 写 0）
        region_status = row.get("expected_region_status")
        if region_status != "available" and row.get("eligible_detections_in_expected_gate") is not None:
            raise ValueError(
                f"diagnostics row {index} expected_region_status={region_status!r} but "
                "eligible_detections_in_expected_gate must be null"
            )


def build_player_display_diagnostics_payload(
    *,
    job_id: str,
    video_id: str | None,
    reference_view_id: str,
    rows: list[PlayerDisplayDiagnosticsRow],
    status: str = "available",
    detail: str = "",
) -> dict[str, object]:
    """构造可序列化的契约 payload（validator 校验通过后返回）。"""
    payload: dict[str, object] = {
        "schema_version": PLAYER_DISPLAY_DIAGNOSTICS_SCHEMA,
        "job_id": job_id,
        "video_id": video_id,
        "reference_view_id": reference_view_id,
        "status": status,
        "detail": detail,
        "rows": [row.model_dump(mode="json") for row in rows],
    }
    validate_player_display_diagnostics(payload)
    return payload


# ---------------------------------------------------------------------------
# 漏斗行构建器（1.2）
# ---------------------------------------------------------------------------


def build_display_diagnostics_rows(
    *,
    canonical_tick: int,
    timestamp_ms: float,
    reference_view_id: str,
    view_results: dict[str, Any],
    frame_status: dict[str, str],
    predictions: dict[str, tuple[float, float, float]],
    view_geometry: dict[str, dict[str, Any]],
    policy: Any,
    roster: list[dict[str, Any]],
    association_decisions: list[Any],
    guidance_decisions: list[Any],
    same_tick_guidance_by_view: dict[str, list[Any]] | None = None,
    roster_conflicts: dict[tuple[str, str], int] | None = None,
) -> list[PlayerDisplayDiagnosticsRow]:
    """对一个 canonical tick 构建 `roster confirmed player × available view` 的漏斗行。

    输入：
    - `view_results`：`{view_id: ViewFrameResult}`（复用运行时已暴露信息，不新增插桩）；
    - `predictions`：pre-tick global prediction（`{gid: (x, y, uncertainty)}`）；
    - `view_geometry`：`{view_id: {orientation, inverse_homography, frame_width,
      frame_height, available}}`；
    - `roster`：当前 roster 快照（`{global_player_id, player_id, lifecycle,
      bindings: {view_id: {view_player_id, visibility}}}`）；
    - `association_decisions`：`associator.last_tick_decisions`（只读）；
    - `guidance_decisions`：`guidance_generator.last_decisions`（只读）。

    输出仅覆盖 `roster_status == "confirmed"` 的 player × `frame_status ==
    "available"` 的 view；不可用组合不生成行（体积控制）。
    """
    rows: list[PlayerDisplayDiagnosticsRow] = []
    guidance_by_key: dict[tuple[str, str], Any] = {
        (d.global_player_id, d.target_view): d for d in guidance_decisions
    }
    assoc_by_key: dict[tuple[str, str], Any] = {}
    for d in association_decisions:
        assoc_by_key.setdefault((d.view_id, d.observation_key), d)

    for player in roster:
        gid = str(player.get("global_player_id", ""))
        player_id = str(player.get("player_id", "") or "")
        if not (player_id.startswith("Player_") and player_id[len("Player_"):].isdigit()):
            continue  # 未稳定到 canonical Player_N（reference binding 缺失）不生成行
        if str(player.get("lifecycle", "")) != "confirmed":
            continue
        bindings = player.get("bindings", {}) or {}
        prediction = predictions.get(gid)

        for view_id, view_result in view_results.items():
            if frame_status.get(view_id) != "available":
                continue
            geometry = view_geometry.get(view_id, {})
            binding = bindings.get(view_id) or {}

            # expected region（只来自 pre-tick prediction；无 hindsight bias）
            region = build_expected_player_region(
                predicted_canonical_position=(
                    (prediction[0], prediction[1]) if prediction is not None else None
                ),
                uncertainty_ft=(prediction[2] if prediction is not None else None),
                orientation=geometry.get("orientation"),
                inverse_homography=geometry.get("inverse_homography"),
                frame_width=geometry.get("frame_width"),
                frame_height=geometry.get("frame_height"),
                policy=policy,
            )
            expected_image_position = (
                list(region.expected_image_position) if region.expected_image_position is not None else None
            )

            # eligible detection 计数：post-lock frame_detections 落在 expected region 门内
            gate_count: int | None = None
            if region.status == "available" and region.roi is not None:
                x1, y1, x2, y2 = region.roi
                gate_count = 0
                for det in getattr(view_result, "frame_detections", []) or []:
                    fp = getattr(det, "image_footpoint", None)
                    if fp is None:
                        continue
                    fx, fy = float(fp[0]), float(fp[1])
                    if x1 <= fx <= x2 and y1 <= fy <= y2:
                        gate_count += 1

            # 分层断裂状态：优先按该 player 的 local identity 匹配 track
            view_player_id = binding.get("view_player_id")
            eligible_present = False
            position_present = False
            court_present = False
            projection_status: str | None = None
            projection_confidence: float | None = None
            matched_track: int | None = None
            for det in getattr(view_result, "frame_detections", []) or []:
                det_pid = getattr(det, "player_id", None) or getattr(det, "view_player_id", None)
                if det_pid is not None and view_player_id is not None and det_pid != view_player_id:
                    continue
                track_id = getattr(det, "track_id", None)
                if track_id is None:
                    continue
                eligible_present = True
                matched_track = int(track_id)
                break
            if matched_track is not None:
                for pos in getattr(view_result, "frame_positions", []) or []:
                    if int(pos.track_id) != matched_track:
                        continue
                    position_present = True
                    court_present = pos.court_position is not None
                    projection_status = getattr(pos, "projection_status", None)
                    projection_confidence = getattr(pos, "projection_confidence", None)
                    break

            # formal observation emitted：view 内存在该 player 的正式观测（court_position 非空）
            formal_emitted = False
            local_player_id = binding.get("view_player_id")
            tracking_status = None
            for obs in _collect_observations(view_result):
                obs_pid = getattr(obs, "view_player_id", None)
                if obs_pid and view_player_id and obs_pid != view_player_id:
                    continue
                formal_emitted = True
                tracking_status = getattr(obs, "tracking_status", None)
                break

            # association / guidance 决策（只读）
            assoc_decision = assoc_by_key.get((view_id, str(local_player_id or "")))
            global_associated = False
            association_reason: str | None = None
            if assoc_decision is not None:
                global_associated = assoc_decision.global_id is not None
                association_reason = assoc_decision.reason
            elif local_player_id:
                # 无匹配决策（观测未进入 association 输入）→ 归因 formal 层
                association_reason = "no_association_input"
            guidance_decision = guidance_by_key.get((gid, view_id))
            guidance_status = None
            guidance_skip_reason = None
            guidance_trigger_source = None
            if guidance_decision is not None:
                guidance_status = guidance_decision.status
                guidance_skip_reason = guidance_decision.reason
                guidance_trigger_source = getattr(guidance_decision, "trigger_source", None)

            # same-tick usable-candidate recovery（B-Phase-2）：只读呈现
            pre_association_status: str | None = None
            same_tick_guidance_status: str | None = None
            if same_tick_guidance_by_view:
                same_tick_guidances = same_tick_guidance_by_view.get(view_id) or []
                if any(
                    g.expected_global_player_id == gid or g.global_player_id == gid
                    for g in same_tick_guidances
                ):
                    same_tick_guidance_status = "generated"
                elif formal_emitted or global_associated:
                    same_tick_guidance_status = "not_needed_observed"
                else:
                    same_tick_guidance_status = "not_generated_no_cross_candidate"
                pre_association_status = (
                    "candidate_found" if eligible_present and court_present
                    else "projection_failed" if eligible_present else "not_assessed"
                )

            rows.append(
                PlayerDisplayDiagnosticsRow(
                    canonical_tick=canonical_tick,
                    timestamp_ms=timestamp_ms,
                    player_id=player_id,
                    view_id=view_id,
                    frame_status=frame_status.get(view_id, "unavailable"),
                    expected_region_status=region.status,
                    expected_image_position=expected_image_position,
                    eligible_detections_in_expected_gate=gate_count,
                    eligible_detection_present=eligible_present,
                    position_present=position_present,
                    court_position_present=court_present,
                    projection_status=projection_status,
                    projection_confidence=projection_confidence,
                    formal_observation_emitted=formal_emitted,
                    formal_local_observation=formal_emitted,
                    local_player_id=local_player_id,
                    tracking_status=tracking_status,
                    global_associated=global_associated,
                    association_reason=association_reason,
                    binding_visibility=binding.get("visibility"),
                    available_miss_streak=int(binding.get("available_miss_streak") or 0),
                    guidance_status=guidance_status,
                    guidance_skip_reason=guidance_skip_reason,
                    guidance_trigger_source=guidance_trigger_source,
                    pre_association_status=pre_association_status,
                    same_tick_guidance_status=same_tick_guidance_status,
                    # fix-multiview-cam1-bootstrap-4player D4：reference 槽位冲突显式观测
                    roster_conflict=bool(
                        roster_conflicts and (view_id, view_player_id) in roster_conflicts
                    ),
                )
            )
    # fix-multiview-player-identity T1 收尾：同一 (player_id, view_id) 在 roster 快照中出现
    # 多次（两个 global 绑定同一 Player_N 的身份冲突）时，保留首行去重，避免 validator
    # 抛 duplicate 导致整个产物 failed。身份冲突本身仍可由保留行的 binding 字段观测。
    seen_keys: set[tuple[str, str]] = set()
    deduped: list[PlayerDisplayDiagnosticsRow] = []
    for row in rows:
        key = (row.player_id, row.view_id)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(row)
    return deduped


def _collect_observations(view_result: Any) -> list[Any]:
    """收集 ViewFrameResult 中的球场观测（frame_positions 已是 formal observation 载体）。"""
    # frame_positions 带 court_position 的即正式观测；此处以它为 formal observation 证据
    return [
        pos for pos in getattr(view_result, "frame_positions", []) or []
        if getattr(pos, "court_position", None) is not None
    ]

