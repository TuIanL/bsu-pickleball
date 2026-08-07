"""球员归属上下文（player_attribution_context）。

把"算法侧"的球员证据聚合为击球归属的统一查询入口：

  - canonical 真值：PlayerTrajectoryArtifact（player_id + track_id + bbox + 球场位置）；
  - 姿态证据：PoseOverlayFrame（经共享上肢证据索引，含 wrist/elbow 坐标与运动强度）；
  - 降级来源：TrackingResult.overlay_frames（仅 detected/tentative 身份映射成功的检测）；
  - 展示元数据：render v2 roster（player_id / render_slot / initial_side）。

`track_id` 内部统一规范化为字符串（TrackKey），禁止混用 int/str。
所有对外身份只允许 canonical `Player_1..Player_4`。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.schemas.pose import PoseOverlayFrame
from app.schemas.tracking import (
    DetectionOverlayFrame,
    PlayerTrajectoryArtifact,
    PlayerTrajectorySample,
)
from app.vision.pickleball_game_analysis.upper_limb_evidence import (
    UpperLimbEvidenceIndex,
    build_upper_limb_evidence_index,
)


def normalize_track_key(track_id: int | str | None) -> str | None:
    """把任意形式的 track_id 规范化为字符串键；None 返回 None。"""
    if track_id is None:
        return None
    return str(track_id)


@dataclass(frozen=True)
class PlayerRosterEntry:
    """render v2 roster 中的一名球员（仅保留归属所需的展示元数据）。"""

    player_id: str
    render_slot: str | None = None
    initial_side: str | None = None


@dataclass
class PlayerAttributionContext:
    """击球归属的统一证据上下文。

    构造后不可修改内部映射（视为只读快照）。
    """

    track_to_player: dict[str, str] = field(default_factory=dict)
    player_samples: dict[str, list[PlayerTrajectorySample]] = field(default_factory=dict)
    upper_limb_index: UpperLimbEvidenceIndex | None = None
    overlay_frames: list[DetectionOverlayFrame] | None = None
    roster: dict[str, PlayerRosterEntry] = field(default_factory=dict)
    fps: float = 30.0
    frame_stride: int = 1

    @property
    def player_ids(self) -> list[str]:
        """已知的 canonical 球员列表（按 Player_N 数字序）。"""
        return sorted(self.player_samples.keys(), key=lambda pid: int(pid.split("_")[1]))

    def tracks_for_player(self, player_id: str) -> list[str]:
        """该球员使用过的全部 track 键（含换 track 后的历史轨迹）。"""
        return sorted(key for key, pid in self.track_to_player.items() if pid == player_id)

    def player_id_for_track(self, track_id: int | str | None) -> str | None:
        """track_id → canonical player_id（规范化键查找）。"""
        key = normalize_track_key(track_id)
        if key is None:
            return None
        return self.track_to_player.get(key)

    def render_slot_for(self, player_id: str | None) -> str | None:
        """canonical player_id → render_slot（用于展示）。"""
        if player_id is None:
            return None
        entry = self.roster.get(player_id)
        return entry.render_slot if entry else None

    def samples_in_window(
        self,
        player_id: str,
        start_sec: float,
        end_sec: float,
    ) -> list[PlayerTrajectorySample]:
        """某球员在时间窗内的轨迹采样（按帧升序）。"""
        return [
            sample
            for sample in self.player_samples.get(player_id, [])
            if start_sec <= sample.timestamp_seconds <= end_sec
        ]

    def side_at(self, player_id: str, timestamp_sec: float) -> str | None:
        """某球员在给定时刻的半场（"near" / "far"，按球场纵向中点划分）。

        使用球员球场坐标动态推导，不使用 roster 的 initial_side（换边后已过时）。
        只用于同侧/异侧的相对比较，不要求绝对语义。
        """
        samples = self.player_samples.get(player_id)
        if not samples:
            return None
        best = min(samples, key=lambda s: abs(s.timestamp_seconds - timestamp_sec))
        unit = best.court_unit
        length = 13.41 if unit == "m" else 44.0
        return "near" if best.court_y < length / 2 else "far"


def build_player_attribution_context(
    player_trajectories: PlayerTrajectoryArtifact | None = None,
    pose_frames: list[PoseOverlayFrame] | None = None,
    overlay_frames: list[DetectionOverlayFrame] | None = None,
    render_trajectory_payload: dict[str, Any] | None = None,
    *,
    smooth_window_frames: int = 5,
    fps: float = 30.0,
    frame_stride: int = 1,
) -> PlayerAttributionContext:
    """从 pipeline 内存对象构建归属上下文。

    render_trajectory_payload 为 render v2 的"players"列表所在 dict
    （`serialize_render_trajectory_v2` 的输入 result，含 players 元数据）。
    """
    track_to_player: dict[str, str] = {}
    player_samples: dict[str, list[PlayerTrajectorySample]] = {}
    if player_trajectories is not None:
        for player_id, samples in player_trajectories.players.items():
            sorted_samples = sorted(samples, key=lambda s: s.frame_index)
            player_samples[player_id] = sorted_samples
            for sample in sorted_samples:
                key = normalize_track_key(sample.track_id)
                if key is not None:
                    track_to_player[key] = sample.player_id

    upper_limb_index = None
    if pose_frames:
        upper_limb_index = build_upper_limb_evidence_index(
            pose_frames,
            smooth_window_frames=smooth_window_frames,
        )

    roster: dict[str, PlayerRosterEntry] = {}
    if render_trajectory_payload:
        for player in render_trajectory_payload.get("players", []):
            player_id = player.get("player_id") if isinstance(player, dict) else getattr(player, "player_id", None)
            if not player_id:
                continue
            render_slot = (
                player.get("render_slot") if isinstance(player, dict) else getattr(player, "render_slot", None)
            )
            initial_side = (
                player.get("initial_side") if isinstance(player, dict) else getattr(player, "initial_side", None)
            )
            roster[player_id] = PlayerRosterEntry(
                player_id=player_id,
                render_slot=render_slot,
                initial_side=initial_side,
            )

    return PlayerAttributionContext(
        track_to_player=track_to_player,
        player_samples=player_samples,
        upper_limb_index=upper_limb_index,
        overlay_frames=overlay_frames,
        roster=roster,
        fps=fps,
        frame_stride=frame_stride,
    )
