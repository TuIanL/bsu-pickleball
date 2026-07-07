"""球员身份管理 —— 将临时跟踪 ID 映射为稳定的比赛级球员身份，支持断线重连和插值。"""

from __future__ import annotations

# dataclass / field：数据结构与可变默认工厂；Counter：统计状态计数；
# hypot：求两点距离。feet_to_meters / meters_to_feet：英制与公制互转；
# 标准球场尺寸常量 PICKLEBALL_COURT_WIDTH_M / LENGTH_M。
from dataclasses import dataclass, field
from collections import Counter
from math import hypot

from app.schemas.tracking import (
    CourtCoordinateMetadata,
    PlayerFramePosition,
    PlayerIdentityDiagnostic,
    PlayerTrajectoryCoverage,
    PlayerTrajectoryCoverageDiagnostics,
    PlayerTrajectoryArtifact,
    PlayerTrajectorySample,
    PlayerTrajectoryState,
    ProjectedTrackPoint,
)
from app.vision.courtvision_calibration_engine.court_units import (
    PICKLEBALL_COURT_LENGTH_M,
    PICKLEBALL_COURT_WIDTH_M,
    feet_to_meters,
    meters_to_feet,
)


@dataclass
class PlayerIdentityConfig:
    # 身份管理的可调参数：最多球员数、帧率、匹配阈值、重连距离/速度上限、
    # 各类缓冲帧数、球场外扩边距、输入坐标单位、平滑窗口大小等。
    max_players: int = 4
    fps: float = 30.0
    match_threshold: float = 0.55
    max_reconnect_distance_m: float = 2.5
    max_speed_mps: float = 7.0
    lost_buffer_frames: int = 90
    inactive_buffer_frames: int = 180
    interpolation_buffer_frames: int = 90
    court_buffer_m: float = 0.75
    input_court_unit: str = "ft"
    smoothing_window: int = 5


@dataclass
class PlayerObservation:
    # 单条“观测”的中间结构：来自某一帧的某个 track 的位置信息（已换算到米）。
    frame_index: int
    timestamp_seconds: float
    track_id: int
    bbox: list[float]
    image_footpoint: list[float]
    court_position_m: list[float]
    confidence: float


@dataclass
class PlayerState:
    # 某个稳定球员身份的运行时状态：活跃/历史 track_id 集合、最近出现帧、位置、速度、置信度、状态、轨迹样本。
    player_id: str
    active_track_ids: set[int] = field(default_factory=set)
    history_track_ids: set[int] = field(default_factory=set)
    last_seen_frame: int = -1
    last_timestamp: float = 0.0
    last_position_m: list[float] | None = None
    last_velocity_mps: list[float] = field(default_factory=lambda: [0.0, 0.0])
    confidence: float = 0.0
    status: str = "inactive"
    trajectory: list[PlayerTrajectorySample] = field(default_factory=list)

    def to_schema(self) -> PlayerTrajectoryState:
        # 把运行时状态转成对外 schema（PlayerTrajectoryState）。
        return PlayerTrajectoryState(
            player_id=self.player_id,
            status=self.status,  # type: ignore[arg-type]
            active_track_ids=sorted(self.active_track_ids),
            history_track_ids=sorted(self.history_track_ids),
            last_seen_frame=self.last_seen_frame,
            last_position_m=self.last_position_m,
            last_velocity_mps=self.last_velocity_mps,
            confidence=self.confidence,
        )


