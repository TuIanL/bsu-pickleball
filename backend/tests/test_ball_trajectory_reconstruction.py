"""事件切分球轨迹重建链单元测试（不依赖真实 YOLO 模型或视频）。"""

from __future__ import annotations

import numpy as np
import pytest

from app.vision.courtvision_calibration_engine.homography import compute_homography
from app.vision.pickleball_game_analysis.ball_contact_event_detector import (
    BallContactEventDetector,
    ContactDetectorConfig,
)
from app.vision.pickleball_game_analysis.ball_event_resolver import BallEventResolver, ResolverConfig
from app.vision.pickleball_game_analysis.ball_flight_segmenter import BallFlightSegmenter
from app.vision.pickleball_game_analysis.event_anchored_trajectory_reconstructor import (
    EventAnchoredTrajectoryReconstructor,
)
from app.vision.pickleball_game_analysis.image_space_trajectory_fitter import ImageSpaceTrajectoryFitter
from app.vision.pickleball_game_analysis.reconstruction_engine import reconstruct_ball_trajectory
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    ReconstructionConfig,
    ReconstructionMode,
    SampleSource,
    TrajectoryEvent,
    TrajectoryEventType,
)
from app.vision.pickleball_game_analysis.schemas import BounceEvent, TrajectoryPoint
from app.vision.pickleball_game_analysis.trajectory_quality_evaluator import TrajectoryQualityEvaluator

# 图像 ↔ 球场 的单应（近似透视，供重建用）
IMG_PTS = [(100, 100), (500, 100), (520, 420), (80, 430)]
COURT_PTS = [(0.0, 0.0), (20.0, 0.0), (20.0, 44.0), (0.0, 44.0)]
HOMOGRAPHY = compute_homography(IMG_PTS, COURT_PTS).tolist()


def _point(frame: int, u: float, v: float, conf: float = 0.85, source: str = "detected") -> TrajectoryPoint:
    return TrajectoryPoint(
        frame_index=frame,
        timestamp_sec=frame / 30.0,
        image_xy=(float(u), float(v)),
        court_xy=None,
        confidence=conf,
        source=source,
    )


def _bounce(frame: int, u: float, v: float, conf: float = 0.9) -> BounceEvent:
    return BounceEvent(
        event_id=f"bounce-{frame}",
        frame_index=frame,
        timestamp_sec=frame / 30.0,
        image_xy=(float(u), float(v)),
        court_xy=None,
        confidence=conf,
        detection_method="test",
    )


# ---------------------------------------------------------------------------
# 8.1 图像空间鲁棒拟合
# ---------------------------------------------------------------------------

class TestImageSpaceTrajectoryFitter:
    def test_fits_smooth_parabola_with_low_residual(self):
        fitter = ImageSpaceTrajectoryFitter()
        points = [_point(i, 100 + 3.0 * i, 150 + (i - 15) ** 2 * 0.05) for i in range(30)]
        result = fitter.fit(points)
        assert result.converged
        assert result.observed_count == 30
        assert result.residual_rmse_px < 1.0
        assert 0 < result.coverage <= 1.0

    def test_insufficient_points_not_converged(self):
        fitter = ImageSpaceTrajectoryFitter()
        points = [_point(i, float(100 + i), float(200 + i)) for i in range(3)]
        result = fitter.fit(points)
        assert not result.converged

    def test_outlier_observation_marked(self):
        fitter = ImageSpaceTrajectoryFitter()
        points = [_point(i, 100 + 3.0 * i, 150 + 2.0 * i) for i in range(20)]
        # 在中间插入一个大跳变离群点
        points[10] = _point(10, 300.0, 400.0)
        result = fitter.fit(points)
        assert result.converged
        assert result.outlier_indices


# ---------------------------------------------------------------------------
# 8.1 击球候选检测 + 事件仲裁
# ---------------------------------------------------------------------------

