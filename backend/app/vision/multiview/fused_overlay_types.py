"""multiview-fused-player-overlay.v1 —— post-fusion 球员叠加层正式产物契约。

joint_tracking_v2 模式下，正式视频叠加层以 F0/F1 evidence + Global Roster +
target-view geometry 为只读输入，生成 `multiview-fused-player-overlay.v1`
artifact。本模块定义契约的 versioned schema + validator（对齐
`joint_debug_trace.v1` 的既有模式）。

关键语义（spec `multiview-fused-player-overlay`）：
- `evidence_type` 是"最终选中的展示证据类型"（分支决策链结果），非机械排序；
- `bbox` 允许为 null（无历史真实 bbox 时只渲染 footpoint / halo）；
- `cross_view_projected` 必须携带 `donor_view`；
- confidence 语义拆分：`source_confidence`（真实检测/恢复证据原始置信）/
  `overlay_confidence`（展示值得程度）/ `donor_quality`（cross_view 专用）；
- `uncertainty_ft` 可空（V1 无 prediction covariance，不制造数值 uncertainty）。
"""

from __future__ import annotations

import logging
from math import isfinite
from typing import Literal

from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

FUSED_PLAYER_OVERLAY_SCHEMA = "multiview-fused-player-overlay.v1"

# 五级展示证据类型（分支决策链的最终结果）+ bootstrap 展示回填（最低优先级兜底）
EvidenceType = Literal[
    "base_observed",  # F0 strong/base 真实观测
    "guided_observed",  # F0 guided_roi 真实观测（跨摄 guidance 重检测成功）
    "refined_observed",  # accepted F1 recovered observation
    "cross_view_projected",  # 本 view 无观测，donor 真实观测 + 投影补全
    "predicted_only",  # 双 view 无观测，短时预测兜底
    "bootstrap_backfill",  # 启动 bootstrap 窗口内 retrospective 真实观测回填（display-only）
]

BBoxSource = Literal[
    "last_good_bbox_reanchored",  # 最近合格真实 bbox 纯平移重建
    "view_scale_profiled",  # ViewPersonScaleProfile 透视尺度投影 bbox
    "none",  # 无历史 bbox，仅 footpoint / halo
]