class PlayerIdentityManager:
    """Map temporary source track IDs into stable match-level doubles player IDs."""

    def __init__(self, config: PlayerIdentityConfig | None = None) -> None:
        self.config = config or PlayerIdentityConfig()
        self.players: dict[str, PlayerState] = {}        # player_id -> 状态
        self.track_to_player: dict[int, str] = {}        # track_id -> player_id 映射
        self.diagnostics: list[PlayerIdentityDiagnostic] = []  # 诊断事件累积

    def update(
        self,
        frame_index: int,
        positions: list[PlayerFramePosition],
        eligible_track_ids: set[int] | None = None,
    ) -> list[PlayerTrajectorySample]:
        # 处理一帧：把有效位置转成观测，按资格过滤，再逐个分配到球员身份并产出轨迹样本。
        observations = [
            self._position_to_observation(position)
            for position in positions
            if position.valid and position.court_position is not None
        ]
        # 若指定了“合格 track 集合”，先记录被过滤掉的观测，再丢弃它们。
        if eligible_track_ids is not None:
            excluded = [obs for obs in observations if obs.track_id not in eligible_track_ids]
            for observation in excluded:
                self._diagnose(
                    frame_index,
                    "filtered",
                    reason="not target-court eligible",
                    track_id=observation.track_id,
                    court_position_m=observation.court_position_m,
                )
            observations = [obs for obs in observations if obs.track_id in eligible_track_ids]

        outputs: list[PlayerTrajectorySample] = []
        updated_players: set[str] = set()
        for observation in observations:
            # 落在度量边界外的点跳过并记录诊断。
            if not self._in_metric_bounds(observation.court_position_m):
                self._diagnose(
                    frame_index,
                    "filtered",
                    reason="metric court bounds",
                    track_id=observation.track_id,
                    court_position_m=observation.court_position_m,
                )
                continue
            player = self._assign_player(observation)
            if player is None:
                self._diagnose(
                    frame_index,
                    "unmatched",
                    reason="no player slot or candidate above threshold",
                    track_id=observation.track_id,
                    court_position_m=observation.court_position_m,
                )
                continue
            samples = self._update_player(player, observation)
            outputs.extend(samples)
            updated_players.add(player.player_id)

        self._update_player_statuses(frame_index, updated_players)
        return outputs

    def to_artifact(
        self,
        *,
        job_id: str,
        video_id: str | None,
        fps: float,
        frame_count: int,
        processed_frame_count: int,
        frame_stride: int,
    ) -> PlayerTrajectoryArtifact:
        # 汇总所有球员轨迹，生成最终 artifact（含平滑轨迹、状态、诊断、覆盖度）。
        players = {
            player_id: _with_smoothed_positions(player.trajectory, self.config.smoothing_window)
            for player_id, player in sorted(self.players.items())
        }
        coverage = self._coverage_diagnostics(players=players, fps=fps, frame_count=frame_count)
        return PlayerTrajectoryArtifact(
            job_id=job_id,
            video_id=video_id,
            fps=fps,
            frame_count=frame_count,
            processed_frame_count=processed_frame_count,
            frame_stride=frame_stride,
            court=CourtCoordinateMetadata(),
            players=players,
            states={player_id: player.to_schema() for player_id, player in sorted(self.players.items())},
            diagnostics=self.diagnostics,
            coverage=coverage,
        )

    def to_projected_track_points(self, output_court_unit: str = "m") -> list[ProjectedTrackPoint]:
        # 把内部（米）轨迹点转成对外投影轨迹点；output_court_unit='ft' 时换算成英尺。
        points: list[ProjectedTrackPoint] = []
        for player in self.players.values():
            for sample in _with_smoothed_positions(player.trajectory, self.config.smoothing_window):
                if sample.court_unit != "m":
                    continue
                if output_court_unit == "ft":
                    court_x = meters_to_feet(sample.court_x)
                    court_y = meters_to_feet(sample.court_y)
                else:
                    court_x = sample.court_x
                    court_y = sample.court_y
                points.append(
                    ProjectedTrackPoint(
                        frame_index=sample.frame_index,
                        timestamp_seconds=sample.timestamp_seconds,
                        track_id=sample.player_id,
                        image_point={
                            "x": (sample.image_footpoint or [0.0, 0.0])[0],
                            "y": (sample.image_footpoint or [0.0, 0.0])[1],
                        },
                        confidence=sample.confidence,
                        side=_side_for_metric_y(sample.court_y),
                        court_point={"x": court_x, "y": court_y},
                    )
                )
        return sorted(points, key=lambda point: (point.timestamp_seconds, point.frame_index, point.track_id))

    def _assign_player(self, observation: PlayerObservation) -> PlayerState | None:
        # 把一次观测分配到球员身份：1) 已有 track->player 映射直接复用；2) 还有空位则新建；
        # 3) 否则在现有球员里找最佳候选（得分需超过阈值），否则返回 None。
        player_id = self.track_to_player.get(observation.track_id)
        if player_id is not None and player_id in self.players:
            return self.players[player_id]

        if len(self.players) < self.config.max_players:
            player_id = f"Player_{len(self.players) + 1}"
            player = PlayerState(player_id=player_id)
            self.players[player_id] = player
            self.track_to_player[observation.track_id] = player_id
            self._diagnose(
                observation.frame_index,
                "created",
                player_id=player_id,
                track_id=observation.track_id,
                score=1.0,
                reason="available player slot",
                court_position_m=observation.court_position_m,
            )
            return player

        player, score, reason = self._best_candidate(observation)
        if player is None or score < self.config.match_threshold:
            return None
        self.track_to_player[observation.track_id] = player.player_id
        self._diagnose(
            observation.frame_index,
            "reconnected" if player.status in {"lost", "inactive"} else "assigned",
            player_id=player.player_id,
            track_id=observation.track_id,
            score=score,
            reason=reason,
            court_position_m=observation.court_position_m,
        )
        return player

    def _best_candidate(self, observation: PlayerObservation) -> tuple[PlayerState | None, float, str]:
        # 在所有已有球员里挑“预测位置离观测最近且运动方向最一致”的作为最佳候选。
        best_player: PlayerState | None = None
        best_score = 0.0
        best_reason = ""
        for player in self.players.values():
            if player.last_position_m is None:
                continue
            predicted = self._predict_position(player, observation.frame_index)
            distance = _distance(predicted, observation.court_position_m)
            # 速度不现实（超过上限）则位置分记 0。
            if not self._speed_is_plausible(player, observation):
                position_score = 0.0
                reason = "implausible speed"
            else:
                # 距预测位置越近，位置分越高（按最大重连距离归一）。0..1
                position_score = max(0.0, 1.0 - distance / self.config.max_reconnect_distance_m)
                reason = "position"
            motion_score = self._motion_score(player, predicted, observation.court_position_m)
            # 综合分：位置占 0.7、运动一致性占 0.3。
            score = 0.7 * position_score + 0.3 * motion_score
            if score > best_score:
                best_player = player
                best_score = score
                best_reason = f"{reason}+motion"
        return best_player, best_score, best_reason

    def _update_player(self, player: PlayerState, observation: PlayerObservation) -> list[PlayerTrajectorySample]:
        # 用一次观测更新球员状态，并产出（含插值）轨迹样本。
        inserted = self._interpolate(player, observation)
        previous_position = player.last_position_m
        previous_timestamp = player.last_timestamp

        player.active_track_ids = {observation.track_id}
        player.history_track_ids.add(observation.track_id)
        self.track_to_player[observation.track_id] = player.player_id
        player.status = "active"
        player.last_seen_frame = observation.frame_index
        player.last_timestamp = observation.timestamp_seconds
        player.confidence = observation.confidence
        # 若前后位置都具备，则按时间差计算原始速度，并用指数平滑（alpha=0.7）更新速度估计。
        if previous_position is not None:
            elapsed = observation.timestamp_seconds - previous_timestamp
            if elapsed > 0:
                raw_velocity = [
                    (observation.court_position_m[0] - previous_position[0]) / elapsed,
                    (observation.court_position_m[1] - previous_position[1]) / elapsed,
                ]
                alpha = 0.7
                player.last_velocity_mps = [
                    alpha * player.last_velocity_mps[0] + (1 - alpha) * raw_velocity[0],
                    alpha * player.last_velocity_mps[1] + (1 - alpha) * raw_velocity[1],
                ]
        player.last_position_m = observation.court_position_m

        # 记录当前帧的真实（detected）样本。
        sample = PlayerTrajectorySample(
            frame_index=observation.frame_index,
            timestamp_seconds=observation.timestamp_seconds,
            player_id=player.player_id,
            track_id=observation.track_id,
            bbox=observation.bbox,
            image_footpoint=observation.image_footpoint,
            court_x=observation.court_position_m[0],
            court_y=observation.court_position_m[1],
            confidence=observation.confidence,
            tracking_status="detected",
            is_interpolated=False,
            source="detector",
        )
        player.trajectory.extend(inserted)
        player.trajectory.append(sample)
        player.trajectory.sort(key=lambda item: (item.frame_index, item.timestamp_seconds))
        return [*inserted, sample]

    def _interpolate(self, player: PlayerState, observation: PlayerObservation) -> list[PlayerTrajectorySample]:
        # 当两次观测之间缺失若干帧（且间隔在可插值范围内）时，做线性插值补齐中间帧（interpolated 样本）。
        if player.last_position_m is None or player.last_seen_frame < 0:
            return []
        gap = observation.frame_index - player.last_seen_frame
        if gap <= 1 or gap > self.config.interpolation_buffer_frames:
            return []
        inserted: list[PlayerTrajectorySample] = []
        elapsed = observation.timestamp_seconds - player.last_timestamp
        for frame_index in range(player.last_seen_frame + 1, observation.frame_index):
            ratio = (frame_index - player.last_seen_frame) / gap
            timestamp = player.last_timestamp + elapsed * ratio
            x = player.last_position_m[0] + (observation.court_position_m[0] - player.last_position_m[0]) * ratio
            y = player.last_position_m[1] + (observation.court_position_m[1] - player.last_position_m[1]) * ratio
            inserted.append(
                PlayerTrajectorySample(
                    frame_index=frame_index,
                    timestamp_seconds=timestamp,
                    player_id=player.player_id,
                    track_id=observation.track_id,
                    court_x=x,
                    court_y=y,
                    confidence=observation.confidence,
                    tracking_status="interpolated",
                    is_interpolated=True,
                    source="interpolation",
                )
            )
        return inserted

    def _update_player_statuses(self, frame_index: int, updated_players: set[str]) -> None:
        # 根据距上次出现的帧间隔更新未在本帧更新的球员状态：lost / inactive。
        for player in self.players.values():
            if player.player_id in updated_players:
                continue
            if player.last_seen_frame < 0:
                continue
            gap = frame_index - player.last_seen_frame
            previous_status = player.status
            if gap <= self.config.lost_buffer_frames:
                player.status = "lost"
            elif gap <= self.config.inactive_buffer_frames:
                player.status = "inactive"
            else:
                player.status = "inactive"
            player.active_track_ids.clear()
            if player.status != previous_status:
                self._diagnose(
                    frame_index,
                    player.status,  # type: ignore[arg-type]
                    player_id=player.player_id,
                    reason=f"missing for {gap} frames",
                    court_position_m=player.last_position_m,
                )

    def _position_to_observation(self, position: PlayerFramePosition) -> PlayerObservation:
        # 把对外 PlayerFramePosition 转成内部（米为单位）的 PlayerObservation。
        court_position = position.court_position or [0.0, 0.0]
        if position.court_unit == "ft":
            court_position_m = [feet_to_meters(court_position[0]), feet_to_meters(court_position[1])]
        else:
            court_position_m = [float(court_position[0]), float(court_position[1])]
        return PlayerObservation(
            frame_index=position.frame_index,
            timestamp_seconds=position.timestamp,
            track_id=position.track_id,
            bbox=position.bbox,
            image_footpoint=position.image_footpoint,
            court_position_m=court_position_m,
            confidence=position.confidence,
        )

    def _predict_position(self, player: PlayerState, frame_index: int) -> list[float]:
        # 基于上一位置与平滑速度，线性预测本帧球员应处的位置（用于重连匹配）。
        if player.last_position_m is None:
            return [0.0, 0.0]
        fps = self.config.fps if self.config.fps > 0 else 30.0
        elapsed = max(0.0, (frame_index - player.last_seen_frame) / fps)
        return [
            player.last_position_m[0] + player.last_velocity_mps[0] * elapsed,
            player.last_position_m[1] + player.last_velocity_mps[1] * elapsed,
        ]

    def _motion_score(self, player: PlayerState, predicted: list[float], observed: list[float]) -> float:
        # 运动一致性分：比较“预测速度方向”与“实际观测位移方向”的余弦相似度（0..1，无关时 0.5）。
        if player.last_position_m is None:
            return 0.5
        observed_delta = [observed[0] - player.last_position_m[0], observed[1] - player.last_position_m[1]]
        return _cosine_score(player.last_velocity_mps, observed_delta) if _norm(observed_delta) > 1e-6 else 0.5

    def _speed_is_plausible(self, player: PlayerState, observation: PlayerObservation) -> bool:
        # 判断本次观测相对上次的移动速度是否不超过上限（过滤明显错误的大跳变）。
        if player.last_position_m is None:
            return True
        elapsed = observation.timestamp_seconds - player.last_timestamp
        if elapsed <= 0:
            return True
        return _distance(player.last_position_m, observation.court_position_m) / elapsed <= self.config.max_speed_mps

    def _in_metric_bounds(self, point: list[float]) -> bool:
        # 判断球场坐标（米）是否落在含外扩边距的球场范围内。
        margin = self.config.court_buffer_m
        return (
            -margin <= point[0] <= PICKLEBALL_COURT_WIDTH_M + margin
            and -margin <= point[1] <= PICKLEBALL_COURT_LENGTH_M + margin
        )

    def _diagnose(
        self,
        frame_index: int,
        event: str,
        *,
        reason: str,
        player_id: str | None = None,
        track_id: int | None = None,
        score: float | None = None,
        court_position_m: list[float] | None = None,
    ) -> None:
        # 追加一条诊断事件（用于排查身份分配/过滤原因）。
        self.diagnostics.append(
            PlayerIdentityDiagnostic(
                frame_index=frame_index,
                event=event,  # type: ignore[arg-type]
                player_id=player_id,
                track_id=track_id,
                score=score,
                reason=reason,
                court_position_m=court_position_m,
            )
        )

    def _coverage_diagnostics(
        self,
        *,
        players: dict[str, list[PlayerTrajectorySample]],
        fps: float,
        frame_count: int,
    ) -> PlayerTrajectoryCoverageDiagnostics:
        # 统计每个球员的轨迹覆盖度（样本数、检测/插值数、首末时间、状态计数等），并产出整体覆盖警告。
        source_duration = frame_count / fps if fps > 0 and frame_count > 0 else None
        player_coverages: list[PlayerTrajectoryCoverage] = []
        first_values: list[float] = []
        last_values: list[float] = []
        warnings: list[str] = []
        for player_id, samples in sorted(players.items()):
            ordered = sorted(samples, key=lambda item: item.timestamp_seconds)
            status_counts = Counter(sample.tracking_status for sample in ordered)
            detected_count = sum(1 for sample in ordered if not sample.is_interpolated)
            interpolated_count = sum(1 for sample in ordered if sample.is_interpolated)
            first = ordered[0].timestamp_seconds if ordered else None
            last = ordered[-1].timestamp_seconds if ordered else None
            if first is not None:
                first_values.append(first)
            if last is not None:
                last_values.append(last)
            player = self.players.get(player_id)
            player_coverages.append(
                PlayerTrajectoryCoverage(
                    player_id=player_id,
                    sample_count=len(ordered),
                    detected_count=detected_count,
                    interpolated_count=interpolated_count,
                    first_timestamp_seconds=first,
                    last_timestamp_seconds=last,
                    first_frame_index=ordered[0].frame_index if ordered else None,
                    last_frame_index=ordered[-1].frame_index if ordered else None,
                    status_counts=dict(status_counts),
                    history_track_ids=sorted(player.history_track_ids) if player else [],
                )
            )
        trajectory_last = max(last_values) if last_values else None
        # 轨迹过早结束（不足源视频 75%）则警告。
        if source_duration and trajectory_last is not None and trajectory_last < source_duration * 0.75:
            warnings.append("trajectory_ends_before_source_video")
        if not player_coverages:
            warnings.append("no_player_trajectories")
        return PlayerTrajectoryCoverageDiagnostics(
            source_duration_seconds=source_duration,
            tracking_last_timestamp_seconds=source_duration,
            trajectory_first_timestamp_seconds=min(first_values) if first_values else None,
            trajectory_last_timestamp_seconds=trajectory_last,
            coverage_ratio=min(1.0, trajectory_last / source_duration) if source_duration and trajectory_last is not None else None,
            players=player_coverages,
            diagnostic_event_counts=dict(Counter(item.event for item in self.diagnostics)),
            warnings=warnings,
        )


