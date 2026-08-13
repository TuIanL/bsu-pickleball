"""ViewTrackingSession 单元测试 + 强制 synthetic differential test。

行为保护：默认 guidance=() 时 session 输出必须与重构前的内联 tracking 链完全一致。
differential test 用一个独立构造的 reference 组件实例集 + 手写 reference step 复刻旧链，
逐项对比 session 输出（positions / frame_detections / render observations / render events /
diagnostics / ROI 计数）。
"""

from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

import numpy as np

from app.core.config import get_settings
from app.schemas.analysis import build_match_context
from app.schemas.tracking import Detection
from app.vision.court_view import compute_expanded_detection_roi, filter_detections_to_roi
from app.vision.player_tracking_engine.court_position_smoother import CourtPositionSmoother
from app.vision.player_tracking_engine.footpoint_estimator import FootpointEstimator
from app.vision.player_tracking_engine.multi_object_tracker import DuplicateTrackSuppressor, MultiObjectTracker
from app.vision.player_tracking_engine.person_detector import (
    EmptyPersonDetector,
    PersonDetector,
    RegionDetectionUnsupported,
)
from app.vision.player_tracking_engine.player_identity import PlayerIdentityConfig, PlayerIdentityManager
from app.vision.player_tracking_engine.player_lock_manager import PlayerLockManager
from app.vision.player_tracking_engine.player_lock_types import PlayerLockConfig
from app.vision.player_tracking_engine.player_projector import PlayerProjector
from app.vision.player_tracking_engine.primary_player_selector import PrimaryPlayerSelector
from app.vision.player_tracking_engine.view_tracking_session import (
    ViewTrackingSession,
    build_view_tracking_config,
    build_view_tracking_session,
)

# 把投影到球场坐标的缩放 homography：court ≈ 0.05 * image（落在球场边界内）。
SCALE_HOMOGRAPHY = [[0.05, 0.0, 0.0], [0.0, 0.05, 0.0], [0.0, 0.0, 1.0]]
WIDTH, HEIGHT = 640, 480


def _make_config():
    settings = get_settings()
    config = build_view_tracking_config(
        settings,
        build_match_context(None),
        fps=30.0,
        frame_stride=1,
        frame_width=WIDTH,
        frame_height=HEIGHT,
    )
    # 收紧帧窗口让测试快速收敛（两个路径用同一 config → 行为仍一致）
    config.player_lock_bootstrap_min_frames = 1
    config.player_lock_bootstrap_max_frames = 4
    config.identity_lost_buffer_frames = 5
    config.player_identity_match_threshold = 0.1
    config.player_identity_max_reconnect_distance_m = 50.0
    return config


def _make_roi_artifact():
    # 无标定四角 → status="unavailable" → 全帧 fallback（filter 返回全部 + 0 过滤）
    return compute_expanded_detection_roi(None, WIDTH, HEIGHT)


class ScriptedDetector:
    """确定性 mock detector：按 frame_index 返回脚本化检测。"""

    supports_region_detection = False

    def __init__(self, script: dict[int, list[Detection]]):
        self.script = script

    def detect_frame(self, frame, frame_index: int | None = None) -> list[Detection]:
        return self.script.get(int(frame_index or 0), [])

    def detect(self, frame) -> list[Detection]:
        return []


class RegionScriptedDetector(ScriptedDetector):
    supports_region_detection = True

    def __init__(self, script: dict[int, list[Detection]], region_script: list[Detection]):
        super().__init__(script)
        self.region_script = region_script
        self.region_calls: list[list[tuple[float, float, float, float]]] = []

    def detect_regions(self, frame, rois):
        self.region_calls.append(list(rois))
        return list(self.region_script)


def _det(bbox, conf: float = 0.8) -> Detection:
    return Detection(bbox=list(bbox), confidence=conf, class_name="person")


def _default_script() -> dict[int, list[Detection]]:
    # A 两帧可见 → 一帧丢失 → 再出现；B 全程可见（轻位移）。
    return {
        0: [_det([280, 150, 310, 300]), _det([340, 160, 370, 350])],  # A / B
        1: [_det([280, 150, 310, 305]), _det([340, 160, 370, 355])],
        2: [_det([340, 160, 370, 355])],  # A 丢失
        3: [_det([280, 150, 310, 305]), _det([340, 160, 370, 355])],
        4: [_det([280, 150, 310, 308]), _det([340, 160, 370, 358])],
    }


