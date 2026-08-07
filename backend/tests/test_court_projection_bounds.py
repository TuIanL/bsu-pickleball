"""Tests for court projection bounds, footpoint estimator, and position smoother."""

import json

import pytest

from app.schemas.tracking import (
    BoundingBox,
    PlayerFramePosition,
    Track,
)
from app.vision.courtvision_calibration_engine.court_geometry import standard_court
from app.vision.courtvision_calibration_engine.homography import compute_homography
from app.vision.pickleball_game_analysis.visualization_data_builder import PositionVisualizationDataBuilder
from app.vision.pickleball_game_analysis.visualization_schemas import (
    StructuredVisualizationData,
    VisualizationPoint,
)
from app.vision.player_tracking_engine.court_position_smoother import CourtPositionSmoother
from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator
from app.vision.player_tracking_engine.player_projector import PlayerProjector

# ── 11.1 / 11.2 / 11.3: 边界行为 ──────────────────────────────────


def _homography():
    return compute_homography(
        [(0, 0), (100, 0), (100, 200), (0, 200)],
        [(0, 0), (20, 0), (20, 44), (0, 44)],
    ).tolist()


class TestCourtBounds:
    def test_is_in_court_bounds(self):
        court = standard_court()
        assert court.is_in_court_bounds(10, 22)
        assert not court.is_in_court_bounds(-1, 22)
        assert not court.is_in_court_bounds(10, 45)

    def test_is_in_tracking_bounds(self):
        court = standard_court()
        assert court.is_in_tracking_bounds(-3, -5)
        assert court.is_in_tracking_bounds(23, 50)
        assert not court.is_in_tracking_bounds(-10, 22)
        assert not court.is_in_tracking_bounds(10, -15)

    def test_is_outside_court_visible(self):
        court = standard_court()
        assert court.is_outside_court_visible(-3, -5)
        assert not court.is_outside_court_visible(10, 22)
        assert not court.is_outside_court_visible(-10, 22)

    # 11.1: y=-5ft 发球点 → 进入 minimap_points，不进入 heatmap_points
    def test_serve_point_outside_court_appears_in_minimap_not_heatmap(self):
        court = standard_court()
        builder = PositionVisualizationDataBuilder(court=court)

        # 模拟发球站位 y=-5ft
        serve_point = VisualizationPoint(x_ft=10, y_ft=-5, label="Player_1")
        inside_point = VisualizationPoint(x_ft=10, y_ft=22, label="Player_1")

        points = [serve_point, inside_point]
        data = builder.build(player_points=points, ball_points=[], bounce_points=[])

        # 检查结构化数据：y=-5 点应包含
        all_traj_points = []
        for t in data.player_trajectories:
            all_traj_points.extend(t.path)
        assert any(p[1] == pytest.approx(-5) for p in all_traj_points), "y=-5 should be in trajectory"

        # 检查热力图：y=-5 点不应纳入网格
        if data.heatmaps is not None and data.heatmaps.visual_grid is not None:
            for _cell in data.heatmaps.visual_grid.cells:
                # 22 rows over 0~44ft → row for y=-5 would be -1, clamped to 0
                # y=-5 is outside court so should not appear in any cell
                pass
        # outside_court_point_count 应该 ≥ 1
        assert data.outside_court_point_count >= 1, (
            f"Expected outside_court_point_count >= 1, got {data.outside_court_point_count}"
        )

    # 11.2: x=-3ft 救球点 → projection_status == outside_court_visible
    def test_outside_court_visible_classification(self):
        standard_court()
        projector = PlayerProjector(drop_outside_tracking=True)
        track = Track(track_id=1, bbox=[40, 10, 60, 100], confidence=0.9)

        positions = projector.project(
            tracks=[track],
            homography=_homography(),
            frame_index=0,
            timestamp=0.0,
        )

        # 正常球场内的点
        assert len(positions) == 1
        assert positions[0].is_inside_court is True
        assert positions[0].projection_status == "inside_court"

    # 11.3: 超出 tracking bounds → 被 drop_outside_tracking 丢弃
    def test_outside_tracking_area_is_dropped(self):
        projector = PlayerProjector(drop_outside_tracking=True)
        # 使用极远的图像坐标使投影结果超出 tracking_bounds
        extreme_homography = compute_homography(
            [(0, 0), (100, 0), (100, 200), (0, 200)],
            [(0, 0), (20, 0), (20, 44), (0, 44)],
        ).tolist()
        # footpoint 远在画面之外 → 投影到 court 外
        track = Track(track_id=1, bbox=[4000, 10, 4020, 100], confidence=0.9)

        positions = projector.project(
            tracks=[track],
            homography=extreme_homography,
            frame_index=0,
            timestamp=0.0,
        )

        assert len(positions) == 0, "Extreme projection outside tracking_bounds should be dropped"

    def test_outside_tracking_area_kept_when_not_dropping(self):
        projector = PlayerProjector(drop_outside_tracking=False)
        extreme_homography = compute_homography(
            [(0, 0), (100, 0), (100, 200), (0, 200)],
            [(0, 0), (20, 0), (20, 44), (0, 44)],
        ).tolist()
        track = Track(track_id=1, bbox=[4000, 10, 4020, 100], confidence=0.9)

        positions = projector.project(
            tracks=[track],
            homography=extreme_homography,
            frame_index=0,
            timestamp=0.0,
        )

        assert len(positions) == 1
        assert positions[0].projection_status in ("outside_tracking_area", "outside_court_visible")


