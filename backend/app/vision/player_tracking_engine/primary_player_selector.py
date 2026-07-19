"""主要球员选择器 —— 基于目标球场归属、tracklet 质量和四人组关系选择展示球员。"""

from __future__ import annotations

# deque：定长历史窗口；dataclass / field：数据结构；hypot 距离、isfinite 有限性判断。
from collections import deque
from dataclasses import dataclass, field
from math import hypot, isfinite

# 轨迹相关 schema：PlayerFramePosition（单帧位置）、PlayerSelectionDiagnostic（诊断）、
# PlayerTrackletFeature（tracklet 特征）、Track（跟踪框）。
from app.schemas.analysis import PlayerGroupProfile, _count_match_score
from app.schemas.tracking import PlayerFramePosition, PlayerSelectionDiagnostic, PlayerTrackletFeature, Track
# 标准球场几何：用于边界判定与半场划分。
from app.vision.courtvision_calibration_engine.court_geometry import StandardPickleballCourt, standard_court


@dataclass(frozen=True)
class PrimaryPlayerSelection:
    # 单次选择结果：track_id、综合分、置信度、滚动置信度、出现次数，以及三个分项得分。
    track_id: int
    score: float
    confidence: float
    rolling_confidence: float
    appearances: int
    target_court_score: float = 0.0
    tracklet_quality_score: float = 0.0
    group_consistency_score: float = 0.0


@dataclass
class _TrackQuality:
    # 内部记录某 track 的出现次数与置信度累计（用于滚动置信度）。
    appearances: int = 0
    confidence_total: float = 0.0

    @property
    def rolling_confidence(self) -> float:
        # 滚动置信度 = 累计置信度 / 出现次数。
        return self.confidence_total / self.appearances if self.appearances else 0.0


@dataclass(frozen=True)
class _Observation:
    # 单帧对某个 track 的观测快照（含 bbox、脚点、球场位置、置信度、面积占比、有效性）。
    frame_index: int
    timestamp: float
    track_id: int
    bbox: list[float]
    image_footpoint: list[float]
    court_position: list[float] | None
    confidence: float
    area_ratio: float
    valid: bool


@dataclass
class PrimaryPlayerSelectorConfig:
    # 选择器的可调参数：置信度阈值、最多展示人数、框面积占比上下限、球场边距(英尺)、
    # 历史窗口、目标球场/质量阈值、四人组权重、是否启用 attention 及其相关配置。
    min_confidence: float = 0.65
    max_subjects: int = 4
    min_box_area_ratio: float = 0.0005
    max_box_area_ratio: float = 0.85
    court_margin_ft: float | None = 12.0
    window_frames: int = 90
    target_court_threshold: float = 0.45
    quality_threshold: float = 0.28
    group_weight: float = 0.18
    attention_enabled: bool = False
    attention_model_path: str | None = None
    attention_confidence_threshold: float = 0.65
    group_profile: PlayerGroupProfile | None = None
    near_side_quota: int = 2
    far_side_quota: int = 2


@dataclass(frozen=True)
class AttentionSelectionResult:
    # attention 模型（若启用）的选择结果：被选中的 track 集合与各类概率、整体置信度。
    selected_track_ids: set[int]
    target_probabilities: dict[int, float]
    non_target_probabilities: dict[int, float]
    confidence: float


class AttentionPlayerSelectorAdapter:
    """Optional adapter boundary for future self-attention inference."""

    def __init__(self, model_path: str | None = None, confidence_threshold: float = 0.65) -> None:
        self.model_path = model_path
        self.confidence_threshold = confidence_threshold
        self.last_fallback_reason: str | None = None

    def select(self, features: list[PlayerTrackletFeature], max_subjects: int) -> AttentionSelectionResult | None:
        # 当前为占位边界：未配置模型路径或未实现推理时均返回 None 并记原因（走规则分支）。
        if not self.model_path:
            self.last_fallback_reason = "attention model path is not configured"
            return None
        try:
            import torch  # type: ignore  # noqa: F401
        except Exception as exc:  # noqa: BLE001 - optional dependency should not block rule path.
            self.last_fallback_reason = f"attention dependency unavailable: {exc}"
            return None

        self.last_fallback_reason = "attention inference is not implemented for untrained local weights"
        return None