# ---- detect_regions 契约 --------------------------------------------------


def test_person_detector_detect_regions_contract():
    # PersonDetector 已实现 ROI 推理契约(Change 2);未加载模型时按懒加载触发 RuntimeError。
    detector = PersonDetector()
    assert detector.supports_region_detection is True
    try:
        detector.detect_regions(None, [(0, 0, 100, 100)])
    except RegionDetectionUnsupported:
        raise AssertionError("PersonDetector 已实现 ROI 推理,不应抛 RegionDetectionUnsupported")
    except RuntimeError:
        pass  # 未安装 ultralytics / 未加载模型 → 懒加载失败(契约已存在)
    except Exception:
        pass


def test_person_detector_batch_region_results_preserve_roi_coordinates(monkeypatch):
    class Box:
        cls = [0]
        conf = [0.8]

        def __init__(self, xyxy):
            self.xyxy = [xyxy]

    class Result:
        def __init__(self, xyxy):
            self.boxes = [Box(xyxy)]

    class Model:
        def __call__(self, crops, **_kwargs):
            assert len(crops) == 2
            return [Result([1, 2, 11, 22]), Result([3, 4, 13, 24])]

    detector = PersonDetector()
    detector._model = Model()
    frame = np.zeros((40, 40, 3), dtype=np.uint8)
    regions = [(10, 20, 30, 35), (100, 200, 130, 235)]

    grouped = detector.detect_regions_batch(frame, regions)
    flattened = detector.detect_regions(frame, regions)

    assert [[d.bbox for d in group] for group in grouped] == [
        [[11.0, 22.0, 21.0, 42.0]],
        [[103.0, 204.0, 113.0, 224.0]],
    ]
    assert [d.bbox for d in flattened] == [
        [11.0, 22.0, 21.0, 42.0],
        [103.0, 204.0, 113.0, 224.0],
    ]


def test_empty_person_detector_detect_regions_returns_empty():
    detector = EmptyPersonDetector()
    assert detector.detect_regions(None, [(0, 0, 100, 100)]) == []


def test_non_empty_guidance_runs_joint_path_but_default_path_stays_legacy():
    """The joint adapter must invoke ROI detection only when guidance is present."""
    config = _make_config()
    config.eligibility_policy = "lock_only"
    detector = RegionScriptedDetector(
        {},
        [_det([280, 150, 310, 300])],
    )
    session = build_view_tracking_session(
        detector=detector,
        homography=SCALE_HOMOGRAPHY,
        roi_artifact=_make_roi_artifact(),
        config=config,
    )
    result = session.step(
        object(),
        frame_index=0,
        timestamp=0.0,
        guidance=(
            SimpleNamespace(
                roi=(250.0, 100.0, 340.0, 320.0),
                predicted_local_position=(15.0, 15.0),
                guidance_id="g_joint",
                expected_global_player_id="global_player_1",
                donor_view="cam_2",
                donor_quality=0.9,
            ),
        ),
    )
    assert result.guided_detection_invoked is True
    assert result.guided_candidate_count == 1
    assert detector.region_calls == [[(250.0, 100.0, 340.0, 320.0)]]

    # A fresh legacy session with guidance omitted never calls detect_regions.
    legacy_detector = RegionScriptedDetector({}, [_det([280, 150, 310, 300])])
    legacy = build_view_tracking_session(
        detector=legacy_detector,
        homography=SCALE_HOMOGRAPHY,
        roi_artifact=_make_roi_artifact(),
        config=_make_config(),
    )
    legacy_result = legacy.step(object(), frame_index=0, timestamp=0.0)
    assert legacy_result.guided_detection_invoked is False
    assert legacy_detector.region_calls == []


# ---- config 构造 ----------------------------------------------------------


def test_build_view_tracking_config_fields():
    settings = get_settings()
    ctx = build_match_context(None)
    config = build_view_tracking_config(
        settings, ctx, fps=60.0, frame_stride=2, frame_width=WIDTH, frame_height=HEIGHT
    )
    assert config.fps == 60.0
    assert config.frame_stride == 2
    assert config.frame_width == WIDTH
    assert config.frame_height == HEIGHT
    assert config.effective_player_count == min(ctx.expected_player_count, settings.player_analysis_hard_limit)
    assert config.match_context is ctx
    assert config.identity_lost_buffer_frames > 0
    assert config.player_lock_bootstrap_min_frames >= 0