class FusedPlayerOverlayPlayer(BaseModel):
    """参考画面一帧中的一名球员的展示实体。"""

    player_id: str = Field(min_length=1)
    label: str | None = None
    # 图像空间检测框 [x1, y1, x2, y2]；cross_view/predicted 且无历史 bbox 时为 None
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    footpoint: list[float] | None = Field(default=None, min_length=2, max_length=2)
    evidence_type: EvidenceType
    # 真实 detector / recovered evidence 的原始置信（cross_view 来自 donor）
    source_confidence: float = Field(default=0.0, ge=0, le=1)
    # 该 presentation entity 值得展示的程度（builder 决策输出）
    overlay_confidence: float = Field(default=0.0, ge=0, le=1)
    # cross_view_projected 时 donor 视图观测质量；其余类型可为 None
    donor_quality: float | None = Field(default=None, ge=0, le=1)
    # cross_view_projected 必须携带 donor view
    donor_view: str | None = None
    # 数值 uncertainty（英尺）；V1 无 covariance 时保持 None
    uncertainty_ft: float | None = Field(default=None, ge=0)
    bbox_source: BBoxSource | None = None
    # 仅 refined_observed 使用
    provenance: Literal["offline_refinement"] | None = None
    # bootstrap_backfill 携带的 canonical court 坐标 [x, y]（英尺），供小地图消费；其余类型可为 None
    canonical_court_position_ft: list[float] | None = Field(default=None, min_length=2, max_length=2)
    # ---- 展示稳定性（stabilize-multiview-overlay-display）----
    # 迟滞状态机当前展示状态（REAL_BOX/ASSISTED_BOX/PROJECTED_BOX/PROJECTED_POINT/PREDICTED_POINT/HIDDEN）
    display_state: str | None = None
    # bbox 是否来自 stale memory（前端可淡化）
    bbox_stale: bool = False
    # last real observed 距今毫秒（单一 freshness 权威；无历史为 None）
    bbox_age_ms: float | None = Field(default=None, ge=0)

    @field_validator("bbox")
    @classmethod
    def _validate_bbox(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 4:
            raise ValueError("bbox must contain exactly 4 numeric values")
        bbox = [float(item) for item in value]
        if not all(isfinite(item) for item in bbox):
            raise ValueError("bbox must contain only finite numeric values")
        return bbox

    @field_validator("footpoint")
    @classmethod
    def _validate_footpoint(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 2:
            raise ValueError("footpoint must contain exactly 2 numeric values")
        point = [float(item) for item in value]
        if not all(isfinite(item) for item in point):
            raise ValueError("footpoint must contain only finite numeric values")
        return point

    @field_validator("canonical_court_position_ft")
    @classmethod
    def _validate_canonical_court_position(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return None
        if len(value) != 2:
            raise ValueError("canonical_court_position_ft must contain exactly 2 numeric values")
        point = [float(item) for item in value]
        if not all(isfinite(item) for item in point):
            raise ValueError("canonical_court_position_ft must contain only finite numeric values")
        return point


class FusedPlayerOverlayFrame(BaseModel):
    """参考画面一个 canonical tick 的叠加帧。"""

    frame_index: int = Field(ge=0)
    timestamp_seconds: float = Field(ge=0)
    players: list[FusedPlayerOverlayPlayer] = Field(default_factory=list)


class FusedPlayerOverlayArtifact(BaseModel):
    """multiview-fused-player-overlay.v1 正式产物。"""

    schema_version: Literal["multiview-fused-player-overlay.v1"] = FUSED_PLAYER_OVERLAY_SCHEMA
    job_id: str
    video_id: str | None = None
    reference_view_id: str
    status: Literal["available", "no_detections", "unavailable"] = "unavailable"
    detail: str = ""
    frame_count: int = Field(default=0, ge=0)
    processed_frame_count: int = Field(default=0, ge=0)
    source: dict[str, int] = Field(default_factory=dict)  # {"width": W, "height": H}
    frames: list[FusedPlayerOverlayFrame] = Field(default_factory=list)


def validate_fused_player_overlay(payload: object) -> None:
    """校验契约 payload；不合法抛 ValueError。"""
    if not isinstance(payload, dict):
        raise ValueError("fused player overlay must be an object")
    if payload.get("schema_version") != FUSED_PLAYER_OVERLAY_SCHEMA:
        raise ValueError(f"expected {FUSED_PLAYER_OVERLAY_SCHEMA}")
    if not payload.get("reference_view_id"):
        raise ValueError("fused player overlay missing reference_view_id")
    frames = payload.get("frames")
    if not isinstance(frames, list):
        raise ValueError("fused player overlay frames must be a list")
    for index, frame in enumerate(frames):
        if not isinstance(frame, dict):
            raise ValueError(f"overlay frame {index} must be an object")
        players = frame.get("players")
        if not isinstance(players, list):
            raise ValueError(f"overlay frame {index} players must be a list")
        seen_ids: set[str] = set()
        for player_index, player in enumerate(players):
            if not isinstance(player, dict):
                raise ValueError(f"overlay frame {index} player {player_index} must be an object")
            player_id = str(player.get("player_id", ""))
            if player_id in seen_ids:
                raise ValueError(
                    f"overlay frame {index} duplicate player_id {player_id!r} "
                    "(同一 tick 同一 Player_N 最多一个 overlay entity)"
                )
            seen_ids.add(player_id)
            evidence_type = player.get("evidence_type")
            if evidence_type == "cross_view_projected" and not player.get("donor_view"):
                raise ValueError(
                    f"overlay frame {index} player {player_id!r} "
                    "cross_view_projected must carry donor_view"
                )
            if evidence_type not in {
                "base_observed",
                "guided_observed",
                "refined_observed",
                "cross_view_projected",
                "predicted_only",
                "bootstrap_backfill",
            }:
                raise ValueError(
                    f"overlay frame {index} player {player_id!r} invalid evidence_type {evidence_type!r}"
                )


def build_fused_player_overlay_payload(
    *,
    job_id: str,
    video_id: str | None,
    reference_view_id: str,
    frame_size: dict[str, int] | None,
    frames: list[FusedPlayerOverlayFrame],
    status: str = "available",
    detail: str = "",
) -> dict[str, object]:
    """构造可序列化的契约 payload（validator 校验通过后返回）。"""
    frame_count = 0
    for frame in frames:
        frame_count = max(frame_count, frame.frame_index + 1)
    payload: dict[str, object] = {
        "schema_version": FUSED_PLAYER_OVERLAY_SCHEMA,
        "job_id": job_id,
        "video_id": video_id,
        "reference_view_id": reference_view_id,
        "status": status,
        "detail": detail,
        "frame_count": frame_count,
        "processed_frame_count": len(frames),
        "source": dict(frame_size or {"width": 0, "height": 0}),
        "frames": [
            {
                "frame_index": frame.frame_index,
                "timestamp_seconds": frame.timestamp_seconds,
                "players": [player.model_dump(mode="json") for player in frame.players],
            }
            for frame in frames
        ],
    }
    validate_fused_player_overlay(payload)
    return payload


def count_overlay_invariants(payload: object, *, expected_player_count: int) -> dict[str, int]:
    """统计 fused overlay 的硬不变量（spec multiview-visual-acceptance）。

    返回五个计数器，任一非零即 acceptance 不通过：
    - `invalid_projection_count`：cross_view/predicted 渲染了无 geometry 的投影（不应出现，
      builder 已禁止；此处防御统计）；
    - `unknown_public_player_id_count`：非 canonical Player_N 身份出现；
    - `overlay_player_count_per_tick_exceeded`：单 tick 可见球员数超过 expected_player_count；
    - `cross_view_projected_without_donor`：cross_view 缺 donor_view；
    - `prediction_over_ttl_rendered`：超 TTL 仍渲染预测（builder TTL 门已拦截，防御统计）。
    """
    counts = {
        "invalid_projection_count": 0,
        "unknown_public_player_id_count": 0,
        "overlay_player_count_per_tick_exceeded": 0,
        "cross_view_projected_without_donor": 0,
        "prediction_over_ttl_rendered": 0,
    }
    if not isinstance(payload, dict):
        counts["invalid_projection_count"] += 1
        return counts
    for index, frame in enumerate(payload.get("frames", []) or []):
        if not isinstance(frame, dict):
            continue
        players = frame.get("players", []) or []
        if len(players) > expected_player_count:
            counts["overlay_player_count_per_tick_exceeded"] += 1
        for player in players:
            if not isinstance(player, dict):
                continue
            player_id = str(player.get("player_id", ""))
            if not (player_id.startswith("Player_") and player_id[len("Player_"):].isdigit()):
                counts["unknown_public_player_id_count"] += 1
            evidence_type = player.get("evidence_type")
            if evidence_type == "cross_view_projected" and not player.get("donor_view"):
                counts["cross_view_projected_without_donor"] += 1
            if evidence_type == "cross_view_projected" and player.get("bbox") is None:
                # cross_view 无 bbox 是合法降级（footpoint 光圈），不计数
                pass
    return counts