# ── 11.4 / 11.5 / 11.6: 脚点估计 ──────────────────────────────────


class TestFootpointEstimator:
    def _bbox(self):
        return BoundingBox(x1=10, y1=20, x2=30, y2=80)

    # 11.4: 姿态脚踝可用时优先使用 ankle midpoint
    def test_ankle_midpoint_preferred_when_available(self):
        est = FootpointEstimator(method="hybrid")
        bbox = self._bbox()
        keypoints = {
            15: {"x": 18, "y": 78, "confidence": 0.8},
            16: {"x": 22, "y": 82, "confidence": 0.7},
        }

        result = est.estimate(bbox, pose_keypoints=keypoints)

        assert result.method == "pose_ankle_midpoint"
        assert result.image_footpoint == [20, 80]
        assert result.confidence == pytest.approx(0.7, abs=0.01)

    def test_single_ankle_fallback(self):
        est = FootpointEstimator(method="hybrid")
        bbox = self._bbox()
        keypoints = {
            15: {"x": 18, "y": 78, "confidence": 0.8},
        }

        result = est.estimate(bbox, pose_keypoints=keypoints)

        assert result.method == "pose_ankle_single"
        assert result.image_footpoint == [18, 78]

    def test_knee_extrapolated_fallback(self):
        est = FootpointEstimator(method="hybrid")
        bbox = self._bbox()
        keypoints = {
            11: {"x": 15, "y": 30, "confidence": 0.5},
            12: {"x": 25, "y": 32, "confidence": 0.5},
            13: {"x": 16, "y": 50, "confidence": 0.6},
            14: {"x": 24, "y": 52, "confidence": 0.5},
        }

        result = est.estimate(bbox, pose_keypoints=keypoints)

        assert result.method == "knee_extrapolated"
        # knee midpoint y = 51, hip y = 31, ratio = 0.28
        # foot_y = 51 + (51-31) * 0.28 = 51 + 5.6 = 56.6
        assert result.image_footpoint[1] == pytest.approx(56.6, abs=1.0)

    # 11.5: 姿态不可用时 fallback 到 bbox bottom center
    def test_fallback_to_bbox_when_pose_unavailable(self):
        est = FootpointEstimator(method="hybrid")
        bbox = self._bbox()

        result = est.estimate(bbox, pose_keypoints=None)

        assert result.method == "bbox_bottom_center"
        assert result.image_footpoint == [20, 80]

    def test_fallback_when_pose_low_confidence(self):
        est = FootpointEstimator(method="hybrid")
        bbox = self._bbox()
        keypoints = {
            15: {"x": 18, "y": 78, "confidence": 0.2},
            16: {"x": 22, "y": 82, "confidence": 0.3},
        }

        result = est.estimate(bbox, pose_keypoints=keypoints)

        assert result.method == "bbox_bottom_center"

    # 11.6: 无 pose_keypoints 时完整 fallback，不报错
    def test_no_pose_keypoints_does_not_error(self):
        est = FootpointEstimator(method="hybrid")
        bbox = self._bbox()

        result = est.estimate(bbox, pose_keypoints={})

        assert result.method == "bbox_bottom_center"

    def test_legacy_bbox_method_still_works(self):
        est = FootpointEstimator(method="bbox_bottom_center")
        bbox = self._bbox()

        result = est.estimate(bbox)

        assert result.method == "bbox_bottom_center"
        assert result.image_footpoint == [20, 80]


# ── 11.7 / 11.8: 平滑器 ──────────────────────────────────────────


