"""真实双摄 CaptureTake 媒体 smoke：验证 late/joint 的输入与产物接线。"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

from app.schemas.analysis import AnalysisJobCreate, AnalysisUploadMetadata, MultiViewCreateRequest, MultiViewViewPayload, build_match_context
from app.schemas.tracking import Detection
from app.services.dual_camera_sync import FrameTiming, SyncCalibration, write_frame_timing_sidecar
from app.services.frame_timing_provider import FrameTimingProvider
from app.services.job_orchestration import analysis_signature
from app.vision.court_view import compute_expanded_detection_roi
from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
from app.vision.multiview.association_global import GlobalPlayerAssociator
from app.vision.multiview.court_frame import CanonicalCourtFrameDefinition, CourtOrientation
from app.vision.multiview.fusion import FusionConfig
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.multiview.guidance import CrossViewGuidancePolicy, GuidanceGenerator, invert_homography
from app.vision.multiview.joint_types import JointViewInput
from app.vision.multiview.joint_view_runtime import JointViewRuntime
from app.vision.multiview.multiview_joint_run import MultiViewJointRun
from app.vision.multiview.pipeline import run_fusion_pipeline
from app.vision.multiview.sync import MultiViewSyncCalibration
from app.vision.multiview.types import ViewObservation
from app.vision.player_tracking_engine.view_tracking_session import build_view_tracking_config, build_view_tracking_session
from app.camera.models import SyncRecordingSession


REAL_TAKE_DIR = (
    Path(__file__).parents[1]
    / "data"
    / "recordings"
    / "captures"
    / "2026-07-18"
    / "take_sync_20260718_095421_f7d52a"
)


def _obs(view_id: str, player_id: str, frame: int, ts: float, x: float, y: float) -> ViewObservation:
    return ViewObservation(
        view_id=view_id,
        source_frame_index=frame,
        timestamp_seconds=ts,
        local_x_ft=x,
        local_y_ft=y,
        view_player_id=player_id,
        projection_confidence=0.9,
        footpoint_method="synthetic_smoke",
        confidence=0.9,
    )


class _ScriptedDetector:
    supports_region_detection = False

    def detect_frame(self, _frame, frame_index: int | None = None) -> list[Detection]:
        offset = float(int(frame_index or 0))
        return [
            Detection(bbox=[280 + offset, 180, 340 + offset, 360], confidence=0.9, class_name="person"),
            Detection(bbox=[460 + offset, 190, 520 + offset, 370], confidence=0.9, class_name="person"),
        ]

    def detect(self, _frame) -> list[Detection]:
        return []


def _load_real_take() -> tuple[SyncRecordingSession, dict[str, Path]]:
    metadata_path = REAL_TAKE_DIR / "metadata" / "recording_session.json"
    session = SyncRecordingSession.model_validate(json.loads(metadata_path.read_text(encoding="utf-8")))
    videos = {
        "cam_1": REAL_TAKE_DIR / f"{session.camera_slots['cam_1'].camera_id}_merged.mp4",
        "cam_2": REAL_TAKE_DIR / f"{session.camera_slots['cam_2'].camera_id}_merged.mp4",
    }
    assert session.capture_take_id
    assert all(path.exists() for path in videos.values())
    return session, videos


def _read_media_probe(videos: dict[str, Path], limit: int = 6) -> tuple[float, int, int]:
    fps_values = []
    width = height = 0
    for path in videos.values():
        capture = cv2.VideoCapture(str(path))
        try:
            assert capture.isOpened(), path
            fps_values.append(float(capture.get(cv2.CAP_PROP_FPS) or 60.0))
            width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            for _ in range(limit):
                ok, frame = capture.read()
                assert ok and frame is not None
        finally:
            capture.release()
    return min(fps_values), width, height


def test_real_capture_take_late_and_joint_smoke(tmp_path):
    session, videos = _load_real_take()
    fps, width, height = _read_media_probe(videos)
    frame_count = 6
    reference_id = session.camera_slots["cam_1"].camera_id
    secondary_id = session.camera_slots["cam_2"].camera_id
    sync = MultiViewSyncCalibration(
        reference_camera=reference_id,
        mappings={
            secondary_id: SyncCalibration(
                reference_camera=reference_id,
                camera_id=secondary_id,
                offset_seconds=0.0,
                rate=1.0,
                drift_ppm=0.0,
                residual_rms_seconds=0.0,
                anchor_count=2,
                quality="good",
            )
        },
    )
    providers = {}
    for slot, media_path in videos.items():
        sidecar = tmp_path / f"{slot}.registered.mp4.pts.jsonl"
        write_frame_timing_sidecar(media_path, sidecar)
        providers[slot] = FrameTimingProvider.from_sidecar(sidecar, media_path=media_path)
        assert providers[slot].provenance.authority == "source_pts"
    canonical = CanonicalCourtFrameDefinition.create(
        session.capture_take_id,
        "recorded-cam-1-end-a",
        "recorded-cam-1-end-b",
        orientation_by_view={"cam_1": "identity", "cam_2": "identity"},
    )

    reference = [_obs("cam_1", "A", i, i / fps, 5.0 + i * 0.1, 8.0) for i in range(frame_count)]
    secondary = [_obs("cam_2", "X", i, i / fps, 5.0 + i * 0.1, 8.0) for i in range(frame_count)]
    late = run_fusion_pipeline(
        reference_view_id="cam_1",
        reference_observations=reference,
        secondary_view_id="cam_2",
        secondary_observations=secondary,
        reference_orientation=CourtOrientation.identity,
        secondary_orientation=CourtOrientation.identity,
        sync=sync,
        secondary_camera_id=secondary_id,
        max_pairing_error_ms=1000.0 / fps,
        config=FusionConfig(),
    )
    assert late.pairing_plan is not None
    assert late.pairing_plan.available_count == frame_count
    assert all(measurement.fusion_status == "dual_observed" for measurement in late.measurements)

    from app.vision.multiview.artifact import build_fused_artifact, build_fusion_diagnostics, write_fused_artifact, write_fusion_diagnostics
    run_dir = tmp_path / "analysis" / "multiview" / "mvf-real-smoke"
    fused = build_fused_artifact(
        late.measurements,
        run_id="mvf-real-smoke",
        capture_take_id=session.capture_take_id,
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        sync_quality="good",
        court_frame_version="canonical_court_frame.v1",
        canonical_frame_id=canonical.frame_id,
    )
    diagnostics = build_fusion_diagnostics(
        late.measurements,
        run_id="mvf-real-smoke",
        global_players=late.global_players,
        orientations={"cam_1": "identity", "cam_2": "identity"},
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        pairing_plan=late.pairing_plan,
        canonical_frame_id=canonical.frame_id,
        requested_mode="late_fusion_v1",
    )
    write_fused_artifact(run_dir, fused)
    write_fusion_diagnostics(run_dir, diagnostics)
    assert fused["capture_take_id"] == session.capture_take_id
    assert diagnostics["pairing_plan"]["available_count"] == frame_count
    assert diagnostics["canonical_frame_id"] == canonical.frame_id

    captures = {slot: cv2.VideoCapture(str(path)) for slot, path in videos.items()}
    config = build_view_tracking_config(
        type("Settings", (), {
            "player_analysis_hard_limit": 4,
            "primary_player_window_seconds": 1.0,
            "primary_player_min_confidence": 0.2,
            "primary_player_min_box_area_ratio": 0.0001,
            "primary_player_max_box_area_ratio": 0.8,
            "primary_player_court_margin_ft": 10.0,
            "primary_player_target_court_threshold": 0.0,
            "primary_player_quality_threshold": 0.0,
            "enable_attention_player_selector": False,
            "attention_player_selector_model_path": None,
            "attention_player_selector_confidence": 0.5,
            "player_identity_lost_buffer_seconds": 1.0,
            "player_identity_inactive_buffer_seconds": 1.0,
            "player_identity_interpolation_buffer_seconds": 1.0,
            "player_identity_match_threshold": 0.1,
            "player_identity_max_reconnect_distance_m": 10.0,
            "player_identity_max_speed_mps": 30.0,
            "player_identity_court_buffer_m": 10.0,
            "player_identity_smoothing_window": 1,
            "player_lock_bootstrap_min_seconds": 0.0,
            "player_lock_bootstrap_max_seconds": 1.0,
            "player_lock_lost_grace_seconds": 1.0,
            "player_lock_lost_max_seconds_locked": 1.0,
            "player_lock_min_observed_frames": 1,
            "player_lock_lock_min_hits": 1,
            "player_lock_plausible_min_hits": 1,
            "player_lock_locked_conf": 0.1,
            "player_lock_tentative_conf": 0.1,
            "player_lock_searching_conf": 0.1,
            "player_lock_reconnect_threshold": 10.0,
            "player_lock_court_margin_ft": 10.0,
            "player_lock_max_reconnect_distance_ft": 10.0,
            "player_lock_bootstrap_court_margin_ft": 10.0,
            "player_lock_lost_reconnect_court_margin_ft": 10.0,
            "player_lock_enable_appearance_score": False,
            "player_duplicate_track_iou_threshold": 0.9,
            "player_duplicate_track_sustain_frames": 5,
        })(),
        build_match_context(None),
        fps=fps,
        frame_stride=1,
        frame_width=width,
        frame_height=height,
    )
    roi = compute_expanded_detection_roi(None, width, height)
    homography = [[20.0 / width, 0.0, 0.0], [0.0, 44.0 / height, 0.0], [0.0, 0.0, 1.0]]
    runtimes = {}
    for slot, camera in captures.items():
        tracking = build_view_tracking_session(
            detector=_ScriptedDetector(),
            homography=homography,
            roi_artifact=roi,
            config=config,
        )
        runtimes[slot] = JointViewRuntime(
            view_input=JointViewInput(camera_slot=slot, camera_id=session.camera_slots[slot].camera_id),
            capture=camera,
            fps=fps,
            frame_size=(width, height),
            homography=homography,
            roi_artifact=roi,
            tracking_session=tracking,
            scope="full" if slot == "cam_1" else "perception",
        )

    try:
        registry = GlobalPlayerRegistry(anchored_dual_view_count=1, confirm_dual_view_count=1)
        joint = MultiViewJointRun(
            run_id="mvr-real-smoke",
            capture_take_id=session.capture_take_id,
            reference_view_id="cam_1",
            clock=CanonicalAnalysisClock(
                reference_view_id="cam_1",
                secondary_view_id="cam_2",
                secondary_frames=list(providers["cam_2"].frames_with_origin()),
                sync=sync,
                secondary_camera_id=secondary_id,
                reference_timing_provider=providers["cam_1"],
                secondary_timing_provider=providers["cam_2"],
                reference_timing_authority="source_pts",
                secondary_timing_authority="source_pts",
            ),
            runtimes=runtimes,
            registry=registry,
            associator=GlobalPlayerAssociator(registry, max_association_distance_ft=10.0),
            guidance_generator=GuidanceGenerator(CrossViewGuidancePolicy()),
            orientations={"cam_1": CourtOrientation.identity, "cam_2": CourtOrientation.identity},
            inverse_homography=invert_homography(homography),
            frame_width=width,
            frame_height=height,
            canonical_frame_ref=canonical,
            timing_authority_by_view={"cam_1": "source_pts", "cam_2": "source_pts"},
            sync_quality="good",
            execution_mode="joint_authoritative",
            authoritative_joint_eligible=True,
        )
        joint_output = joint.run(reference_frame_count=frame_count, reference_fps=fps)
    finally:
        for capture in captures.values():
            capture.release()

    assert joint_output.trajectory["capture_take_id"] == session.capture_take_id
    assert joint_output.diagnostics["canonical_frame_id"] == canonical.frame_id
    assert all(runtime.counters.get("stepped_frames", 0) > 0 for runtime in runtimes.values())
    assert joint_output.diagnostics["execution_mode"] == "joint_authoritative"
    assert joint_output.diagnostics["authoritative_eligible_tick_count"] > 0
    assert joint_output.diagnostics["frame_status_counts"]["available"] >= frame_count
    assert all(
        field in next(iter(sample["view_observations"].values()))
        for sample in joint_output.trajectory["samples"]
        for field in (
            "source_frame_index",
            "source_timestamp_ms",
            "mapped_take_timestamp_ms",
            "selection_error_ms",
            "timing_authority",
            "sync_quality",
        )
    ) if joint_output.trajectory["samples"] else True

    def payload(mode: str) -> AnalysisJobCreate:
        metadata = AnalysisUploadMetadata(
            fileName="real-dual-capture.mp4",
            matchTitle="real dual smoke",
            venue="test",
            matchDate="2026-07-18",
            matchFormat="doubles",
            cameraAngle="baseline",
            athleteLabel="smoke",
            level="test",
            capture_take_id=session.capture_take_id,
        )
        return AnalysisJobCreate(
            metadata=metadata,
            analysisKind="multiview",
            multiview=MultiViewCreateRequest(
                executionMode=mode,
                referenceViewId="cam_1",
                views=[
                    MultiViewViewPayload(viewId="cam_1", videoId="v1", calibrationId="c1", courtOrientation="identity"),
                    MultiViewViewPayload(viewId="cam_2", videoId="v2", calibrationId="c2", courtOrientation="identity"),
                ],
            ),
        )

    assert analysis_signature(payload("late_fusion_v1"))[0] != analysis_signature(payload("joint_tracking_v2"))[0]


def test_real_capture_pts_drift_and_seek_smoke(tmp_path):
    """Use the checked-in dual-camera media without mutating its source files."""
    _session, videos = _load_real_take()
    providers: dict[str, FrameTimingProvider] = {}
    for slot, media_path in videos.items():
        sidecar = tmp_path / f"{slot}.pts.jsonl"
        summary = write_frame_timing_sidecar(media_path, sidecar)
        provider = FrameTimingProvider.from_sidecar(sidecar, media_path=media_path)
        assert summary["frame_count"] == len(provider.frames) > 0
        assert provider.is_source_pts
        assert provider.duration_seconds > 0
        providers[slot] = provider

        seek_time = min(1.0, provider.duration_seconds / 2.0)
        frame_index = provider.frame_index_at_or_after_take_time(seek_time)
        assert frame_index is not None
        capture = cv2.VideoCapture(str(media_path))
        try:
            assert capture.isOpened()
            assert capture.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
            ok, frame = capture.read()
            assert ok and frame is not None
            assert int(capture.get(cv2.CAP_PROP_POS_FRAMES)) >= frame_index
        finally:
            capture.release()

    reference = providers["cam_1"]
    secondary = providers["cam_2"]
    duration_ratio = secondary.duration_seconds / reference.duration_seconds
    drift_ppm = (duration_ratio - 1.0) * 1_000_000.0
    offset_seconds = (secondary.first_timestamp_seconds or 0.0) - (reference.first_timestamp_seconds or 0.0)
    assert np.isfinite(drift_ppm)
    assert np.isfinite(offset_seconds)
    assert abs(drift_ppm) < 100_000
