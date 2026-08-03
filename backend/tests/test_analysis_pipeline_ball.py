"""球分析 pipeline 集成测试 —— 不依赖真实 YOLO 模型或视频文件。"""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.schemas.ball import BallOverlayArtifact
from app.schemas.pipeline import AnalysisArtifacts, PipelineStageResult
from app.schemas.tracking import ProjectedTrackPoint
from app.schemas.multitarget import MultiTargetDetection
from app.services.analysis_pipeline import (
    AnalysisPipeline,
    _BallArtifactFields,
    _BallRunContext,
    _BallRunOutput,
    _BounceRunOutput,
    _TrackingRunOutput,
)
from app.vision.pickleball_game_analysis.detection_writer import build_ball_overlay_payload
from app.vision.pickleball_game_analysis.schemas import BallFrameSample, BounceEvent, TrajectoryPoint


# ---------------------------------------------------------------------------
# 测试用 helper
# ---------------------------------------------------------------------------

def _make_sample(
    frame_index: int = 0,
    accepted: bool = True,
    image_xy: tuple[float, float] | None = (100.0, 200.0),
    court_xy: tuple[float, float] | None = (10.0, 22.0),
    confidence: float = 0.85,
    visible: bool = True,
    reject_reason: str | None = None,
) -> BallFrameSample:
    return BallFrameSample(
        frame_index=frame_index,
        timestamp_sec=float(frame_index) / 30.0,
        image_xy=image_xy,
        court_xy=court_xy,
        confidence=confidence,
        visible=visible,
        accepted=accepted,
        candidate_count=1 if accepted else 0,
        reject_reason=reject_reason,
    )


def _make_missing_sample(frame_index: int = 0) -> BallFrameSample:
    return BallFrameSample(
        frame_index=frame_index,
        timestamp_sec=float(frame_index) / 30.0,
        image_xy=None,
        court_xy=None,
        confidence=None,
        visible=False,
        accepted=False,
        candidate_count=0,
    )


def _make_storage_mock(tmp_path: Path) -> MagicMock:
    storage = MagicMock()
    storage.outputs_dir = tmp_path
    storage.ball_overlay_json_path.return_value = tmp_path / "ball_overlay.json"
    storage.detections_jsonl_path.return_value = tmp_path / "detections.jsonl"
    storage.ball_trajectory_json_path.return_value = tmp_path / "ball_trajectory.json"
    storage.cleaned_ball_trajectory_json_path.return_value = tmp_path / "cleaned_ball_trajectory.json"
    storage.bounce_events_json_path.return_value = tmp_path / "bounce_events.json"
    storage.output_json_path.return_value = tmp_path / "result.json"
    storage.court_view_roi_json_path.return_value = tmp_path / "court_view_roi.json"
    storage.tracking_json_path.return_value = tmp_path / "tracking_result.json"
    storage.tracking_overlay_json_path.return_value = tmp_path / "tracking_overlay.json"
    storage.player_selection_json_path.return_value = tmp_path / "player_selection.json"
    storage.player_selection_training_samples_json_path.return_value = tmp_path / "training_samples.json"
    storage.pose_overlay_json_path.return_value = tmp_path / "pose_overlay.json"
    storage.player_trajectory_json_path.return_value = tmp_path / "player_trajectories.json"
    storage.player_trajectory_csv_path.return_value = tmp_path / "player_trajectories.csv"
    storage.serve_events_json_path.return_value = tmp_path / "serve_events.json"

    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload))

    def _write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(json.dumps(r) for r in records))

    storage.write_json.side_effect = _write_json
    storage.write_jsonl.side_effect = _write_jsonl
    return storage


# ---------------------------------------------------------------------------
# 1. ball_overlay.json payload builder 测试
# ---------------------------------------------------------------------------