def _distance(a: list[float], b: list[float]) -> float:
    # 欧氏距离。
    return hypot(a[0] - b[0], a[1] - b[1])


def _norm(vector: list[float]) -> float:
    # 向量的模长。
    return hypot(vector[0], vector[1])


def _cosine_score(a: list[float], b: list[float]) -> float:
    # 余弦相似度映射到 0..1（(-1,1)→(0,1)）。任一向量过短返回 0.5。
    norm_a = _norm(a)
    norm_b = _norm(b)
    if norm_a < 1e-6 or norm_b < 1e-6:
        return 0.5
    cosine = (a[0] * b[0] + a[1] * b[1]) / (norm_a * norm_b)
    return max(0.0, min(1.0, (cosine + 1.0) / 2.0))


def _side_for_metric_y(y: float) -> str:
    # 按球场长度方向把位置分成近侧(near)/远侧(far)。
    return "near" if y < PICKLEBALL_COURT_LENGTH_M / 2.0 else "far"


def _with_smoothed_positions(
    samples: list[PlayerTrajectorySample],
    window: int,
) -> list[PlayerTrajectorySample]:
    # 对轨迹坐标做滑动窗口均值平滑（window<=1 则直接浅拷贝原样本）。
    if window <= 1 or not samples:
        return [sample.model_copy() for sample in samples]
    ordered = sorted(samples, key=lambda item: (item.frame_index, item.timestamp_seconds))
    radius = window // 2
    smoothed: list[PlayerTrajectorySample] = []
    for index, sample in enumerate(ordered):
        start = max(0, index - radius)
        end = min(len(ordered), index + radius + 1)
        neighbors = ordered[start:end]
        updated = sample.model_copy()
        updated.smoothed_court_x = sum(item.court_x for item in neighbors) / len(neighbors)
        updated.smoothed_court_y = sum(item.court_y for item in neighbors) / len(neighbors)
        smoothed.append(updated)
    return smoothed