class TestBallContactEventDetector:
    def test_direction_reversal_produces_confirmed_hit(self):
        detector = BallContactEventDetector(ContactDetectorConfig(context_points=3))
        # 轨迹在 i=15 处方向反转（类似击球）
        points = []
        for i in range(30):
            if i <= 15:
                points.append(_point(i, 100 + i * 4, 200 + i * 2))
            else:
                points.append(_point(i, 100 + 90 - (i - 15) * 4, 200 + 60 - (i - 15) * 2))
        candidates = detector.detect(points, fps=30)
        confirmed = [c for c in candidates if c.status == "confirmed_hit"]
        assert confirmed
        # 反转发生在 i=15 附近，检测器取该区域最强突变点（允许 ±2 帧）
        assert confirmed[0].frame_index in {15, 16, 17}

    def test_insufficient_context_is_rejected(self):
        detector = BallContactEventDetector(ContactDetectorConfig(context_points=5))
        points = [_point(i, 100 + i * 2, 200) for i in range(8)]
        # 轨迹平滑，不应有击球候选
        candidates = detector.detect(points, fps=30)
        assert not [c for c in candidates if c.status == "confirmed_hit"]

    def test_bounce_window_suppresses_candidate(self):
        detector = BallContactEventDetector(ContactDetectorConfig(context_points=3))
        points = []
        for i in range(24):
            if i <= 12:
                points.append(_point(i, 100 + i * 4, 200 + i * 2))
            else:
                points.append(_point(i, 100 + 90 - (i - 12) * 4, 200 + 60 - (i - 12) * 2))
        # 在方向反转点附近放一个高可信弹地事件
        bounce = _bounce(13, 140.0, 226.0, conf=0.95)
        candidates = detector.detect(points, bounce_events=[bounce], fps=30)
        assert not [c for c in candidates if c.status == "confirmed_hit"]


class TestBallEventResolver:
    def test_high_confidence_bounce_suppresses_hit(self):
        resolver = BallEventResolver(ResolverConfig(bounce_suppression_window_frames=6))
        from app.vision.pickleball_game_analysis.ball_contact_event_detector import HitCandidate

        candidate = HitCandidate(16, 0.53, (140.0, 226.0), 0.8, status="confirmed_hit")
        bounce = _bounce(13, 140.0, 226.0, conf=0.95)
        events = resolver.resolve([candidate], [bounce])
        hits = [e for e in events if e.event_type == TrajectoryEventType.HIT]
        assert hits
        assert hits[0].diagnostics.get("status") == "suppressed_by_bounce"

    def test_no_bounce_confirms_hit(self):
        resolver = BallEventResolver()
        from app.vision.pickleball_game_analysis.ball_contact_event_detector import HitCandidate

        candidate = HitCandidate(10, 0.33, (140.0, 226.0), 0.8, status="confirmed_hit")
        events = resolver.resolve([candidate], [])
        hits = [e for e in events if e.event_type == TrajectoryEventType.HIT]
        assert len(hits) == 1
        assert hits[0].source == "heuristic"


# ---------------------------------------------------------------------------
# 8.1 飞行段切分
# ---------------------------------------------------------------------------

class TestBallFlightSegmenter:
    def test_bounce_cuts_into_two_segments_sharing_anchor(self):
        segmenter = BallFlightSegmenter(ReconstructionConfig())
        points = [_point(i, 100 + i * 3, 200) for i in range(30)]
        bounce_event = TrajectoryEvent(
            event_id="bounce-15",
            event_type=TrajectoryEventType.BOUNCE,
            frame_index=15,
            timestamp_sec=0.5,
            confidence=0.9,
        )
        segments = segmenter.segment(points, [bounce_event])
        assert len(segments) == 2
        # 弹地前后共享锚点
        assert segments[0].end_anchor_id == segments[1].start_anchor_id == "anchor-bounce-15"
        assert segments[0].end_event_type == TrajectoryEventType.BOUNCE
        assert segments[1].start_event_type == TrajectoryEventType.BOUNCE

    def test_long_loss_cuts_without_anchor(self):
        segmenter = BallFlightSegmenter(ReconstructionConfig(long_loss_gap_frames=12))
        points = [_point(i, 100 + i * 2, 200) for i in range(30)]
        # 大帧缺口（29 → 50）之后补足 3 个有效点
        points.append(_point(50, 200.0, 210.0))
        points.append(_point(51, 202.0, 212.0))
        points.append(_point(52, 204.0, 214.0))
        segments = segmenter.segment(points, [])
        assert len(segments) == 2
        # 丢失边界不是空间锚点
        assert segments[0].end_anchor_id is None
        assert segments[1].start_anchor_id is None
        # 重新捕获点不并入丢失前段
        assert segments[0].end_index == 29


# ---------------------------------------------------------------------------
# 8.1 事件锚定 2.5D 重建（含锚点降级与高度边界）
# ---------------------------------------------------------------------------