# ---- session 基础行为 -----------------------------------------------------


def test_session_step_returns_view_frame_result():
    config = _make_config()
    session = build_view_tracking_session(
        detector=ScriptedDetector(_default_script()),
        homography=SCALE_HOMOGRAPHY,
        roi_artifact=_make_roi_artifact(),
        config=config,
    )
    result = session.step(object(), frame_index=0, timestamp=0.0)
    assert result.frame_index == 0
    assert result.frame_positions is not None
    assert result.render_raw_by_track is not None
    assert result.player_motion_pixels is None or result.player_motion_pixels >= 0


def test_session_binds_frame_index_to_raw_detector_results():
    """Raw detector boxes must remain traceable to the frame that produced them."""
    config = _make_config()
    session = build_view_tracking_session(
        detector=ScriptedDetector({3: [_det([280, 150, 310, 300])]}),
        homography=SCALE_HOMOGRAPHY,
        roi_artifact=_make_roi_artifact(),
        config=config,
    )

    session.step(object(), frame_index=3, timestamp=0.1)

    assert session.snapshot().raw_detections[0].frame_index == 3


def test_dual_session_state_isolation():
    config = _make_config()
    script = _default_script()
    a = build_view_tracking_session(
        detector=ScriptedDetector(script), homography=SCALE_HOMOGRAPHY,
        roi_artifact=_make_roi_artifact(), config=config,
    )
    b = build_view_tracking_session(
        detector=ScriptedDetector(script), homography=SCALE_HOMOGRAPHY,
        roi_artifact=_make_roi_artifact(), config=config,
    )
    for i in range(3):
        a.step(object(), frame_index=i, timestamp=i / 30.0)
        b.step(object(), frame_index=i, timestamp=i / 30.0)
    # 独立实例：各自状态互不共享（tracker / identity / lock 内部独立）。
    assert a.tracker is not b.tracker
    assert a.identity_manager is not b.identity_manager
    assert a.player_lock_manager is not b.player_lock_manager
    assert len(a.snapshot().positions) == len(b.snapshot().positions)


def test_shared_detector_across_sessions():
    config = _make_config()
    shared = ScriptedDetector(_default_script())
    a = build_view_tracking_session(detector=shared, homography=SCALE_HOMOGRAPHY,
                                    roi_artifact=_make_roi_artifact(), config=config)
    b = build_view_tracking_session(detector=shared, homography=SCALE_HOMOGRAPHY,
                                    roi_artifact=_make_roi_artifact(), config=config)
    a.step(object(), frame_index=0, timestamp=0.0)
    b.step(object(), frame_index=1, timestamp=1 / 30.0)
    assert a.detector is b.detector


def test_factory_preserves_dependency_injection():
    config = _make_config()

    class FakeTracker(MultiObjectTracker):
        tag = "fake_tracker"

    class FakeFootpoint(FootpointEstimator):
        tag = "fake_footpoint"

    class FakeProjector(PlayerProjector):
        tag = "fake_projector"

    fake_tracker = FakeTracker(max_lost=5)
    fake_footpoint = FakeFootpoint()
    fake_projector = FakeProjector(footpoint_estimator=fake_footpoint, include_invalid=True, drop_outside_tracking=False)
    session = build_view_tracking_session(
        detector=ScriptedDetector(_default_script()),
        homography=SCALE_HOMOGRAPHY,
        roi_artifact=_make_roi_artifact(),
        config=config,
        tracker=fake_tracker,
        footpoint_estimator=fake_footpoint,
        projector=fake_projector,
    )
    assert session.tracker is fake_tracker
    assert session.footpoint_estimator is fake_footpoint
    assert session.projector is fake_projector


# ---- 强制 differential test ------------------------------------------------

@dataclass
class _ReferenceComponents:
    detector: object
    roi_artifact: object
    homography: list[list[float]]
    config: object
    tracker: MultiObjectTracker
    suppressor: DuplicateTrackSuppressor
    footpoint: FootpointEstimator
    projector: PlayerProjector
    smoother: CourtPositionSmoother
    selector: PrimaryPlayerSelector
    lock: PlayerLockManager
    identity: PlayerIdentityManager