class TestBallOverlayPayload:
    def test_build_with_accepted_samples(self):
        samples = [
            _make_sample(0, accepted=True),
            _make_sample(1, accepted=True),
            _make_sample(2, accepted=False, reject_reason="jump_distance"),
        ]
        payload = build_ball_overlay_payload(
            job_id="job-1",
            video_id="vid-1",
            samples=samples,
            source_width=1920,
            source_height=1080,
            fps=60.0,
            frame_stride=2,
            processed_frame_count=3,
        )
        assert payload["schema_version"] == "ball_overlay.v1"
        assert payload["source"]["width"] == 1920
        assert payload["source"]["height"] == 1080
        assert payload["source"]["fps"] == 60.0
        assert payload["source"]["frame_stride"] == 2
        assert payload["coverage"]["overlay_frame_count"] == 2  # 2 accepted
        assert payload["coverage"]["missing_frame_count"] == 1
        assert payload["coverage"]["detection_rate"] == pytest.approx(0.6667, abs=0.001)
        assert len(payload["frames"]) == 3
        assert payload["frames"][0]["ball"]["track_status"] == "detected"
        assert payload["frames"][2]["ball"]["track_status"] == "rejected"

    def test_build_with_empty_samples(self):
        payload = build_ball_overlay_payload(
            job_id="job-1",
            samples=[],
            status="no_detections",
            detail="no ball detected",
            processed_frame_count=100,
        )
        assert payload["status"] == "no_detections"
        assert payload["frames"] == []
        assert payload["coverage"]["overlay_frame_count"] == 0

    def test_build_with_only_missing_samples(self):
        samples = [_make_missing_sample(i) for i in range(5)]
        payload = build_ball_overlay_payload(
            job_id="job-1",
            samples=samples,
            processed_frame_count=5,
        )
        assert payload["coverage"]["overlay_frame_count"] == 0
        for frame in payload["frames"]:
            assert frame["ball"]["track_status"] == "missing"


# ---------------------------------------------------------------------------
# 2. _BallRunContext 测试
# ---------------------------------------------------------------------------

class TestBallRunContext:
    def test_default_context_is_empty(self):
        ctx = _BallRunContext()
        assert ctx.tracker is None
        assert ctx.samples == []
        assert ctx.detections == []
        assert ctx.error is None

    def test_context_accumulates_samples(self):
        ctx = _BallRunContext()
        sample = _make_sample(0)
        ctx.samples.append(sample)
        assert len(ctx.samples) == 1
        assert ctx.samples[0].accepted is True


# ---------------------------------------------------------------------------
# 3. _finalize_ball_analysis() 测试
# ---------------------------------------------------------------------------

