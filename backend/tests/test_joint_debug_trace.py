from __future__ import annotations

import json
from types import SimpleNamespace

import cv2
import numpy as np
import pytest

from app.services.joint_debug_renderer import (
    JointDebugRenderError,
    JointDebugRenderInputs,
    render_joint_debug_artifacts,
)
from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
from app.vision.multiview.association_global import GlobalPlayerAssociator
from app.vision.multiview.court_frame import CanonicalCourtFrameDefinition, CourtOrientation
from app.vision.multiview.debug_trace import (
    build_joint_debug_manifest,
    build_joint_debug_trace,
    load_joint_debug_trace,
    write_joint_debug_trace,
)
from app.vision.multiview.fusion_run import default_run_output_dir
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.multiview.guidance import CrossViewGuidancePolicy, GuidanceGenerator
from app.vision.multiview.joint_artifact import write_fused_v2
from app.vision.multiview.multiview_joint_run import MultiViewJointRun
from app.services.dual_camera_sync import FrameTiming


def _view(*, status: str = "available", source_frame_index: int | None = 0) -> dict[str, object]:
    return {
        "status": status,
        "source_frame_index": source_frame_index,
        "source_timestamp_ms": 0.0 if source_frame_index is not None else None,
        "mapped_take_timestamp_ms": 0.0,
        "selection_error_ms": 0.0 if source_frame_index is not None else None,
        "timing_authority": "source_pts" if source_frame_index is not None else "missing",
        "sync_quality": "good" if source_frame_index is not None else "unknown",
        "observations": [],
        "observation_status": "missing" if source_frame_index is not None else "unavailable",
        "detections": [],
        "guidance": [],
        "bindings": {},
    }


def _trace(tick_count: int = 1) -> dict[str, object]:
    ticks = []
    for index in range(tick_count):
        ticks.append(
            {
                "canonical_tick": index,
                "reference_frame_index": index,
                "canonical_timestamp_ms": index * 100.0,
                "authoritative_tick": True,
                "frame_status": {"cam_1": "available", "cam_2": "available"},
                "views": {"cam_1": _view(source_frame_index=index), "cam_2": _view(source_frame_index=2 - index)},
                "global_predictions": {},
                "canonical_observations": [],
                "fused": {},
                "recovery": {},
            }
        )
    return build_joint_debug_trace(
        run_id="mvr_debug",
        capture_take_id="take_debug",
        reference_view_id="cam_1",
        timing_authority_by_view={"cam_1": "source_pts", "cam_2": "source_pts"},
        sync_quality="good",
        execution_mode="joint_authoritative",
        authoritative_joint_eligible=True,
        ticks=ticks,
    )


def test_trace_writer_and_manifest_are_versioned_and_atomic(tmp_path):
    trace_path = write_joint_debug_trace(tmp_path / "joint_debug_trace.v1.json", _trace())
    loaded = load_joint_debug_trace(trace_path)
    assert loaded["schema_version"] == "joint_debug_trace.v1"
    assert loaded["ticks"][0]["views"]["cam_1"]["observation_status"] == "missing"

    manifest = build_joint_debug_manifest(run_id="mvr_debug", capture_take_id="take_debug", config={"frame_stride": 1})
    assert manifest["trace_schema"] == "joint_debug_trace.v1"
    assert manifest["debug_trace_enabled"] is True


def _make_joint_run(*, debug_trace_enabled: bool) -> MultiViewJointRun:
    class FakeRuntime:
        def __init__(self, view_id: str):
            self.view_id = view_id

        def step(self, source_frame_index, timestamp_s, guidance=()):
            return SimpleNamespace(frame_index=source_frame_index, frame_positions=[], frame_detections=[])

    registry = GlobalPlayerRegistry()
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        secondary_frames=[],
        sync=None,
        secondary_camera_id="camera-2",
    )
    return MultiViewJointRun(
        run_id="mvr_test",
        capture_take_id="take_test",
        reference_view_id="cam_1",
        clock=clock,
        runtimes={"cam_1": FakeRuntime("cam_1"), "cam_2": FakeRuntime("cam_2")},
        registry=registry,
        associator=GlobalPlayerAssociator(registry),
        guidance_generator=GuidanceGenerator(CrossViewGuidancePolicy()),
        orientations={"cam_1": CourtOrientation.identity, "cam_2": CourtOrientation.identity},
        inverse_homography=np.eye(3),
        frame_width=64,
        frame_height=48,
        debug_trace_enabled=debug_trace_enabled,
    )


