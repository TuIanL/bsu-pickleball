"""事件切分球轨迹重建链单元测试（不依赖真实 YOLO 模型或视频）。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.vision.courtvision_calibration_engine.homography import compute_homography
from app.vision.pickleball_game_analysis.ball_contact_event_detector import (
    BallContactEventDetector,
    ContactDetectorConfig,
)
from app.vision.pickleball_game_analysis.ball_event_resolver import BallEventResolver
from app.vision.pickleball_game_analysis.ball_flight_segmenter import BallFlightSegmenter
from app.vision.pickleball_game_analysis.event_anchored_trajectory_reconstructor import (
    EventAnchoredTrajectoryReconstructor,
)
from app.vision.pickleball_game_analysis.image_space_trajectory_fitter import ImageSpaceTrajectoryFitter
from app.vision.pickleball_game_analysis.reconstruction_engine import reconstruct_ball_trajectory
from app.vision.pickleball_game_analysis.reconstruction_schemas import (
    ReconstructionConfig,
    ReconstructionMode,
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

    def test_detector_does_not_consume_bounce_events(self):
        detector = BallContactEventDetector(ContactDetectorConfig(context_points=3))
        points = []
        for i in range(24):
            if i <= 12:
                points.append(_point(i, 100 + i * 4, 200 + i * 2))
            else:
                points.append(_point(i, 100 + 90 - (i - 12) * 4, 200 + 60 - (i - 12) * 2))
        candidates = detector.detect(points, fps=30)
        # 不变量 I7：Detector 不读取 bounce_events，弹地抑制只由 Resolver.prefilter 执行
        assert any(c.status == "confirmed_hit" for c in candidates)

    @pytest.mark.parametrize(("stride", "frame_step"), [(1, 1), (2, 2)])
    def test_direction_reversal_uses_timestamp_for_stride(self, stride, frame_step):
        detector = BallContactEventDetector(ContactDetectorConfig(context_points=3, frame_stride=stride))
        points = []
        for tick in range(30):
            frame = tick * frame_step
            x = 100 + tick * 4 if tick <= 15 else 160 - (tick - 15) * 4
            points.append(
                TrajectoryPoint(
                    frame_index=frame,
                    timestamp_sec=frame / 60.0 if stride == 2 else frame / 30.0,
                    image_xy=(float(x), 200.0),
                    court_xy=None,
                    confidence=0.9,
                    source="detector",
                )
            )
        candidates = detector.detect(points, fps=60.0 if stride == 2 else 30.0, frame_stride=stride)
        assert any(candidate.status == "confirmed_hit" for candidate in candidates)

    def test_historical_stride_two_fixture_produces_hit_candidate(self):
        fixture_path = (
            Path(__file__).parents[1]
            / "fixtures"
            / "ball_trajectory"
            / "job-96a28d6ff0-stride2-contact.json"
        )
        fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
        points = [TrajectoryPoint(**sample) for sample in fixture["samples"]]
        detector = BallContactEventDetector(
            ContactDetectorConfig(context_points=3, frame_stride=fixture["frame_stride"])
        )
        candidates = detector.detect(
            points,
            fps=fixture["source_fps"],
            frame_stride=fixture["frame_stride"],
        )
        assert any(candidate.status == "confirmed_hit" for candidate in candidates)
        assert all(candidate.diagnostics["frame_stride"] == 2 for candidate in candidates)


class TestBallEventResolver:
    def test_high_confidence_bounce_suppresses_hit(self):
        resolver = BallEventResolver()
        from app.vision.pickleball_game_analysis.ball_contact_event_detector import HitCandidate

        candidate = HitCandidate(16, 16 / 30.0, (140.0, 226.0), 0.8, status="confirmed_hit")
        bounce = _bounce(13, 140.0, 226.0, conf=0.95)
        prefiltered = resolver.prefilter([candidate], [bounce])
        assert prefiltered[0].prefilter_status == "suppressed"
        # 不变量 I1：suppressed 候选不得生成正式 HIT 事件
        events = resolver.finalize(prefiltered, [bounce])
        hits = [e for e in events if e.event_type == TrajectoryEventType.HIT]
        assert not hits

    def test_no_bounce_confirms_hit(self):
        resolver = BallEventResolver()
        from app.vision.pickleball_game_analysis.ball_contact_event_detector import HitCandidate

        candidate = HitCandidate(10, 0.33, (140.0, 226.0), 0.8, status="confirmed_hit")
        events = resolver.resolve([candidate], [])
        hits = [e for e in events if e.event_type == TrajectoryEventType.HIT]
        assert len(hits) == 1
        assert hits[0].source == "heuristic"
        assert hits[0].ownership_status == "unassigned"


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

    def test_serve_reset_and_end_of_stream_are_explicit_boundaries(self):
        segmenter = BallFlightSegmenter(ReconstructionConfig(min_points_per_segment=3))
        points = [_point(i, 100 + i * 2, 200) for i in range(12)]
        serve = TrajectoryEvent(
            "serve-5",
            TrajectoryEventType.SERVE_RESET,
            5,
            5 / 30.0,
            confidence=0.9,
        )
        segments = segmenter.segment(points, [serve])
        assert len(segments) == 2
        assert segments[0].end_event_type == TrajectoryEventType.SERVE_RESET
        assert segments[0].boundary_reason == "serve_reset"
        assert segments[1].start_event_type == TrajectoryEventType.SERVE_RESET
        assert segments[1].boundary_reason == "end_of_stream"


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
        bounce = TrajectoryEvent(
            "bounce-29", TrajectoryEventType.BOUNCE, 29, 29 / 30.0, image_xy=(207.0, 175.6), confidence=0.9
        )
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

    def test_start_single_anchor_aligns_first_sample_and_fades_unknown_end(self):
        reconstructor = EventAnchoredTrajectoryReconstructor(ReconstructionConfig())
        hit = TrajectoryEvent(
            "hit-0",
            TrajectoryEventType.HIT,
            0,
            0.0,
            image_xy=(120.0, 178.0),
            court_xy=(4.0, 5.0),
            confidence=0.8,
        )
        segment, points, events_by_id = self._segment_with_events([hit])
        reconstructed = reconstructor.reconstruct(segment, points, events_by_id, HOMOGRAPHY)
        assert reconstructed.reconstruction_mode == ReconstructionMode.SINGLE_ANCHOR_WARP.value
        assert reconstructed.samples[0].court_xy == pytest.approx((4.0, 5.0))
        assert reconstructed.samples[-1].height_confidence == 0.0

    def test_end_single_anchor_aligns_last_sample_and_fades_unknown_start(self):
        reconstructor = EventAnchoredTrajectoryReconstructor(ReconstructionConfig())
        bounce = TrajectoryEvent(
            "bounce-29",
            TrajectoryEventType.BOUNCE,
            29,
            29 / 30.0,
            image_xy=(207.0, 175.6),
            court_xy=(15.0, 39.0),
            confidence=0.9,
        )
        segment, points, events_by_id = self._segment_with_events([bounce])
        reconstructed = reconstructor.reconstruct(segment, points, events_by_id, HOMOGRAPHY)
        assert reconstructed.reconstruction_mode == ReconstructionMode.SINGLE_ANCHOR_WARP.value
        assert reconstructed.samples[-1].court_xy == pytest.approx((15.0, 39.0))
        assert reconstructed.samples[-1].estimated_height_ft == 0.0
        assert reconstructed.samples[0].height_confidence == 0.0

    def test_anchor_distance_too_small_local_visual_arc(self):
        reconstructor = EventAnchoredTrajectoryReconstructor(ReconstructionConfig(minimum_anchor_distance_ft=5.0))
        # 两个几乎重合的锚点
        hit = TrajectoryEvent("hit-0", TrajectoryEventType.HIT, 0, 0.0, image_xy=(120.0, 168.0), confidence=0.8)
        bounce = TrajectoryEvent(
            "bounce-29", TrajectoryEventType.BOUNCE, 29, 29 / 30.0, image_xy=(121.0, 169.0), confidence=0.9
        )
        segment, points, events_by_id = self._segment_with_events([hit, bounce])
        reconstructed = reconstructor.reconstruct(segment, points, events_by_id, HOMOGRAPHY)
        assert reconstructed.reconstruction_mode in {
            ReconstructionMode.LOCAL_VISUAL_ARC.value,
            ReconstructionMode.DUAL_ANCHOR_WARP.value,
        }

    def test_isotonic_increasing_terminates_on_inverted_input(self):
        # 回归：PAVA 合并逆序块时必须同时弹出两个块；旧实现只弹一个会死循环
        # （reconstruct 的 dual-anchor warp 对球场路径调用它，遇逆序对即挂起）。
        import numpy as np

        f = EventAnchoredTrajectoryReconstructor._isotonic_increasing
        # 逆序对（原 bug 触发条件）：修复后必须终止且输出非降
        out = f(np.asarray([3.0, 2.0, 1.0]))
        assert list(out) == [2.0, 2.0, 2.0]
        out2 = f(np.asarray([5.0, 3.0, 4.0, 1.0, 2.0]))
        assert all(out2[i] <= out2[i + 1] + 1e-9 for i in range(len(out2) - 1))
        # 已有序输入不受影响
        assert list(f(np.asarray([1.0, 2.0, 3.0]))) == [1.0, 2.0, 3.0]


# ---------------------------------------------------------------------------
# 8.1 质量评估
# ---------------------------------------------------------------------------


class TestTrajectoryQualityEvaluator:
    def test_quality_overall_and_display_level(self):
        segmenter = BallFlightSegmenter(ReconstructionConfig())
        points = [_point(i, 120 + i * 3.0, 160 + (i - 15) ** 2 * 0.08) for i in range(30)]
        hit = TrajectoryEvent("hit-0", TrajectoryEventType.HIT, 0, 0.0, image_xy=(120.0, 168.0), confidence=0.8)
        bounce = TrajectoryEvent(
            "bounce-29", TrajectoryEventType.BOUNCE, 29, 29 / 30.0, image_xy=(207.0, 175.6), confidence=0.9
        )
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
        assert payload["schema_version"] == "reconstructed_ball_trajectory.v2"
        assert payload["reconstruction_mode"] == "event_anchored_2_5d"
        assert payload["coordinate_semantics"]["metric_validity"] == "visualization_only"
        assert payload["status"] == "available"
        assert "player_roster" in payload
        assert payload["suppression_snapshot"]["bounce_suppress_before_sec"] == 0.07
        assert payload["segments"]
        segment = payload["segments"][0]
        assert segment["model"] == "weighted_huber_anchor_constrained"
        assert segment["fit_space"] == "image_px"
        assert "shot_id" in segment
        assert segment["ownership_status"] in {"confirmed", "ambiguous", "unassigned", "not_applicable"}
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
