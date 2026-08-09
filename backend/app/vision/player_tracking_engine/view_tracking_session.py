"""可复用单视角逐帧 tracking session（view_tracking_session）。

从 `AnalysisPipeline._run_tracking()` 抽出的逐帧 tracking 计算链：

    detect → ROI filter → tracker.update → duplicate suppress → footpoint →
    project → smooth → select → lock → identity → render observations/events

设计要点：
- `ViewTrackingSession` = **状态容器 + step 算法**；components 由工厂 `build_view_tracking_session`
  解析/构造并注入，保留调用方对 tracker / footpoint_estimator / projector 的依赖注入语义。
- 默认 `guidance=()` 时输出与重构前的单视角路径完全一致（行为保护，differential test 守护）。
- `processed_frame_count` 由调用方（AnalysisPipeline）持有，session 不持有（见 design D1b）。
- 渲染生命周期顺序不变量：identity update → 构建当帧 render observation（旧 epoch）→
  读取 diagnostics → 若 reset 才递增 epoch（见 design D2b）。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import hypot
from typing import Any

from app.schemas.analysis import MatchAnalysisContext, build_match_context, build_player_group_profile
from app.schemas.multitarget import MultiTargetDetection
from app.schemas.tracking import (
    Detection,
    DetectionOverlayFrame,
    FrameDetection,
    PlayerFramePosition,
    PlayerIdentityDiagnostic,
    PlayerTrajectoryArtifact,
    ProjectedTrackPoint,
    Track,
)
from app.utils.fps import frames_for_seconds
from app.vision.court_view import filter_detections_to_roi
from app.vision.player_tracking_engine.court_position_smoother import CourtPositionSmoother
from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator
from app.vision.player_tracking_engine.multi_object_tracker import DuplicateTrackSuppressor, MultiObjectTracker
from app.vision.player_tracking_engine.player_identity import PlayerIdentityConfig, PlayerIdentityManager
from app.vision.player_tracking_engine.player_lock_manager import PlayerLockManager
from app.vision.player_tracking_engine.player_lock_types import PlayerLockConfig
from app.vision.player_tracking_engine.player_projector import PlayerProjector
from app.vision.player_tracking_engine.primary_player_selector import PrimaryPlayerSelector
from app.vision.pickleball_game_analysis.court_track_types import (
    CourtTrackEvent,
    CourtTrackObservation,
    canonical_player_id,
)

# 渲染事件映射表：IdentityManager/LockManager diagnostics event → CourtTrackEvent type
_RENDER_EVENT_MAPPING: dict[str, str] = {
    "created": "identity_created",
    "reconnected": "identity_reconnected",
    "player_locked": "lock_acquired",
    "player_reconnected_from_lost": "lock_reconnected",
    "player_reconnected_after_track_change": "lock_reconnected",
}


@dataclass
class ViewTrackingSessionConfig:
    """从 settings + match_context 解析出的单视角 tracking 运行配置。

    与 `_run_tracking` 1753-1860 行推导块逐字段等价；由 `build_view_tracking_config`
    纯函数解析，保持 session 与全局 Settings 解耦、可独立单测。
    """

    fps: float
    frame_stride: int
    frame_width: int
    frame_height: int
    effective_player_count: int
    match_context: MatchAnalysisContext
    group_profile: Any

    # PrimaryPlayerSelector（来自 settings）
    primary_player_window_frames: int
    primary_player_min_confidence: float
    primary_player_min_box_area_ratio: float
    primary_player_max_box_area_ratio: float
    primary_player_court_margin_ft: float
    primary_player_target_court_threshold: float
    primary_player_quality_threshold: float
    attention_enabled: bool
    attention_model_path: str | None
    attention_confidence_threshold: float

    # PlayerIdentityManager（来自 settings，buffers 由 seconds 换算）
    identity_lost_buffer_frames: int
    identity_inactive_buffer_frames: int
    identity_interpolation_buffer_frames: int
    player_identity_match_threshold: float
    player_identity_max_reconnect_distance_m: float
    player_identity_max_speed_mps: float
    player_identity_court_buffer_m: float
    player_identity_smoothing_window: int

    # PlayerLockManager（来自 settings，bootstrap/lost 由 seconds 换算）
    player_lock_bootstrap_min_frames: int
    player_lock_bootstrap_max_frames: int
    player_lock_lost_grace_frames: int
    player_lock_lost_max_frames_locked: int
    player_lock_min_observed_frames: int
    player_lock_lock_min_hits: int
    player_lock_plausible_min_hits: int
    player_lock_locked_conf: float
    player_lock_tentative_conf: float
    player_lock_searching_conf: float
    player_lock_reconnect_threshold: float
    player_lock_court_margin_ft: float
    player_lock_max_reconnect_distance_ft: float
    player_lock_bootstrap_court_margin_ft: float
    player_lock_lost_reconnect_court_margin_ft: float
    player_lock_enable_appearance_score: bool

    # tracker / suppressor / smoother
    player_duplicate_track_iou_threshold: float
    player_duplicate_track_sustain_frames: int
    position_smoother_alpha: float = 0.45
    position_smoother_max_speed_ft_s: float = 30.0
    position_smoother_max_gap_frames: int = 10


@dataclass
class ViewFrameResult:
    """一次 step 的实时输出，供调用方（pipeline）驱动 debug / ball / pose。"""

    frame_index: int
    timestamp: float
    frame_detections: list[FrameDetection]
    frame_positions: list[PlayerFramePosition]
    render_raw_by_track: dict[int, dict[str, Any]]
    player_motion_pixels: float | None


@dataclass
class ViewTrackingSessionOutputs:
    """结束阶段快照：session 累积的 tracking 产物 + 诊断 + selector 状态。

    调用方据此组装 TrackingResult / PlayerTrajectoryArtifact / PlayerSelectionArtifact /
    渲染轨迹等单视角 artifacts。
    """

    raw_detections: list[Detection]
    tracks: list[Track]
    positions: list[PlayerFramePosition]
    overlay_frames: list[DetectionOverlayFrame]
    render_observations: list[CourtTrackObservation]
    render_events: list[CourtTrackEvent]
    player_multitarget_detections: list[MultiTargetDetection]
    selection_diagnostics: list[Any]
    lock_diagnostics: list[PlayerIdentityDiagnostic]
    latest_selection_training_samples: list[Any]
    roi_filtered_detection_count: int
    full_frame_fallback_count: int
    selector_mode: str
    selector_fallback_reason: str | None


def build_view_tracking_config(
    settings,
    match_context: MatchAnalysisContext | None,
    *,
    fps: float,
    frame_stride: int,
    frame_width: int,
    frame_height: int,
) -> ViewTrackingSessionConfig:
    """把 settings + match_context 解析为 ViewTrackingSessionConfig（逐字段等价迁移）。

    与 `_run_tracking` 1753-1860 行推导块保持一致，作为行为保护的字段核对清单。
    """
    match_ctx = match_context or build_match_context(None)
    group_profile = build_player_group_profile(match_ctx)
    effective_player_count = min(match_ctx.expected_player_count, settings.player_analysis_hard_limit)

    primary_player_window_frames = frames_for_seconds(settings.primary_player_window_seconds, fps)
    identity_lost_buffer_frames = frames_for_seconds(settings.player_identity_lost_buffer_seconds, fps)
    identity_inactive_buffer_frames = frames_for_seconds(settings.player_identity_inactive_buffer_seconds, fps)
    identity_interpolation_buffer_frames = frames_for_seconds(
        settings.player_identity_interpolation_buffer_seconds, fps
    )
    player_lock_bootstrap_min_frames = frames_for_seconds(settings.player_lock_bootstrap_min_seconds, fps)
    player_lock_bootstrap_max_frames = max(
        player_lock_bootstrap_min_frames,
        frames_for_seconds(settings.player_lock_bootstrap_max_seconds, fps),
    )
    player_lock_lost_grace_frames = frames_for_seconds(settings.player_lock_lost_grace_seconds, fps, minimum=0)
    player_lock_lost_max_frames_locked = frames_for_seconds(settings.player_lock_lost_max_seconds_locked, fps)
    position_smoother_max_gap_frames = frames_for_seconds(10.0 / 30.0, fps)

    return ViewTrackingSessionConfig(
        fps=fps,
        frame_stride=max(1, int(frame_stride)),
        frame_width=int(frame_width),
        frame_height=int(frame_height),
        effective_player_count=effective_player_count,
        match_context=match_ctx,
        group_profile=group_profile,
        primary_player_window_frames=primary_player_window_frames,
        primary_player_min_confidence=settings.primary_player_min_confidence,
        primary_player_min_box_area_ratio=settings.primary_player_min_box_area_ratio,
        primary_player_max_box_area_ratio=settings.primary_player_max_box_area_ratio,
        primary_player_court_margin_ft=settings.primary_player_court_margin_ft,
        primary_player_target_court_threshold=settings.primary_player_target_court_threshold,
        primary_player_quality_threshold=settings.primary_player_quality_threshold,
        attention_enabled=settings.enable_attention_player_selector,
        attention_model_path=settings.attention_player_selector_model_path,
        attention_confidence_threshold=settings.attention_player_selector_confidence,
        identity_lost_buffer_frames=identity_lost_buffer_frames,
        identity_inactive_buffer_frames=identity_inactive_buffer_frames,
        identity_interpolation_buffer_frames=identity_interpolation_buffer_frames,
        player_identity_match_threshold=settings.player_identity_match_threshold,
        player_identity_max_reconnect_distance_m=settings.player_identity_max_reconnect_distance_m,
        player_identity_max_speed_mps=settings.player_identity_max_speed_mps,
        player_identity_court_buffer_m=settings.player_identity_court_buffer_m,
        player_identity_smoothing_window=settings.player_identity_smoothing_window,
        player_lock_bootstrap_min_frames=player_lock_bootstrap_min_frames,
        player_lock_bootstrap_max_frames=player_lock_bootstrap_max_frames,
        player_lock_lost_grace_frames=player_lock_lost_grace_frames,
        player_lock_lost_max_frames_locked=player_lock_lost_max_frames_locked,
        player_lock_min_observed_frames=settings.player_lock_min_observed_frames,
        player_lock_lock_min_hits=settings.player_lock_lock_min_hits,
        player_lock_plausible_min_hits=settings.player_lock_plausible_min_hits,
        player_lock_locked_conf=settings.player_lock_locked_conf,
        player_lock_tentative_conf=settings.player_lock_tentative_conf,
        player_lock_searching_conf=settings.player_lock_searching_conf,
        player_lock_reconnect_threshold=settings.player_lock_reconnect_threshold,
        player_lock_court_margin_ft=settings.player_lock_court_margin_ft,
        player_lock_max_reconnect_distance_ft=settings.player_lock_max_reconnect_distance_ft,
        player_lock_bootstrap_court_margin_ft=settings.player_lock_bootstrap_court_margin_ft,
        player_lock_lost_reconnect_court_margin_ft=settings.player_lock_lost_reconnect_court_margin_ft,
        player_lock_enable_appearance_score=settings.player_lock_enable_appearance_score,
        player_duplicate_track_iou_threshold=settings.player_duplicate_track_iou_threshold,
        player_duplicate_track_sustain_frames=settings.player_duplicate_track_sustain_frames,
        position_smoother_max_gap_frames=position_smoother_max_gap_frames,
    )


class ViewTrackingSession:
    """单视角逐帧 tracking 状态容器 + step 算法。"""

    def __init__(
        self,
        *,
        detector: Any,
        homography: list[list[float]],
        roi_artifact: Any,
        config: ViewTrackingSessionConfig,
        tracker: MultiObjectTracker,
        duplicate_suppressor: DuplicateTrackSuppressor,
        footpoint_estimator: FootpointEstimator,
        projector: PlayerProjector,
        position_smoother: CourtPositionSmoother,
        primary_player_selector: PrimaryPlayerSelector,
        player_lock_manager: PlayerLockManager,
        identity_manager: PlayerIdentityManager,
    ) -> None:
        self.detector = detector
        self.homography = homography
        self.roi_artifact = roi_artifact
        self.config = config

        self.tracker = tracker
        self.duplicate_suppressor = duplicate_suppressor
        self.footpoint_estimator = footpoint_estimator
        self.projector = projector
        self.position_smoother = position_smoother
        self.primary_player_selector = primary_player_selector
        self.player_lock_manager = player_lock_manager
        self.identity_manager = identity_manager

        # 累积产物
        self._raw_detections: list[Detection] = []
        self._tracks: list[Track] = []
        self._positions: list[PlayerFramePosition] = []
        self._overlay_frames: list[DetectionOverlayFrame] = []
        self.render_observations: list[CourtTrackObservation] = []
        self.render_events: list[CourtTrackEvent] = []
        self.player_multitarget_detections: list[MultiTargetDetection] = []
        self.selection_diagnostics: list[Any] = []
        self.lock_diagnostics: list[PlayerIdentityDiagnostic] = []
        # 最新快照（每帧覆盖），非累计列表
        self.latest_selection_training_samples: list[Any] = []
        self.roi_filtered_detection_count = 0
        self.full_frame_fallback_count = 0

        # 渲染生命周期内部状态
        self.render_identity_epoch_by_player: dict[str, int] = {}
        self._render_identity_diagnostic_cursor = 0
        self._prev_player_centroids: dict[str, tuple[float, float]] = {}

    # ---- 主接口 -------------------------------------------------------------

    def step(
        self,
        frame: object,
        *,
        frame_index: int,
        timestamp: float,
        guidance: Sequence[Any] = (),
    ) -> ViewFrameResult:
        """推进一帧：完整 tracking 链（检测→…→身份→渲染观测）。默认 guidance=() 时与重构前一致。"""
        _ = guidance  # Change 1：guidance 仅占位，不触发 guided detection

        # 1) 检测
        raw_detections = self._detect_frame(frame, frame_index)
        # 2) ROI 过滤（ROI artifact 由调用方计算、构造时注入）
        detections, roi_filtered = filter_detections_to_roi(raw_detections, self.roi_artifact)
        self.roi_filtered_detection_count += roi_filtered
        if self.roi_artifact.status != "available":
            self.full_frame_fallback_count += 1
        # 2b) guidance → guided re-detection（跨视角 feedback,pre-gate 在 tracker 之前,invariant 2/9）
        if guidance:
            guided = self._run_guided_detection(frame, guidance)
            if guided:
                from app.vision.multiview.guided_detection import merge_base_and_guided

                detections = merge_base_and_guided(detections, guided)
        # 3) 跟踪 + 重复抑制
        tracks = self.tracker.update(detections)
        tracks = self.duplicate_suppressor.filter(tracks)
        # 4) 脚点 + 投影
        footpoints = {
            track.track_id: self.footpoint_estimator.estimate(track, frame_shape=(self.config.frame_width, self.config.frame_height))
            for track in tracks
        }
        frame_positions = self.projector.project(
            tracks=tracks,
            homography=self.homography,
            frame_index=frame_index,
            timestamp=timestamp,
            footpoints=footpoints,
            frame_shape=(self.config.frame_width, self.config.frame_height),
        )
        # 5) 平滑前保存原始球场坐标（供渲染轨迹 / projection debug 使用）
        render_raw_by_track: dict[int, dict[str, Any]] = {}
        for pos in frame_positions:
            if pos.court_position is not None:
                render_raw_by_track[pos.track_id] = {
                    "x_ft": pos.court_position[0],
                    "y_ft": pos.court_position[1],
                    "projection_status": pos.projection_status,
                    "projection_confidence": pos.projection_confidence,
                    "footpoint_method": pos.footpoint_method,
                    "confidence": pos.confidence,
                }
        # 6) 平滑
        for pos in frame_positions:
            if pos.court_position is not None:
                result = self.position_smoother.update(
                    track_id=pos.track_id,
                    frame_index=pos.frame_index,
                    x_ft=pos.court_position[0],
                    y_ft=pos.court_position[1],
                    timestamp=pos.timestamp,
                    confidence=pos.confidence,
                )
                pos.court_position = [result.x, result.y]
        # 7) 主球员选择（建议集合，非硬门控）
        primary_selections = self.primary_player_selector.select(
            tracks=tracks,
            positions=frame_positions,
            frame_width=self.config.frame_width,
            frame_height=self.config.frame_height,
        )
        suggested_track_ids = {selection.track_id for selection in primary_selections}
        self.selection_diagnostics.extend(self.primary_player_selector.last_diagnostics)
        self.latest_selection_training_samples = self.primary_player_selector.last_training_samples
        # 8) 锁定管理 + 合格 track 集合（eligibility 语义保持现状）
        lock_update = self.player_lock_manager.update(
            frame_index=frame_index,
            positions=frame_positions,
            suggestions=primary_selections,
            frame=frame,
            frame_width=self.config.frame_width,
            frame_height=self.config.frame_height,
        )
        self.lock_diagnostics.extend(lock_update.diagnostics)
        eligible_track_ids = lock_update.eligible_track_ids | suggested_track_ids
        # 9) 帧检测（仅主球员集合）
        frame_detections = self._tracks_to_frame_detections(
            tracks,
            frame_index,
            timestamp,
            self.config.frame_width,
            self.config.frame_height,
            eligible_track_ids,
        )
        # 10) 身份管理
        player_samples = self.identity_manager.update(
            frame_index=frame_index,
            positions=frame_positions,
            eligible_track_ids=eligible_track_ids,
            track_identity_hints=lock_update.track_identity_hints,
        )
        player_by_track = {
            sample.track_id: sample.player_id
            for sample in player_samples
            if sample.track_id is not None and sample.tracking_status in ("detected", "tentative")
        }
        tentative_by_track = {
            sample.track_id
            for sample in player_samples
            if sample.track_id is not None and sample.tracking_status == "tentative"
        }
        # 11) 渲染观测（使用当前 epoch；须在 diagnostics 驱动的 epoch 递增之前 —— D2b）
        for pos in frame_positions:
            raw = render_raw_by_track.get(pos.track_id)
            if raw is None:
                continue
            player_id = player_by_track.get(pos.track_id)
            if player_id is None:
                continue
            canonical_id = canonical_player_id(player_id)
            self.render_observations.append(
                CourtTrackObservation(
                    frame_index=frame_index,
                    timestamp_seconds=timestamp,
                    player_id=canonical_id,
                    identity_epoch=self.render_identity_epoch_by_player.get(canonical_id, 0),
                    track_id=pos.track_id,
                    raw_x_ft=raw["x_ft"],
                    raw_y_ft=raw["y_ft"],
                    confidence=raw["confidence"],
                    projection_status=raw["projection_status"],
                    projection_confidence=raw["projection_confidence"],
                    footpoint_method=raw["footpoint_method"],
                    lock_state=None,
                    tracking_status="tentative" if pos.track_id in tentative_by_track else "detected",
                )
            )
        # 12) 帧检测标注 player_id（pose 消费）
        for detection in frame_detections:
            if detection.track_id is None:
                continue
            player_id = player_by_track.get(int(detection.track_id))
            if player_id is not None:
                detection.player_id = player_id
                detection.label = player_id.replace("Player_", "P")

        # 累积
        self._raw_detections.extend(raw_detections)
        self._overlay_frames.append(
            DetectionOverlayFrame(
                frame_index=frame_index,
                timestamp_seconds=timestamp,
                detections=frame_detections,
            )
        )
        for detection in frame_detections:
            try:
                self.player_multitarget_detections.append(
                    MultiTargetDetection(
                        frame_index=frame_index,
                        timestamp_seconds=timestamp,
                        class_name="player",
                        bbox=[float(value) for value in detection.bbox],
                        confidence=float(detection.confidence),
                        source_width=max(1, self.config.frame_width),
                        source_height=max(1, self.config.frame_height),
                        track_id=str(detection.track_id) if detection.track_id is not None else None,
                    )
                )
            except ValueError:
                pass
        self._tracks.extend(tracks)
        self._positions.extend(frame_positions)

        # 13) 球员帧间位移（供球追踪的静止误检抑制）
        player_motion_pixels = self._compute_player_motion_pixels(frame_detections)

        # 14) 生命周期事件（须在渲染观测生成之后处理 diagnostics —— D2b）
        new_diags = self.identity_manager.diagnostics[self._render_identity_diagnostic_cursor:]
        self._render_identity_diagnostic_cursor = len(self.identity_manager.diagnostics)
        for diag in new_diags:
            event_type = _RENDER_EVENT_MAPPING.get(diag.event)
            if event_type is None:
                continue
            diag_player_id = canonical_player_id(diag.player_id) if diag.player_id else ""
            self.render_events.append(
                CourtTrackEvent(
                    frame_index=frame_index,
                    timestamp_seconds=timestamp,
                    player_id=diag_player_id,
                    event_type=event_type,
                    reason=diag.reason,
                )
            )
            if diag.event == "player_reset_after_prolonged_loss" and diag.player_id:
                epoch_player = canonical_player_id(diag.player_id)
                self.render_identity_epoch_by_player[epoch_player] = (
                    self.render_identity_epoch_by_player.get(epoch_player, 0) + 1
                )
        for lock_diag in lock_update.diagnostics:
            lock_event_type = _RENDER_EVENT_MAPPING.get(lock_diag.event)
            if lock_event_type is None:
                continue
            lock_player_id = canonical_player_id(lock_diag.player_id) if lock_diag.player_id else ""
            self.render_events.append(
                CourtTrackEvent(
                    frame_index=frame_index,
                    timestamp_seconds=timestamp,
                    player_id=lock_player_id,
                    event_type=lock_event_type,
                    reason=lock_diag.reason,
                )
            )
            if lock_diag.event == "player_reset_after_prolonged_loss" and lock_diag.player_id:
                epoch_player = canonical_player_id(lock_diag.player_id)
                self.render_identity_epoch_by_player[epoch_player] = (
                    self.render_identity_epoch_by_player.get(epoch_player, 0) + 1
                )

        return ViewFrameResult(
            frame_index=frame_index,
            timestamp=timestamp,
            frame_detections=frame_detections,
            frame_positions=frame_positions,
            render_raw_by_track=render_raw_by_track,
            player_motion_pixels=player_motion_pixels,
        )

    # ---- 结束阶段窄接口 -----------------------------------------------------

    def snapshot(self) -> ViewTrackingSessionOutputs:
        """结束阶段快照：累积产物 + selector 状态（供 pipeline 组装 artifacts）。"""
        return ViewTrackingSessionOutputs(
            raw_detections=self._raw_detections,
            tracks=self._tracks,
            positions=self._positions,
            overlay_frames=self._overlay_frames,
            render_observations=self.render_observations,
            render_events=self.render_events,
            player_multitarget_detections=self.player_multitarget_detections,
            selection_diagnostics=self.selection_diagnostics,
            lock_diagnostics=self.lock_diagnostics,
            latest_selection_training_samples=self.latest_selection_training_samples,
            roi_filtered_detection_count=self.roi_filtered_detection_count,
            full_frame_fallback_count=self.full_frame_fallback_count,
            selector_mode=self.primary_player_selector.last_selection_mode,
            selector_fallback_reason=self.primary_player_selector.last_fallback_reason,
        )

    def build_player_trajectory_artifact(
        self,
        *,
        job_id: str,
        video_id: str | None,
        fps: float,
        frame_count: int,
        processed_frame_count: int,
        frame_stride: int,
    ) -> PlayerTrajectoryArtifact:
        """构建球员轨迹 artifact，并原样合并 lock diagnostics（与重构前一致）。"""
        artifact = self.identity_manager.to_artifact(
            job_id=job_id,
            video_id=video_id,
            fps=fps,
            frame_count=frame_count,
            processed_frame_count=processed_frame_count,
            frame_stride=frame_stride,
        )
        if self.lock_diagnostics:
            all_diagnostics = [*artifact.diagnostics, *self.lock_diagnostics]
            artifact.diagnostics = sorted(
                all_diagnostics,
                key=lambda diagnostic: (
                    diagnostic.frame_index,
                    diagnostic.track_id is None,
                    diagnostic.track_id if diagnostic.track_id is not None else -1,
                    diagnostic.event,
                ),
            )
            if artifact.coverage is not None:
                diagnostic_event_counts: dict[str, int] = {}
                for diagnostic in artifact.diagnostics:
                    diagnostic_event_counts[diagnostic.event] = (
                        diagnostic_event_counts.get(diagnostic.event, 0) + 1
                    )
                artifact.coverage.diagnostic_event_counts = diagnostic_event_counts
        return artifact

    def projected_metric_tracks(self, output_court_unit: str = "ft") -> list[ProjectedTrackPoint]:
        """身份层投影轨迹点（供指标计算；ft 为与现状一致的输出单位）。"""
        return self.identity_manager.to_projected_track_points(output_court_unit=output_court_unit)

    # ---- 内部 ---------------------------------------------------------------

    def _detect_frame(self, frame: object, frame_index: int) -> list[Detection]:
        # 统一检测入口（兼容 detect_frame / detect 两种接口）。
        if hasattr(self.detector, "detect_frame"):
            return self.detector.detect_frame(frame, frame_index)
        return self.detector.detect(frame)

    def _run_guided_detection(self, frame: object, guidance) -> list[Detection]:
        """按跨视角 guidance 对目标 ROI 做 guided re-detection,pre-gate 后返回 accepted。

        只在本 session 的检测链内使用(在 tracker.update 之前);pre-gate 拒绝的 candidate 不触碰 tracker。
        """
        from app.vision.multiview.guided_detection import guided_candidate_pre_gate

        accepted: list[Detection] = []
        for g in guidance:
            roi = getattr(g, "roi", None)
            predicted = getattr(g, "predicted_canonical_position", None)
            if roi is None or predicted is None:
                continue
            try:
                candidates = self.detector.detect_regions(frame, [roi])
            except Exception:
                continue
            for d in candidates:
                gated = guided_candidate_pre_gate(
                    d,
                    homography=self.homography,
                    predicted_canonical=predicted,
                    max_residual_ft=3.0,
                    frame_width=self.config.frame_width,
                    frame_height=self.config.frame_height,
                )
                if gated.accepted:
                    accepted.append(d)
        return accepted

    @staticmethod
    def _tracks_to_frame_detections(
        tracks,
        frame_index: int,
        timestamp: float,
        frame_width: int,
        frame_height: int,
        eligible_track_ids: set[int] | None = None,
    ) -> list[FrameDetection]:
        # 把"跟踪轨迹"转成"帧检测"列表，过滤丢失的与不在主球员集合里的。
        source_width = max(1, int(frame_width))
        source_height = max(1, int(frame_height))
        return [
            FrameDetection(
                frame_index=frame_index,
                timestamp_seconds=timestamp,
                bbox=track.bbox,
                confidence=track.confidence,
                track_id=str(track.track_id),
                source_width=source_width,
                source_height=source_height,
            )
            for track in tracks
            if not track.lost and (eligible_track_ids is None or track.track_id in eligible_track_ids)
        ]

    def _compute_player_motion_pixels(self, frame_detections: list[FrameDetection]) -> float | None:
        # 球员帧间质心最大位移（供球检测静止抑制）。
        player_motion_pixels: float | None = None
        if frame_detections:
            current_centroids: dict[str, tuple[float, float]] = {}
            for det in frame_detections:
                if det.track_id is not None:
                    x1, y1, x2, y2 = det.bbox
                    current_centroids[det.track_id] = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            if self._prev_player_centroids and current_centroids:
                max_displacement = 0.0
                for track_id, (cx, cy) in current_centroids.items():
                    if track_id in self._prev_player_centroids:
                        px, py = self._prev_player_centroids[track_id]
                        disp = hypot(cx - px, cy - py)
                        if disp > max_displacement:
                            max_displacement = disp
                if max_displacement > 0:
                    player_motion_pixels = max_displacement
            self._prev_player_centroids = current_centroids
        return player_motion_pixels


def build_view_tracking_session(
    *,
    detector: Any,
    homography: list[list[float]],
    roi_artifact: Any,
    config: ViewTrackingSessionConfig,
    tracker: MultiObjectTracker | None = None,
    footpoint_estimator: FootpointEstimator | None = None,
    projector: PlayerProjector | None = None,
) -> ViewTrackingSession:
    """解析/构造 components 并装配 ViewTrackingSession（保留依赖注入语义）。

    单摄适配：`tracker = self.tracker or MultiObjectTracker(...)`、`footpoint_estimator`、
    `projector` 注入优先。P1 双摄可各自调用本工厂，但共享同一 `PersonDetector` 实例。
    """
    primary_player_selector = PrimaryPlayerSelector(
        min_confidence=config.primary_player_min_confidence,
        max_subjects=config.effective_player_count,
        min_box_area_ratio=config.primary_player_min_box_area_ratio,
        max_box_area_ratio=config.primary_player_max_box_area_ratio,
        court_margin_ft=config.primary_player_court_margin_ft,
        window_frames=config.primary_player_window_frames,
        target_court_threshold=config.primary_player_target_court_threshold,
        quality_threshold=config.primary_player_quality_threshold,
        attention_enabled=config.attention_enabled,
        attention_model_path=config.attention_model_path,
        attention_confidence_threshold=config.attention_confidence_threshold,
        group_profile=config.group_profile,
        near_side_quota=config.match_context.near_side_quota,
        far_side_quota=config.match_context.far_side_quota,
    )
    resolved_tracker = tracker or MultiObjectTracker(max_lost=config.identity_lost_buffer_frames)
    duplicate_suppressor = DuplicateTrackSuppressor(
        iou_threshold=config.player_duplicate_track_iou_threshold,
        sustain_frames=config.player_duplicate_track_sustain_frames,
    )
    resolved_footpoint = footpoint_estimator or FootpointEstimator()
    resolved_projector = projector or PlayerProjector(
        footpoint_estimator=resolved_footpoint,
        include_invalid=True,
        drop_outside_tracking=False,
    )
    identity_manager = PlayerIdentityManager(
        PlayerIdentityConfig(
            max_players=config.effective_player_count,
            fps=config.fps,
            match_threshold=config.player_identity_match_threshold,
            max_reconnect_distance_m=config.player_identity_max_reconnect_distance_m,
            max_speed_mps=config.player_identity_max_speed_mps,
            lost_buffer_frames=config.identity_lost_buffer_frames,
            inactive_buffer_frames=config.identity_inactive_buffer_frames,
            interpolation_buffer_frames=config.identity_interpolation_buffer_frames,
            court_buffer_m=config.player_identity_court_buffer_m,
            input_court_unit="ft",
            smoothing_window=config.player_identity_smoothing_window,
        )
    )
    player_lock_manager = PlayerLockManager(
        PlayerLockConfig(
            fps=config.fps,
            target_player_count=config.effective_player_count,
            near_side_quota=config.match_context.near_side_quota,
            far_side_quota=config.match_context.far_side_quota,
            bootstrap_min_frames=config.player_lock_bootstrap_min_frames,
            bootstrap_max_frames=config.player_lock_bootstrap_max_frames,
            min_observed_frames=config.player_lock_min_observed_frames,
            lock_min_hits=config.player_lock_lock_min_hits,
            plausible_min_hits=config.player_lock_plausible_min_hits,
            lost_grace_frames=config.player_lock_lost_grace_frames,
            lost_max_frames_locked=config.player_lock_lost_max_frames_locked,
            locked_conf=config.player_lock_locked_conf,
            tentative_conf=config.player_lock_tentative_conf,
            searching_conf=config.player_lock_searching_conf,
            reconnect_threshold=config.player_lock_reconnect_threshold,
            court_margin_ft=config.player_lock_court_margin_ft,
            max_reconnect_distance_ft=config.player_lock_max_reconnect_distance_ft,
            bootstrap_court_margin_ft=config.player_lock_bootstrap_court_margin_ft,
            lost_reconnect_court_margin_ft=config.player_lock_lost_reconnect_court_margin_ft,
            enable_appearance_score=config.player_lock_enable_appearance_score,
        )
    )
    position_smoother = CourtPositionSmoother(
        alpha=config.position_smoother_alpha,
        max_speed_ft_s=config.position_smoother_max_speed_ft_s,
        max_gap_frames=config.position_smoother_max_gap_frames,
        frame_stride=config.frame_stride,
    )
    return ViewTrackingSession(
        detector=detector,
        homography=homography,
        roi_artifact=roi_artifact,
        config=config,
        tracker=resolved_tracker,
        duplicate_suppressor=duplicate_suppressor,
        footpoint_estimator=resolved_footpoint,
        projector=resolved_projector,
        position_smoother=position_smoother,
        primary_player_selector=primary_player_selector,
        player_lock_manager=player_lock_manager,
        identity_manager=identity_manager,
    )