def test_joint_run_trace_is_opt_in_and_preserves_unavailable_status():
    disabled = _make_joint_run(debug_trace_enabled=False).run(reference_frame_count=1, reference_fps=30.0)
    assert disabled.debug_trace is None

    enabled = _make_joint_run(debug_trace_enabled=True).run(reference_frame_count=1, reference_fps=30.0)
    assert enabled.debug_trace is not None
    tick = enabled.debug_trace["ticks"][0]
    assert tick["views"]["cam_2"]["status"] == "unavailable_no_sync"
    assert tick["views"]["cam_2"]["observation_status"] == "unavailable"
    assert tick["recovery"] == {}


def _write_video(path, colors):
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5.0, (64, 48))
    assert writer.isOpened()
    for color in colors:
        writer.write(np.full((48, 64, 3), color, dtype=np.uint8))
    writer.release()


def test_renderer_uses_trace_frame_decisions_and_reports_zero_opportunity(tmp_path):
    videos = {"cam_1": tmp_path / "cam1.mp4", "cam_2": tmp_path / "cam2.mp4"}
    _write_video(videos["cam_1"], [(0, 0, 220), (0, 220, 0), (220, 0, 0)])
    _write_video(videos["cam_2"], [(0, 220, 220), (220, 220, 0), (220, 0, 220)])
    trace_path = tmp_path / "trace.json"
    trace = _trace(tick_count=2)
    write_joint_debug_trace(trace_path, trace)
    trajectory = write_fused_v2(
        run_id="mvr_debug", capture_take_id="take_debug", reference_view_id="cam_1", samples=[]
    )
    trajectory_path = tmp_path / "trajectory.json"
    trajectory_path.write_text(json.dumps(trajectory), encoding="utf-8")
    diagnostics = {"recovery_funnel": {key: 0 for key in ("recovery_opportunity_count", "guidance_generated_count", "guided_roi_invocation_count", "guided_recovery_success_count", "base_recovered_count")}}
    diagnostics_path = tmp_path / "diagnostics.json"
    diagnostics_path.write_text(json.dumps(diagnostics), encoding="utf-8")
    canonical_path = tmp_path / "canonical.json"
    canonical_path.write_text(json.dumps(CanonicalCourtFrameDefinition.create("take_debug", "A", "B").to_dict()), encoding="utf-8")
    mapping_path = tmp_path / "mapping.json"
    mapping_path.write_text(json.dumps({"schema_version": "dual_camera_sync_calibration.v1"}), encoding="utf-8")
    output_path = tmp_path / "debug.mp4"
    summary_path = tmp_path / "summary.json"

    summary = render_joint_debug_artifacts(
        JointDebugRenderInputs(
            video_paths=videos,
            trace_path=trace_path,
            trajectory_path=trajectory_path,
            diagnostics_path=diagnostics_path,
            canonical_frame_path=canonical_path,
            timing_mapping_path=mapping_path,
            output_video_path=output_path,
            summary_path=summary_path,
            fps=5.0,
        )
    )
    assert summary["rendered_tick_count"] == 2
    assert summary["natural_recovery_opportunity_zero"] is True
    assert output_path.is_file()
    assert summary_path.is_file()
    capture = cv2.VideoCapture(str(output_path))
    assert capture.isOpened()
    assert int(capture.get(cv2.CAP_PROP_FRAME_WIDTH)) == 1280
    assert int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT)) == 620
    capture.release()

    trajectory_before = trajectory_path.read_text(encoding="utf-8")
    output_path.unlink()
    summary_path.unlink()
    assert trajectory_path.read_text(encoding="utf-8") == trajectory_before


def test_renderer_reports_specific_missing_input_and_never_falls_back(tmp_path):
    with pytest.raises(JointDebugRenderError, match="missing input trace_path"):
        render_joint_debug_artifacts(
            JointDebugRenderInputs(
                video_paths={"cam_1": "missing-a.mp4", "cam_2": "missing-b.mp4"},
                trace_path=tmp_path / "missing-trace.json",
                trajectory_path=tmp_path / "trajectory.json",
                diagnostics_path=tmp_path / "diagnostics.json",
                canonical_frame_path=tmp_path / "canonical.json",
                timing_mapping_path=tmp_path / "mapping.json",
                output_video_path=tmp_path / "debug.mp4",
                summary_path=tmp_path / "summary.json",
            )
        )