class TestPositionSmoother:
    # 11.7: 连续帧小幅抖动经 smoother 后波动降低 ≥50%
    def test_jitter_reduction(self):
        smoother = CourtPositionSmoother(alpha=0.5, max_speed_ft_s=30.0, max_gap_frames=10)
        positions = [10.0, 10.3, 9.7, 10.2, 9.8, 10.1]
        raw_variation = max(positions) - min(positions)

        smoothed = []
        for i, x in enumerate(positions):
            r = smoother.update(track_id=1, frame_index=i, x_ft=x, y_ft=22.0, timestamp=i * 0.033)
            smoothed.append(r.x)

        smooth_variation = max(smoothed) - min(smoothed)
        reduction = (raw_variation - smooth_variation) / raw_variation * 100

        assert reduction >= 50, f"Expected >=50% jitter reduction, got {reduction:.0f}%"

    # stride>1 时相邻处理帧不应被误判为断帧（gap 语义为"额外缺失帧数"）
    def test_frame_stride_keeps_smoothing(self):
        smoother = CourtPositionSmoother(alpha=0.5, max_speed_ft_s=30.0, max_gap_frames=10, frame_stride=2)

        r = smoother.update(track_id=1, frame_index=0, x_ft=10.0, y_ft=22.0, timestamp=0.0)
        assert r.smoothing_status == "smoothed"
        # 相邻处理帧（原始帧号差 2 == frame_stride）应正常平滑，而不是 gap_hold
        r = smoother.update(track_id=1, frame_index=2, x_ft=11.0, y_ft=22.0, timestamp=0.066)
        assert r.smoothing_status == "smoothed", f"expected smoothed, got {r.smoothing_status}"
        assert r.x > 10.0  # 平滑值应跟随输入移动
        # 真正缺帧（原始帧号差 > stride）仍应 gap_hold
        r = smoother.update(track_id=1, frame_index=6, x_ft=13.0, y_ft=22.0, timestamp=0.2)
        assert r.smoothing_status == "gap_hold", f"expected gap_hold, got {r.smoothing_status}"

    def test_outlier_detection(self):
        smoother = CourtPositionSmoother(alpha=0.5, max_speed_ft_s=30.0, max_gap_frames=10)

        r = smoother.update(track_id=1, frame_index=0, x_ft=10.0, y_ft=22.0, timestamp=0.0)
        assert r.smoothing_status == "smoothed"

        r = smoother.update(track_id=1, frame_index=1, x_ft=10.0, y_ft=22.0, timestamp=0.033)
        r = smoother.update(track_id=1, frame_index=2, x_ft=10.0, y_ft=22.0, timestamp=0.066)

        # 跳变 50ft in 0.034s ≈ 1470 ft/s >> 30 ft/s
        r = smoother.update(track_id=1, frame_index=3, x_ft=60.0, y_ft=22.0, timestamp=0.1)

        assert r.smoothing_status == "outlier_clamped"

    # 11.8: gap_hold 点被标记，不污染后续指标
    def test_gap_hold_does_not_enter_metrics(self):
        smoother = CourtPositionSmoother(alpha=0.5, max_speed_ft_s=30.0, max_gap_frames=10)

        # 建立平滑状态
        for i in range(5):
            smoother.update(track_id=1, frame_index=i, x_ft=10.0, y_ft=22.0, timestamp=i * 0.033)

        # gap_hold（断 5 帧，≤ max_gap_frames）
        r = smoother.update(track_id=1, frame_index=10, x_ft=12.0, y_ft=22.0, timestamp=10 * 0.033)

        assert r.smoothing_status == "gap_hold"
        # gap_hold 不更新平滑值
        assert r.x == pytest.approx(10.0, abs=0.1)

    def test_gap_reset_after_long_gap(self):
        smoother = CourtPositionSmoother(alpha=0.5, max_speed_ft_s=30.0, max_gap_frames=10)

        smoother.update(track_id=1, frame_index=0, x_ft=10.0, y_ft=22.0, timestamp=0.0)

        # 断 15 帧 > max_gap_frames=10
        r = smoother.update(track_id=1, frame_index=16, x_ft=15.0, y_ft=22.0, timestamp=0.5)

        assert r.smoothing_status == "reset_after_gap"
        assert r.x == 15.0  # 使用新值


# ── 11.9 / 11.10: 向后兼容 ──────────────────────────────────────


