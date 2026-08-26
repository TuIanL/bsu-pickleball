"""分析流水线 —— MVP 版本的端到端视频分析流程（检测→跟踪→投影→指标计算→可视化）。

这是整个后端"分析"的核心。给定一段视频 + 一份标定，它会：
1. 逐帧读取（按 frame_stride 抽帧）；
2. 跑人体检测（YOLO）+ 多目标跟踪，把每帧的人连成轨迹；
3. 用标定矩阵把"画面脚点"投影成"球场坐标"；
4. 选出主球员、做姿态识别、检测发球开始；
5. 计算移动距离/速度/厨房区/双打间距/热力图等指标；
6. 把所有结果写成 JSON 产物，并返回给上层。

如果缺视频或标定，会走"mock/demo"分支，返回确定性的占位结果，
保证前端在 MVP 阶段也有东西可展示。
"""

from __future__ import annotations

import csv
import logging
import os
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from math import hypot
from pathlib import Path
from typing import Any, Protocol

from app.core.config import get_settings
from app.schemas.analysis import MatchAnalysisContext, build_match_context
from app.schemas.calibration import CalibrationKeypoint, ImagePoint
from app.schemas.court_view import CourtViewRoiArtifact, CourtViewThresholds
from app.schemas.events import ServeDebugArtifactRefs, ServeEventsArtifact
from app.schemas.metrics import MetricStatus, PerformanceMetrics
from app.schemas.multitarget import MultiTargetDetection
from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult, PipelineStageResult
from app.schemas.pose import PoseOverlayArtifact, default_skeleton_edges
from app.schemas.tracking import (
    PlayerFramePosition,
    PlayerSelectionArtifact,
    PlayerTrajectoryArtifact,
    ProjectedCourtPoint2D,
    ProjectedTrackPoint,
    SourceFrameSize,
    TrackingOverlayArtifact,
    TrackingResult,
)
from app.services.calibration_service import CalibrationService
from app.services.analysis_window import AnalysisWindowError, resolve_analysis_window
from app.services.frame_timing_provider import FrameTimingProvider
from app.services.storage_service import StorageService
from app.services.video_service import VideoMetadata, VideoService
from app.utils.fps import frames_for_seconds, resolve_effective_fps
from app.vision.court_view import (
    CourtViewFrameScorer,
    CourtViewStateMachine,
    RoiComputationConfig,
    build_court_view_roi_artifact,
    compute_expanded_detection_roi,
    filter_detections_to_roi,
)

# 视觉引擎：球场几何、球场视角评分、各项性能指标、跟踪与姿态相关组件
from app.vision.courtvision_calibration_engine.court_geometry import standard_court

# 可配置的球检测适配器（缺失模型/依赖时抛出清晰错误，由 pipeline 降级为 unavailable）
from app.vision.detectors.ball_adapter import (
    BallDetectionModelMissingError,
    YoloBallDetectorAdapter,
)
from app.vision.events.serve_start_detector import ServeStartDetector, ServeStartDetectorConfig

# 球分析引擎（detector-agnostic，仅在启用球分析时参与）：轨迹、清洗、弹跳、球场投影
from app.vision.pickleball_game_analysis.ball_tracker import BallTracker
from app.vision.pickleball_game_analysis.bounce_detector import BounceDetector, BounceDetectorConfig
from app.vision.pickleball_game_analysis.calibration_diagnostics import CalibrationDiagnostics
from app.vision.pickleball_game_analysis.court_adapter import BallCourtAdapter
from app.vision.pickleball_game_analysis.court_track_postprocessor import CourtTrackPostProcessor
from app.vision.pickleball_game_analysis.court_track_types import (
    RenderSlotOverflowError,
)
from app.vision.pickleball_game_analysis.detection_writer import (
    build_ball_overlay_payload,
    build_bounce_events_payload,
    build_cleaned_trajectory_payload,
    build_raw_trajectory_payload,
)
from app.vision.pickleball_game_analysis.effective_time_windows import resolve_effective_windows
from app.vision.pickleball_game_analysis.ball_semantic_search_policy import (
    BallBoundaryAction,
    BallSearchDecision,
    BallSearchPolicy,
    BallSemanticPolicyConfig,
    MatchSemanticSnapshot,
    SemanticAuthority,
    SemanticPolicyMode,
    SemanticTimelineProvider,
    build_semantic_timeline_payload,
    serve_candidate_semantic_snapshot,
)
from app.vision.pickleball_game_analysis.semantic_boundary_calibration import (
    build_semantic_boundary_evaluation_payload,
)
from app.vision.pickleball_game_analysis.minimap_visualizer import MinimapVisualizer
from app.vision.pickleball_game_analysis.overlay_video_writer import OverlayVideoWriter
from app.vision.pickleball_game_analysis.player_attribution_context import build_player_attribution_context
from app.vision.pickleball_game_analysis.position_visualizer import PositionVisualizer
from app.vision.pickleball_game_analysis.projection_debug_overlay_writer import ProjectionDebugOverlayWriter
from app.vision.pickleball_game_analysis.projection_debug_writer import ProjectionDebugWriter
from app.vision.pickleball_game_analysis.reconstruction_engine import reconstruct_ball_trajectory
from app.vision.pickleball_game_analysis.reconstruction_schemas import ReconstructionConfig
from app.vision.pickleball_game_analysis.schemas import BallFrameSample, BounceEvent, TrajectoryPoint
from app.vision.pickleball_game_analysis.trajectory_cleaner import TrajectoryCleaner, TrajectoryCleanerConfig
from app.vision.pickleball_game_analysis.visualization_data_builder import PositionVisualizationDataBuilder
from app.vision.pickleball_game_analysis.visualization_schemas import (
    VisualizationConfig,
    VisualizationResult,
    ball_points_from_artifact,
    bounce_points_from_artifact,
    load_render_profiles,
    player_points_from_artifact,
    player_render_points_from_artifact,
    serialize_render_trajectory_v2,
)
from app.vision.pickleball_performance_engine.doubles_spacing_metrics import doubles_spacing
from app.vision.pickleball_performance_engine.heatmap_generator import generate_heatmap
from app.vision.pickleball_performance_engine.metric_inputs import standard_court_metric_points
from app.vision.pickleball_performance_engine.speed_metrics import speed_summaries
from app.vision.pickleball_performance_engine.trajectory_metrics import total_distances
from app.vision.pickleball_performance_engine.zone_metrics import kitchen_dwell
from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator
from app.vision.player_tracking_engine.multi_object_tracker import MultiObjectTracker
from app.vision.player_tracking_engine.person_detector import EmptyPersonDetector, PersonDetector
from app.vision.player_tracking_engine.player_projector import PlayerProjector
from app.vision.player_tracking_engine.primary_player_selector import PrimaryPlayerSelector
from app.vision.player_tracking_engine.view_tracking_session import (
    build_view_tracking_config,
    build_view_tracking_session,
)
from app.vision.pose.rtmpose26_adapter import RTMPose26Adapter

logger = logging.getLogger(__name__)


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").lower() in {"1", "true", "yes"}


def _timing_provider_for_video(path: Path) -> FrameTimingProvider:
    """Probe media once for clip/debug exports and retain explicit fallback metadata."""
    import cv2  # type: ignore

    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        return FrameTimingProvider.nominal(frame_count=0, fps=1.0, media_path=path)
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    finally:
        capture.release()
    return FrameTimingProvider.from_media(path, frame_count=frame_count, fps=fps or 25.0)


# 进度回调类型：每完成一个阶段就调用一次
ProgressCallback = Callable[[PipelineStageResult], None]


class CancellationToken(Protocol):
    # 取消令牌协议（Protocol = 结构化类型，只要实现了 raise_if_cancelled 就满足）。
    def raise_if_cancelled(self) -> None: ...