class TestEventAnchoredTrajectoryReconstructor:
    def _segment_with_events(self, events):
        segmenter = BallFlightSegmenter(ReconstructionConfig())
        points = [_point(i, 120 + i * 3.0, 160 + (i - 15) ** 2 * 0.08) for i in range(30)]
        segments = segmenter.segment(points, events)
        assert segments, "expected at least one segment"
        return segments[0], points, {e.event_id: e for e in events}

    def test_bounce_hit_dual_anchor_bounce_height_zero(self):
        reconstructor = EventAnchoredTrajectoryReconstructor(ReconstructionConfig())
        # 段：hit（开始）→ bounce（结束）
        hit = TrajectoryEvent("hit-0", TrajectoryEventType.HIT, 0, 0.0, image_xy=(120.0, 168.0), confidence=0.8)
        bounce = TrajectoryEvent("bounce-29", TrajectoryEventType.BOUNCE, 29, 29 / 30.0, image_xy=(207.0, 175.6), confidence=0.9)
        segment, points, events_by_id = self._segment_with_events([hit, bounce])
        reconstructed = reconstructor.reconstruct(segment, points, events_by_id, HOMOGRAPHY)
        assert reconstructed.reconstruction_mode == ReconstructionMode.DUAL_ANCHOR_WARP.value
        # 弹地边界高度严格为 0
        assert reconstructed.samples[-1].estimated_height_ft == 0.0
        # 击球边界高度 = 接触高度先验，非 0
        assert reconstructed.samples[0].estimated_height_ft == pytest.approx(1.10 * 3.28084, abs=0.01)
        assert reconstructed.samples[0].estimated_height_ft != 0.0

    def test_image_only_when_no_anchors(self):
        reconstructor = EventAnchoredTrajectoryReconstructor(ReconstructionConfig())
        segment, points, events_by_id = self._segment_with_events([])
        reconstructed = reconstructor.reconstruct(segment, points, events_by_id, HOMOGRAPHY)
        assert reconstructed.reconstruction_mode == ReconstructionMode.IMAGE_ONLY.value
        assert reconstructed.status == "insufficient_spatial_anchors"
        # image_only 不伪造高度
        assert all(sample.estimated_height_ft is None for sample in reconstructed.samples)

    def test_anchor_distance_too_small_local_visual_arc(self):
        reconstructor = EventAnchoredTrajectoryReconstructor(ReconstructionConfig(minimum_anchor_distance_ft=5.0))
        # 两个几乎重合的锚点
        hit = TrajectoryEvent("hit-0", TrajectoryEventType.HIT, 0, 0.0, image_xy=(120.0, 168.0), confidence=0.8)
        bounce = TrajectoryEvent("bounce-29", TrajectoryEventType.BOUNCE, 29, 29 / 30.0, image_xy=(121.0, 169.0), confidence=0.9)
        segment, points, events_by_id = self._segment_with_events([hit, bounce])
        reconstructed = reconstructor.reconstruct(segment, points, events_by_id, HOMOGRAPHY)
        assert reconstructed.reconstruction_mode in {
            ReconstructionMode.LOCAL_VISUAL_ARC.value,
            ReconstructionMode.DUAL_ANCHOR_WARP.value,
        }


# ---------------------------------------------------------------------------
# 8.1 质量评估
# ---------------------------------------------------------------------------

class TestTrajectoryQualityEvaluator:
    def test_quality_overall_and_display_level(self):
        segmenter = BallFlightSegmenter(ReconstructionConfig())
        points = [_point(i, 120 + i * 3.0, 160 + (i - 15) ** 2 * 0.08) for i in range(30)]
        hit = TrajectoryEvent("hit-0", TrajectoryEventType.HIT, 0, 0.0, image_xy=(120.0, 168.0), confidence=0.8)
        bounce = TrajectoryEvent("bounce-29", TrajectoryEventType.BOUNCE, 29, 29 / 30.0, image_xy=(207.0, 175.6), confidence=0.9)
        segment = segmenter.segment(points, [hit, bounce])[0]
        events_by_id = {e.event_id: e for e in [hit, bounce]}
        reconstructor = EventAnchoredTrajectoryReconstructor(ReconstructionConfig())
        reconstructed = reconstructor.reconstruct(segment, points, events_by_id, HOMOGRAPHY)
        fitter = ImageSpaceTrajectoryFitter()
        fit = fitter.fit([points[i] for i in segment.point_indices])
        quality = TrajectoryQualityEvaluator().evaluate(reconstructed, fit, events_by_id)
        assert "overall" in quality
        assert "net_crossing_status" in quality
        assert quality["overall"] > 0
        assert quality["display_level"] in {"high", "medium", "low", "none"}

    def test_image_only_quality_capped(self):
        segmenter = BallFlightSegmenter(ReconstructionConfig())
        points = [_point(i, 120 + i * 3.0, 160) for i in range(30)]
        segment = segmenter.segment(points, [])[0]
        reconstructor = EventAnchoredTrajectoryReconstructor(ReconstructionConfig())
        reconstructed = reconstructor.reconstruct(segment, points, {}, HOMOGRAPHY)
        quality = TrajectoryQualityEvaluator().evaluate(reconstructed, None, {})
        assert quality["overall"] < 0.4
        assert quality["display_level"] == "none"