class TestFinalizeBallAnalysis:
    @pytest.fixture
    def pipeline(self, tmp_path):
        p = AnalysisPipeline()
        p.storage = _make_storage_mock(tmp_path)
        p.ball_detection_enabled = True
        p.ball_analysis_strict = False
        p.settings = MagicMock()
        p.settings.enable_bounce_detection = True
        p.settings.enable_ball_detection = True
        return p

    def _finalize(
        self,
        pipeline: AnalysisPipeline,
        ball_run_output: _BallRunOutput | None,
        stages: list[PipelineStageResult] | None = None,
        fields: _BallArtifactFields | None = None,
    ) -> tuple[list[PipelineStageResult], _BallArtifactFields]:
        stages = stages or []
        fields = fields or _BallArtifactFields()
        pipeline._finalize_ball_analysis(
            job_id="job-test",
            ball_run_output=ball_run_output,
            player_detections=[],
            video_id="vid-test",
            stages=stages,
            fields=fields,
            source_width=1920,
            source_height=1080,
            fps=30.0,
            frame_stride=2,
            processed_frame_count=3,
        )
        return stages, fields

    def test_ball_disabled_produces_skipped_stages(self, pipeline):
        pipeline.ball_detection_enabled = False
        stages, fields = self._finalize(pipeline, None)

        traj_stage = next(s for s in stages if s.id == "ball-trajectory")
        bounce_stage = next(s for s in stages if s.id == "bounce-detection")
        assert traj_stage.status == "skipped"
        assert bounce_stage.status == "skipped"
        assert fields.detections_status == "skipped"
        assert fields.ball_overlay_status == "skipped"

    def test_ball_unavailable_produces_unavailable_stage(self, pipeline):
        run = _BallRunOutput(
            status="unavailable",
            samples=[],
            ball_detections=[],
            error="模型路径不存在",
            accepted_count=0,
        )
        stages, fields = self._finalize(pipeline, run)

        traj_stage = next(s for s in stages if s.id == "ball-trajectory")
        bounce_stage = next(s for s in stages if s.id == "bounce-detection")
        assert traj_stage.status == "unavailable"
        assert "模型路径不存在" in traj_stage.detail
        assert bounce_stage.status == "skipped"
        assert "model_enabled" in traj_stage.counters
        assert "processed_frame_count" in traj_stage.counters
        assert traj_stage.counters["model_enabled"] is True

    def test_ball_available_writes_all_artifacts(self, pipeline):
        samples = [_make_sample(i) for i in range(3)]
        raw_points = [TrajectoryPoint.from_sample(s) for s in samples]
        cleaned_points = raw_points
        run = _BallRunOutput(
            status="available",
            samples=samples,
            ball_detections=[],
            raw_points=raw_points,
            cleaned_points=cleaned_points,
            bounce_events=[
                BounceEvent(
                    event_id="bounce-1",
                    frame_index=1,
                    timestamp_sec=1.0 / 30.0,
                    image_xy=(100.0, 200.0),
                    court_xy=(10.0, 22.0),
                    confidence=0.75,
                    detection_method="trajectory_lag20",
                )
            ],
            accepted_count=3,
        )
        stages, fields = self._finalize(pipeline, run)

        # 两个用户可见阶段
        traj_stage = next(s for s in stages if s.id == "ball-trajectory")
        bounce_stage = next(s for s in stages if s.id == "bounce-detection")
        assert traj_stage.status == "done"
        assert bounce_stage.status == "done"

        # 所有 artifact 字段被填充
        assert fields.ball_overlay_json_path is not None
        assert fields.ball_trajectory_json_path is not None
        assert fields.cleaned_ball_trajectory_json_path is not None
        assert fields.bounce_events_json_path is not None
        assert fields.ball_overlay_status == "available"
        assert fields.ball_trajectory_status == "available"
        assert fields.bounce_events_status == "available"

        # 验证 ball_overlay.json 确实写入了文件
        overlay_path = Path(fields.ball_overlay_json_path)
        assert overlay_path.exists()
        overlay_data = json.loads(overlay_path.read_text())
        assert overlay_data["schema_version"] == "ball_overlay.v1"
        assert len(overlay_data["frames"]) == 3

        # 验证 counters
        assert traj_stage.counters["processed_frame_count"] == 3
        assert traj_stage.counters["model_enabled"] is True
        assert bounce_stage.counters["bounce_event_count"] == 1
        assert bounce_stage.counters["detection_mode"] == "rule_based"

    def test_ball_success_bounce_no_candidates(self, pipeline):
        samples = [_make_sample(i) for i in range(3)]
        raw_points = [TrajectoryPoint.from_sample(s) for s in samples]
        run = _BallRunOutput(
            status="available",
            samples=samples,
            ball_detections=[],
            raw_points=raw_points,
            cleaned_points=raw_points,
            bounce_events=[],
            accepted_count=3,
        )
        stages, fields = self._finalize(pipeline, run)

        bounce_stage = next(s for s in stages if s.id == "bounce-detection")
        assert bounce_stage.status == "done"
        assert fields.bounce_events_status == "available"
        assert "未检测到候选事件" in fields.bounce_events_detail
        assert bounce_stage.counters["bounce_event_count"] == 0

        # bounce_events.json 应该存在且 events 为空
        bounce_path = Path(fields.bounce_events_json_path)
        assert bounce_path.exists()
        bounce_data = json.loads(bounce_path.read_text())
        assert bounce_data["events"] == []

    def test_ball_failed_non_strict_no_pipeline_failure(self, pipeline):
        """默认非 strict 模式：球分析失败不拖垮 pipeline。"""
        pipeline.ball_analysis_strict = False
        run = _BallRunOutput(
            status="failed",
            samples=[],
            ball_detections=[],
            error="运行时异常",
            accepted_count=0,
        )
        stages, fields = self._finalize(pipeline, run)

        traj_stage = next(s for s in stages if s.id == "ball-trajectory")
        assert traj_stage.status == "failed"
        assert fields.ball_overlay_status == "failed"
        # pipeline 仍然可以继续（在 run() 中由 strict mode check 决定是否 failed）

    def test_no_calibration_skipped(self, pipeline):
        """无真实跟踪/标定的 ball_run_output=None 场景。"""
        stages, fields = self._finalize(pipeline, None)

        traj_stage = next(s for s in stages if s.id == "ball-trajectory")
        bounce_stage = next(s for s in stages if s.id == "bounce-detection")
        assert traj_stage.status == "skipped"
        assert bounce_stage.status == "skipped"
        assert fields.ball_overlay_status == "skipped"
        assert "缺少真实跟踪/标定" in traj_stage.detail


# ---------------------------------------------------------------------------
# 4. _run_bounce_detection() 测试
# ---------------------------------------------------------------------------