def _render_track_list_to_players(render_tracks: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    players: dict[str, list[dict[str, Any]]] = {}
    for rf in render_tracks:
        pid = rf["player_id"]
        if pid not in players:
            players[pid] = []
        players[pid].append(
            {
                "frame_index": rf["frame_index"],
                "timestamp_seconds": rf["timestamp_seconds"],
                "x_ft": rf["x_ft"],
                "y_ft": rf["y_ft"],
                "source": rf["source"],
                "confidence": rf["confidence"],
            }
        )
    for pid in players:
        players[pid].sort(key=lambda p: p["frame_index"])
    return players


@dataclass
class _BallRunOutput:
    # 球分析运行的内部汇总输出（仅在启用球分析时由 _run_tracking 产生）。
    status: str = "skipped"  # available / unavailable / failed / skipped
    samples: list[BallFrameSample] = field(default_factory=list)
    ball_detections: list[MultiTargetDetection] = field(default_factory=list)
    raw_points: list[TrajectoryPoint] | None = None
    cleaned_points: list[TrajectoryPoint] | None = None
    bounce_events: list[BounceEvent] | None = None
    accepted_count: int = 0
    error: str | None = None
    semantic_snapshots: list[MatchSemanticSnapshot] = field(default_factory=list)
    semantic_decisions: list[BallSearchDecision] = field(default_factory=list)
    semantic_diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass
class _BallArtifactFields:
    # 球相关 artifact 路径/URL/状态/说明的收集器，供 AnalysisArtifacts 装配。
    detections_jsonl_path: str | None = None
    detections_url: str | None = None
    detections_status: str | None = None
    detections_detail: str | None = None
    ball_overlay_json_path: str | None = None
    ball_overlay_url: str | None = None
    ball_overlay_status: str | None = None
    ball_overlay_detail: str | None = None
    ball_trajectory_json_path: str | None = None
    ball_trajectory_url: str | None = None
    ball_trajectory_status: str | None = None
    ball_trajectory_detail: str | None = None
    cleaned_ball_trajectory_json_path: str | None = None
    cleaned_ball_trajectory_url: str | None = None
    cleaned_ball_trajectory_status: str | None = None
    cleaned_ball_trajectory_detail: str | None = None
    bounce_events_json_path: str | None = None
    bounce_events_url: str | None = None
    bounce_events_status: str | None = None
    bounce_events_detail: str | None = None
    reconstructed_ball_trajectory_json_path: str | None = None
    reconstructed_ball_trajectory_url: str | None = None
    reconstructed_ball_trajectory_status: str | None = None
    reconstructed_ball_trajectory_detail: str | None = None
    ball_semantic_timeline_json_path: str | None = None
    ball_semantic_timeline_url: str | None = None
    ball_semantic_timeline_status: str | None = None
    ball_semantic_timeline_detail: str | None = None
    ball_semantic_boundary_eval_json_path: str | None = None
    ball_semantic_boundary_eval_url: str | None = None
    ball_semantic_boundary_eval_status: str | None = None
    ball_semantic_boundary_eval_detail: str | None = None


@dataclass
class _VisualizationArtifactFields:
    analysis_overlay_video_path: str | None = None
    analysis_overlay_video_url: str | None = None
    analysis_overlay_video_status: str | None = None
    analysis_overlay_video_detail: str | None = None
    analysis_overlay_video_metadata: dict[str, Any] | None = None
    heatmaps_manifest_json_path: str | None = None
    heatmaps_url: str | None = None
    scatter_plots_manifest_json_path: str | None = None
    scatter_plots_url: str | None = None
    position_visualizations_status: str | None = None
    position_visualizations_detail: str | None = None
    stage_status: str = "skipped"
    stage_detail: str = "可视化输出未启用"


@dataclass
class _BounceRunOutput:
    """弹跳检测后处理的汇总输出。"""

    cleaned_points: list[TrajectoryPoint] | None = None
    bounce_events: list[BounceEvent] | None = None
    bounce_count: int = 0
    input_sample_count: int = 0
    cleaned_sample_count: int = 0
    interpolated_sample_count: int = 0
    status: str = "skipped"  # available / no_candidates / skipped / failed
    detail: str = ""


@dataclass
class _BallRunContext:
    """逐帧球检测的运行时上下文（局部状态，不污染 AnalysisPipeline 实例）。"""

    tracker: BallTracker | None = None
    samples: list[BallFrameSample] = field(default_factory=list)
    detections: list[MultiTargetDetection] = field(default_factory=list)
    error: str | None = None
    disabled_reason: str | None = None
    semantic_provider: SemanticTimelineProvider | None = None
    semantic_policy: BallSearchPolicy | None = None
    semantic_evidence: dict[str, Any] = field(default_factory=dict)
    semantic_snapshots: list[MatchSemanticSnapshot] = field(default_factory=list)
    semantic_decisions: list[BallSearchDecision] = field(default_factory=list)
    semantic_raw_candidate_count: int = 0
    semantic_suppressed_count: int = 0
    semantic_fallback_count: int = 0
    semantic_hard_gate_active: bool = False
    semantic_boundary_events: list[dict[str, Any]] = field(default_factory=list)
    semantic_formal_candidate_before_count: int = 0
    semantic_formal_candidate_after_count: int = 0
    semantic_warm_capture_count: int = 0
    semantic_formal_publish_count: int = 0
    semantic_segment_ids: list[str] = field(default_factory=list)


@dataclass
class _TrackingRunOutput:
    # 一次跟踪运行的内部汇总输出（多个产物打包在一起，方便 run() 使用）。
    tracking: TrackingResult
    player_trajectories: PlayerTrajectoryArtifact | None = None
    player_metric_tracks: list[ProjectedTrackPoint] | None = None
    player_selection: PlayerSelectionArtifact | None = None
    pose: PoseOverlayArtifact | None = None
    pose_stage: PipelineStageResult | None = None
    pose_frames: list[Any] | None = None
    court_view_roi: CourtViewRoiArtifact | None = None
    ball_run_output: _BallRunOutput | None = None
    player_multitarget_detections: list[MultiTargetDetection] = field(default_factory=list)
    calibration_diagnostics_path: str | None = None
    render_trajectory: list[dict[str, Any]] | None = None
    requested_clip: dict[str, int] | None = None
    decoded_range: dict[str, int] | None = None
    analysis_window: dict[str, Any] = field(default_factory=dict)


class PipelineConfigurationError(ValueError): ...


class AnalysisPipeline:
    """MVP 分析流水线：当视频和标定都可用时，执行真实的球员跟踪。"""

    def __init__(
        self,
        video_service: VideoService | None = None,
        calibration_service: CalibrationService | None = None,
        storage: StorageService | None = None,
        detector: Any | None = None,
        tracker: MultiObjectTracker | None = None,
        footpoint_estimator: FootpointEstimator | None = None,
        projector: PlayerProjector | None = None,
        primary_player_selector: PrimaryPlayerSelector | None = None,
        pose_estimator: Any | None = None,
        serve_start_detector: ServeStartDetector | None = None,
        ball_detector: Any | None = None,
        frame_stride: int | None = None,
        # 任务级推理开关：None 表示沿用后端全局配置（enable_model_inference / enable_pose_inference）
        enable_model_inference: bool | None = None,
        enable_pose_inference: bool | None = None,
    ) -> None:
        self.video_service = video_service or VideoService()
        self.calibration_service = calibration_service or CalibrationService()
        self.storage = storage or StorageService()
        self.settings = get_settings()
        # 解析任务级覆盖：显式传入时优先，否则用全局配置
        self._enable_model_inference = (
            self.settings.enable_model_inference if enable_model_inference is None else enable_model_inference
        )
        self._enable_pose_inference = (
            self.settings.enable_pose_inference if enable_pose_inference is None else enable_pose_inference
        )
        # 检测器：没注入就按配置创建；如果关闭模型推理，则用一个"空检测器"（不真跑模型）
        detector_was_injected = detector is not None
        self.detector = detector or (
            PersonDetector(
                model_path=self.settings.default_detector_model,
                conf_threshold=self.settings.detector_confidence,
                device=self.settings.detector_device,
            )
            if self._enable_model_inference
            else EmptyPersonDetector()
        )
        self.model_inference_enabled = (
            not isinstance(self.detector, EmptyPersonDetector)
            if detector_was_injected
            else self._enable_model_inference
        )
        self.tracker = tracker
        self.footpoint_estimator = footpoint_estimator or FootpointEstimator()
        self.projector = projector or PlayerProjector(
            footpoint_estimator=self.footpoint_estimator,
            include_invalid=True,
            drop_outside_tracking=False,
        )
        # 姿态估计器：按配置创建 RTMPose26 适配器，关闭时设为 None
        self.pose_estimator = pose_estimator or (
            RTMPose26Adapter(
                config_path=self.settings.rtmpose_config_path,
                checkpoint_path=self.settings.rtmpose_checkpoint_path,
                device=self.settings.rtmpose_device,
                conf_threshold=self.settings.pose_confidence,
                conf_exit_threshold=self.settings.pose_confidence_exit,
                keypoint_schema=self.settings.pose_keypoint_schema,
            )
            if self._enable_pose_inference
            else None
        )
        # 发球开始检测器
        self.serve_start_detector = serve_start_detector or ServeStartDetector(
            ServeStartDetectorConfig(
                min_gap_seconds=self.settings.serve_min_gap_seconds,
                pre_roll_seconds=self.settings.serve_clip_pre_seconds,
                baseline_margin_ft=self.settings.serve_baseline_margin_ft,
                pre_still_window_seconds=self.settings.serve_pre_still_window_seconds,
                pre_still_gap_seconds=self.settings.serve_pre_still_gap_seconds,
                post_rally_window_seconds=self.settings.serve_post_rally_window_seconds,
                pose_smooth_window_frames=self.settings.serve_pose_smooth_window_frames,
                clip_pre_seconds=self.settings.serve_clip_pre_seconds,
                clip_post_seconds=self.settings.serve_clip_post_seconds,
            )
        )
        self.pose_inference_enabled = self.pose_estimator is not None
        # 球检测适配器：按配置接入；未注入则尝试用配置的模型路径构建 YOLO 适配器。
        # 缺失模型/依赖时只记录原因并降级为 unavailable，不中断任务。
        self.ball_detection_enabled = self.settings.enable_ball_detection
        self.ball_detector = ball_detector
        self.ball_detection_unavailable_reason: str | None = None
        self.ball_analysis_strict = self.settings.ball_analysis_strict
        if self.ball_detection_enabled and self.ball_detector is None:
            if self.settings.ball_model_path:
                try:
                    self.ball_detector = YoloBallDetectorAdapter(
                        model_path=self.settings.ball_model_path,
                        confidence_threshold=self.settings.detector_confidence or 0.18,
                        device=self.settings.detector_device,
                    )
                except BallDetectionModelMissingError as exc:
                    self.ball_detection_unavailable_reason = str(exc)
                except Exception as exc:  # 其它初始化异常也降级，不中断主流程
                    self.ball_detection_unavailable_reason = f"球检测适配器初始化失败：{exc}"
            else:
                self.ball_detection_unavailable_reason = (
                    "未配置球检测模型路径（PICKLEBALL_BALL_MODEL_PATH），球检测不可用"
                )
        # 抽帧步长：至少 1
        self.frame_stride = max(1, int(frame_stride or self.settings.overlay_frame_stride))

    def run(
        self,
        job_id: str,
        video_id: str | None,
        calibration_id: str | None = None,
        frame_stride: int | None = None,
        source_fps: float | None = None,
        court_view_match_threshold: float | None = None,
        match_context: MatchAnalysisContext | None = None,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        clip_start_ms: int | None = None,
        clip_end_ms: int | None = None,
        capture_take_id: str | None = None,
    ) -> AnalysisPipelineResult:
        # 流水线主入口。根据"有没有视频 / 有没有标定"分三条路径：
        #   A) 有视频 + 有标定 → 跑真实跟踪（最完整）
        #   B) 有视频 + 无标定 → 只做有限阶段（跳过需要标定的部分）
        #   C) 无视频（demo）→ 返回确定性 mock 轨迹
        match_ctx = match_context or build_match_context(None)
        if match_ctx.expected_player_count > self.settings.player_analysis_hard_limit:
            raise PipelineConfigurationError(
                f"系统球员分析容量不足：比赛需要 {match_ctx.expected_player_count} 人，"
                f"配置上限 {self.settings.player_analysis_hard_limit} 人"
            )

        stages: list[PipelineStageResult] = []
        ball_run_output: _BallRunOutput | None = None
        ball_fields = _BallArtifactFields()
        player_multitarget_detections: list[MultiTargetDetection] = []
        analysis_window_metadata: dict[str, Any] | None = None
        self._check_cancelled(cancellation_token)
        video = self.video_service.get_video(video_id) if video_id else None

        if video_id and video is None:
            # 指定了 video_id 却找不到视频 → 直接判失败
            result = self._failed(job_id, video_id, calibration_id, "Uploaded video not found")
            self._write_result(result)
            return result

        video_stage = self._stage(
            "video-read", "读取视频", "done", "视频元数据已加载" if video else "未提供视频，使用 MVP mock 轨迹"
        )
        stages.append(video_stage)
        self._notify_progress(progress_callback, video_stage)
        self._check_cancelled(cancellation_token)

        calibration = self.calibration_service.get_calibration(calibration_id) if calibration_id else None
        calibration_stage = self._stage(
            "calibration",
            "场地标定",
            "done" if calibration else "skipped",
            "已加载手工标定" if calibration else "未提供标定，使用标准场地 mock 轨迹",
        )
        stages.append(calibration_stage)
        self._notify_progress(progress_callback, calibration_stage)
        self._check_cancelled(cancellation_token)

        # 下面这一大堆变量，用来收集各产物的"路径 / URL / 状态 / 说明"，
        # 最后统一塞进 AnalysisArtifacts 返回。先全部初始化为 None。
        source_video_url = f"/api/videos/{video_id}/stream" if video_id else None
        tracking_artifact_path: str | None = None
        tracking_overlay_artifact_path: str | None = None
        tracking_overlay_url: str | None = None
        tracking_overlay_status: str | None = None
        tracking_overlay_detail: str | None = None
        player_selection_path: str | None = None
        player_selection_url: str | None = None
        player_selection_training_samples_path: str | None = None
        player_selection_training_samples_url: str | None = None
        player_selection_status: str | None = None
        player_selection_detail: str | None = None
        detections_jsonl_path: str | None = None
        detections_url: str | None = None
        detections_status: str | None = None
        detections_detail: str | None = None
        ball_overlay_json_path: str | None = None
        ball_overlay_url: str | None = None
        ball_overlay_status: str | None = None
        ball_overlay_detail: str | None = None
        ball_trajectory_json_path: str | None = None
        ball_trajectory_url: str | None = None
        ball_trajectory_status: str | None = None
        ball_trajectory_detail: str | None = None
        cleaned_ball_trajectory_json_path: str | None = None
        cleaned_ball_trajectory_url: str | None = None
        cleaned_ball_trajectory_status: str | None = None
        cleaned_ball_trajectory_detail: str | None = None
        bounce_events_json_path: str | None = None
        bounce_events_url: str | None = None
        bounce_events_status: str | None = None
        bounce_events_detail: str | None = None
        analysis_overlay_video_path: str | None = None
        analysis_overlay_video_url: str | None = None
        analysis_overlay_video_status: str | None = None
        analysis_overlay_video_detail: str | None = None
        heatmaps_manifest_json_path: str | None = None
        heatmaps_url: str | None = None
        scatter_plots_manifest_json_path: str | None = None
        scatter_plots_url: str | None = None
        position_visualizations_status: str | None = None
        position_visualizations_detail: str | None = None
        pose_overlay_artifact_path: str | None = None
        pose_overlay_url: str | None = None
        pose_overlay_status: str | None = None
        pose_overlay_detail: str | None = None
        serve_events_artifact_path: str | None = None
        serve_events_url: str | None = None
        serve_events_status: str | None = None
        serve_events_detail: str | None = None
        serve_debug_candidates_path: str | None = None
        serve_debug_candidates_url: str | None = None
        serve_score_series_path: str | None = None
        serve_score_series_url: str | None = None
        serve_clips_manifest_path: str | None = None
        serve_clips_manifest_url: str | None = None
        serve_debug_overlay_path: str | None = None
        serve_debug_overlay_url: str | None = None
        serve_debug_artifacts_status: str | None = None
        serve_debug_artifacts_detail: str | None = None
        player_trajectory_json_path: str | None = None
        player_trajectory_csv_path: str | None = None
        player_trajectory_url: str | None = None
        player_trajectory_status: str | None = None
        player_trajectory_detail: str | None = None
        player_render_trajectory_json_path: str | None = None
        player_render_trajectory_url: str | None = None
        player_render_trajectory_status: str | None = None
        player_render_trajectory_detail: str | None = None
        calibration_diagnostics_json_path: str | None = None
        calibration_diagnostics_url: str | None = None
        court_view_roi_path: str | None = None
        court_view_roi_url: str | None = None
        court_view_roi_status: str | None = None
        court_view_roi_detail: str | None = None
        if video and calibration:
            # ===== 路径 A：有视频 + 有标定，跑真实跟踪 =====
            try:
                self._notify_progress(
                    progress_callback,
                    self._stage("frame-sampling", "抽帧采样", "active", "正在读取视频帧并按配置抽样"),
                )
                run_output = self._run_tracking(
                    job_id=job_id,
                    video=video,
                    homography=calibration.homography.values,
                    video_id=video_id,
                    calibration_id=calibration_id,
                    calibration_keypoints=calibration.keypoints,
                    capture_take_id=capture_take_id,
                    frame_stride=frame_stride or self.frame_stride,
                    source_fps=source_fps,
                    court_view_match_threshold=court_view_match_threshold,
                    match_context=match_ctx,
                    progress_callback=progress_callback,
                    cancellation_token=cancellation_token,
                    clip_start_ms=clip_start_ms,
                    clip_end_ms=clip_end_ms,
                )
            except Exception as exc:
                # 跟踪阶段抛异常 → 整个任务失败
                failed_stage = self._stage("tracking", "多目标跟踪", "failed", str(exc))
                stages.append(failed_stage)
                self._notify_progress(progress_callback, failed_stage)
                result = self._failed(job_id, video_id, calibration_id, str(exc), stages=stages)
                self._write_result(result)
                return result
            tracking_result = run_output.tracking
            analysis_window_metadata = run_output.analysis_window or None
            ball_run_output = run_output.ball_run_output
            player_multitarget_detections = run_output.player_multitarget_detections
            calibration_diagnostics_json_path = run_output.calibration_diagnostics_path
            calibration_diagnostics_url = (
                f"/api/analysis/jobs/{job_id}/artifacts/calibration-diagnostics"
                if run_output.calibration_diagnostics_path
                else None
            )
            if run_output.court_view_roi is not None:
                court_view_roi_json = self.storage.court_view_roi_json_path(job_id)
                self.storage.write_json(court_view_roi_json, run_output.court_view_roi.model_dump(mode="json"))
                court_view_roi_path = str(court_view_roi_json)
                court_view_roi_url = f"/api/analysis/jobs/{job_id}/artifacts/court-view-roi"
                court_view_roi_status = run_output.court_view_roi.status
                court_view_roi_detail = run_output.court_view_roi.detail
            sampling_stage = self._stage(
                "frame-sampling",
                "抽帧采样",
                "done",
                f"已按配置帧间隔读取 {tracking_result.processed_frame_count} 帧",
            )
            stages.append(sampling_stage)
            self._notify_progress(progress_callback, sampling_stage)
            self._check_cancelled(cancellation_token)

            if run_output.court_view_roi is not None:
                # 球场视角 ROI 阶段：根据状态决定 done / skipped
                court_view_stage = self._stage(
                    "court-view-roi",
                    "球场视角与检测 ROI",
                    "done" if run_output.court_view_roi.status in {"available", "partial"} else "skipped",
                    run_output.court_view_roi.detail,
                )
                court_view_stage.counters = {
                    "status": run_output.court_view_roi.status,
                    "processed_frame_count": run_output.court_view_roi.processed_frame_count,
                    "candidate_segment_count": len(run_output.court_view_roi.candidate_segments),
                    "gated_frame_count": run_output.court_view_roi.gated_frame_count,
                    "roi_status": run_output.court_view_roi.roi.status,
                    "roi_filtered_detection_count": run_output.court_view_roi.roi_filtered_detection_count,
                    "full_frame_fallback_count": run_output.court_view_roi.full_frame_fallback_count,
                    "semantic_boundary": "court-view candidates are not complete rally segmentation",
                }
                stages.append(court_view_stage)
                self._notify_progress(progress_callback, court_view_stage)
                self._check_cancelled(cancellation_token)

            # 写出跟踪结果 JSON + 检测叠加 JSON
            tracking_path = self.storage.tracking_json_path(job_id)
            self.storage.write_json(tracking_path, tracking_result.model_dump(mode="json"))
            tracking_artifact_path = str(tracking_path)
            tracking_overlay = self._build_tracking_overlay(
                job_id,
                video_id,
                tracking_result,
                enabled=self.model_inference_enabled,
            )
            tracking_overlay_path = self.storage.tracking_overlay_json_path(job_id)
            self.storage.write_json(tracking_overlay_path, tracking_overlay.model_dump(mode="json"))
            tracking_overlay_artifact_path = str(tracking_overlay_path)
            tracking_overlay_url = f"/api/analysis/jobs/{job_id}/artifacts/tracking-overlay"
            tracking_overlay_status = tracking_overlay.status
            tracking_overlay_detail = tracking_overlay.detail

            if run_output.player_selection is not None:
                # 主球员选择结果 + 训练样本
                selection_json_path = self.storage.player_selection_json_path(job_id)
                self.storage.write_json(selection_json_path, run_output.player_selection.model_dump(mode="json"))
                player_selection_path = str(selection_json_path)
                player_selection_url = f"/api/analysis/jobs/{job_id}/artifacts/player-selection"
                player_selection_status = run_output.player_selection.status
                player_selection_detail = run_output.player_selection.detail
                training_samples_path = self.storage.player_selection_training_samples_json_path(job_id)
                self.storage.write_json(
                    training_samples_path,
                    {
                        "job_id": job_id,
                        "video_id": video_id,
                        "labels": ["target_player", "neighbor_court_player", "spectator", "uncertain"],
                        "samples": [
                            sample.model_dump(mode="json") | {"label": "uncertain"}
                            for sample in run_output.player_selection.training_samples
                        ],
                    },
                )
                player_selection_training_samples_path = str(training_samples_path)
                player_selection_training_samples_url = (
                    f"/api/analysis/jobs/{job_id}/artifacts/player-selection-training-samples"
                )

            if run_output.pose is not None:
                # 姿态叠加结果
                pose_overlay_path = self.storage.pose_overlay_json_path(job_id)
                self.storage.write_json(pose_overlay_path, run_output.pose.model_dump(mode="json"))
                pose_overlay_artifact_path = str(pose_overlay_path)
                pose_overlay_url = f"/api/analysis/jobs/{job_id}/artifacts/pose-overlay"
                pose_overlay_status = run_output.pose.status
                pose_overlay_detail = run_output.pose.detail
            elif run_output.pose_stage is not None:
                pose_overlay_status = "unavailable"
                pose_overlay_detail = run_output.pose_stage.detail

            if run_output.player_trajectories is not None:
                # 球员轨迹 JSON + CSV
                player_trajectory_json = self.storage.player_trajectory_json_path(job_id)
                player_trajectory_csv = self.storage.player_trajectory_csv_path(job_id)
                self.storage.write_json(player_trajectory_json, run_output.player_trajectories.model_dump(mode="json"))
                self._write_player_trajectory_csv(player_trajectory_csv, run_output.player_trajectories)
                player_trajectory_json_path = str(player_trajectory_json)
                player_trajectory_csv_path = str(player_trajectory_csv)
                player_trajectory_url = f"/api/analysis/jobs/{job_id}/artifacts/player-trajectories"
                player_count = len(run_output.player_trajectories.players)
                sample_count = sum(len(samples) for samples in run_output.player_trajectories.players.values())
                player_trajectory_status = "available" if sample_count else "no_detections"
                player_trajectory_detail = f"已生成 {player_count} 名球员的 {sample_count} 个公制轨迹样本"

            if run_output.render_trajectory is not None:
                render_traj_path = self.storage.player_render_trajectory_path(job_id)
                style_profile, seg_profile = load_render_profiles()
                render_traj_payload = serialize_render_trajectory_v2(
                    run_output.render_trajectory,
                    style_profile=style_profile,
                    segmentation_profile=seg_profile,
                )
                render_traj_payload["job_id"] = job_id
                render_traj_payload["status"] = "available"
                render_traj_payload["fps"] = tracking_result.fps
                render_traj_payload["total_frames"] = tracking_result.frame_count
                render_traj_payload["analysis_window"] = run_output.analysis_window
                sample_count = len(run_output.render_trajectory.get("samples", []))
                render_traj_payload["detail"] = f"已生成逐帧渲染轨迹，共 {sample_count} 帧"
                self.storage.write_json(render_traj_path, render_traj_payload)
                player_render_trajectory_json_path = str(render_traj_path)
                player_render_trajectory_url = f"/api/analysis/jobs/{job_id}/artifacts/player-render-trajectories"
                player_render_trajectory_status = "available"
                player_render_trajectory_detail = render_traj_payload["detail"]
            else:
                player_render_trajectory_json_path = None
                player_render_trajectory_url = None
                player_render_trajectory_status = "unavailable"
                player_render_trajectory_detail = "渲染轨迹未生成"

            # 发球开始检测（若开启调试产物，先准备调试引用）
            debug_refs = self._serve_debug_refs(job_id) if self.settings.enable_serve_debug_artifacts else None
            try:
                serve_events = self.serve_start_detector.detect(
                    job_id=job_id,
                    video_id=video_id,
                    tracking=tracking_result,
                    player_trajectories=run_output.player_trajectories,
                    pose_frames=run_output.pose_frames,
                    debug_artifacts=debug_refs,
                )
            except Exception as exc:
                # 检测失败则降级为 unavailable，不阻断主流程
                serve_events = self.serve_start_detector.unavailable(
                    job_id=job_id,
                    video_id=video_id,
                    detail=f"发球开始检测不可用：{exc}",
                )
            if self.settings.enable_serve_debug_artifacts:
                debug_status, debug_detail = self._write_serve_debug_artifacts(
                    job_id=job_id,
                    serve_events=serve_events,
                    source_video_path=Path(video.path),
                )
                serve_debug_artifacts_status = debug_status
                serve_debug_artifacts_detail = debug_detail
                if serve_events.debug_artifacts is not None:
                    serve_events.debug_artifacts.status = debug_status
                    serve_events.debug_artifacts.detail = debug_detail
                if self.storage.serve_debug_candidates_json_path(job_id).exists():
                    serve_debug_candidates_path = str(self.storage.serve_debug_candidates_json_path(job_id))
                    serve_debug_candidates_url = f"/api/analysis/jobs/{job_id}/artifacts/serve-debug-candidates"
                if self.storage.serve_score_series_json_path(job_id).exists():
                    serve_score_series_path = str(self.storage.serve_score_series_json_path(job_id))
                    serve_score_series_url = f"/api/analysis/jobs/{job_id}/artifacts/serve-score-series"
                if self.storage.serve_clips_manifest_json_path(job_id).exists():
                    serve_clips_manifest_path = str(self.storage.serve_clips_manifest_json_path(job_id))
                    serve_clips_manifest_url = f"/api/analysis/jobs/{job_id}/artifacts/serve-clips-manifest"
                if self.storage.serve_debug_overlay_video_path(job_id).exists():
                    serve_debug_overlay_path = str(self.storage.serve_debug_overlay_video_path(job_id))
                    serve_debug_overlay_url = f"/api/analysis/jobs/{job_id}/artifacts/serve-debug-overlay"
            serve_events_path = self.storage.serve_events_json_path(job_id)
            self.storage.write_json(serve_events_path, serve_events.model_dump(mode="json"))
            serve_events_artifact_path = str(serve_events_path)
            serve_events_url = f"/api/analysis/jobs/{job_id}/artifacts/serve-events"
            serve_events_status = serve_events.status
            serve_events_detail = serve_events.detail

            # 以下把各个"阶段"的状态/详情汇总进 stages 列表
            detection_stage = self._stage(
                "detection",
                "人体检测",
                "done" if self.model_inference_enabled else "skipped",
                self._detection_stage_detail(tracking_result, enabled=self.model_inference_enabled),
            )
            stages.append(detection_stage)
            self._notify_progress(progress_callback, detection_stage)
            self._check_cancelled(cancellation_token)
            tracking_stage = self._stage(
                "tracking",
                "多目标跟踪",
                "done" if self.model_inference_enabled else "skipped",
                (
                    f"已输出 {len(tracking_result.tracks)} 个当前轨迹样本"
                    if self.model_inference_enabled
                    else "YOLO 人体检测未运行，未生成可跟踪人体框"
                ),
            )
            stages.append(tracking_stage)
            self._notify_progress(progress_callback, tracking_stage)
            self._check_cancelled(cancellation_token)
            pose_stage = run_output.pose_stage or self._stage(
                "pose",
                "人体姿态",
                "skipped",
                "RTMPose 姿态识别未启用，暂不生成骨架关节",
            )
            stages.append(pose_stage)
            self._notify_progress(progress_callback, pose_stage)
            self._check_cancelled(cancellation_token)
            projection_stage = self._stage(
                "projection",
                "脚点投影",
                "done",
                self._projection_stage_detail(tracking_result.positions),
            )
            stages.append(projection_stage)
            self._notify_progress(progress_callback, projection_stage)
            self._check_cancelled(cancellation_token)
            serve_stage = self._stage(
                "serve-start-detection",
                "发球开始检测",
                "done" if serve_events.status in {"available", "partial", "no_candidates"} else "skipped",
                f"{serve_events.detail}（候选 {len(serve_events.events)} 个）",
            )
            serve_stage.counters = {
                "candidate_count": len(serve_events.events),
                "status": serve_events.status,
                "has_tracking": bool(tracking_result.overlay_frames),
                "has_pose": bool(run_output.pose_frames),
                "detection_mode": serve_events.detection_mode,
                "available_signals": serve_events.available_signals,
                "debug_artifacts_status": serve_debug_artifacts_status,
                "court_unit": run_output.player_trajectories.court.court_unit
                if run_output.player_trajectories
                else None,
                "player_selection_status": player_selection_status,
                "coverage": serve_events.coverage.model_dump(mode="json") if serve_events.coverage else None,
            }
            stages.append(serve_stage)
            self._notify_progress(progress_callback, serve_stage)
            self._check_cancelled(cancellation_token)
            tracks = run_output.player_metric_tracks or self._positions_to_projected_tracks(tracking_result.positions)
            message = "Pipeline completed with Player Tracking Engine output."
        elif video and not calibration:
            # ===== 路径 B：有视频但无标定 → 有限阶段，跳过需要标定的部分 =====
            limited_stages = [
                self._stage("frame-sampling", "抽帧采样", "skipped", "未提供标定，跳过真实抽帧分析"),
                self._stage("detection", "人体检测", "skipped", "缺少场地标定，暂不运行真实检测"),
                self._stage("tracking", "多目标跟踪", "skipped", "需要有效标定后才能生成可用场地轨迹"),
                self._stage("pose", "人体姿态", "skipped", "需要检测和跟踪框后才能运行 RTMPose"),
                self._stage("projection", "脚点投影", "skipped", "未提供标定，无法投影到标准球场坐标"),
                self._stage(
                    "serve-start-detection",
                    "发球开始检测",
                    "skipped",
                    "缺少场地标定和可用球员轨迹，暂不识别发球开始候选点",
                ),
            ]
            for stage in limited_stages:
                stages.append(stage)
                self._notify_progress(progress_callback, stage)
                self._check_cancelled(cancellation_token)
            tracks = []
            serve_events_status = "unavailable"
            serve_events_detail = "缺少场地标定和可用球员轨迹，暂不识别发球开始候选点"
            message = "Limited pipeline completed without court calibration; no court-projected tracks were generated."
        else:
            # ===== 路径 C：无视频（demo） → 返回确定性 mock 轨迹 =====
            mock_stages = [
                self._stage("frame-sampling", "抽帧采样", "skipped", "未提供真实视频，跳过抽帧"),
                self._stage("detection", "人体检测", "skipped", "未提供视频或标定，返回确定性轨迹"),
                self._stage("tracking", "多目标跟踪", "done", "已生成 MVP 轨迹样本"),
                self._stage("pose", "人体姿态", "skipped", "未提供真实视频，跳过骨架关节识别"),
                self._stage("serve-start-detection", "发球开始检测", "skipped", "未提供真实视频，跳过发球开始候选检测"),
            ]
            for stage in mock_stages:
                stages.append(stage)
                self._notify_progress(progress_callback, stage)
                self._check_cancelled(cancellation_token)
            tracks = self._mock_projected_tracks()
            serve_events_status = "unavailable"
            serve_events_detail = "未提供真实视频，跳过发球开始候选检测"
            projection_stage = self._stage("projection", "脚点投影", "done", "轨迹已位于标准球场坐标系")
            stages.append(projection_stage)
            self._notify_progress(progress_callback, projection_stage)
            self._check_cancelled(cancellation_token)
            message = "MVP pipeline completed with deterministic model-free tracking output."

        # 球分析阶段（所有路径统一处理：启用/缺依赖/未启用）
        _ball_source_width = tracking_result.frame_width if video and calibration else 0
        _ball_source_height = tracking_result.frame_height if video and calibration else 0
        _ball_fps = tracking_result.fps if video and calibration else 0.0
        _ball_processed = tracking_result.processed_frame_count if video and calibration else 0
        _ball_stride = frame_stride or self.frame_stride
        _timing_provenance = (
            tracking_result.timing_provenance if video and calibration else None
        )
        # 重建球轨迹需要 homography 与（可选的）serve 事件；mock 路径下均不可用
        _reconstruction_homography = (
            calibration.homography.values if (calibration is not None and calibration.homography is not None) else None
        )
        _reconstruction_serve_events = locals().get("serve_events")
        self._finalize_ball_analysis(
            job_id,
            ball_run_output,
            player_multitarget_detections,
            video_id,
            stages,
            ball_fields,
            source_width=_ball_source_width,
            source_height=_ball_source_height,
            fps=_ball_fps,
            frame_stride=_ball_stride,
            processed_frame_count=_ball_processed,
            progress_callback=progress_callback,
            homography=_reconstruction_homography,
            serve_events=_reconstruction_serve_events,
            capture_take_id=capture_take_id,
            tracking_run_output=locals().get("run_output"),
            timing_provenance=_timing_provenance,
        )

        # 球分析 strict mode 检查：strict=true 且球分析失败时，整体 pipeline failed
        if self.ball_analysis_strict:
            ball_traj_failed = any(
                stage.id == "ball-trajectory" and stage.status in {"failed", "unavailable"} for stage in stages
            )
            bounce_failed = any(
                stage.id == "bounce-detection" and stage.status in {"failed", "unavailable"} for stage in stages
            )
            if ball_traj_failed or bounce_failed:
                failed_stage_id = "ball-trajectory" if ball_traj_failed else "bounce-detection"
                reason = f"球分析严格模式启用，{failed_stage_id} 阶段失败导致 pipeline 终止"
                result = self._failed(job_id, video_id, calibration_id, reason, stages=stages)
                self._write_result(result)
                return result

        # 把球分析阶段产出的 artifact 字段映射到结果构造用的局部变量
        detections_jsonl_path = ball_fields.detections_jsonl_path
        detections_url = ball_fields.detections_url
        detections_status = ball_fields.detections_status
        detections_detail = ball_fields.detections_detail
        ball_overlay_json_path = ball_fields.ball_overlay_json_path
        ball_overlay_url = ball_fields.ball_overlay_url
        ball_overlay_status = ball_fields.ball_overlay_status
        ball_overlay_detail = ball_fields.ball_overlay_detail
        ball_trajectory_json_path = ball_fields.ball_trajectory_json_path
        ball_trajectory_url = ball_fields.ball_trajectory_url
        ball_trajectory_status = ball_fields.ball_trajectory_status
        ball_trajectory_detail = ball_fields.ball_trajectory_detail
        cleaned_ball_trajectory_json_path = ball_fields.cleaned_ball_trajectory_json_path
        cleaned_ball_trajectory_url = ball_fields.cleaned_ball_trajectory_url
        cleaned_ball_trajectory_status = ball_fields.cleaned_ball_trajectory_status
        cleaned_ball_trajectory_detail = ball_fields.cleaned_ball_trajectory_detail
        bounce_events_json_path = ball_fields.bounce_events_json_path
        bounce_events_url = ball_fields.bounce_events_url
        bounce_events_status = ball_fields.bounce_events_status
        bounce_events_detail = ball_fields.bounce_events_detail
        reconstructed_ball_trajectory_json_path = ball_fields.reconstructed_ball_trajectory_json_path
        reconstructed_ball_trajectory_url = ball_fields.reconstructed_ball_trajectory_url
        reconstructed_ball_trajectory_status = ball_fields.reconstructed_ball_trajectory_status
        reconstructed_ball_trajectory_detail = ball_fields.reconstructed_ball_trajectory_detail
        ball_semantic_timeline_json_path = ball_fields.ball_semantic_timeline_json_path
        ball_semantic_timeline_url = ball_fields.ball_semantic_timeline_url
        ball_semantic_timeline_status = ball_fields.ball_semantic_timeline_status
        ball_semantic_timeline_detail = ball_fields.ball_semantic_timeline_detail
        ball_semantic_boundary_eval_json_path = ball_fields.ball_semantic_boundary_eval_json_path
        ball_semantic_boundary_eval_url = ball_fields.ball_semantic_boundary_eval_url

        # 计算运动指标（附加球分析摘要）
        _ball_metrics = self._build_ball_metrics_summary(ball_run_output)
        metrics = self._compute_metrics(tracks, ball_metrics=_ball_metrics, match_context=match_ctx)
        metrics_stage = self._stage("metrics", "运动指标", "done", "已计算距离、速度、厨房区、双打间距和热力图")
        stages.append(metrics_stage)
        self._notify_progress(progress_callback, metrics_stage)
        self._check_cancelled(cancellation_token)

        visualization_fields = self._run_visualization(
            job_id=job_id,
            video=video,
            progress_callback=progress_callback,
            clip_start_ms=clip_start_ms,
            clip_end_ms=clip_end_ms,
            capture_take_id=capture_take_id,
        )
        visualization_stage = self._stage(
            "visualization",
            "可视化输出",
            visualization_fields.stage_status,
            visualization_fields.stage_detail,
        )
        visualization_stage.counters = {
            "overlay_video_status": visualization_fields.analysis_overlay_video_status,
            "position_visualizations_status": visualization_fields.position_visualizations_status,
            "heatmaps_url": visualization_fields.heatmaps_url,
            "scatter_plots_url": visualization_fields.scatter_plots_url,
        }
        stages.append(visualization_stage)
        self._notify_progress(progress_callback, visualization_stage)
        self._check_cancelled(cancellation_token)
        analysis_overlay_video_path = visualization_fields.analysis_overlay_video_path
        analysis_overlay_video_url = visualization_fields.analysis_overlay_video_url
        analysis_overlay_video_status = visualization_fields.analysis_overlay_video_status
        analysis_overlay_video_detail = visualization_fields.analysis_overlay_video_detail
        heatmaps_manifest_json_path = visualization_fields.heatmaps_manifest_json_path
        heatmaps_url = visualization_fields.heatmaps_url
        scatter_plots_manifest_json_path = visualization_fields.scatter_plots_manifest_json_path
        scatter_plots_url = visualization_fields.scatter_plots_url
        position_visualizations_status = visualization_fields.position_visualizations_status
        position_visualizations_detail = visualization_fields.position_visualizations_detail
        if analysis_window_metadata is not None and visualization_fields.analysis_overlay_video_metadata:
            output_origin = visualization_fields.analysis_overlay_video_metadata.get("output_time_origin_ms")
            if output_origin is not None:
                analysis_window_metadata["output_time_origin_ms"] = output_origin

        # 汇总成最终结果
        result = AnalysisPipelineResult(
            job_id=job_id,
            video_id=video_id,
            calibration_id=calibration_id,
            status="completed",
            generated_at=datetime.now(UTC),
            stages=stages,
            tracks=tracks,
            metrics=metrics,
            artifacts=AnalysisArtifacts(
                result_json_path=str(self.storage.output_json_path(job_id)),
                tracking_result_json_path=tracking_artifact_path,
                tracking_overlay_json_path=tracking_overlay_artifact_path,
                tracking_overlay_url=tracking_overlay_url,
                player_selection_json_path=player_selection_path,
                player_selection_url=player_selection_url,
                player_selection_training_samples_json_path=player_selection_training_samples_path,
                player_selection_training_samples_url=player_selection_training_samples_url,
                detections_jsonl_path=detections_jsonl_path,
                detections_url=detections_url,
                ball_overlay_json_path=ball_overlay_json_path,
                ball_overlay_url=ball_overlay_url,
                ball_trajectory_json_path=ball_trajectory_json_path,
                ball_trajectory_url=ball_trajectory_url,
                cleaned_ball_trajectory_json_path=cleaned_ball_trajectory_json_path,
                cleaned_ball_trajectory_url=cleaned_ball_trajectory_url,
                bounce_events_json_path=bounce_events_json_path,
                bounce_events_url=bounce_events_url,
                reconstructed_ball_trajectory_json_path=reconstructed_ball_trajectory_json_path,
                reconstructed_ball_trajectory_url=reconstructed_ball_trajectory_url,
                ball_semantic_timeline_json_path=ball_semantic_timeline_json_path,
                ball_semantic_timeline_url=ball_semantic_timeline_url,
                ball_semantic_boundary_eval_json_path=ball_semantic_boundary_eval_json_path,
                ball_semantic_boundary_eval_url=ball_semantic_boundary_eval_url,
                analysis_overlay_video_path=analysis_overlay_video_path,
                analysis_overlay_video_url=analysis_overlay_video_url,
                heatmaps_manifest_json_path=heatmaps_manifest_json_path,
                heatmaps_url=heatmaps_url,
                scatter_plots_manifest_json_path=scatter_plots_manifest_json_path,
                scatter_plots_url=scatter_plots_url,
                pose_overlay_json_path=pose_overlay_artifact_path,
                pose_overlay_url=pose_overlay_url,
                serve_events_json_path=serve_events_artifact_path,
                serve_events_url=serve_events_url,
                serve_debug_candidates_json_path=serve_debug_candidates_path,
                serve_debug_candidates_url=serve_debug_candidates_url,
                serve_score_series_json_path=serve_score_series_path,
                serve_score_series_url=serve_score_series_url,
                serve_clips_manifest_json_path=serve_clips_manifest_path,
                serve_clips_manifest_url=serve_clips_manifest_url,
                serve_debug_overlay_path=serve_debug_overlay_path,
                serve_debug_overlay_url=serve_debug_overlay_url,
                player_trajectory_json_path=player_trajectory_json_path,
                player_trajectory_csv_path=player_trajectory_csv_path,
                player_trajectory_url=player_trajectory_url,
                player_render_trajectory_json_path=player_render_trajectory_json_path,
                player_render_trajectory_url=player_render_trajectory_url,
                court_view_roi_json_path=court_view_roi_path,
                court_view_roi_url=court_view_roi_url,
                calibration_diagnostics_json_path=calibration_diagnostics_json_path,
                calibration_diagnostics_url=calibration_diagnostics_url,
                source_video_url=source_video_url,
                tracking_overlay_status=tracking_overlay_status,
                tracking_overlay_detail=tracking_overlay_detail,
                player_selection_status=player_selection_status,
                player_selection_detail=player_selection_detail,
                detections_status=detections_status,
                detections_detail=detections_detail,
                ball_overlay_status=ball_overlay_status,
                ball_overlay_detail=ball_overlay_detail,
                ball_trajectory_status=ball_trajectory_status,
                ball_trajectory_detail=ball_trajectory_detail,
                cleaned_ball_trajectory_status=cleaned_ball_trajectory_status,
                cleaned_ball_trajectory_detail=cleaned_ball_trajectory_detail,
                bounce_events_status=bounce_events_status,
                bounce_events_detail=bounce_events_detail,
                reconstructed_ball_trajectory_status=reconstructed_ball_trajectory_status,
                reconstructed_ball_trajectory_detail=reconstructed_ball_trajectory_detail,
                ball_semantic_timeline_status=ball_semantic_timeline_status,
                ball_semantic_timeline_detail=ball_semantic_timeline_detail,
                ball_semantic_boundary_eval_status=ball_fields.ball_semantic_boundary_eval_status,
                ball_semantic_boundary_eval_detail=ball_fields.ball_semantic_boundary_eval_detail,
                analysis_overlay_video_status=analysis_overlay_video_status,
                analysis_overlay_video_detail=analysis_overlay_video_detail,
                position_visualizations_status=position_visualizations_status,
                position_visualizations_detail=position_visualizations_detail,
                pose_overlay_status=pose_overlay_status,
                pose_overlay_detail=pose_overlay_detail,
                serve_events_status=serve_events_status,
                serve_events_detail=serve_events_detail,
                serve_debug_artifacts_status=serve_debug_artifacts_status,
                serve_debug_artifacts_detail=serve_debug_artifacts_detail,
                player_trajectory_status=player_trajectory_status,
                player_trajectory_detail=player_trajectory_detail,
                court_view_roi_status=court_view_roi_status,
                court_view_roi_detail=court_view_roi_detail,
                analysis_window=analysis_window_metadata,
                analysis_overlay_video_metadata=(
                    visualization_fields.analysis_overlay_video_metadata
                    if hasattr(visualization_fields, "analysis_overlay_video_metadata")
                    else None
                ),
            ),
            message=message,
            match_context=match_ctx,
            observed_player_count=len({t.track_id for t in tracks if t.track_id}),
            analysis_window=analysis_window_metadata,
        )
        result = self.storage.publicize_pipeline_result(result)
        self._write_result(result)
        return result

    @staticmethod
    def _build_attribution_context(
        tracking_run_output: Any | None,
        *,
        fps: float,
        frame_stride: int,
    ) -> Any | None:
        """从 _TrackingRunOutput 内存对象构建球员归属上下文。

        直接使用内存对象（render_trajectory / pose_frames / tracking / player_trajectories），
        不先写文件再从 JSON 读回（设计 D4 / 任务 2.4）。
        """
        if tracking_run_output is None:
            return None
        try:
            tracking = getattr(tracking_run_output, "tracking", None)
            overlay_frames = tracking.overlay_frames if tracking is not None else None
            return build_player_attribution_context(
                player_trajectories=getattr(tracking_run_output, "player_trajectories", None),
                pose_frames=getattr(tracking_run_output, "pose_frames", None),
                overlay_frames=overlay_frames,
                render_trajectory_payload=getattr(tracking_run_output, "render_trajectory", None),
                fps=fps or 30.0,
                frame_stride=frame_stride or 1,
            )
        except Exception:
            logger.exception("构建球员归属上下文失败，降级为无归属重建")
            return None

    def _finalize_ball_analysis(
        self,
        job_id: str,
        ball_run_output: _BallRunOutput | None,
        player_detections: list[MultiTargetDetection],
        video_id: str | None,
        stages: list[PipelineStageResult],
        fields: _BallArtifactFields,
        source_width: int = 0,
        source_height: int = 0,
        fps: float = 0.0,
        frame_stride: int = 1,
        processed_frame_count: int = 0,
        progress_callback: ProgressCallback | None = None,
        homography: list[list[float]] | None = None,
        serve_events: list[Any] | None = None,
        capture_take_id: str | None = None,
        tracking_run_output: Any | None = None,
        timing_provenance: dict[str, object] | None = None,
    ) -> None:
        """统一处理球分析阶段的状态记录与 artifact 写入。

        所有路径都会进入：球未启用 → skipped；启用但缺依赖 → unavailable；
        启用且产生候选 → 写入 ball_overlay / detections / 轨迹 / 清洗 / 弹跳 / 重建 artifact。

        用户可见阶段收敛为两个：ball-trajectory 和 bounce-detection。
        ball-detection 的内部信息并入 ball-trajectory 的 counters。
        重建产物（第三套）在弹跳检测之后生成，不新增用户可见阶段。

        tracking_run_output：路径 A 的 `_TrackingRunOutput`（含球员轨迹 / 姿态 /
        跟踪叠加帧 / render roster），用于重建链的球员归属；B/C 路径为 None 时
        归属字段降级为 unassigned（I4 / I6），不伪造。
        """
        enabled = self.ball_detection_enabled
        if ball_run_output is None:
            # 球检测未启用，或路径 B/C（无真实跟踪/标定）下不可用
            detail = (
                "球检测未启用（PICKLEBALL_ENABLE_BALL_DETECTION=false）"
                if not enabled
                else "缺少真实跟踪/标定，球轨迹不可用"
            )
            skip_traj = self._stage("ball-trajectory", "球轨迹", "skipped", detail)
            skip_traj.counters = {
                "model_enabled": enabled,
                "processed_frame_count": 0,
                "ball_detection_count": 0,
                "raw_sample_count": 0,
                "missing_frame_count": 0,
                "detection_rate": 0.0,
                "frame_stride": frame_stride,
                "court_unit": "ft",
            }
            self._notify_progress(
                progress_callback, self._stage("ball-trajectory", "球轨迹", "active", "正在准备球轨迹分析…")
            )
            stages.append(skip_traj)
            stages.append(self._stage("bounce-detection", "弹跳候选", "skipped", "球轨迹未生成，未运行弹跳检测"))
            fields.detections_status = "skipped"
            fields.detections_detail = detail
            fields.ball_overlay_status = "skipped"
            fields.ball_overlay_detail = detail
            fields.ball_trajectory_status = "skipped"
            fields.ball_trajectory_detail = "球检测未运行"
            fields.cleaned_ball_trajectory_status = "skipped"
            fields.cleaned_ball_trajectory_detail = "球轨迹未生成"
            fields.bounce_events_status = "skipped"
            fields.bounce_events_detail = "球轨迹未生成"
            fields.reconstructed_ball_trajectory_status = "skipped"
            fields.reconstructed_ball_trajectory_detail = "球轨迹未生成"
            fields.ball_semantic_timeline_status = "skipped"
            fields.ball_semantic_timeline_detail = "球分析未运行，未生成语义搜索诊断"
            fields.ball_semantic_boundary_eval_status = "skipped"
            fields.ball_semantic_boundary_eval_detail = "球分析未运行，未生成语义边界评估"
            return

        run = ball_run_output

        # ServeStartDetector 在单摄离线链路中属于后处理证据；把候选追加到
        # semantic trace，供回放验证 PRE_SERVE/SERVE_ARMED 策略，不改变球事件。
        serve_candidates = list(getattr(serve_events, "events", ()) or ())
        if serve_candidates:
            policy_mode = (
                run.semantic_decisions[0].policy_mode
                if run.semantic_decisions
                else SemanticPolicyMode.SHADOW
            )
            serve_policy = BallSearchPolicy(BallSemanticPolicyConfig(mode=policy_mode))
            for candidate in serve_candidates:
                serve_snapshot = serve_candidate_semantic_snapshot(candidate, mode=policy_mode)
                run.semantic_snapshots.append(serve_snapshot)
                run.semantic_decisions.append(serve_policy.evaluate(serve_snapshot))

        # 语义策略诊断是旁路 artifact：生成失败不得影响旧球轨迹和球员主链。
        try:
            semantic_payload = build_semantic_timeline_payload(
                job_id=job_id,
                take_id=capture_take_id,
                snapshots=run.semantic_snapshots,
                decisions=run.semantic_decisions,
                diagnostics=run.semantic_diagnostics,
                frame_stride=frame_stride,
                timestamp_provenance=timing_provenance,
            )
            semantic_path = self.storage.ball_semantic_timeline_json_path(job_id)
            self.storage.write_json(semantic_path, semantic_payload)
            fields.ball_semantic_timeline_json_path = str(semantic_path)
            fields.ball_semantic_timeline_url = f"/api/analysis/jobs/{job_id}/artifacts/ball-semantic-timeline"
            fields.ball_semantic_timeline_status = "available"
            fields.ball_semantic_timeline_detail = (
                f"已记录 {len(run.semantic_snapshots)} 个语义 tick，"
                f"{run.semantic_diagnostics.get('policy_mode', 'shadow')} 策略决策 {len(run.semantic_decisions)} 个，"
                f"边界动作 {len(run.semantic_diagnostics.get('boundary_events', ())) } 个"
            )
        except Exception as exc:  # pragma: no cover - artifact failure must be non-fatal
            logger.warning("Ball semantic timeline artifact failed: %s", exc)
            fields.ball_semantic_timeline_status = "failed"
            fields.ball_semantic_timeline_detail = f"语义搜索诊断写入失败：{exc}"

        # 边界校准评估与时间线分开落盘，便于离线回放和版本间对比；它是旁路诊断，
        # 即使写入失败也不能影响球轨迹主链。
        boundary_eval_enabled = bool(run.semantic_diagnostics.get("boundary_eval_enabled", True))
        if not boundary_eval_enabled:
            fields.ball_semantic_boundary_eval_status = "skipped"
            fields.ball_semantic_boundary_eval_detail = "语义边界评估未启用"
        else:
            try:
                boundary_eval_payload = build_semantic_boundary_evaluation_payload(
                    job_id=job_id,
                    take_id=capture_take_id,
                    snapshots=run.semantic_snapshots,
                    decisions=run.semantic_decisions,
                    evidence_ledger=run.semantic_diagnostics.get("evidence_ledger", ()),
                    diagnostics=run.semantic_diagnostics,
                    reference_boundaries=run.semantic_diagnostics.get("reference_boundaries"),
                    frame_stride=frame_stride,
                    timestamp_provenance=timing_provenance,
                )
                boundary_eval_path = self.storage.ball_semantic_boundary_eval_json_path(job_id)
                self.storage.write_json(boundary_eval_path, boundary_eval_payload)
                fields.ball_semantic_boundary_eval_json_path = str(boundary_eval_path)
                fields.ball_semantic_boundary_eval_url = (
                    f"/api/analysis/jobs/{job_id}/artifacts/ball-semantic-boundary-eval"
                )
                fields.ball_semantic_boundary_eval_status = "available"
                fields.ball_semantic_boundary_eval_detail = (
                    f"已评估 {len(run.semantic_snapshots)} 个语义 tick，"
                    f"记录 {len(run.semantic_diagnostics.get('evidence_ledger', ())) } 条证据"
                )
            except Exception as exc:  # pragma: no cover - artifact failure must be non-fatal
                logger.warning("Ball semantic boundary evaluation artifact failed: %s", exc)
                fields.ball_semantic_boundary_eval_status = "failed"
                fields.ball_semantic_boundary_eval_detail = f"语义边界评估写入失败：{exc}"

        # 确定球轨迹 stage 状态与说明（合并原 ball-detection 的信息）
        if run.status == "available":
            traj_stage_status = "done"
            if run.accepted_count > 0:
                traj_status = "available"
                traj_detail = (
                    f"球检测已运行，{run.accepted_count} 帧接受候选（共 {len(run.ball_detections)} 条 ball 检测记录）"
                )
            else:
                traj_status = "available"
                traj_detail = "球检测已运行，但没有达到置信度/连续性阈值的球候选"
        elif run.status == "unavailable":
            traj_stage_status = "unavailable"
            traj_status = "unavailable"
            traj_detail = run.error or "球检测不可用（缺少模型路径或依赖）"
        else:  # failed
            traj_stage_status = "failed"
            traj_status = "failed"
            traj_detail = run.error or "球检测或轨迹处理失败"

        # ball-trajectory stage
        self._notify_progress(None, self._stage("ball-trajectory", "球轨迹", "active", "正在生成球轨迹 artifact…"))
        traj_stage = self._stage("ball-trajectory", "球轨迹", traj_stage_status, traj_detail)
        missing_count = max(0, processed_frame_count - len([s for s in run.samples if s.accepted]))
        detection_rate = (
            round(len([s for s in run.samples if s.accepted]) / max(1, processed_frame_count), 4)
            if processed_frame_count > 0
            else 0.0
        )
        traj_stage.counters = {
            "model_enabled": enabled,
            "processed_frame_count": processed_frame_count,
            "ball_detection_count": len([s for s in run.samples if s.visible]),
            "raw_sample_count": len(run.samples),
            "accepted_count": run.accepted_count,
            "missing_frame_count": missing_count,
            "detection_rate": detection_rate,
            "frame_stride": frame_stride,
            "court_unit": "ft",
        }
        stages.append(traj_stage)
        fields.detections_status = traj_status
        fields.detections_detail = traj_detail
        fields.ball_trajectory_status = traj_status
        fields.ball_trajectory_detail = traj_detail

        fields.ball_trajectory_status = (
            run.status if run.status != "available" else ("available" if run.raw_points else "skipped")
        )
        fields.ball_trajectory_detail = (
            traj_detail if run.status != "available" or run.raw_points else "未生成可用球轨迹"
        )

        # 只有可用的球分析才生成 overlay 文件；其他状态保留诊断但由 API 返回 404。
        overlay_status = "available" if run.status == "available" else run.status
        overlay_detail = (
            f"已生成 {len([s for s in run.samples if s.accepted])} 帧球叠加记录"
            if run.status == "available"
            else traj_detail
        )
        fields.ball_overlay_status = overlay_status
        fields.ball_overlay_detail = overlay_detail
        if run.status == "available":
            overlay_path = self.storage.ball_overlay_json_path(job_id)
            overlay_payload = build_ball_overlay_payload(
                job_id=job_id,
                video_id=video_id,
                samples=run.samples,
                source_width=source_width,
                source_height=source_height,
                fps=fps,
                frame_stride=frame_stride,
                processed_frame_count=processed_frame_count,
                timing_provenance=timing_provenance,
                status=overlay_status,
                detail=overlay_detail,
            )
            self.storage.write_json(overlay_path, overlay_payload)
            fields.ball_overlay_json_path = str(overlay_path)
            fields.ball_overlay_url = f"/api/analysis/jobs/{job_id}/artifacts/ball-overlay"

        if run.status != "available" or not run.raw_points:
            # 无可用轨迹：弹跳检测阶段 skipped
            bounce_stage = self._stage("bounce-detection", "弹跳候选", "skipped", "未生成可用球轨迹")
            bounce_stage.counters = {
                "input_sample_count": 0,
                "cleaned_sample_count": 0,
                "interpolated_sample_count": 0,
                "bounce_event_count": 0,
                "detection_mode": "rule_based",
                "status": "skipped",
            }
            stages.append(bounce_stage)
            fields.cleaned_ball_trajectory_status = "skipped"
            fields.cleaned_ball_trajectory_detail = "未生成可用球轨迹"
            fields.bounce_events_status = "skipped"
            fields.bounce_events_detail = "未生成可用球轨迹"
            fields.reconstructed_ball_trajectory_status = "skipped"
            fields.reconstructed_ball_trajectory_detail = "未生成可用球轨迹"
            return

        # 写入 detections.jsonl（player + ball 共享合同）
        detections_records = list(player_detections) + list(run.ball_detections)
        if detections_records:
            detections_path = self.storage.detections_jsonl_path(job_id)
            self.storage.write_jsonl(detections_path, [rec.model_dump(mode="json") for rec in detections_records])
            fields.detections_jsonl_path = str(detections_path)
            fields.detections_url = f"/api/analysis/jobs/{job_id}/artifacts/detections"
            fields.detections_status = "available"
            fields.detections_detail = f"已生成 {len(detections_records)} 条检测记录"
        else:
            fields.detections_status = "skipped"
            fields.detections_detail = "没有可写入的检测记录"

        # 写入原始轨迹
        raw_path = self.storage.ball_trajectory_json_path(job_id)
        self.storage.write_json(raw_path, build_raw_trajectory_payload(job_id=job_id, samples=run.raw_points))
        fields.ball_trajectory_json_path = str(raw_path)
        fields.ball_trajectory_url = f"/api/analysis/jobs/{job_id}/artifacts/ball-trajectory"
        fields.ball_trajectory_status = "available"
        fields.ball_trajectory_detail = f"已生成 {len(run.raw_points)} 个逐帧球轨迹样本"

        # 写入清洗轨迹
        if run.cleaned_points is not None:
            cleaned_path = self.storage.cleaned_ball_trajectory_json_path(job_id)
            self.storage.write_json(
                cleaned_path,
                build_cleaned_trajectory_payload(job_id=job_id, samples=run.cleaned_points),
            )
            fields.cleaned_ball_trajectory_json_path = str(cleaned_path)
            fields.cleaned_ball_trajectory_url = f"/api/analysis/jobs/{job_id}/artifacts/cleaned-ball-trajectory"
            fields.cleaned_ball_trajectory_status = "available"
            fields.cleaned_ball_trajectory_detail = f"已清洗并插值生成 {len(run.cleaned_points)} 个轨迹点"

        # 弹跳检测阶段
        self._notify_progress(
            progress_callback, self._stage("bounce-detection", "弹跳候选", "active", "正在运行弹跳候选检测…")
        )
        bounce_interpolated = sum(1 for p in (run.cleaned_points or []) if p.interpolated)
        if self.settings.enable_bounce_detection and run.bounce_events is not None:
            bounce_path = self.storage.bounce_events_json_path(job_id)
            self.storage.write_json(bounce_path, build_bounce_events_payload(job_id=job_id, events=run.bounce_events))
            fields.bounce_events_json_path = str(bounce_path)
            fields.bounce_events_url = f"/api/analysis/jobs/{job_id}/artifacts/bounce-events"
            fields.bounce_events_status = "available"
            fields.bounce_events_detail = (
                f"检测到 {len(run.bounce_events)} 个弹跳候选"
                if run.bounce_events
                else "弹跳检测已运行，但未检测到候选事件"
            )
            bounce_stage_status = "done"
            bounce_stage_detail = fields.bounce_events_detail
        else:
            bounce_stage_status = "skipped"
            bounce_stage_detail = (
                "PICKLEBALL_ENABLE_BOUNCE_DETECTION=false，跳过弹跳候选检测"
                if not self.settings.enable_bounce_detection
                else "未生成清洗球轨迹，跳过弹跳检测"
            )
            fields.bounce_events_status = "skipped"
            fields.bounce_events_detail = bounce_stage_detail

        bounce_stage = self._stage("bounce-detection", "弹跳候选", bounce_stage_status, bounce_stage_detail)
        bounce_stage.counters = {
            "input_sample_count": len(run.raw_points) if run.raw_points else 0,
            "cleaned_sample_count": len(run.cleaned_points) if run.cleaned_points else 0,
            "interpolated_sample_count": bounce_interpolated,
            "bounce_event_count": len(run.bounce_events) if run.bounce_events else 0,
            "detection_mode": "rule_based",
            "status": fields.bounce_events_status,
        }
        stages.append(bounce_stage)

        # 重建球轨迹（第三套产物）：在弹跳检测之后生成，不覆盖 raw/cleaned。
        if self.settings.enable_ball_reconstruction and run.status == "available" and run.cleaned_points:
            try:
                reconstruction_config = ReconstructionConfig(
                    default_contact_height_m=self.settings.ball_reconstruction_contact_height_m,
                )
                player_context = self._build_attribution_context(
                    tracking_run_output,
                    fps=fps,
                    frame_stride=frame_stride,
                )
                reconstructed_payload = reconstruct_ball_trajectory(
                    job_id=job_id,
                    cleaned_points=run.cleaned_points,
                    bounce_events=run.bounce_events or [],
                    serve_events=serve_events,
                    homography=homography,
                    fps=fps,
                    frame_stride=frame_stride,
                    config=reconstruction_config,
                    player_context=player_context,
                )
                if reconstructed_payload["status"] in {"available", "no_candidates"}:
                    reconstructed_path = self.storage.reconstructed_ball_trajectory_json_path(job_id)
                    self.storage.write_json(reconstructed_path, reconstructed_payload)
                    fields.reconstructed_ball_trajectory_json_path = str(reconstructed_path)
                    fields.reconstructed_ball_trajectory_url = (
                        f"/api/analysis/jobs/{job_id}/artifacts/reconstructed-ball-trajectory"
                    )
                    fields.reconstructed_ball_trajectory_status = reconstructed_payload["status"]
                    fields.reconstructed_ball_trajectory_detail = reconstructed_payload["detail"]
                else:
                    fields.reconstructed_ball_trajectory_status = reconstructed_payload["status"]
                    fields.reconstructed_ball_trajectory_detail = reconstructed_payload["detail"]
            except Exception as exc:
                logger.warning("Ball trajectory reconstruction failed: %s", exc)
                fields.reconstructed_ball_trajectory_status = "failed"
                fields.reconstructed_ball_trajectory_detail = f"球轨迹重建失败：{exc}"
        elif self.settings.enable_ball_reconstruction and run.status == "available":
            fields.reconstructed_ball_trajectory_status = "skipped"
            fields.reconstructed_ball_trajectory_detail = "未生成清洗球轨迹，跳过重建"
        else:
            fields.reconstructed_ball_trajectory_status = "skipped"
            fields.reconstructed_ball_trajectory_detail = "球轨迹重建未启用"

    def _run_visualization(
        self,
        *,
        job_id: str,
        video: VideoMetadata | None,
        progress_callback: ProgressCallback | None = None,
        clip_start_ms: int | None = None,
        clip_end_ms: int | None = None,
        capture_take_id: str | None = None,
    ) -> _VisualizationArtifactFields:
        enabled_overlay = bool(self.settings.enable_analysis_overlay_video)
        enabled_positions = bool(self.settings.enable_position_visualizations)
        fields = _VisualizationArtifactFields()
        if not enabled_overlay and not enabled_positions:
            fields.analysis_overlay_video_status = "skipped"
            fields.analysis_overlay_video_detail = "分析叠加视频未启用"
            fields.position_visualizations_status = "skipped"
            fields.position_visualizations_detail = "位置可视化未启用"
            return fields

        self._notify_progress(
            progress_callback, self._stage("visualization", "可视化输出", "active", "正在生成可视化 artifact…")
        )
        config = VisualizationConfig(language=self.settings.visualization_language)
        inputs = self._load_visualization_inputs(job_id)
        metric_player_points = player_points_from_artifact(inputs.get("players_trajectory") or {})
        render_player_points = (
            player_render_points_from_artifact(inputs.get("player_render_trajectory") or {}) or metric_player_points
        )
        cleaned_ball_points = ball_points_from_artifact(
            inputs.get("cleaned_ball_trajectory") or {}, source="cleaned_ball_trajectory"
        )
        raw_ball_points = ball_points_from_artifact(inputs.get("ball_trajectory") or {}, source="ball_trajectory")
        ball_points = cleaned_ball_points or raw_ball_points
        bounce_points = bounce_points_from_artifact(inputs.get("bounce_events") or {})
        overlay_fps = float((inputs.get("tracking_overlay") or {}).get("fps") or 0.0) or None
        results: list[VisualizationResult] = []

        if enabled_positions:
            try:
                # 0. 解析比赛有效时间（KCR 分母）：clip 区间 > 时间线 rally 净时间 > 总时长回退
                effective_windows = resolve_effective_windows(
                    clip_start_ms=clip_start_ms,
                    clip_end_ms=clip_end_ms,
                    capture_take_id=capture_take_id,
                )
                # 1. 构建结构化可视化数据（前端 SVG 渲染 + PNG fallback 共用）
                builder = PositionVisualizationDataBuilder(
                    reference_distance_m=self.settings.kitchen_line_reference_distance_m,
                )
                structured_data = builder.build_and_write(
                    output_path=self.storage.structured_visualization_data_path(job_id),
                    player_points=metric_player_points,
                    ball_points=ball_points,
                    bounce_points=bounce_points,
                    effective_windows=effective_windows,
                )
                # 2. 生成 PNG（消费结构化数据以避免重复计算 22×10 网格）
                heatmaps_url = f"/api/analysis/jobs/{job_id}/artifacts/position-heatmaps"
                scatter_url = f"/api/analysis/jobs/{job_id}/artifacts/position-scatter-plots"
                image_prefix = f"/api/analysis/jobs/{job_id}/artifacts/position-visualization-images"
                heat_result, scatter_result = PositionVisualizer(config=config).generate(
                    job_id=job_id,
                    structured_data=structured_data,
                    heatmaps_dir=self.storage.heatmaps_dir(job_id),
                    scatter_plots_dir=self.storage.scatter_plots_dir(job_id),
                    heatmaps_manifest_path=self.storage.heatmaps_manifest_json_path(job_id),
                    scatter_manifest_path=self.storage.scatter_plots_manifest_json_path(job_id),
                    image_url_prefix=image_prefix,
                    heatmaps_artifact_url=heatmaps_url,
                    scatter_artifact_url=scatter_url,
                    player_points=metric_player_points,
                    ball_points=ball_points,
                    bounce_points=bounce_points,
                )
                fields.heatmaps_manifest_json_path = heat_result.path
                fields.heatmaps_url = heatmaps_url
                fields.scatter_plots_manifest_json_path = scatter_result.path
                fields.scatter_plots_url = scatter_url
                fields.position_visualizations_status = (
                    "available"
                    if any(result.status == "available" for result in [heat_result, scatter_result])
                    else "no_data"
                )
                fields.position_visualizations_detail = f"{heat_result.detail}；{scatter_result.detail}"
                results.extend([heat_result, scatter_result])
            except Exception as exc:
                detail = f"位置可视化生成失败：{exc}"
                fields.position_visualizations_status = "failed"
                fields.position_visualizations_detail = detail
                results.append(VisualizationResult("failed", detail))
        else:
            fields.position_visualizations_status = "skipped"
            fields.position_visualizations_detail = "位置可视化未启用"

        if enabled_overlay:
            overlay_url = f"/api/analysis/jobs/{job_id}/artifacts/analysis-overlay-video"
            if video is None:
                fields.analysis_overlay_video_status = "unavailable"
                fields.analysis_overlay_video_detail = "缺少源视频，无法生成分析叠加视频"
                results.append(VisualizationResult("unavailable", fields.analysis_overlay_video_detail))
            else:
                try:

                    def overlay_progress(written: int, frame_count: int) -> None:
                        stage = self._stage(
                            "visualization",
                            "可视化输出",
                            "active",
                            f"正在生成分析叠加视频：已写出 {written}/{frame_count or 'unknown'} 帧",
                        )
                        if frame_count > 0:
                            stage.progress = min(95, max(20, int((written / frame_count) * 95)))
                        else:
                            stage.progress = min(95, max(20, 20 + written // 120))
                        stage.counters = {
                            "written_frame_count": written,
                            "planned_frame_count": frame_count,
                            "artifact": "analysis-overlay-video",
                        }
                        self._notify_progress(progress_callback, stage)

                    overlay_result = OverlayVideoWriter(config=config).write(
                        source_video_path=Path(video.path),
                        output_path=self.storage.analysis_overlay_video_path(job_id),
                        tracking_overlay=inputs.get("tracking_overlay"),
                        pose_overlay=inputs.get("pose_overlay"),
                        ball_overlay=inputs.get("ball_overlay"),
                        player_points=render_player_points,
                        ball_points=ball_points,
                        bounce_points=bounce_points,
                        fps_override=overlay_fps,
                        clip_start_ms=clip_start_ms,
                        clip_end_ms=clip_end_ms,
                        progress_callback=overlay_progress,
                    )
                    fields.analysis_overlay_video_status = overlay_result.status
                    fields.analysis_overlay_video_detail = overlay_result.detail
                    if overlay_result.status == "available":
                        fields.analysis_overlay_video_path = overlay_result.path
                        fields.analysis_overlay_video_url = overlay_url
                        fields.analysis_overlay_video_metadata = overlay_result.metadata
                    results.append(overlay_result)
                except Exception as exc:
                    detail = f"分析叠加视频生成失败：{exc}"
                    fields.analysis_overlay_video_status = "failed"
                    fields.analysis_overlay_video_detail = detail
                    results.append(VisualizationResult("failed", detail))
        else:
            fields.analysis_overlay_video_status = "skipped"
            fields.analysis_overlay_video_detail = "分析叠加视频未启用"

        fields.stage_status = self._visualization_stage_status(results)
        fields.stage_detail = self._visualization_stage_detail(fields)
        return fields

    def _load_visualization_inputs(self, job_id: str) -> dict[str, dict[str, Any]]:
        paths = {
            "tracking_overlay": self.storage.tracking_overlay_json_path(job_id),
            "pose_overlay": self.storage.pose_overlay_json_path(job_id),
            "ball_overlay": self.storage.ball_overlay_json_path(job_id),
            "players_trajectory": self.storage.player_trajectory_json_path(job_id),
            "player_render_trajectory": self.storage.player_render_trajectory_path(job_id),
            "ball_trajectory": self.storage.ball_trajectory_json_path(job_id),
            "cleaned_ball_trajectory": self.storage.cleaned_ball_trajectory_json_path(job_id),
            "bounce_events": self.storage.bounce_events_json_path(job_id),
        }
        payloads: dict[str, dict[str, Any]] = {}
        for name, path in paths.items():
            if not path.exists():
                continue
            try:
                payload = self.storage.read_json(path)
            except Exception:
                continue
            if isinstance(payload, dict):
                payloads[name] = payload
        return payloads

    @staticmethod
    def _visualization_stage_status(results: list[VisualizationResult]) -> str:
        statuses = [result.status for result in results] or ["skipped"]
        if any(status == "available" for status in statuses) and any(
            status in {"failed", "unavailable"} for status in statuses
        ):
            return "partial"
        if any(status == "available" for status in statuses):
            return "done"
        if any(status == "failed" for status in statuses):
            return "failed"
        if any(status in {"no_data", "unavailable"} for status in statuses):
            return "unavailable"
        return "skipped"

    @staticmethod
    def _visualization_stage_detail(fields: _VisualizationArtifactFields) -> str:
        parts = []
        if fields.analysis_overlay_video_status:
            parts.append(f"叠加视频：{fields.analysis_overlay_video_detail or fields.analysis_overlay_video_status}")
        if fields.position_visualizations_status:
            parts.append(f"位置图：{fields.position_visualizations_detail or fields.position_visualizations_status}")
        return "；".join(parts) if parts else "可视化输出未生成"

    def _run_tracking(
        self,
        job_id: str,
        video: VideoMetadata,
        homography: list[list[float]],
        video_id: str | None,
        calibration_id: str | None,
        calibration_keypoints: list[CalibrationKeypoint] | None,
        frame_stride: int,
        capture_take_id: str | None = None,
        source_fps: float | None = None,
        court_view_match_threshold: float | None = None,
        match_context: MatchAnalysisContext | None = None,
        progress_callback: ProgressCallback | None = None,
        cancellation_token: CancellationToken | None = None,
        clip_start_ms: int | None = None,
        clip_end_ms: int | None = None,
    ) -> _TrackingRunOutput:
        # 真正的"逐帧跟踪"循环（只在 路径A 调用）。
        try:
            import cv2  # type: ignore
        except ImportError as exc:
            raise RuntimeError("OpenCV is required to read video frames") from exc

        stride = max(1, int(frame_stride))
        capture = cv2.VideoCapture(video.path)
        if not capture.isOpened():
            raise RuntimeError(f"Could not read uploaded video: {video.path}")

        # 读取视频基础信息
        raw_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
        fps_info = resolve_effective_fps(source_fps, raw_fps)
        fps = fps_info.effective_fps
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        frame_width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        frame_height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        timing_provider = FrameTimingProvider.from_media(
            video.path,
            frame_count=frame_count,
            fps=fps,
        )

        # ── 时间裁剪 + 预热区间 ──
        pre_roll_ms = self.settings.pre_roll_ms if hasattr(self.settings, "pre_roll_ms") else 1500
        post_roll_ms = self.settings.post_roll_ms if hasattr(self.settings, "post_roll_ms") else 500
        video_duration_ms = int(timing_provider.duration_seconds * 1000)
        try:
            window = resolve_analysis_window(
                source_duration_ms=video_duration_ms,
                source_frame_count=frame_count,
                fps=fps,
                clip_start_ms=clip_start_ms,
                clip_end_ms=clip_end_ms,
                pre_roll_ms=pre_roll_ms,
                post_roll_ms=post_roll_ms,
                timing_provider=timing_provider,
            )
        except AnalysisWindowError:
            capture.release()
            raise
        clip_applied = window.enabled
        decode_start_frame = window.decoded_start_frame
        decode_end_frame = window.decoded_end_frame
        clip_start_frame = window.requested_start_frame
        clip_end_frame = window.requested_end_frame
        frame_index = decode_start_frame
        if clip_applied:
            capture.set(cv2.CAP_PROP_POS_FRAMES, decode_start_frame)
        # 球场视角（court-view）相关评分器/状态机/阈值
        # 支持任务级覆盖 court_view_match_threshold
        effective_match_threshold = (
            court_view_match_threshold
            if court_view_match_threshold is not None
            else self.settings.court_view_match_threshold
        )
        court_view_thresholds = CourtViewThresholds(
            match_threshold=effective_match_threshold,
            start_frames=self.settings.court_view_start_frames,
            end_frames=self.settings.court_view_end_frames,
            diagnostic_only=self.settings.court_view_diagnostic_only or not self.settings.enable_court_view_gate,
            skip_non_court_frames=self.settings.court_view_skip_non_court_frames
            and self.settings.enable_court_view_gate,
        )
        court_view_scorer = CourtViewFrameScorer(match_width=self.settings.court_view_match_width)
        court_view_state = CourtViewStateMachine(thresholds=court_view_thresholds)
        court_view_frame_samples = []
        # 检测 ROI（感兴趣区域）：开启则按标定四角算一个扩大框，关闭则用全帧 fallback
        roi_artifact = (
            compute_expanded_detection_roi(
                self._calibration_image_points(calibration_keypoints),
                frame_width,
                frame_height,
                calibration_id=calibration_id,
                config=RoiComputationConfig(
                    padding_ratio=self.settings.detection_roi_padding_ratio,
                    min_padding_px=self.settings.detection_roi_min_padding_px,
                ),
            )
            if self.settings.enable_detection_roi_filter
            else compute_expanded_detection_roi(
                None,
                frame_width,
                frame_height,
                calibration_id=calibration_id,
            ).model_copy(
                update={
                    "status": "skipped",
                    "detail": "detection ROI filter 已被配置禁用，使用全帧 detection fallback",
                    "disabled": True,
                    "diagnostics": {"reason": "disabled_by_config"},
                }
            )
        )
        roi_filtered_detection_count = 0
        full_frame_fallback_count = 0

        calibration_diagnostics_path: str | None = None
        calibration_quality: str | None = None
        if calibration_keypoints and frame_width > 0 and frame_height > 0:
            try:
                image_points = self._calibration_image_points(calibration_keypoints)
                court_points = [(kp.court.x, kp.court.y) for kp in calibration_keypoints]
                if image_points and len(image_points) >= 4 and len(court_points) >= 4:
                    diagnostics = CalibrationDiagnostics(
                        homography=homography,
                        image_points=image_points,
                        court_points=court_points,
                        frame_shape=(frame_width, frame_height),
                    )
                    diag_result = diagnostics.diagnose()
                    calibration_quality = diag_result.calibration_quality
                    diag_path = self.storage.calibration_diagnostics_json_path(job_id)
                    diagnostics.write_artifact(diag_path, job_id)
                    calibration_diagnostics_path = str(diag_path)
            except Exception:
                pass

        debug_writer: ProjectionDebugWriter | None = None
        debug_minimap: MinimapVisualizer | None = None
        debug_overlay: ProjectionDebugOverlayWriter | None = None
        debug_path = self.storage.outputs_dir / job_id / "projection_debug.jsonl"
        debug_writer = ProjectionDebugWriter(debug_path)
        debug_writer.open()
        debug_minimap = MinimapVisualizer()
        debug_overlay_path = self.storage.outputs_dir / job_id / "projection_debug_overlay.mp4"
        debug_overlay = ProjectionDebugOverlayWriter(
            debug_overlay_path,
            fps=fps,
            width=frame_width,
            height=frame_height,
        )

        last_processed_frame_index: int | None = None
        last_processed_timestamp: float | None = None
        processed_frame_count = 0
        pose_frames = []
        # 姿态阶段：未启用姿态估计时先预置一个 skipped 阶段
        pose_stage = (
            self._stage("pose", "人体姿态", "skipped", "RTMPose 姿态识别未启用，暂不生成骨架关节")
            if self.pose_estimator is None
            else None
        )
        pose_error: str | None = None
        # 解析单视角 tracking 运行配置并装配可复用 ViewTrackingSession
        # （保留 tracker / footpoint_estimator / projector 依赖注入语义）。
        ball_stationary_blacklist_frames = frames_for_seconds(self.settings.ball_stationary_blacklist_seconds, fps)
        match_ctx = match_context or build_match_context(None)
        tracking_config = build_view_tracking_config(
            self.settings,
            match_ctx,
            fps=fps,
            frame_stride=stride,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        session = build_view_tracking_session(
            detector=self.detector,
            homography=homography,
            roi_artifact=roi_artifact,
            config=tracking_config,
            tracker=self.tracker,
            footpoint_estimator=self.footpoint_estimator,
            projector=self.projector,
        )
        from app.vision.pickleball_game_analysis.ball_tracker import BallTrackerConfig

        semantic_mode_raw = str(getattr(self.settings, "ball_semantic_policy_mode", "shadow") or "shadow").lower()
        try:
            semantic_mode = SemanticPolicyMode(semantic_mode_raw)
        except ValueError:
            semantic_mode = SemanticPolicyMode.SHADOW
        semantic_config = BallSemanticPolicyConfig(
            mode=semantic_mode,
            enforce_authoritative_non_play=bool(
                getattr(self.settings, "ball_semantic_enforce_authoritative_non_play", False)
            ),
            enforced_rollout_enabled=bool(
                getattr(self.settings, "ball_semantic_enforced_rollout", False)
            ),
            rollout_id=str(getattr(self.settings, "ball_semantic_rollout_id", "default") or "default"),
            semantic_timeline_enabled=bool(getattr(self.settings, "ball_semantic_timeline_enabled", True)),
            serve_prepare_confidence=float(
                getattr(self.settings, "ball_semantic_serve_prepare_confidence", 0.55)
            ),
            serve_armed_confidence=float(getattr(self.settings, "ball_semantic_serve_armed_confidence", 0.70)),
            rally_end_min_evidence=int(getattr(self.settings, "ball_semantic_rally_end_min_evidence", 2)),
            policy_version=str(
                getattr(self.settings, "ball_semantic_policy_version", "semantic_boundary_policy.v1")
            ),
            min_confirm_ticks=int(getattr(self.settings, "ball_semantic_min_confirm_ticks", 2)),
            grace_window_sec=float(getattr(self.settings, "ball_semantic_grace_window_seconds", 0.20)),
            rescue_min_consecutive_ticks=int(
                getattr(self.settings, "ball_semantic_rescue_min_consecutive_ticks", 2)
            ),
            rescue_min_motion_pixels=float(
                getattr(self.settings, "ball_semantic_rescue_min_motion_pixels", 15.0)
            ),
            evidence_freshness_sec=float(
                getattr(self.settings, "ball_semantic_evidence_freshness_seconds", 0.50)
            ),
            conflict_penalty=float(getattr(self.settings, "ball_semantic_conflict_penalty", 0.25)),
            boundary_eval_enabled=bool(getattr(self.settings, "ball_semantic_boundary_eval_enabled", True)),
        )
        semantic_provider = (
            SemanticTimelineProvider.from_capture_take(
                capture_take_id,
                clip_start_ms=clip_start_ms,
                clip_end_ms=clip_end_ms,
                video_duration_ms=video_duration_ms,
                config=semantic_config,
            )
            if bool(getattr(self.settings, "enable_ball_semantic_policy", True))
            and semantic_config.semantic_timeline_enabled
            else None
        )
        # 球检测（可选）：启用且适配器可用时逐帧运行，使用局部 context 封装状态
        ball_ctx = _BallRunContext(
            tracker=(
                BallTracker(
                    detector=self.ball_detector,
                    config=BallTrackerConfig(
                        effective_fps=fps / max(1, stride),
                        frame_stride=max(1, stride),
                        stationary_blacklist_frames=ball_stationary_blacklist_frames,
                    ),
                    court_adapter=BallCourtAdapter(),
                )
                if self.ball_detector is not None
                else None
            ),
            disabled_reason=(
                self.ball_detection_unavailable_reason
                if self.ball_detector is None and self.ball_detection_enabled
                else None
            ),
            semantic_provider=semantic_provider,
            semantic_policy=BallSearchPolicy(semantic_config) if semantic_provider is not None else None,
        )

        window_metadata = window.metadata()
        window_metadata["timing_provenance"] = timing_provider.metadata()
        window_metadata["processed_frame_count"] = 0
        requested_clip = window_metadata.get("requested_clip") if clip_applied else None
        decoded_range = window_metadata.get("decoded_range") if clip_applied else None

        try:
            while True:
                self._check_cancelled(cancellation_token)
                ok, frame = capture.read()
                if not ok:
                    break
                # clip 范围终止
                if clip_applied and frame_index >= decode_end_frame:
                    break
                # 按 stride 抽帧：不是目标帧就跳过
                if frame_index % stride != 0:
                    frame_index += 1
                    continue

                timestamp = timing_provider.take_timestamp_for_frame(frame_index)
                if timestamp is None:
                    timestamp = frame_index / fps
                # 标记帧是否为预热帧（pre-roll / post-roll context）
                last_processed_frame_index = frame_index
                last_processed_timestamp = timestamp
                if processed_frame_count == 0 and self.settings.enable_court_view_gate:
                    court_view_scorer.initialize(frame)
                court_view_score = (
                    court_view_scorer.score(frame)
                    if self.settings.enable_court_view_gate and court_view_scorer.available
                    else None
                )
                court_view_sample = court_view_state.update(frame_index, timestamp, court_view_score)
                court_view_frame_samples.append(court_view_sample)
                processed_frame_count += 1
                window_metadata["processed_frame_count"] = processed_frame_count
                # 被"非球场视角"门控挡住的帧，跳过后续检测
                if court_view_sample.reason == "gated_non_court_view":
                    self._check_cancelled(cancellation_token)
                    frame_index += 1
                    continue

                # 1-8b) 复用 ViewTrackingSession 完成逐帧 tracking 计算链
                # （detect → ROI filter → tracker → footpoint → project → smooth →
                #  select → lock → identity → render observations）。processed_frame_count
                # 已在 gate 前递增（D1b），此处只消费 session 输出驱动 debug / ball / pose。
                result = session.step(frame, frame_index=frame_index, timestamp=timestamp)
                frame_positions = result.frame_positions
                frame_detections = result.frame_detections
                render_raw_by_track = result.render_raw_by_track
                player_motion_pixels = result.player_motion_pixels

                # 5d) 投影调试日志写入（每帧每个球员一行 JSONL）—— 消费 session 结果
                if debug_writer is not None and debug_minimap is not None:
                    for pos in frame_positions:
                        # 原始投影值（session 在平滑前保存），平滑后 court_position 已被覆盖
                        raw = render_raw_by_track.get(pos.track_id)
                        raw = [raw["x_ft"], raw["y_ft"]] if raw else None
                        smoothed = pos.court_position
                        px = None
                        if smoothed and len(smoothed) >= 2:
                            px = debug_minimap.court_to_pixel(smoothed[0], smoothed[1])
                        fp_method = pos.footpoint_method or "unknown"
                        near_bottom = False
                        clip_suspected = False
                        pose_unavailable = False
                        if hasattr(pos, "footpoint_metadata") and pos.footpoint_metadata:
                            near_bottom = pos.footpoint_metadata.get("near_frame_bottom", False)
                            clip_suspected = pos.footpoint_metadata.get("bbox_clip_suspected", False)
                            pose_unavailable = bool(pos.footpoint_metadata.get("pose_unavailable", False))
                        status = pos.projection_status or "unknown"
                        filter_reason = None
                        if status == "outside_tracking_area":
                            filter_reason = "court position outside allowed tracking bounds (x:-4..24, y:-8..52)"
                        debug_writer.write_frame(
                            frame_index=frame_index,
                            track_id=pos.track_id,
                            bbox=pos.bbox,
                            image_footpoint=pos.image_footpoint,
                            footpoint_method=fp_method,
                            footpoint_confidence=pos.projection_confidence,
                            court_position_raw=raw if raw else [0, 0],
                            court_position_smoothed=smoothed if smoothed else [0, 0],
                            projection_status=status,
                            minimap_pixel=px,
                            calibration_quality=calibration_quality,
                            near_frame_bottom=near_bottom,
                            bbox_clip_suspected=clip_suspected,
                            pose_unavailable=pose_unavailable,
                            filter_reason=filter_reason,
                        )
                # 球检测（可选）：提取至 _process_ball_frame()，保持单视频循环
                if ball_ctx.tracker is not None:
                    self._process_ball_frame(
                        context=ball_ctx,
                        frame=frame,
                        frame_index=frame_index,
                        timestamp=timestamp,
                        homography=homography,
                        frame_width=frame_width,
                        frame_height=frame_height,
                        player_motion_pixels=player_motion_pixels,
                    )
                # 9) 姿态估计（可选）
                if self.pose_estimator is not None and frame_detections and pose_error is None:
                    try:
                        pose_frame = self.pose_estimator.estimate_frame(
                            frame=frame,
                            subjects=frame_detections,
                            frame_index=frame_index,
                            timestamp_seconds=timestamp,
                        )
                        # 只保留有关键点的骨架
                        pose_frame.subjects = [subject for subject in pose_frame.subjects if subject.keypoints]
                        if pose_frame.subjects:
                            pose_frames.append(pose_frame)
                    except Exception as exc:
                        pose_error = str(exc)
                        pose_frames = []
                self._check_cancelled(cancellation_token)

                # 每隔 30 帧打一条进度日志
                if processed_frame_count == 1 or processed_frame_count % 30 == 0:
                    frame_progress = self._tracking_frame_progress(
                        processed_frame_count=processed_frame_count,
                        frame_count=window.planned_frame_count,
                        stride=stride,
                    )
                    progress_stage = self._stage(
                        "frame-sampling",
                        "抽帧采样",
                        "active",
                        f"正在逐帧分析：已处理 {processed_frame_count}/{max(1, (window.planned_frame_count + stride - 1) // stride) if window.planned_frame_count else 'unknown'} 个抽样帧",  # noqa: E501
                    )
                    progress_stage.progress = frame_progress
                    progress_stage.counters = {
                        "processed_frame_count": processed_frame_count,
                        "source_frame_count": frame_count,
                        "planned_frame_count": window.planned_frame_count,
                        "frame_stride": stride,
                    }
                    self._notify_progress(progress_callback, progress_stage)
                    logger.info(
                        "Player tracking progress: processed %s/%s frames",
                        processed_frame_count,
                        frame_count or "unknown",
                    )

                if debug_overlay is not None and frame_positions:
                    debug_overlay.write_frame(frame, frame_index, frame_positions)

                frame_index += 1
        finally:
            capture.release()
            if debug_writer is not None:
                debug_writer.close()
            if debug_overlay is not None:
                debug_overlay.close()
        court_view_state.finish(last_processed_frame_index, last_processed_timestamp)

        # 结束阶段快照：session 累积的 tracking 产物 + 诊断 + selector 状态
        outputs = session.snapshot()
        # 预热帧可以留在 tracker 内部状态中，但所有正式 artifact 都只暴露
        # requested clip。这样 child 融合和前端可视化不会把 pre-roll 当成分析结果。
        if clip_applied:
            outputs.raw_detections = [
                item for item in outputs.raw_detections if window.is_requested_frame(item.frame_index)
            ]
            outputs.overlay_frames = [
                item for item in outputs.overlay_frames if window.is_requested_frame(item.frame_index)
            ]
            outputs.positions = [
                item for item in outputs.positions if window.is_requested_frame(item.frame_index)
            ]
            outputs.player_multitarget_detections = [
                item
                for item in outputs.player_multitarget_detections
                if window.is_requested_frame(item.frame_index)
            ]
            outputs.render_observations = [
                item for item in outputs.render_observations if window.is_requested_frame(item.frame_index)
            ]
            outputs.render_events = [
                item for item in outputs.render_events if window.is_requested_frame(item.frame_index)
            ]
        logger.info(
            "Player tracking completed: processed %s frames, %s projected position samples",
            processed_frame_count,
            len(outputs.positions),
        )

        # 组装跟踪结果
        tracking_result = TrackingResult(
            video_id=video_id,
            calibration_id=calibration_id,
            fps=fps,
            frame_count=frame_count,
            frame_width=frame_width,
            frame_height=frame_height,
            processed_frame_count=processed_frame_count,
            frame_stride=stride,
            detections=outputs.raw_detections,
            overlay_frames=outputs.overlay_frames,
            tracks=outputs.tracks,
            positions=outputs.positions,
            timing_provenance=timing_provider.metadata(),
        )
        # 球员轨迹 + 投影轨迹点 + 主球员选择（lock diagnostics 合并由 session 内部完成）
        player_trajectories = session.build_player_trajectory_artifact(
            job_id=job_id,
            video_id=video_id,
            fps=fps,
            frame_count=frame_count,
            processed_frame_count=processed_frame_count,
            frame_stride=stride,
        )
        if clip_applied:
            player_trajectories = player_trajectories.model_copy(
                update={
                    "players": {
                        player_id: [sample for sample in samples if window.is_requested_frame(sample.frame_index)]
                        for player_id, samples in player_trajectories.players.items()
                    },
                    "processed_frame_count": window.requested_frame_count,
                }
            )
        player_trajectories = player_trajectories.model_copy(
            update={"timing_provenance": timing_provider.metadata()}
        )
        player_metric_tracks = session.projected_metric_tracks(output_court_unit="ft")

        # ── 过滤预热帧：仅保留 clip 范围内的 track points 用于指标计算 ──
        if clip_applied and player_metric_tracks:
            player_metric_tracks = [
                pt for pt in player_metric_tracks if window.is_requested_frame(pt.frame_index)
            ]

        player_selection = PlayerSelectionArtifact(
            job_id=job_id,
            video_id=video_id,
            status="available",
            detail=(
                f"已生成 {len(outputs.selection_diagnostics)} 条目标球场主球员选择诊断；"
                f"模式 {outputs.selector_mode}"
            ),
            selection_mode=outputs.selector_mode,  # type: ignore[arg-type]
            fallback_reason=outputs.selector_fallback_reason,
            participant_limit=session.config.effective_player_count,
            diagnostics=outputs.selection_diagnostics,
            training_samples=outputs.latest_selection_training_samples,
        )
        if self.pose_estimator is not None:
            # 根据姿态估计结果决定姿态阶段状态
            if pose_error:
                pose_stage = self._stage("pose", "人体姿态", "skipped", f"RTMPose 不可用：{pose_error}")
            elif pose_frames:
                pose_stage = self._stage(
                    "pose", "人体姿态", "done", f"已生成 {sum(len(frame.subjects) for frame in pose_frames)} 组骨架关节"
                )
            else:
                pose_stage = self._stage("pose", "人体姿态", "skipped", "没有可用人体框或骨架关键点，未生成骨架关节")
        pose_artifact = None
        if pose_frames:
            pose_artifact = PoseOverlayArtifact(
                job_id=job_id,
                video_id=video_id,
                status="available",
                detail=f"已生成 {sum(len(frame.subjects) for frame in pose_frames)} 组骨架关节",
                keypoint_schema=self.settings.pose_keypoint_schema,
                source=SourceFrameSize(width=max(1, frame_width), height=max(1, frame_height)),
                timing_provenance=timing_provider.metadata(),
                skeleton_edges=default_skeleton_edges(),
                frames=pose_frames,
            )
        # 球场视角 ROI 产物
        court_view_roi_artifact = build_court_view_roi_artifact(
            job_id=job_id,
            video_id=video_id,
            calibration_id=calibration_id,
            thresholds=court_view_thresholds,
            roi=roi_artifact,
            state_machine=court_view_state,
            processed_frame_count=processed_frame_count,
            frame_samples=court_view_frame_samples,
            scorer_detail=court_view_scorer.detail
            if self.settings.enable_court_view_gate
            else "court-view gate 已被配置禁用",
            scorer_available=court_view_scorer.available and self.settings.enable_court_view_gate,
            roi_filtered_detection_count=outputs.roi_filtered_detection_count,
            full_frame_fallback_count=outputs.full_frame_fallback_count,
        )
        # 在 diagnostics 中记录阈值来源
        threshold_source = "task_override" if court_view_match_threshold is not None else "default_config"
        court_view_roi_artifact.diagnostics["match_threshold_source"] = threshold_source
        court_view_roi_artifact.diagnostics["match_threshold_effective"] = effective_match_threshold
        court_view_roi_artifact.diagnostics.update(fps_info.diagnostics())
        court_view_roi_artifact.diagnostics["fps_time_windows"] = {
            "primary_player_window_frames": session.config.primary_player_window_frames,
            "player_identity_lost_buffer_frames": session.config.identity_lost_buffer_frames,
            "player_identity_inactive_buffer_frames": session.config.identity_inactive_buffer_frames,
            "player_identity_interpolation_buffer_frames": session.config.identity_interpolation_buffer_frames,
            "player_lock_bootstrap_min_frames": session.config.player_lock_bootstrap_min_frames,
            "player_lock_bootstrap_max_frames": session.config.player_lock_bootstrap_max_frames,
            "player_lock_lost_grace_frames": session.config.player_lock_lost_grace_frames,
            "player_lock_lost_max_frames_locked": session.config.player_lock_lost_max_frames_locked,
            "ball_stationary_blacklist_frames": ball_stationary_blacklist_frames,
        }
        # 高剔除率预警
        if (
            court_view_roi_artifact.processed_frame_count > 0
            and court_view_roi_artifact.non_court_view_frame_count / court_view_roi_artifact.processed_frame_count > 0.9
        ):
            gate_rate = (
                court_view_roi_artifact.non_court_view_frame_count / court_view_roi_artifact.processed_frame_count
            )
            court_view_roi_artifact.detail += (
                f"；注意：门控剔除率过高（{gate_rate:.0%}），骨架输出可能极度稀疏。"
                f"可通过降低 courtViewMatchThreshold（当前 {effective_match_threshold}）或关闭门控来提升覆盖率"
            )
            court_view_roi_artifact.diagnostics["high_gating_rate_warning"] = (
                f"non_court_view_frame_count/court_view_frame_count 比例为 "
                f"{court_view_roi_artifact.non_court_view_frame_count}/{court_view_roi_artifact.court_view_frame_count} "  # noqa: E501
                f"（剔除率 {gate_rate:.0%}），骨架输出可能极度稀疏"
            )
        # 球分析后处理：提取至 _run_bounce_detection()，不再内联处理
        if clip_applied:
            ball_ctx.samples = [
                item for item in ball_ctx.samples if window.is_requested_frame(item.frame_index)
            ]
            ball_ctx.detections = [
                item for item in ball_ctx.detections if window.is_requested_frame(item.frame_index)
            ]
            pose_frames = [item for item in pose_frames if window.is_requested_frame(item.frame_index)]
        ball_run_output = self._run_bounce_detection(
            job_id=job_id,
            video_id=video_id,
            ball_ctx=ball_ctx,
            fps=fps,
        )
        # 渲染轨迹后处理：生成逐帧位置（仅在存在观测时）
        render_output = None
        if outputs.render_observations:
            try:
                postprocessor = CourtTrackPostProcessor(
                    max_interpolation_gap_seconds=self.settings.overlay_frame_stride / fps + 0.15,
                    max_visible_gap_seconds=0.60,
                    max_spike_displacement_ft=6.0,
                )
                postprocess_result = postprocessor.process(
                    observations=outputs.render_observations,
                    events=outputs.render_events,
                    fps=fps,
                    total_frames=window.requested_frame_count if clip_applied else frame_count,
                )
                render_output = {
                    "players": [
                        {
                            "player_id": p.player_id,
                            "render_slot": p.render_slot,
                            "initial_side": p.initial_side,
                            "dominant_side": p.dominant_side,
                            "first_frame_index": p.first_frame_index,
                            "source_track_ids": p.source_track_ids,
                        }
                        for p in postprocess_result.players
                    ],
                    "segments": [
                        {
                            "segment_id": s.segment_id,
                            "player_id": s.player_id,
                            "identity_epoch": s.identity_epoch,
                            "start_frame_index": s.start_frame_index,
                            "end_frame_index": s.end_frame_index,
                            "start_timestamp_seconds": s.start_timestamp_seconds,
                            "end_timestamp_seconds": s.end_timestamp_seconds,
                            "break_before": s.break_before,
                            "sample_count": s.sample_count,
                        }
                        for s in postprocess_result.segments
                    ],
                    "samples": [
                        {
                            "sequence_index": s.sequence_index,
                            "frame_index": s.frame_index,
                            "timestamp_seconds": s.timestamp_seconds,
                            "x_ft": s.x_ft,
                            "y_ft": s.y_ft,
                            "source": s.source,
                            "confidence": s.confidence,
                            "player_id": s.player_id,
                            "render_slot": s.render_slot,
                            "side": s.side,
                            "segment_id": s.segment_id,
                            "identity_epoch": s.identity_epoch,
                            "source_track_id": s.source_track_id,
                            "projection_status": s.projection_status,
                            "projection_confidence": s.projection_confidence,
                            "footpoint_method": s.footpoint_method,
                        }
                        for s in postprocess_result.samples
                    ],
                }
            except RenderSlotOverflowError as exc:
                logger.warning("渲染轨迹槽位不足: %s", exc)
                render_output = None
            except Exception:
                logger.exception("渲染轨迹后处理失败，跳过 render_trajectory 生成")
        return _TrackingRunOutput(
            tracking=tracking_result,
            player_trajectories=player_trajectories,
            player_metric_tracks=player_metric_tracks,
            player_selection=player_selection,
            pose=pose_artifact,
            pose_stage=pose_stage,
            pose_frames=pose_frames,
            court_view_roi=court_view_roi_artifact,
            ball_run_output=ball_run_output,
            player_multitarget_detections=outputs.player_multitarget_detections,
            calibration_diagnostics_path=calibration_diagnostics_path,
            render_trajectory=render_output,
            requested_clip=requested_clip,
            decoded_range=decoded_range,
            analysis_window=window_metadata,
        )

    @staticmethod
    def _process_ball_frame(
        *,
        context: _BallRunContext,
        frame: object,
        frame_index: int,
        timestamp: float,
        homography: list[list[float]],
        frame_width: int,
        frame_height: int,
        player_motion_pixels: float | None = None,
    ) -> None:
        """逐帧球检测处理，封装 try/except 和 context.tracker 降级逻辑。

        当 context.tracker 为 None 时直接返回（不处理）。
        异常时记录 error 并将 tracker 置为 None，禁用后续帧的球检测。
        """
        if context.tracker is None:
            return
        try:
            # 只在这里调用一次 detector；随后把同一份候选交给策略和 tracker。
            raw_candidates = list(
                context.tracker.detector.detect(frame, conf=float(getattr(context.tracker.config, "confidence", 0.18)))
            )
            pre_tick = context.tracker.pre_tick_snapshot(timestamp)
            ball_motion_pixels: float | None = None
            valid_ball_motion = False
            if pre_tick.predicted_position is not None and raw_candidates:
                nearest_distance = min(
                    (
                        (candidate.image_xy[0] - pre_tick.predicted_position[0]) ** 2
                        + (candidate.image_xy[1] - pre_tick.predicted_position[1]) ** 2
                    ) ** 0.5
                    for candidate in raw_candidates
                )
                ball_motion_pixels = float(nearest_distance)
                valid_ball_motion = pre_tick.continuity_score >= 0.72
            context.semantic_raw_candidate_count += len(raw_candidates)
            context.semantic_formal_candidate_before_count += len(raw_candidates)
            snapshot = None
            decision = None
            if context.semantic_provider is not None and context.semantic_policy is not None:
                snapshot = context.semantic_provider.snapshot(
                    timestamp * 1000.0,
                    evidence={
                        **dict(context.semantic_evidence),
                        "player_motion_pixels": player_motion_pixels,
                        "raw_candidate_count": len(raw_candidates),
                        "ball_motion_pixels": ball_motion_pixels,
                        "valid_ball_motion": valid_ball_motion,
                        "ball_continuity": pre_tick.continuity_score,
                    },
                )
                decision = context.semantic_policy.evaluate(
                    snapshot,
                    raw_candidate_count=len(raw_candidates),
                )
                context.semantic_snapshots.append(snapshot)
                context.semantic_decisions.append(decision)
                if snapshot.semantic_fallback:
                    context.semantic_fallback_count += 1

            semantic_enforced_authority = bool(
                decision is not None
                and decision.policy_mode == SemanticPolicyMode.ENFORCED
                and decision.rollout_enabled
                and decision.authority in {SemanticAuthority.MANUAL, SemanticAuthority.CORRECTED}
            )
            boundary_result: dict[str, Any] = {}
            if (
                decision is not None
                and semantic_enforced_authority
                and decision.boundary_action != BallBoundaryAction.NONE
            ):
                boundary_result = context.tracker.apply_semantic_boundary(
                    decision.boundary_action.value,
                    decision.boundary_action_id,
                    timestamp_sec=timestamp,
                )
                context.semantic_boundary_events.append(
                    {
                        "frame_index": frame_index,
                        "timestamp_sec": timestamp,
                        "action": decision.boundary_action.value,
                        "action_id": decision.boundary_action_id,
                        **boundary_result,
                    }
                )
                if boundary_result.get("applied"):
                    if decision.boundary_action in {
                        BallBoundaryAction.WARM_REACQUIRE,
                        BallBoundaryAction.SERVE_REACQUIRE,
                    }:
                        context.semantic_warm_capture_count += 1
                    after_segment_id = (boundary_result.get("after") or {}).get("formal_segment_id")
                    if after_segment_id and after_segment_id not in context.semantic_segment_ids:
                        context.semantic_segment_ids.append(after_segment_id)

            hard_gate = bool(
                decision is not None
                and decision.hard_gate_active
                and not decision.tracker_update_allowed
            )
            if hard_gate:
                context.semantic_suppressed_count += len(raw_candidates)
                context.semantic_formal_candidate_after_count += 0
                context.semantic_hard_gate_active = True
                ball_sample = BallFrameSample(
                    frame_index=frame_index,
                    timestamp_sec=timestamp,
                    image_xy=None,
                    court_xy=None,
                    confidence=None,
                    visible=bool(raw_candidates),
                    accepted=False,
                    candidate_count=len(raw_candidates),
                    reject_reason=decision.reason,
                    source="semantic_policy",
                    track_state=context.tracker.track_state.value,
                    overall_decision=decision.action.value,
                    publication_eligible=False,
                    quality_status="diagnostic_only",
                    diagnostics={
                        "semantic_snapshot": snapshot.to_dict() if snapshot is not None else None,
                        "semantic_decision": decision.to_dict(),
                        "raw_candidate_count": len(raw_candidates),
                        "boundary_result": boundary_result,
                        "formal_candidate_count_before": len(raw_candidates),
                        "formal_candidate_count_after": 0,
                    },
                )
            else:
                if context.semantic_hard_gate_active:
                    if not boundary_result.get("applied"):
                        context.tracker.clear()
                    context.semantic_hard_gate_active = False
                ball_sample = context.tracker.update_from_candidates(
                    frame_index=frame_index,
                    timestamp_sec=timestamp,
                    view_candidates=raw_candidates,
                    frame_shape=frame.shape,
                    roi_corners=None,
                    homography=homography,
                    player_motion_pixels=player_motion_pixels,
                )
                if decision is not None:
                    formal_publish = bool(decision.formal_publish_allowed)
                    if not formal_publish:
                        context.semantic_warm_capture_count += 1
                        ball_sample = replace(
                            ball_sample,
                            source="semantic_warm",
                            publication_eligible=False,
                            quality_status="warm_diagnostic",
                            overall_decision=decision.action.value,
                        )
                    elif ball_sample.accepted and ball_sample.publication_eligible:
                        context.semantic_formal_publish_count += 1
                    context.semantic_formal_candidate_after_count += (
                        1 if formal_publish and ball_sample.accepted else 0
                    )
                    ball_sample = replace(
                        ball_sample,
                        diagnostics={
                            **dict(ball_sample.diagnostics),
                            "semantic_snapshot": snapshot.to_dict() if snapshot is not None else None,
                            "semantic_decision": decision.to_dict(),
                            "boundary_result": boundary_result,
                            "formal_candidate_count_before": len(raw_candidates),
                            "formal_candidate_count_after": 1 if formal_publish and ball_sample.accepted else 0,
                        },
                    )
            context.samples.append(ball_sample)
            if ball_sample.image_xy is not None and ball_sample.accepted and ball_sample.publication_eligible:
                context.detections.append(
                    MultiTargetDetection(
                        frame_index=frame_index,
                        timestamp_seconds=timestamp,
                        class_name="ball",
                        point=[float(ball_sample.image_xy[0]), float(ball_sample.image_xy[1])],
                        confidence=float(ball_sample.confidence) if ball_sample.confidence is not None else 0.0,
                        source_width=max(1, frame_width),
                        source_height=max(1, frame_height),
                    )
                )
        except Exception as exc:
            logger.warning("Ball detection failed on frame %s: %s", frame_index, exc)
            context.error = f"球检测运行时失败：{exc}"
            context.tracker = None

    def _run_bounce_detection(
        self,
        *,
        job_id: str,
        video_id: str | None,
        ball_ctx: _BallRunContext,
        fps: float,
    ) -> _BallRunOutput | None:
        """弹跳检测后处理：trajectory cleaning + bounce detection。

        只做算法处理，不负责写文件。写文件由 _finalize_ball_analysis() 负责。
        当 ball context 无 tracker 或无样本时，返回对应的 unavailable/skipped 状态。
        """
        semantic_diagnostics = {
            **(
                ball_ctx.semantic_provider.diagnostics_snapshot()
                if ball_ctx.semantic_provider is not None
                else {"enabled": False}
            ),
            "raw_candidate_count": ball_ctx.semantic_raw_candidate_count,
            "suppressed_candidate_count": ball_ctx.semantic_suppressed_count,
            "fallback_tick_count": ball_ctx.semantic_fallback_count,
            "warm_capture_count": ball_ctx.semantic_warm_capture_count,
            "formal_publish_count": ball_ctx.semantic_formal_publish_count,
            "formal_candidate_count_before": ball_ctx.semantic_formal_candidate_before_count,
            "formal_candidate_count_after": ball_ctx.semantic_formal_candidate_after_count,
            "boundary_events": list(ball_ctx.semantic_boundary_events),
            "segment_ids": list(ball_ctx.semantic_segment_ids),
            "policy_mode": (
                ball_ctx.semantic_policy.config.mode.value
                if ball_ctx.semantic_policy is not None
                else "disabled"
            ),
            "rollout_id": (
                ball_ctx.semantic_policy.config.rollout_id
                if ball_ctx.semantic_policy is not None
                else None
            ),
            "rollout_enabled": (
                bool(ball_ctx.semantic_policy.config.enforced_rollout_enabled)
                if ball_ctx.semantic_policy is not None
                else False
            ),
            "shadow_baseline": (
                ball_ctx.semantic_policy is None
                or ball_ctx.semantic_policy.config.mode == SemanticPolicyMode.SHADOW
            ),
            "policy_version": (
                ball_ctx.semantic_policy.config.policy_version
                if ball_ctx.semantic_policy is not None
                else None
            ),
            "boundary_eval_enabled": (
                bool(ball_ctx.semantic_policy.config.boundary_eval_enabled)
                if ball_ctx.semantic_policy is not None
                else False
            ),
            "evidence_ledger": (
                ball_ctx.semantic_provider.diagnostics_snapshot().get("evidence_ledger", [])
                if ball_ctx.semantic_provider is not None
                else []
            ),
        }
        if ball_ctx.tracker is None and ball_ctx.samples:
            # 球检测中途异常，有部分 sample 但 tracker 已置 None
            accepted_count = sum(1 for s in ball_ctx.samples if s.accepted)
            return _BallRunOutput(
                status="failed",
                samples=ball_ctx.samples,
                ball_detections=ball_ctx.detections,
                raw_points=None,
                cleaned_points=None,
                bounce_events=None,
                accepted_count=accepted_count,
                error=ball_ctx.error or "球检测运行时异常",
                semantic_snapshots=ball_ctx.semantic_snapshots,
                semantic_decisions=ball_ctx.semantic_decisions,
                semantic_diagnostics=semantic_diagnostics,
            )

        if ball_ctx.tracker is None and not ball_ctx.samples:
            # 未启用或未运行
            if self.ball_detector is None and self.ball_detection_enabled:
                return _BallRunOutput(
                    status="unavailable",
                    samples=[],
                    ball_detections=[],
                    raw_points=None,
                    cleaned_points=None,
                    bounce_events=None,
                    accepted_count=0,
                    error=ball_ctx.disabled_reason or self.ball_detection_unavailable_reason,
                    semantic_snapshots=ball_ctx.semantic_snapshots,
                    semantic_decisions=ball_ctx.semantic_decisions,
                    semantic_diagnostics=semantic_diagnostics,
                )
            return None

        # 正常路径：有 tracker 有 sample，执行后处理
        try:
            raw_points = [TrajectoryPoint.from_sample(sample) for sample in ball_ctx.samples]
            # 球路插值按真实秒数限幅，避免 frame_stride 较大时把长丢失误补成直线。
            cleaned_points = TrajectoryCleaner(
                TrajectoryCleanerConfig(max_interpolation_gap_seconds=0.20)
            ).clean(raw_points)
            bounce_events: list[BounceEvent] = []
            if self.settings.enable_bounce_detection and cleaned_points:
                bounce_detector = BounceDetector(config=BounceDetectorConfig(fps=fps))
                bounce_events = bounce_detector.detect(cleaned_points)
            accepted_count = sum(1 for sample in ball_ctx.samples if sample.accepted)
            return _BallRunOutput(
                status="available",
                samples=ball_ctx.samples,
                ball_detections=ball_ctx.detections,
                raw_points=raw_points,
                cleaned_points=cleaned_points,
                bounce_events=bounce_events,
                accepted_count=accepted_count,
                error=None,
                semantic_snapshots=ball_ctx.semantic_snapshots,
                semantic_decisions=ball_ctx.semantic_decisions,
                semantic_diagnostics=semantic_diagnostics,
            )
        except Exception as exc:
            logger.warning("Ball trajectory post-processing failed: %s", exc)
            return _BallRunOutput(
                status="failed",
                samples=ball_ctx.samples,
                ball_detections=ball_ctx.detections,
                raw_points=None,
                cleaned_points=None,
                bounce_events=None,
                accepted_count=sum(1 for sample in ball_ctx.samples if sample.accepted),
                error=str(exc),
                semantic_snapshots=ball_ctx.semantic_snapshots,
                semantic_decisions=ball_ctx.semantic_decisions,
                semantic_diagnostics=semantic_diagnostics,
            )

    @staticmethod
    def _calibration_image_points(keypoints: list[CalibrationKeypoint] | None) -> list[tuple[float, float]] | None:
        # 内部：从标定关键点里按固定顺序（左上、右上、右下、左下）取出图像坐标。
        # 顺序对不上或不足 4 个时，退化为取前 4 个。
        if not keypoints:
            return None
        by_name = {keypoint.name: keypoint.image for keypoint in keypoints}
        ordered_names = ["top_left", "top_right", "bottom_right", "bottom_left"]
        if all(name in by_name for name in ordered_names):
            return [(float(by_name[name].x), float(by_name[name].y)) for name in ordered_names]
        if len(keypoints) < 4:
            return None
        return [(float(keypoint.image.x), float(keypoint.image.y)) for keypoint in keypoints[:4]]

    @staticmethod
    def _detection_stage_detail(tracking_result: TrackingResult, enabled: bool = True) -> str:
        # 内部：根据真实检测结果，生成"人体检测"阶段的人类可读说明。
        if not enabled:
            return "模型推理未启用，未运行 YOLO 人体检测；可设置 PICKLEBALL_ENABLE_MODEL_INFERENCE=true"
        detection_count = len(tracking_result.detections)
        overlay_count = sum(len(frame.detections) for frame in tracking_result.overlay_frames)
        dropped_count = max(0, detection_count - overlay_count)
        if detection_count == 0:
            return (
                f"已处理 {tracking_result.processed_frame_count} 帧，没有检测到可用人体框；"
                "请检查模型配置、拍摄角度、视频清晰度或标定范围"
            )
        if overlay_count == 0:
            return (
                f"已处理 {tracking_result.processed_frame_count} 帧，检测到 {detection_count} 个人体框，"
                "但没有通过主要球员置信度筛选的可渲染比赛球员框"
            )
        return (
            f"已处理 {tracking_result.processed_frame_count} 帧，检测到 {detection_count} 个人体框，"
            f"其中 {overlay_count} 个通过主要球员筛选并用于视频叠加，过滤 {dropped_count} 个低置信度或非主体人物框"
        )

    def _build_tracking_overlay(
        self,
        job_id: str,
        video_id: str | None,
        tracking_result: TrackingResult,
        enabled: bool = True,
    ) -> TrackingOverlayArtifact:
        # 内部：根据检测情况，构造"检测叠加"产物（含状态与说明）。
        detection_count = sum(len(frame.detections) for frame in tracking_result.overlay_frames)
        if not enabled:
            status = "unavailable"
            detail = "YOLO 人体检测未启用，未运行模型推理；请启用后重新分析"
        elif detection_count:
            status = "available"
            raw_count = len(tracking_result.detections)
            dropped_count = max(0, raw_count - detection_count)
            detail = (
                f"已生成 {detection_count} 个通过主要球员置信度筛选的可渲染比赛球员框；"
                f"原始检测 {raw_count} 个，过滤 {dropped_count} 个低置信度或非主体人物框"
            )
        else:
            status = "no_detections"
            detail = (
                f"YOLO 已运行并检测到 {len(tracking_result.detections)} 个人体框，"
                "但没有通过主要球员置信度筛选的可渲染比赛球员框；请检查阈值、球员人数、拍摄角度、视频清晰度或模型配置"
            )
        return TrackingOverlayArtifact(
            job_id=job_id,
            video_id=video_id,
            status=status,
            detail=detail,
            source=SourceFrameSize(
                width=max(1, tracking_result.frame_width),
                height=max(1, tracking_result.frame_height),
            ),
            fps=tracking_result.fps,
            frame_count=tracking_result.frame_count,
            processed_frame_count=tracking_result.processed_frame_count,
            frame_stride=tracking_result.frame_stride,
            timing_provenance=tracking_result.timing_provenance,
            frames=tracking_result.overlay_frames,
        )

    def _positions_to_projected_tracks(self, positions: list[PlayerFramePosition]) -> list[ProjectedTrackPoint]:
        # 内部：把"逐帧球员位置"转成"投影轨迹点"列表。
        # 球员允许站在场地外（发球/接发球站位在底线外），因此不用 position.valid（仅场内）
        # 一刀切过滤；过滤边界与前端 CourtMinimap TRACKING_BOUNDS（x:-4~24, y:-8~52）对齐。
        # 但场外放行仅对高置信度点生效（≥ 主球员置信度阈值），低置信度观众/杂散检测仍排除，
        # 避免小地图渲染观众。
        projected: list[ProjectedTrackPoint] = []
        for position in positions:
            if position.court_position is None:
                continue
            court_x, court_y = position.court_position
            if not (-4.0 <= court_x <= 24.0 and -8.0 <= court_y <= 52.0):
                continue
            in_court = 0.0 <= court_x <= 20.0 and 0.0 <= court_y <= 44.0
            if not in_court and (position.confidence or 0.0) < self.settings.primary_player_min_confidence:
                continue
            image_x, image_y = position.image_footpoint
            projected.append(
                ProjectedTrackPoint(
                    frame_index=position.frame_index,
                    timestamp_seconds=position.timestamp,
                    track_id=str(position.track_id),
                    image_point=ImagePoint(x=image_x, y=image_y),
                    confidence=position.confidence,
                    side="unknown",
                    court_point=ProjectedCourtPoint2D(x=court_x, y=court_y),
                )
            )
        return projected

    @staticmethod
    def _projection_stage_detail(positions: list[PlayerFramePosition]) -> str:
        # 内部：生成"脚点投影"阶段的说明（有效 / 越界样本数量）。
        valid_count = sum(1 for position in positions if position.valid and position.court_position is not None)
        invalid_count = len(positions) - valid_count
        if invalid_count:
            return f"已生成 {valid_count} 个有效场地坐标球员位置，并保留 {invalid_count} 个越界投影诊断样本"
        return f"已生成 {valid_count} 个有效场地坐标球员位置"

    @staticmethod
    def _build_ball_metrics_summary(ball_run_output: _BallRunOutput | None) -> dict[str, Any]:
        """从 _BallRunOutput 构造球分析指标摘要 dict。

        当 ball_run_output 为 None 或不可用时，返回全零/null 的默认值。
        """
        if ball_run_output is None or ball_run_output.status not in {"available"}:
            return {}
        run = ball_run_output
        samples = run.samples or []
        cleaned = run.cleaned_points or []
        bounce_events = run.bounce_events or []
        accepted_count = sum(1 for s in samples if s.accepted)
        detection_rate = round(accepted_count / max(1, len(samples)), 4) if samples else 0.0
        first_bounce = None
        last_bounce = None
        if bounce_events:
            sorted_events = sorted(bounce_events, key=lambda e: e.timestamp_sec)
            first_bounce = float(sorted_events[0].timestamp_sec)
            last_bounce = float(sorted_events[-1].timestamp_sec)
        return {
            "ball_detected_frame_count": accepted_count,
            "ball_detection_rate": detection_rate,
            "ball_trajectory_sample_count": len(run.raw_points) if run.raw_points else 0,
            "cleaned_ball_trajectory_sample_count": len(cleaned),
            "bounce_event_count": len(bounce_events),
            "first_bounce_timestamp_seconds": first_bounce,
            "last_bounce_timestamp_seconds": last_bounce,
        }

    def _compute_metrics(
        self,
        tracks: list[ProjectedTrackPoint],
        ball_metrics: dict[str, Any] | None = None,
        match_context: MatchAnalysisContext | None = None,
    ) -> PerformanceMetrics:
        # 内部：根据投影轨迹点计算各项运动指标，可选地附加球分析摘要。
        metric_tracks = standard_court_metric_points(tracks)
        ball = ball_metrics or {}
        ctx = match_context or build_match_context(None)
        statuses: dict[str, MetricStatus] = {}
        if ctx.enable_doubles_spacing:
            spacing_result = doubles_spacing(metric_tracks)
            statuses["doubles_spacing"] = MetricStatus(status="available")
        else:
            spacing_result = []
            statuses["doubles_spacing"] = MetricStatus(
                status="not_applicable",
                reason="singles_match",
                expected_player_count=ctx.expected_player_count,
            )
        return PerformanceMetrics(
            distances=total_distances(metric_tracks),
            speeds=speed_summaries(metric_tracks),
            kitchen_dwell=kitchen_dwell(metric_tracks),
            doubles_spacing=spacing_result,
            heatmap=generate_heatmap(metric_tracks),
            metric_statuses=statuses,
            ball_detected_frame_count=ball.get("ball_detected_frame_count", 0),
            ball_detection_rate=ball.get("ball_detection_rate", 0.0),
            ball_trajectory_sample_count=ball.get("ball_trajectory_sample_count", 0),
            cleaned_ball_trajectory_sample_count=ball.get("cleaned_ball_trajectory_sample_count", 0),
            bounce_event_count=ball.get("bounce_event_count", 0),
            first_bounce_timestamp_seconds=ball.get("first_bounce_timestamp_seconds"),
            last_bounce_timestamp_seconds=ball.get("last_bounce_timestamp_seconds"),
        )

    @staticmethod
    def _write_player_trajectory_csv(path: Path, artifact: PlayerTrajectoryArtifact) -> None:
        # 内部：把球员轨迹写出成 CSV（方便 Excel 查看）。
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(
                handle,
                fieldnames=[
                    "frame_index",
                    "timestamp_seconds",
                    "player_id",
                    "track_id",
                    "bbox",
                    "image_footpoint",
                    "court_x",
                    "court_y",
                    "smoothed_court_x",
                    "smoothed_court_y",
                    "court_unit",
                    "confidence",
                    "tracking_status",
                    "is_interpolated",
                ],
            )
            writer.writeheader()
            for player_id, samples in sorted(artifact.players.items()):
                for sample in samples:
                    writer.writerow(
                        {
                            "frame_index": sample.frame_index,
                            "timestamp_seconds": sample.timestamp_seconds,
                            "player_id": player_id,
                            "track_id": sample.track_id if sample.track_id is not None else "",
                            "bbox": sample.bbox or "",
                            "image_footpoint": sample.image_footpoint or "",
                            "court_x": sample.court_x,
                            "court_y": sample.court_y,
                            "smoothed_court_x": sample.smoothed_court_x if sample.smoothed_court_x is not None else "",
                            "smoothed_court_y": sample.smoothed_court_y if sample.smoothed_court_y is not None else "",
                            "court_unit": sample.court_unit,
                            "confidence": sample.confidence,
                            "tracking_status": sample.tracking_status,
                            "is_interpolated": sample.is_interpolated,
                        }
                    )

    def _serve_debug_refs(self, job_id: str) -> ServeDebugArtifactRefs:
        # 内部：构造发球调试产物的引用 URL（先占位，检测后写入）。
        return ServeDebugArtifactRefs(
            candidates_url=f"/api/analysis/jobs/{job_id}/artifacts/serve-debug-candidates",
            score_series_url=f"/api/analysis/jobs/{job_id}/artifacts/serve-score-series",
            clips_manifest_url=f"/api/analysis/jobs/{job_id}/artifacts/serve-clips-manifest"
            if self.settings.enable_serve_debug_clips
            else None,
            debug_overlay_url=f"/api/analysis/jobs/{job_id}/artifacts/serve-debug-overlay"
            if self.settings.enable_serve_debug_overlay
            else None,
            status="pending",
            detail="发球候选调试 artifact 将在检测后写入",
        )

    def _write_serve_debug_artifacts(
        self,
        *,
        job_id: str,
        serve_events: ServeEventsArtifact,
        source_video_path: Path,
    ) -> tuple[str, str]:
        # 内部：把发球调试产物（候选 JSON、评分序列、片段、叠加视频）写盘。
        # 即使这里出错也绝不阻断主结果（所以 except 后只返回 failed 状态）。
        try:
            debug = getattr(self.serve_start_detector, "last_debug", None)
            candidates_payload = {
                "job_id": job_id,
                "detector_version": serve_events.detector_version,
                "status": serve_events.status,
                "detail": serve_events.detail,
                "coverage": serve_events.coverage.model_dump(mode="json")
                if serve_events.coverage
                else getattr(debug, "coverage", {}),
                "thresholds": getattr(debug, "thresholds", {}),
                "candidates": getattr(debug, "candidates", []),
                "rejected": getattr(debug, "rejected", []),
                "rejected_buckets": getattr(debug, "rejected_buckets", []),
            }
            self.storage.write_json(self.storage.serve_debug_candidates_json_path(job_id), candidates_payload)
            score_payload = {
                "job_id": job_id,
                "detector_version": serve_events.detector_version,
                "coverage": serve_events.coverage.model_dump(mode="json")
                if serve_events.coverage
                else getattr(debug, "coverage", {}),
                "rejected_buckets": getattr(debug, "rejected_buckets", []),
                "series": getattr(debug, "score_series", []),
            }
            self.storage.write_json(self.storage.serve_score_series_json_path(job_id), score_payload)
            if self.settings.enable_serve_debug_clips:
                manifest = self._write_serve_clip_manifest(
                    job_id=job_id, serve_events=serve_events, source_video_path=source_video_path
                )
                self.storage.write_json(self.storage.serve_clips_manifest_json_path(job_id), manifest)
            if self.settings.enable_serve_debug_overlay:
                self._write_serve_debug_overlay(job_id=job_id, source_video_path=source_video_path)
            return "available", "已生成发球候选调试 JSON 和 score 时间序列"
        except Exception as exc:  # noqa: BLE001 - debug artifacts should never block main results.
            return "failed", f"发球候选调试 artifact 写入失败：{exc}"

    def _write_serve_clip_manifest(
        self,
        *,
        job_id: str,
        serve_events: ServeEventsArtifact,
        source_video_path: Path,
    ) -> dict[str, object]:
        # 内部：为每个发球候选生成一段短视频片段（clip），返回 manifest。
        limit = self.settings.serve_debug_clip_limit
        clips = []
        for event in serve_events.events[:limit]:
            output_path = self.storage.serve_clips_dir(job_id) / f"{event.id}.mp4"
            status = "planned"
            if self.settings.enable_serve_debug_clips:
                status = self._export_video_clip(
                    source_video_path=source_video_path,
                    output_path=output_path,
                    start_seconds=event.start_time_seconds
                    or max(0.0, event.timestamp_seconds - self.settings.serve_clip_pre_seconds),
                    end_seconds=event.end_time_seconds
                    or event.timestamp_seconds + self.settings.serve_clip_post_seconds,
                )
            clips.append(
                {
                    "id": event.id,
                    "timestamp_seconds": event.timestamp_seconds,
                    "start_time_seconds": event.start_time_seconds,
                    "end_time_seconds": event.end_time_seconds,
                    "player_id": event.player_id,
                    "track_id": event.track_id,
                    "confidence": event.confidence,
                    "source_video_path": str(source_video_path),
                    "output_path": str(output_path),
                    "status": status,
                }
            )
        return {
            "job_id": job_id,
            "status": "available",
            "detail": "候选片段导出 manifest 已生成",
            "clip_limit": limit,
            "candidate_count": len(serve_events.events),
            "omitted_count": max(0, len(serve_events.events) - len(clips)),
            "timing_provenance": _timing_provider_for_video(source_video_path).metadata(),
            "clips": clips,
        }

    @staticmethod
    def _export_video_clip(
        *,
        source_video_path: Path,
        output_path: Path,
        start_seconds: float,
        end_seconds: float,
    ) -> str:
        # 内部：从源视频里截取 [start, end] 一段，写成新 mp4。返回状态字符串。
        try:
            import cv2  # type: ignore
        except ImportError:
            return "skipped_opencv_unavailable"
        capture = cv2.VideoCapture(str(source_video_path))
        if not capture.isOpened():
            return "failed_open_source"
        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            if fps <= 0 or width <= 0 or height <= 0:
                return "failed_video_metadata"
            timing_provider = FrameTimingProvider.from_media(
                source_video_path,
                frame_count=frame_count,
                fps=fps,
            )
            start_frame = timing_provider.frame_index_at_or_after_take_time(max(0.0, start_seconds)) or 0
            end_frame = timing_provider.frame_index_at_or_after_take_time(max(start_seconds, end_seconds))
            end_frame = frame_count if end_frame is None else end_frame
            end_frame = max(start_frame + 1, min(frame_count, end_frame))
            output_path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = output_path.with_suffix(".tmp.mp4")
            writer = cv2.VideoWriter(str(temp_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
            if not writer.isOpened():
                return "failed_open_writer"
            try:
                capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
                frame_index = start_frame
                while frame_index < end_frame:
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        break
                    writer.write(frame)
                    frame_index += 1
            finally:
                writer.release()
            temp_path.replace(output_path)
            return "available"
        finally:
            capture.release()

    def _write_serve_debug_overlay(self, *, job_id: str, source_video_path: Path) -> str:
        # 内部：把发球候选在源视频上画框 + 文字，生成一段调试叠加视频。
        try:
            import cv2  # type: ignore
        except ImportError:
            return "skipped_opencv_unavailable"
        debug = getattr(self.serve_start_detector, "last_debug", None)
        candidates = getattr(debug, "candidates", []) if debug is not None else []
        if not candidates:
            return "skipped_no_candidates"
        capture = cv2.VideoCapture(str(source_video_path))
        if not capture.isOpened():
            return "failed_open_source"
        try:
            fps = float(capture.get(cv2.CAP_PROP_FPS) or 0.0)
            frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            if fps <= 0 or width <= 0 or height <= 0:
                return "failed_video_metadata"
            timing_provider = FrameTimingProvider.from_media(
                source_video_path,
                frame_count=frame_count,
                fps=fps,
            )
            output_path = self.storage.serve_debug_overlay_video_path(job_id)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(output_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
            if not writer.isOpened():
                return "failed_open_writer"
            windows = []
            for candidate in candidates[: self.settings.serve_debug_clip_limit]:
                ts = float(candidate.get("timestamp_seconds", 0.0))
                windows.append(
                    (
                        max(0.0, ts - self.settings.serve_clip_pre_seconds),
                        ts + self.settings.serve_clip_post_seconds,
                        candidate,
                    )
                )
            try:
                frame_index = 0
                while True:
                    ok, frame = capture.read()
                    if not ok or frame is None:
                        break
                    timestamp = timing_provider.take_timestamp_for_frame(frame_index)
                    if timestamp is None:
                        timestamp = frame_index / fps
                    active = next((item for item in windows if item[0] <= timestamp <= item[1]), None)
                    if active is not None:
                        _start, _end, candidate = active
                        label = f"{candidate.get('player_id', '')} serve {candidate.get('confidence', 0):.2f}"
                        cv2.putText(frame, label, (24, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
                        bbox = candidate.get("bbox")
                        if isinstance(bbox, list) and len(bbox) == 4:
                            x1, y1, x2, y2 = [int(value) for value in bbox]
                            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 255), 2)
                        writer.write(frame)
                    frame_index += 1
            finally:
                writer.release()
            return "available"
        finally:
            capture.release()

    def _write_result(self, result: AnalysisPipelineResult) -> None:
        # 内部：把最终结果 JSON 落盘。
        self.storage.write_json(self.storage.output_json_path(result.job_id), result.model_dump(mode="json"))

    def _failed(
        self,
        job_id: str,
        video_id: str | None,
        calibration_id: str | None,
        message: str,
        stages: list[PipelineStageResult] | None = None,
    ) -> AnalysisPipelineResult:
        # 内部：构造一个"失败"的最终结果。
        result = AnalysisPipelineResult(
            job_id=job_id,
            video_id=video_id,
            calibration_id=calibration_id,
            status="failed",
            generated_at=datetime.now(UTC),
            stages=stages or [self._stage("video-read", "读取视频", "failed", message)],
            tracks=[],
            metrics=self._compute_metrics([], match_context=None),
            artifacts=AnalysisArtifacts(result_json_path=str(self.storage.output_json_path(job_id))),
            message=message,
        )
        return self.storage.publicize_pipeline_result(result)

    @staticmethod
    def _stage(stage_id: str, label: str, status: str, detail: str) -> PipelineStageResult:
        # 内部：构造一个阶段结果（统一封装）。
        return PipelineStageResult(id=stage_id, label=label, status=status, detail=detail)

    @staticmethod
    def _tracking_frame_progress(*, processed_frame_count: int, frame_count: int, stride: int) -> int:
        # frame-sampling 只是长流水线的前半段，最高停在 95，给后续阶段留出进度空间。
        if frame_count <= 0:
            return min(95, max(10, processed_frame_count // 30))
        expected_sample_count = max(1, (frame_count + max(1, stride) - 1) // max(1, stride))
        return min(95, max(10, int((processed_frame_count / expected_sample_count) * 95)))

    @staticmethod
    def _notify_progress(progress_callback: ProgressCallback | None, stage: PipelineStageResult) -> None:
        # 内部：如果上层传了进度回调，就通知它。
        if progress_callback is not None:
            progress_callback(stage)

    @staticmethod
    def _check_cancelled(cancellation_token: CancellationToken | None) -> None:
        # 内部：如果任务被取消了，立即抛异常中断。
        if cancellation_token is not None:
            cancellation_token.raise_if_cancelled()

    @staticmethod
    def _mock_projected_tracks() -> list[ProjectedTrackPoint]:
        # 内部：演示模式用的确定性 mock 轨迹（不依赖任何模型）。
        court = standard_court()
        raw_points = [
            ("near-a", "near", 0, 0.0, 5.0, 12.0),
            ("near-a", "near", 1, 1.0, 8.0, 15.5),
            ("near-a", "near", 2, 2.0, 10.0, 18.0),
            ("near-b", "near", 0, 0.0, 15.0, 11.0),
            ("near-b", "near", 1, 1.0, 13.5, 14.0),
            ("near-b", "near", 2, 2.0, 12.0, 16.0),
        ]
        tracks = []
        for track_id, side, frame_index, timestamp, x, y in raw_points:
            x = min(max(x, 0.0), court.width_ft)
            y = min(max(y, 0.0), court.length_ft)
            tracks.append(
                ProjectedTrackPoint(
                    frame_index=frame_index,
                    timestamp_seconds=timestamp,
                    track_id=track_id,
                    image_point={"x": x * 10.0, "y": y * 10.0},
                    confidence=0.95,
                    side=side,
                    court_point={"x": x, "y": y},
                )
            )
        return tracks