class PrimaryPlayerSelector:
    """Select presentation subjects from tracked people using court-aware tracklet history."""

    def __init__(
        self,
        min_confidence: float = 0.65,
        max_subjects: int = 4,
        min_box_area_ratio: float = 0.0005,
        max_box_area_ratio: float = 0.85,
        court_margin_ft: float | None = 12.0,
        court: StandardPickleballCourt | None = None,
        window_frames: int = 90,
        target_court_threshold: float = 0.45,
        quality_threshold: float = 0.28,
        attention_enabled: bool = False,
        attention_model_path: str | None = None,
        attention_confidence_threshold: float = 0.65,
        attention_adapter: AttentionPlayerSelectorAdapter | None = None,
        group_profile: PlayerGroupProfile | None = None,
        near_side_quota: int = 2,
        far_side_quota: int = 2,
    ) -> None:
        # 把所有入参做"夹到合理范围"后写入配置对象（防止越界值）。
        self.config = PrimaryPlayerSelectorConfig(
            min_confidence=min(max(min_confidence, 0.0), 1.0),
            max_subjects=max(1, int(max_subjects)),
            min_box_area_ratio=max(0.0, min_box_area_ratio),
            max_box_area_ratio=max(max(0.0, min_box_area_ratio), max_box_area_ratio),
            court_margin_ft=court_margin_ft,
            window_frames=max(1, int(window_frames)),
            target_court_threshold=min(max(target_court_threshold, 0.0), 1.0),
            quality_threshold=min(max(quality_threshold, 0.0), 1.0),
            attention_enabled=attention_enabled,
            attention_model_path=attention_model_path,
            attention_confidence_threshold=min(max(attention_confidence_threshold, 0.0), 1.0),
            group_profile=group_profile,
            near_side_quota=near_side_quota,
            far_side_quota=far_side_quota,
        )
        self.court = court or standard_court()
        self._qualities: dict[int, _TrackQuality] = {}   # track_id -> 质量累计
        self._history: dict[int, deque[_Observation]] = {}  # track_id -> 定长历史窗口
        self.last_diagnostics: list[PlayerSelectionDiagnostic] = []
        self.last_training_samples: list[PlayerTrackletFeature] = []
        self.last_selection_mode: str = "rule"   # 当前选择模式：rule / attention / fallback
        self.last_fallback_reason: str | None = None
        self.attention_adapter = attention_adapter or AttentionPlayerSelectorAdapter(
            model_path=attention_model_path,
            confidence_threshold=self.config.attention_confidence_threshold,
        )

    @property
    def min_confidence(self) -> float:
        return self.config.min_confidence

    @property
    def max_subjects(self) -> int:
        return self.config.max_subjects

    @property
    def min_box_area_ratio(self) -> float:
        return self.config.min_box_area_ratio

    @property
    def max_box_area_ratio(self) -> float:
        return self.config.max_box_area_ratio

    @property
    def court_margin_ft(self) -> float | None:
        return self.config.court_margin_ft

    def select(
        self,
        tracks: list[Track],
        positions: list[PlayerFramePosition],
        frame_width: int,
        frame_height: int,
    ) -> list[PrimaryPlayerSelection]:
        # 主流程：1) 更新每个 track 的质量与历史观测；2) 抽取 tracklet 特征；
        # 3) 计算四人组一致性分、尝试 attention 选择；4) 对每个特征打分并产出候选；
        # 5) 排序取前 max_subjects 名（若 attention 生效则用其选定集合）。返回选择结果列表。
        active_tracks = [track for track in tracks if not track.lost]
        positions_by_track_id = {position.track_id: position for position in positions}
        for track in active_tracks:
            quality = self._qualities.setdefault(track.track_id, _TrackQuality())
            quality.appearances += 1
            quality.confidence_total += track.confidence
            self._record_observation(track, positions_by_track_id.get(track.track_id), frame_width, frame_height)

        features = [
            feature
            for track in active_tracks
            if (feature := self._tracklet_feature(track.track_id, track, frame_width, frame_height)) is not None
        ]
        group_scores = self._group_consistency_scores(features)
        attention_result = self._attention_select(features)
        selected_by_attention = attention_result.selected_track_ids if attention_result is not None else set()

        candidates: list[PrimaryPlayerSelection] = []
        diagnostics: list[PlayerSelectionDiagnostic] = []
        for feature in features:
            selection = self._score_feature(feature, group_scores.get(feature.track_id, 0.0), attention_result)
            selected_by_rule = selection is not None
            selected = feature.track_id in selected_by_attention if attention_result is not None else selected_by_rule
            if selection is not None:
                candidates.append(selection)
            diagnostics.append(
                self._diagnostic_for_feature(
                    feature,
                    selected=selected,
                    group_score=group_scores.get(feature.track_id, 0.0),
                    final_score=selection.score if selection else self._raw_score(feature, group_scores.get(feature.track_id, 0.0)),
                    attention_result=attention_result,
                )
            )
        # 按 (综合分, 滚动置信度, 置信度) 降序排序。
        candidates.sort(key=lambda selection: (selection.score, selection.rolling_confidence, selection.confidence), reverse=True)
        # 使用 quota-aware 最终组合选择（覆盖 rule 和 attention 两条路径）。
        selected_candidates = self._select_balanced_candidates(
            candidates=candidates,
            positions_by_track_id=positions_by_track_id,
            near_quota=self.config.near_side_quota,
            far_quota=self.config.far_side_quota,
        )
        if attention_result is not None:
            # attention 路径同样经过 quota-aware selection
            attention_candidates = [c for c in candidates if c.track_id in selected_by_attention]
            selected_candidates = self._select_balanced_candidates(
                candidates=attention_candidates,
                positions_by_track_id=positions_by_track_id,
                near_quota=self.config.near_side_quota,
                far_quota=self.config.far_side_quota,
            )
        # 回填诊断中的"是否最终被选中"标记，并缓存训练样本。
        self.last_diagnostics = [
            diagnostic.model_copy(update={"selected": diagnostic.track_id in {selection.track_id for selection in selected_candidates}})
            for diagnostic in diagnostics
        ]
        self.last_training_samples = features
        return selected_candidates

    def _score_feature(
        self,
        feature: PlayerTrackletFeature,
        group_score: float,
        attention_result: AttentionSelectionResult | None,
    ) -> PrimaryPlayerSelection | None:
        # 按一系列门槛过滤：置信度、框面积占比、目标球场归属、tracklet 质量、attention 命中。
        # 全通过后计算各项分并包装成 PrimaryPlayerSelection。
        if feature.latest_confidence < self.min_confidence:
            return None
        if not (self.min_box_area_ratio <= feature.mean_bbox_area_ratio <= self.max_box_area_ratio):
            return None
        if feature.valid_positions > 0 and feature.target_court_occupancy < self.config.target_court_threshold and group_score < 0.75:
            return None
        if self._tracklet_quality_score(feature) < self.config.quality_threshold:
            return None
        if attention_result is not None and feature.track_id not in attention_result.selected_track_ids:
            return None

        quality = self._qualities.get(feature.track_id, _TrackQuality())
        rolling_confidence = quality.rolling_confidence
        target_score = self._target_court_score(feature)
        quality_score = self._tracklet_quality_score(feature)
        score = self._raw_score(feature, group_score)
        if attention_result is not None:
            # attention 生效时用其目标概率覆盖综合分。
            score = attention_result.target_probabilities.get(feature.track_id, score)
        return PrimaryPlayerSelection(
            track_id=feature.track_id,
            score=score,
            confidence=feature.latest_confidence,
            rolling_confidence=rolling_confidence,
            appearances=feature.appearances,
            target_court_score=target_score,
            tracklet_quality_score=quality_score,
            group_consistency_score=group_score,
        )

    def _raw_score(self, feature: PlayerTrackletFeature, group_score: float) -> float:
        # 综合分 = 目标球场 0.42 + 质量 0.28 + 置信度 0.12 + 四人组 group_weight。
        # 置信度分由 latest_confidence(0.45) 与 mean_confidence(0.55) 加权。
        target_score = self._target_court_score(feature)
        quality_score = self._tracklet_quality_score(feature)
        confidence_score = feature.latest_confidence * 0.45 + feature.mean_confidence * 0.55
        weighted = (
            target_score * 0.42
            + quality_score * 0.28
            + confidence_score * 0.12
            + group_score * self.config.group_weight
        )
        return min(1.0, max(0.0, weighted))

    def _target_court_score(self, feature: PlayerTrackletFeature) -> float:
        # 目标球场归属分：有效位置为 0 时给中性 0.5；否则由“归属比例 0.72 + 距离惩罚补足 0.28”构成。
        if feature.valid_positions == 0:
            return 0.5
        distance_penalty = min(1.0, feature.mean_target_court_distance / max(1.0, float(self.court_margin_ft or 1.0)))
        occupancy_score = feature.target_court_occupancy
        return min(1.0, max(0.0, occupancy_score * 0.72 + (1.0 - distance_penalty) * 0.28))

    def _tracklet_quality_score(self, feature: PlayerTrackletFeature) -> float:
        # tracklet 质量分：持续性、有效位置比例、框面积是否合规，以及置信度/连续性的加权组合。
        persistence = min(1.0, feature.appearances / 12.0)
        valid_ratio = feature.valid_positions / max(1, feature.appearances)
        bbox_score = 1.0 if self.min_box_area_ratio <= feature.mean_bbox_area_ratio <= self.max_box_area_ratio else 0.0
        return min(
            1.0,
            max(
                0.0,
                feature.mean_confidence * 0.42
                + persistence * 0.22
                + feature.continuity * 0.18
                + valid_ratio * 0.12
                + bbox_score * 0.06,
            ),
        )

    def _group_consistency_scores(self, features: list[PlayerTrackletFeature]) -> dict[int, float]:
        # 赛制感知分组一致性：考察每个 track 与"同侧/对侧"人数比例是否匹配赛制期望。
        profile = self.config.group_profile
        if not features or profile is None:
            return {}
        valid = [feature for feature in features if feature.mean_court_position is not None]
        if not valid:
            return {feature.track_id: 0.5 for feature in features}
        near_far_balance: dict[int, float] = {}
        half_length = self.court.length_ft / 2.0
        for feature in valid:
            same_side_count = sum(
                1
                for other in valid
                if other.track_id != feature.track_id
                and other.mean_court_position is not None
                and (other.mean_court_position[1] < half_length) == (feature.mean_court_position[1] < half_length)
            )
            opposite_side_count = sum(
                1
                for other in valid
                if other.track_id != feature.track_id
                and other.mean_court_position is not None
                and (other.mean_court_position[1] < half_length) != (feature.mean_court_position[1] < half_length)
            )
            same_score = _count_match_score(same_side_count, profile.expected_same_side_others)
            opposite_score = _count_match_score(opposite_side_count, profile.expected_opposite_players)
            side_score = same_score * 0.45 + opposite_score * 0.55
            center_x = feature.mean_court_position[0]
            width_score = 1.0 - min(1.0, abs(center_x - self.court.width_ft / 2.0) / max(1.0, self.court.width_ft))
            near_far_balance[feature.track_id] = min(1.0, max(0.0, side_score * 0.7 + width_score * 0.3))
        return {feature.track_id: near_far_balance.get(feature.track_id, 0.35) for feature in features}

    def _infer_side(
        self,
        track_id: int,
        positions_by_track_id: dict[int, PlayerFramePosition],
    ) -> str | None:
        position = positions_by_track_id.get(track_id)
        if position is None or position.court_position is None:
            return None
        half_length = self.court.length_ft / 2.0
        y = position.court_position[1]
        if abs(y - half_length) < 2.0:
            return None
        return "near" if y < half_length else "far"

    def _select_balanced_candidates(
        self,
        candidates: list[PrimaryPlayerSelection],
        positions_by_track_id: dict[int, PlayerFramePosition],
        near_quota: int,
        far_quota: int,
    ) -> list[PrimaryPlayerSelection]:
        near_group: list[PrimaryPlayerSelection] = []
        far_group: list[PrimaryPlayerSelection] = []
        unknown_group: list[PrimaryPlayerSelection] = []
        for c in candidates:
            side = self._infer_side(c.track_id, positions_by_track_id)
            if side == "near":
                near_group.append(c)
            elif side == "far":
                far_group.append(c)
            else:
                unknown_group.append(c)
        near_group.sort(key=lambda x: x.score, reverse=True)
        far_group.sort(key=lambda x: x.score, reverse=True)
        selected = near_group[:near_quota] + far_group[:far_quota]
        remaining_slots = (near_quota + far_quota) - len(selected)
        if remaining_slots > 0 and unknown_group:
            unknown_group.sort(key=lambda x: x.score, reverse=True)
            selected.extend(unknown_group[:remaining_slots])
        selected.sort(key=lambda x: x.score, reverse=True)
        return selected[: min(self.max_subjects, near_quota + far_quota)]

    def _attention_select(self, features: list[PlayerTrackletFeature]) -> AttentionSelectionResult | None:
        # 尝试用 attention 适配器选择；未启用 / 无结果 / 置信度不足时回退规则分支。
        self.last_selection_mode = "rule"
        self.last_fallback_reason = None
        if not self.config.attention_enabled:
            return None
        result = self.attention_adapter.select(features, self.max_subjects)
        if result is None:
            self.last_selection_mode = "fallback"
            self.last_fallback_reason = self.attention_adapter.last_fallback_reason or "attention selector returned no result"
            return None
        if result.confidence < self.config.attention_confidence_threshold:
            self.last_selection_mode = "fallback"
            self.last_fallback_reason = "attention confidence below threshold"
            return None
        self.last_selection_mode = "attention"
        return result

    def _diagnostic_for_feature(
        self,
        feature: PlayerTrackletFeature,
        *,
        selected: bool,
        group_score: float,
        final_score: float,
        attention_result: AttentionSelectionResult | None,
    ) -> PlayerSelectionDiagnostic:
        # 为单个特征生成选择诊断（含各项分、attention 概率、最终分、标签与拒绝原因）。
        target_score = self._target_court_score(feature)
        quality_score = self._tracklet_quality_score(feature)
        reason = "selected target-court player" if selected else self._rejection_reason(feature, target_score, quality_score, group_score)
        label = (
            "target_player"
            if selected
            else ("neighbor_court_player" if feature.valid_positions > 0 and target_score < self.config.target_court_threshold else "uncertain")
        )
        return PlayerSelectionDiagnostic(
            track_id=feature.track_id,
            selected=selected,
            selection_mode=self.last_selection_mode,  # type: ignore[arg-type]
            fallback_reason=self.last_fallback_reason,
            target_court_score=target_score,
            tracklet_quality_score=quality_score,
            group_consistency_score=group_score,
            attention_target_probability=attention_result.target_probabilities.get(feature.track_id) if attention_result else None,
            attention_non_target_probability=attention_result.non_target_probabilities.get(feature.track_id) if attention_result else None,
            final_score=final_score,
            candidate_label=label,
            reason=reason,
            frame_start=feature.frame_start,
            frame_end=feature.frame_end,
            components={
                "target_court_occupancy": feature.target_court_occupancy,
                "mean_target_court_distance": feature.mean_target_court_distance,
                "mean_confidence": feature.mean_confidence,
                "appearances": feature.appearances,
                "continuity": feature.continuity,
            },
        )

    def _rejection_reason(self, feature: PlayerTrackletFeature, target_score: float, quality_score: float, group_score: float) -> str:
        # 按优先级返回被拒绝的原因（用于诊断展示）。
        if feature.latest_confidence < self.min_confidence:
            return "confidence below threshold"
        if feature.valid_positions > 0 and target_score < self.config.target_court_threshold:
            return "low target-court membership"
        if quality_score < self.config.quality_threshold:
            return "low tracklet quality"
        if group_score < 0.35:
            return "weak doubles group consistency"
        return "ranked outside participant limit"

    def _record_observation(
        self,
        track: Track,
        position: PlayerFramePosition | None,
        frame_width: int,
        frame_height: int,
    ) -> None:
        # 把当前帧的 track 与位置打包成 _Observation，追加到该 track 的定长历史窗口。
        area_ratio = self._bbox_area_ratio(track.bbox, frame_width, frame_height)
        court_position = position.court_position if position and position.court_position is not None else None
        image_footpoint = position.image_footpoint if position is not None else self._bbox_bottom_center(track.bbox)
        frame_index = position.frame_index if position is not None else 0
        timestamp = position.timestamp if position is not None else 0.0
        observation = _Observation(
            frame_index=frame_index,
            timestamp=timestamp,
            track_id=track.track_id,
            bbox=[float(value) for value in track.bbox],
            image_footpoint=[float(value) for value in image_footpoint],
            court_position=[float(value) for value in court_position] if court_position is not None else None,
            confidence=track.confidence,
            area_ratio=area_ratio,
            valid=bool(position.valid and position.court_position is not None) if position is not None else False,
        )
        history = self._history.setdefault(track.track_id, deque(maxlen=self.config.window_frames))
        history.append(observation)

    def _has_reasonable_box(self, track: Track, frame_width: int, frame_height: int) -> bool:
        # 判断框面积占比是否落在合理区间。
        area_ratio = self._bbox_area_ratio(track.bbox, frame_width, frame_height)
        return self.min_box_area_ratio <= area_ratio <= self.max_box_area_ratio

    def _bbox_area_ratio(self, bbox: list[float], frame_width: int, frame_height: int) -> float:
        # 计算检测框面积占整帧面积的比例；坐标非法或面积非正返回 0。
        source_area = max(1.0, float(frame_width) * float(frame_height))
        x1, y1, x2, y2 = [float(value) for value in bbox]
        if not all(isfinite(value) for value in (x1, y1, x2, y2)):
            return 0.0
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)
        if width <= 0.0 or height <= 0.0:
            return 0.0
        return (width * height) / source_area

    def _passes_scene_sanity(self, position: PlayerFramePosition | None) -> bool:
        # 场景合理性检查：若设置了 court_margin_ft，则要求位置在“球场外扩边距”内；否则直接通过。
        if self.court_margin_ft is None or position is None or position.court_position is None:
            return True
        x, y = position.court_position
        margin = self.court_margin_ft
        return (
            -margin <= x <= self.court.width_ft + margin
            and -margin <= y <= self.court.length_ft + margin
        )

    def _tracklet_feature(
        self,
        track_id: int,
        fallback_track: Track,
        frame_width: int,
        frame_height: int,
    ) -> PlayerTrackletFeature | None:
        # 根据历史窗口抽取该 track 的 tracklet 特征（供打分与（未来）训练使用）。
        history = list(self._history.get(track_id, []))
        if not history:
            return None
        latest = history[-1]
        court_points = [observation.court_position for observation in history if observation.court_position is not None]
        valid_positions = len(court_points)
        distances = [self._distance_from_target_court(point) for point in court_points]
        in_target_count = sum(1 for distance in distances if distance <= float(self.court_margin_ft or 0.0))
        target_occupancy = in_target_count / valid_positions if valid_positions else 0.0
        # 位置均值（米/英尺坐标）。
        mean_position = (
            [
                sum(point[0] for point in court_points) / valid_positions,
                sum(point[1] for point in court_points) / valid_positions,
            ]
            if valid_positions
            else None
        )
        # 基于相邻观测位置差与时间间隔估计速度序列。
        speeds = []
        for previous, current in zip(history, history[1:]):
            if previous.court_position is None or current.court_position is None:
                continue
            elapsed = current.timestamp - previous.timestamp
            if elapsed <= 0:
                continue
            speeds.append(_distance(previous.court_position, current.court_position) / elapsed)
        # 连续性：窗口内实际观测帧数 / 窗口跨帧数（越接近 1 越连续）。
        frame_span = max(1, history[-1].frame_index - history[0].frame_index + 1)
        continuity = min(1.0, len(history) / frame_span)
        bbox = latest.bbox or [float(value) for value in fallback_track.bbox]
        image_footpoint = latest.image_footpoint or self._bbox_bottom_center(bbox)
        return PlayerTrackletFeature(
            track_id=track_id,
            frame_start=history[0].frame_index,
            frame_end=history[-1].frame_index,
            first_timestamp_seconds=history[0].timestamp,
            last_timestamp_seconds=history[-1].timestamp,
            appearances=len(history),
            valid_positions=valid_positions,
            mean_confidence=sum(observation.confidence for observation in history) / len(history),
            latest_confidence=latest.confidence,
            mean_bbox_area_ratio=sum(observation.area_ratio for observation in history) / len(history),
            court_position=latest.court_position,
            mean_court_position=mean_position,
            target_court_occupancy=target_occupancy,
            mean_target_court_distance=sum(distances) / len(distances) if distances else float(self.court_margin_ft or 0.0) + 1.0,
            max_target_court_distance=max(distances) if distances else float(self.court_margin_ft or 0.0) + 1.0,
            mean_speed=sum(speeds) / len(speeds) if speeds else 0.0,
            continuity=continuity,
            bbox=bbox,
            image_footpoint=image_footpoint,
        )

    def _distance_from_target_court(self, point: list[float]) -> float:
        # 点到“目标球场矩形”的最近距离（球场外为 0，球场内为正距离）。
        x, y = point
        dx = max(0.0, -x, x - self.court.width_ft)
        dy = max(0.0, -y, y - self.court.length_ft)
        return hypot(dx, dy)

    @staticmethod
    def _bbox_bottom_center(bbox: list[float]) -> list[float]:
        # 检测框底边中点（脚点兜底估计），与 FootpointEstimator 的默认方法一致。
        x1, _y1, x2, y2 = [float(value) for value in bbox]
        return [(x1 + x2) / 2.0, y2]


def _distance(a: list[float], b: list[float]) -> float:
    # 两点欧氏距离。
    return hypot(a[0] - b[0], a[1] - b[1])