# ---------------------------------------------------------------------------
# 8.1 重建产物序列化
# ---------------------------------------------------------------------------

class TestReconstructionArtifact:
    def test_payload_structure_and_sources(self):
        points = [_point(i, 120 + i * 3.0, 160 + (i - 15) ** 2 * 0.08) for i in range(30)]
        bounce = _bounce(15, 165.0, 178.0)
        payload = reconstruct_ball_trajectory(
            job_id="job-recon-1",
            cleaned_points=points,
            bounce_events=[bounce],
            serve_events=None,
            homography=HOMOGRAPHY,
            fps=30,
        )
        assert payload["schema_version"] == "reconstructed_ball_trajectory.v1"
        assert payload["reconstruction_mode"] == "event_anchored_2_5d"
        assert payload["coordinate_semantics"]["metric_validity"] == "visualization_only"
        assert payload["status"] == "available"
        assert payload["segments"]
        segment = payload["segments"][0]
        assert segment["model"] == "weighted_huber_anchor_constrained"
        assert segment["fit_space"] == "image_px"
        sources = {sample["source"] for sample in segment["samples"]}
        assert sources <= {"detected", "interpolated", "model_predicted", "anchor"}
        assert "overall" in segment["quality"]

    def test_model_predicted_distinguishable_from_detected(self):
        points = [_point(i, 120 + i * 3.0, 160 + (i - 15) ** 2 * 0.08) for i in range(30)]
        # 中间挖一个缺失（模拟 model_predicted 补点）
        points[20] = TrajectoryPoint(20, 20 / 30.0, None, None, None)
        payload = reconstruct_ball_trajectory(
            job_id="job-recon-2",
            cleaned_points=points,
            bounce_events=[],
            serve_events=None,
            homography=HOMOGRAPHY,
            fps=30,
        )
        segment = payload["segments"][0]
        sources = [sample["source"] for sample in segment["samples"]]
        assert "model_predicted" in sources
        assert "detected" in sources


# ---------------------------------------------------------------------------
# 8.2 确定性
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_repeated_run_produces_identical_results(self):
        points = [_point(i, 120 + i * 3.0, 160 + (i - 15) ** 2 * 0.08) for i in range(30)]
        bounce = _bounce(15, 165.0, 178.0)
        kwargs = dict(
            job_id="job-det-1",
            cleaned_points=points,
            bounce_events=[bounce],
            serve_events=None,
            homography=HOMOGRAPHY,
            fps=30,
        )
        first = reconstruct_ball_trajectory(**kwargs)
        second = reconstruct_ball_trajectory(**kwargs)
        assert first == second
        assert [e["event_id"] for e in first["events"]] == [e["event_id"] for e in second["events"]]
        assert [s["segment_id"] for s in first["segments"]] == [s["segment_id"] for s in second["segments"]]


# ---------------------------------------------------------------------------
# 8.3 验收不变量
# ---------------------------------------------------------------------------

class TestAcceptanceInvariants:
    def test_bounce_and_long_loss_always_produce_new_segment_id(self):
        segmenter = BallFlightSegmenter(ReconstructionConfig(long_loss_gap_frames=12))
        points = [_point(i, 100 + i * 2, 200) for i in range(30)]
        bounce_event = TrajectoryEvent("bounce-15", TrajectoryEventType.BOUNCE, 15, 0.5, confidence=0.9)
        # 29 → 42 长丢失（gap 13 > 12）后补足 3 个有效点
        points.append(_point(42, 180.0, 210.0))
        points.append(_point(43, 182.0, 212.0))
        points.append(_point(44, 184.0, 214.0))
        segments = segmenter.segment(points, [bounce_event])
        ids = [s.segment_id for s in segments]
        assert len(set(ids)) == len(ids)  # 每个边界产生新 segment_id
        assert len(segments) == 3  # bounce + loss → 3 段
        assert segments[0].end_anchor_id == segments[1].start_anchor_id == "anchor-bounce-15"

    def test_no_anchor_segment_not_high_confidence_court_space(self):
        points = [_point(i, 120 + i * 3.0, 160) for i in range(30)]
        payload = reconstruct_ball_trajectory(
            job_id="job-invariant",
            cleaned_points=points,
            bounce_events=[],
            serve_events=None,
            homography=None,  # 无 homography → image_only
            fps=30,
        )
        for segment in payload["segments"]:
            assert segment["reconstruction_mode"] == "image_only"
            assert segment["status"] == "insufficient_spatial_anchors"
            assert segment["quality"]["display_level"] == "none"