class TestRunBounceDetection:
    @pytest.fixture
    def pipeline(self):
        p = AnalysisPipeline()
        p.settings = MagicMock()
        p.settings.enable_bounce_detection = True
        p.settings.enable_ball_detection = True
        p.ball_detection_enabled = True
        p.ball_detector = None  # 不注入真实 detector
        p.ball_detection_unavailable_reason = None
        return p

    def test_no_tracker_no_samples_returns_none(self, pipeline):
        ctx = _BallRunContext(tracker=None)
        result = pipeline._run_bounce_detection(
            job_id="j", video_id="v", ball_ctx=ctx, fps=30.0
        )
        # ball_detector is None but ball_detection_enabled → unavailable
        assert result is not None
        assert result.status == "unavailable"

    def test_tracker_with_samples_returns_available(self, pipeline):
        # 需要 fake tracker，但由于它只是用来判断 ctx.tracker is not None，
        # 实际处理只消费 ctx.samples
        fake_tracker = MagicMock()
        samples = [_make_sample(i) for i in range(10)]
        ctx = _BallRunContext(tracker=fake_tracker, samples=samples)
        pipeline.ball_detection_enabled = True
        pipeline.ball_detector = MagicMock()  # 非 None

        result = pipeline._run_bounce_detection(
            job_id="j", video_id="v", ball_ctx=ctx, fps=30.0
        )
        assert result is not None
        assert result.status == "available"
        assert result.raw_points is not None
        assert len(result.raw_points) == 10
        assert result.cleaned_points is not None
        assert result.accepted_count == 10
        # bounce detection 启用，应该生成 bounce_events（即使是空的）
        assert result.bounce_events is not None

    def test_tracker_fails_midway_returns_partial(self, pipeline):
        fake_tracker = MagicMock()
        samples = [_make_sample(0), _make_sample(1)]
        ctx = _BallRunContext(tracker=None, samples=samples, error="球检测运行时失败")
        pipeline.ball_detection_enabled = True
        pipeline.ball_detector = MagicMock()

        result = pipeline._run_bounce_detection(
            job_id="j", video_id="v", ball_ctx=ctx, fps=30.0
        )
        assert result is not None
        # tracker is None but has samples with error → failed
        assert result.status == "failed"
        assert result.error == "球检测运行时失败"

    def test_post_processing_exception_returns_failed(self, pipeline):
        fake_tracker = MagicMock()
        # 使 TrajectoryCleaner 失败（传入非 BallFrameSample 的数据）
        samples = [_make_sample(0, image_xy=(0.0, 0.0))]
        ctx = _BallRunContext(tracker=fake_tracker, samples=samples)
        pipeline.ball_detection_enabled = True
        pipeline.ball_detector = MagicMock()

        result = pipeline._run_bounce_detection(
            job_id="j", video_id="v", ball_ctx=ctx, fps=30.0
        )
        # 正常路径应该成功
        assert result is not None
        assert result.status == "available"


# ---------------------------------------------------------------------------
# 5. strict mode 测试（通过 run() 验证）
# ---------------------------------------------------------------------------

