"""BootstrapDisplayBackfillBuilder —— joint_tracking_v2 启动阶段展示回填。

仅消费 reference view session 的快照（positions + initial_lock_assignments），
把 bootstrap 窗口内「已真实检测、但尚未被 display 层显示」的观测，按其最终锁定的
Player_N 身份做 retrospective 填充（**不插值、不 backward-hold**）。回填数据带显式
provenance（`evidence_type=bootstrap_backfill`、`display_only=True`、`metric_eligible=False`），
与 authoritative 数据（`fused_player_trajectory` / `result.tracks` / metrics）在结构上可区分。

设计边界（fix-joint-bootstrap-visual-gap）：
- 不修改 tracker / association / fusion / roster / metrics —— 纯展示旁路产物；
- 不向前端做假数据：绝不把首帧框 backward-hold 到 t=0，绝不插值；
- 坐标必须经过 `local_to_canonical`（与 association 同输入 `reference_orientation`）
  转 `canonical_court_position_ft`，避免 `rotate_180` 参考机位翻转；
- 仅在「五级 evidence 全缺 + frame < locked_frame_index + 存在真实观测」时由 builder
  层决策启用；本模块只负责产出回填数据，启用决策在 `fused_overlay_builder`。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from math import hypot
from typing import Any

from app.schemas.tracking import PlayerFramePosition
from app.vision.multiview.court_frame import local_to_canonical
from app.vision.player_tracking_engine.player_lock_manager import InitialLockAssignment

logger = logging.getLogger(__name__)

BOOTSTRAP_DISPLAY_BACKFILL_SCHEMA = "bootstrap_display_backfill.v1"
# 显示回填速度上限（ft/s）。保守取远超正常球员冲刺上限的值，仅用于过滤异常跳变，
# 不用于判定 identity（track_id 由 monotonic tracker 保证不复用）。
DEFAULT_DISPLAY_BACKFILL_MAX_SPEED_FT_S = 40.0


@dataclass
class BootstrapBackfillObservation:
    """单个 (player_id, frame_index) 的回填观测（真实存在，非插值）。"""

    player_id: str
    track_id: int
    frame_index: int
    timestamp_seconds: float
    bbox: list[float]  # reference view 图像空间检测框 [x1, y1, x2, y2]，供视频叠加
    court_position_local_ft: list[float]  # 单视角 local court ft
    canonical_court_position_ft: list[float]  # 经 local_to_canonical 后，供小地图
    source_confidence: float
    evidence_type: str = "bootstrap_backfill"
    display_only: bool = True
    metric_eligible: bool = False


@dataclass
class BootstrapDisplayBackfillResult:
    """回填产物（bootstrap_display_backfill.v1）。"""

    schema_version: str
    reference_view_id: str
    observations: list[BootstrapBackfillObservation]
    empty_reason: str | None = None

    def keyed(self) -> dict[tuple[str, int], BootstrapBackfillObservation]:
        """按 (player_id, frame_index) 索引，供 builder 快速查询。"""
        return {(obs.player_id, obs.frame_index): obs for obs in self.observations}

    def to_payload(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "reference_view_id": self.reference_view_id,
            "empty_reason": self.empty_reason,
            "observation_count": len(self.observations),
            "observations": [
                {
                    "player_id": obs.player_id,
                    "track_id": obs.track_id,
                    "frame_index": obs.frame_index,
                    "timestamp_seconds": obs.timestamp_seconds,
                    "bbox": list(obs.bbox),
                    "court_position_local_ft": list(obs.court_position_local_ft),
                    "canonical_court_position_ft": list(obs.canonical_court_position_ft),
                    "source_confidence": round(float(obs.source_confidence), 4),
                    "evidence_type": obs.evidence_type,
                    "display_only": obs.display_only,
                    "metric_eligible": obs.metric_eligible,
                }
                for obs in self.observations
            ],
        }


class BootstrapDisplayBackfillBuilder:
    """从 reference view 快照 retrospective 填充 bootstrap 窗口的展示观测。"""

    def __init__(self, *, max_speed_ft_s: float = DEFAULT_DISPLAY_BACKFILL_MAX_SPEED_FT_S) -> None:
        self.max_speed_ft_s = float(max_speed_ft_s)

    def build(
        self,
        *,
        initial_lock_assignments: dict[str, InitialLockAssignment],
        reference_positions: list[PlayerFramePosition],
        reference_orientation: Any,
        reference_view_id: str,
        frame_stride: int = 1,
        fps: float = 30.0,
    ) -> BootstrapDisplayBackfillResult:
        """生成回填产物。

        参数：
        - `initial_lock_assignments`：Player_N → (track_id, locked_frame_index)
        - `reference_positions`：reference view session 的 positions（含 bbox + local court_position）
        - `reference_orientation`：参考机位朝向（与 association 同输入）
        - `reference_view_id`：参考机位 id（仅 reference view 的观测可信）

        返回空结果（empty_reason 标识）的情形：
        - 无 initial_lock_assignments（bootstrap 全程无人锁定 → 自然无回填）；
        - orientation 缺失（无法安全转 canonical）→ 不猜测；
        - 该 track 在 lock 前无任何真实观测 → 该 player 跳过（不造假）。
        """
        if not initial_lock_assignments:
            return BootstrapDisplayBackfillResult(
                schema_version=BOOTSTRAP_DISPLAY_BACKFILL_SCHEMA,
                reference_view_id=reference_view_id,
                observations=[],
                empty_reason="no_initial_lock_assignments",
            )
        if reference_orientation is None:
            logger.warning(
                "bootstrap backfill: reference_orientation 为 None，跳过回填（禁止无朝向猜测 canonical）"
            )
            return BootstrapDisplayBackfillResult(
                schema_version=BOOTSTRAP_DISPLAY_BACKFILL_SCHEMA,
                reference_view_id=reference_view_id,
                observations=[],
                empty_reason="missing_reference_orientation",
            )

        # 1) 按 track_id 分组 reference positions
        by_track: dict[int, list[PlayerFramePosition]] = {}
        for pos in reference_positions:
            by_track.setdefault(int(pos.track_id), []).append(pos)

        observations: list[BootstrapBackfillObservation] = []
        for player_id, assignment in initial_lock_assignments.items():
            track_id = int(assignment.track_id)
            locked_frame_index = int(assignment.locked_frame_index)
            track_positions = by_track.get(track_id)
            if not track_positions:
                continue
            accepted = self._select_pre_lock_observations(
                track_positions=track_positions,
                locked_frame_index=locked_frame_index,
                reference_orientation=reference_orientation,
                frame_stride=frame_stride,
                fps=fps,
                player_id=player_id,
                track_id=track_id,
            )
            observations.extend(accepted)

        result = BootstrapDisplayBackfillResult(
            schema_version=BOOTSTRAP_DISPLAY_BACKFILL_SCHEMA,
            reference_view_id=reference_view_id,
            observations=observations,
            empty_reason=("no_pre_lock_observations" if not observations else None),
        )
        return result

    def _select_pre_lock_observations(
        self,
        *,
        track_positions: list[PlayerFramePosition],
        locked_frame_index: int,
        reference_orientation: Any,
        frame_stride: int,
        fps: float,
        player_id: str,
        track_id: int,
    ) -> list[BootstrapBackfillObservation]:
        """筛出 lock 之前的真实观测，做 temporal/spatial continuity guard。

        仅取 `frame_index < locked_frame_index` 且 bbox 与 court_position 都有效的观测；
        按 frame_index 升序，相邻真实观测若 Δt 合理 **且** 位移/Δt ≤ max_speed（空间连续）
        则接受，否则从异常处截断历史（舍弃该段，**宁可少填、绝不填错**）。
        """
        stride = max(1, int(frame_stride))
        effective_fps = max(1e-3, float(fps))
        candidates = [
            p
            for p in track_positions
            if int(p.frame_index) < locked_frame_index
            and p.bbox is not None
            and len(p.bbox) == 4
            and p.court_position is not None
            and len(p.court_position) == 2
            and p.valid
        ]
        candidates.sort(key=lambda p: int(p.frame_index))

        accepted: list[BootstrapBackfillObservation] = []
        last_frame: int | None = None
        last_canon: tuple[float, float] | None = None

        for pos in candidates:
            frame_index = int(pos.frame_index)
            local = (float(pos.court_position[0]), float(pos.court_position[1]))
            try:
                canon = local_to_canonical(
                    local[0], local[1], reference_orientation
                )
            except Exception as exc:  # noqa: BLE001 - 单点转换失败不应中断整段回填
                logger.warning(
                    "bootstrap backfill: track %s frame %s 坐标转换失败，跳过：%s",
                    track_id, frame_index, exc,
                )
                break

            # 连续性护栏：首观测直接接受；后续需 Δt 合理且位移速率不超标（异常跳变 → 截断）
            if last_frame is not None and last_canon is not None:
                dt_seconds = abs(frame_index - last_frame) * stride / effective_fps
                dx = canon[0] - last_canon[0]
                dy = canon[1] - last_canon[1]
                displacement = hypot(dx, dy)
                if dt_seconds <= 0 or displacement / dt_seconds > self.max_speed_ft_s:
                    # 异常跳变：截断历史，停止接受（不把跳变点纳入回填）
                    break
            last_frame = frame_index
            last_canon = canon

            accepted.append(
                BootstrapBackfillObservation(
                    player_id=player_id,
                    track_id=track_id,
                    frame_index=frame_index,
                    timestamp_seconds=float(pos.timestamp),
                    bbox=[float(v) for v in pos.bbox],
                    court_position_local_ft=[local[0], local[1]],
                    canonical_court_position_ft=[float(canon[0]), float(canon[1])],
                    source_confidence=float(pos.confidence or 0.0),
                )
            )
        return accepted