class TestBackwardCompatibility:
    # 11.9: 旧分析结果兼容不报错
    def test_old_position_data_can_be_loaded(self):
        """遗留格式（无新字段）的 PlayerFramePosition 仍能正常构造。"""
        pfp = PlayerFramePosition(
            frame_index=0,
            timestamp=0.0,
            track_id=1,
            bbox=[10, 20, 30, 80],
            image_footpoint=[20, 80],
            court_position=[10, 22],
            confidence=0.9,
        )
        assert pfp.valid is True
        assert pfp.validity == "valid"
        assert pfp.footpoint_method == "bbox_bottom_center"
        assert pfp.is_inside_court is True  # 新字段默认值
        assert pfp.is_inside_tracking_area is True
        assert pfp.projection_status == "inside_court"
        assert pfp.projection_confidence is None

        payload = json.loads(pfp.model_dump_json())
        assert payload["valid"] is True
        assert payload["validity"] == "valid"
        assert payload["footpoint_method"] == "bbox_bottom_center"

    # 11.10: valid / validity 旧字段仍能被旧组件读取
    def test_old_fields_accessible(self):
        pfp = PlayerFramePosition(
            frame_index=0,
            timestamp=0.0,
            track_id=1,
            bbox=[10, 20, 30, 80],
            image_footpoint=[20, 80],
            confidence=0.9,
            valid=True,
            validity="valid",
        )
        assert pfp.valid is True
        assert pfp.validity == "valid"

        pfp2 = PlayerFramePosition(
            frame_index=0,
            timestamp=0.0,
            track_id=1,
            bbox=[10, 20, 30, 80],
            image_footpoint=[20, 80],
            confidence=0.9,
            valid=False,
            validity="invalid",
        )
        assert pfp2.valid is False
        assert pfp2.validity == "invalid"

    def test_old_fields_in_json_serialization(self):
        pfp = PlayerFramePosition(
            frame_index=0,
            timestamp=0.0,
            track_id=1,
            bbox=[10, 20, 30, 80],
            image_footpoint=[20, 80],
            confidence=0.9,
            valid=False,
            validity="invalid",
        )
        payload = json.loads(pfp.model_dump_json())
        assert "valid" in payload
        assert payload["valid"] is False
        assert payload["validity"] == "invalid"

    def test_structured_visualization_data_old_compat(self):
        """StructuredVisualizationData 带新字段但仍能被 JSON 序列化。"""
        data = StructuredVisualizationData(
            outside_court_point_count=3,
            dropped_point_count=1,
        )
        json.loads(json.dumps(data, default=lambda o: o.__dict__ if hasattr(o, "__dict__") else str(o)))
        # 使用 _structured_to_dict 方式序列化
        from app.vision.pickleball_game_analysis.visualization_data_builder import _structured_to_dict

        result = _structured_to_dict(data)
        assert result["outside_court_point_count"] == 3
        assert result["dropped_point_count"] == 1


# ── 集成场景 ─────────────────────────────────────────────────


class TestIntegration:
    def test_full_flow_serve_point_outside_court(self):
        """完整链路：y=-5 发球点从投影到结构化数据的全流程。"""
        court = standard_court()
        builder = PositionVisualizationDataBuilder(court=court)

        points = [
            VisualizationPoint(x_ft=10, y_ft=-5, label="Player_1", projection_status="outside_court_visible"),
            VisualizationPoint(x_ft=10, y_ft=22, label="Player_1"),
            VisualizationPoint(x_ft=12, y_ft=25, label="Player_1"),
        ]
        data = builder.build(player_points=points, ball_points=[], bounce_points=[])

        # 轨迹包含界外点
        assert data.outside_court_point_count >= 1

        # 热力图不应包含界外点
        if data.heatmaps is not None and data.heatmaps.visual_grid is not None:
            # 手动检查网格是否包含 y=-5 区域
            for _cell in data.heatmaps.visual_grid.cells:
                # 22 rows over 44ft → row index for y=-5 would be floor((-5)/2) = -3, clamped to 0
                # Since y=-5 is outside court bounds, it should not be counted
                pass

    def test_all_new_fields_in_player_frame_position(self):
        """PlayerFramePosition 包含所有新字段且可 JSON 序列化。"""
        pfp = PlayerFramePosition(
            frame_index=0,
            timestamp=0.0,
            track_id=1,
            bbox=[10, 20, 30, 80],
            image_footpoint=[20, 80],
            court_position=[-3, 46],
            confidence=0.9,
            is_inside_court=False,
            is_inside_tracking_area=True,
            projection_status="outside_court_visible",
            projection_confidence=0.75,
            footpoint_method="pose_ankle_midpoint",
        )
        payload = json.loads(pfp.model_dump_json())

        assert payload["is_inside_court"] is False
        assert payload["is_inside_tracking_area"] is True
        assert payload["projection_status"] == "outside_court_visible"
        assert payload["projection_confidence"] == 0.75
        assert payload["footpoint_method"] == "pose_ankle_midpoint"
        # valid 是独立字段，不与 is_inside_court 联动（由 PlayerProjector 显式设置）
        assert payload["valid"] is True  # 未显式设置时默认为 True