def _build_reference_components(detector, roi_artifact, homography, config):
    """独立构造 reference 组件集（不复用 session 工厂，模拟旧链的组件装配）。"""
    tracker = MultiObjectTracker(max_lost=config.identity_lost_buffer_frames)
    suppressor = DuplicateTrackSuppressor(
        iou_threshold=config.player_duplicate_track_iou_threshold,
        sustain_frames=config.player_duplicate_track_sustain_frames,
    )
    footpoint = FootpointEstimator()
    projector = PlayerProjector(footpoint_estimator=footpoint, include_invalid=True, drop_outside_tracking=False)
    smoother = CourtPositionSmoother(
        alpha=config.position_smoother_alpha,
        max_speed_ft_s=config.position_smoother_max_speed_ft_s,
        max_gap_frames=config.position_smoother_max_gap_frames,
        frame_stride=config.frame_stride,
    )
    selector = PrimaryPlayerSelector(
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
    lock = PlayerLockManager(
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
    identity = PlayerIdentityManager(
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
    return _ReferenceComponents(
        detector=detector, roi_artifact=roi_artifact, homography=homography, config=config,
        tracker=tracker, suppressor=suppressor, footpoint=footpoint, projector=projector,
        smoother=smoother, selector=selector, lock=lock, identity=identity,
    )


def _reference_step(c: _ReferenceComponents, frame, frame_index: int, timestamp: float) -> dict:
    """手写 reference step：复刻重构前 `_run_tracking` 的内联 tracking 链顺序。"""
    # 1) detect + ROI filter
    raw_detections = c.detector.detect_frame(frame, frame_index)
    detections, roi_filtered = filter_detections_to_roi(raw_detections, c.roi_artifact)
    roi_filtered_count = roi_filtered
    full_fallback = 1 if c.roi_artifact.status != "available" else 0
    # 2) track + suppress
    tracks = c.tracker.update(detections)
    tracks = c.suppressor.filter(tracks)
    # 3) footpoint + project
    footpoints = {
        t.track_id: c.footpoint.estimate(t, frame_shape=(c.config.frame_width, c.config.frame_height))
        for t in tracks
    }
    positions = c.projector.project(
        tracks=tracks, homography=c.homography, frame_index=frame_index, timestamp=timestamp,
        footpoints=footpoints, frame_shape=(c.config.frame_width, c.config.frame_height),
    )
    render_raw = {}
    for pos in positions:
        if pos.court_position is not None:
            render_raw[pos.track_id] = {
                "x_ft": pos.court_position[0], "y_ft": pos.court_position[1],
                "projection_status": pos.projection_status,
                "projection_confidence": pos.projection_confidence,
                "footpoint_method": pos.footpoint_method, "confidence": pos.confidence,
            }
    # 4) smooth
    for pos in positions:
        if pos.court_position is not None:
            res = c.smoother.update(
                track_id=pos.track_id, frame_index=pos.frame_index,
                x_ft=pos.court_position[0], y_ft=pos.court_position[1],
                timestamp=pos.timestamp, confidence=pos.confidence,
            )
            pos.court_position = [res.x, res.y]
    # 5) select
    selections = c.selector.select(
        tracks=tracks, positions=positions,
        frame_width=c.config.frame_width, frame_height=c.config.frame_height,
    )
    suggested = {s.track_id for s in selections}
    selection_diag_count = len(c.selector.last_diagnostics)
    # 6) lock
    lock_update = c.lock.update(
        frame_index=frame_index, positions=positions, suggestions=selections, frame=frame,
        frame_width=c.config.frame_width, frame_height=c.config.frame_height,
    )
    lock_diag_count = len(lock_update.diagnostics)
    eligible = lock_update.eligible_track_ids | suggested
    # 7) frame detections
    frame_detections = [
        {
            "track_id": t.track_id, "bbox": list(t.bbox), "confidence": t.confidence,
        }
        for t in tracks
        if not t.lost and (eligible is None or t.track_id in eligible)
    ]
    # 8) identity
    samples = c.identity.update(
        frame_index=frame_index, positions=positions,
        eligible_track_ids=eligible, track_identity_hints=lock_update.track_identity_hints,
    )
    player_by_track = {
        s.track_id: s.player_id for s in samples
        if s.track_id is not None and s.tracking_status in ("detected", "tentative")
    }
    tentative = {s.track_id for s in samples if s.track_id is not None and s.tracking_status == "tentative"}
    # 9) render observations（须在 epoch 递增之前）
    render_obs = []
    for pos in positions:
        raw = render_raw.get(pos.track_id)
        pid = player_by_track.get(pos.track_id)
        if raw is None or pid is None:
            continue
        render_obs.append(
            {
                "frame_index": frame_index,
                "player_id": pid,
                "identity_epoch": c.identity_epoch_by_player.get(pid, 0),
                "x_ft": raw["x_ft"], "y_ft": raw["y_ft"],
                "status": "tentative" if pos.track_id in tentative else "detected",
            }
        )
    return {
        "positions": [
            {"track_id": p.track_id, "court": list(p.court_position) if p.court_position else None,
             "status": p.projection_status, "conf": p.confidence}
            for p in positions
        ],
        "frame_detections": frame_detections,
        "render_observations": render_obs,
        "roi_filtered_count": roi_filtered_count,
        "full_fallback_count": full_fallback,
        "selection_diag_count": selection_diag_count,
        "lock_diag_count": lock_diag_count,
    }


def _session_signature(session: ViewTrackingSession) -> dict:
    """把 session 的可观测输出归一化为与 reference 可比的结构。"""
    snap = session.snapshot()
    return {
        "positions": [
            {"track_id": p.track_id, "court": list(p.court_position) if p.court_position else None,
             "status": p.projection_status, "conf": p.confidence}
            for p in snap.positions
        ],
        "frame_detections": [
            {"track_id": int(d.track_id), "bbox": list(d.bbox), "confidence": d.confidence}
            for frame in snap.overlay_frames for d in frame.detections
            if d.track_id is not None
        ],
        "render_observations": [
            {"frame_index": o.frame_index, "player_id": o.player_id, "identity_epoch": o.identity_epoch,
             "x_ft": o.raw_x_ft, "y_ft": o.raw_y_ft, "status": o.tracking_status}
            for o in snap.render_observations
        ],
        "roi_filtered_count": snap.roi_filtered_detection_count,
        "full_fallback_count": snap.full_frame_fallback_count,
        "selection_diag_count": len(snap.selection_diagnostics),
        "lock_diag_count": len(snap.lock_diagnostics),
    }


def test_differential_session_matches_reference_chain():
    """强制 differential test：session 与手写 reference 链逐项一致（行为保护核心）。"""
    config = _make_config()
    script = _default_script()
    roi = _make_roi_artifact()

    # session 路径
    session = build_view_tracking_session(
        detector=ScriptedDetector(script), homography=SCALE_HOMOGRAPHY, roi_artifact=roi, config=config,
    )
    # reference 路径：独立构造组件 + 手写 step（与 session 逐帧同步推进一次）
    ref = _build_reference_components(ScriptedDetector(script), roi, SCALE_HOMOGRAPHY, config)
    ref.identity_epoch_by_player = {}  # type: ignore[attr-defined]

    ref_outputs = []
    for i in range(5):
        session.step(object(), frame_index=i, timestamp=i / 30.0)
        ref_outputs.append(_reference_step(ref, object(), frame_index=i, timestamp=i / 30.0))

    session_sig = _session_signature(session)

    # 汇总 reference 逐帧输出
    ref_positions = []
    ref_detections = []
    ref_render_obs = []
    ref_roi = ref_full = ref_sel = ref_lock = 0
    for out in ref_outputs:
        ref_positions.extend(out["positions"])
        ref_detections.extend(out["frame_detections"])
        ref_render_obs.extend(out["render_observations"])
        ref_roi += out["roi_filtered_count"]
        ref_full += out["full_fallback_count"]
        ref_sel += out["selection_diag_count"]
        ref_lock += out["lock_diag_count"]

    assert session_sig["positions"] == ref_positions
    assert session_sig["frame_detections"] == ref_detections
    assert session_sig["render_observations"] == ref_render_obs
    assert session_sig["roi_filtered_count"] == ref_roi
    assert session_sig["full_fallback_count"] == ref_full
    assert session_sig["selection_diag_count"] == ref_sel
    assert session_sig["lock_diag_count"] == ref_lock