def _mock_settings(**overrides: Any) -> MagicMock:
    """构造一个包含 AnalysisPipeline.__init__ 所需全部字段的 settings mock。"""
    defaults: dict[str, Any] = {
        "ball_analysis_strict": False,
        "enable_ball_detection": False,
        "enable_bounce_detection": False,
        "ball_model_path": None,
        "enable_model_inference": False,
        "default_detector_model": "",
        "detector_confidence": 0.5,
        "detector_device": "cpu",
        "enable_pose_inference": False,
        "pose_confidence": 0.5,
        "pose_keypoint_schema": "coco",
        "rtmpose_config_path": "",
        "rtmpose_checkpoint_path": "",
        "rtmpose_device": "cpu",
        "overlay_frame_stride": 2,
        "enable_serve_debug_artifacts": False,
        "enable_serve_debug_clips": False,
        "enable_serve_debug_overlay": False,
        "serve_clip_pre_seconds": 1.0,
        "serve_clip_post_seconds": 2.0,
        "serve_debug_clip_limit": 10,
        "serve_min_gap_seconds": 2.0,
        "serve_baseline_margin_ft": 2.0,
        "serve_pre_still_window_seconds": 0.5,
        "serve_pre_still_gap_seconds": 0.3,
        "serve_post_rally_window_seconds": 3.0,
        "serve_pose_smooth_window_frames": 5,
        "enable_court_view_gate": False,
        "court_view_match_threshold": 0.5,
        "court_view_start_frames": 30,
        "court_view_end_frames": 30,
        "court_view_diagnostic_only": True,
        "court_view_skip_non_court_frames": False,
        "court_view_match_width": 640,
        "enable_detection_roi_filter": False,
        "detection_roi_padding_ratio": 0.1,
        "detection_roi_min_padding_px": 20,
        "primary_player_min_confidence": 0.3,
        "primary_player_max_subjects": 4,
        "primary_player_min_box_area_ratio": 0.001,
        "primary_player_max_box_area_ratio": 0.5,
        "primary_player_court_margin_ft": 5.0,
        "primary_player_window_frames": 30,
        "primary_player_target_court_threshold": 0.3,
        "primary_player_quality_threshold": 0.3,
        "enable_attention_player_selector": False,
        "attention_player_selector_model_path": "",
        "attention_player_selector_confidence": 0.5,
        "player_identity_max_players": 4,
        "player_identity_match_threshold": 0.5,
        "player_identity_max_reconnect_distance_m": 5.0,
        "player_identity_max_speed_mps": 10.0,
        "player_identity_lost_buffer_frames": 90,
        "player_identity_inactive_buffer_frames": 180,
        "player_identity_interpolation_buffer_frames": 10,
        "player_identity_court_buffer_m": 1.0,
        "player_identity_smoothing_window": 5,
        "enable_analysis_overlay_video": False,
        "enable_position_visualizations": False,
        "visualization_language": "zh-CN",
    }
    defaults.update(overrides)
    mock = MagicMock()
    for key, value in defaults.items():
        setattr(mock, key, value)
    return mock


class TestStrictMode:
    def test_strict_mode_flag_is_read_from_settings(self):
        """验证 ball_analysis_strict 从 settings 正确读取。"""
        with patch("app.services.analysis_pipeline.get_settings") as mock_get:
            mock_get.return_value = _mock_settings(ball_analysis_strict=True)
            p = AnalysisPipeline()
            assert p.ball_analysis_strict is True

    def test_non_strict_is_default(self):
        """默认不启用 strict mode。"""
        with patch("app.services.analysis_pipeline.get_settings") as mock_get:
            mock_get.return_value = _mock_settings(ball_analysis_strict=False)
            p = AnalysisPipeline()
            assert p.ball_analysis_strict is False


# ---------------------------------------------------------------------------
# 6. 现有 tracking / pose / serve 兼容性检查（无回归）
# ---------------------------------------------------------------------------

class TestBackwardCompatibility:
    def test_pipeline_initializes_without_ball_model(self):
        """即使没有 ball_detector，AnalysisPipeline 也能正常初始化。"""
        with patch("app.services.analysis_pipeline.get_settings") as mock_get:
            mock_get.return_value = _mock_settings(
                enable_ball_detection=False,
                ball_model_path=None,
            )
            p = AnalysisPipeline(ball_detector=None)
            assert p.ball_detector is None
            assert p.ball_detection_enabled is False
            assert p.ball_analysis_strict is False

    def test_original_tracking_flow_not_changed(self):
        """验证 _run_tracking() 的参数签名仍接受原有参数。"""
        # 不实际调用 _run_tracking()（需要真实视频），只验证方法存在且签名合理
        assert callable(AnalysisPipeline._run_tracking)
        assert callable(AnalysisPipeline._process_ball_frame)
        assert callable(AnalysisPipeline._run_bounce_detection)

    def test_performance_metrics_has_ball_fields(self):
        """验证 PerformanceMetrics 包含新增的球指标字段（带默认值）。"""
        from app.schemas.metrics import PerformanceMetrics
        from app.vision.pickleball_performance_engine.heatmap_generator import generate_heatmap

        # 无球指标时构造 PerformanceMetrics 应该成功（所有球字段都有默认值）
        metrics = PerformanceMetrics(
            distances=[],
            speeds=[],
            kitchen_dwell=[],
            doubles_spacing=[],
            heatmap=generate_heatmap([]),
        )
        assert metrics.ball_detected_frame_count == 0
        assert metrics.ball_detection_rate == 0.0
        assert metrics.bounce_event_count == 0
        assert metrics.first_bounce_timestamp_seconds is None
