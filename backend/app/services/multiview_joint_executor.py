"""MultiViewJointExecutor —— joint_tracking_v2 执行体(design D10)。

Parent 被 claim 后:
    先持久化 `jointRunId` → 再打开视频/模型
    → 同步解码两路视频 + 双 view tracking(MultiViewJointRun)
    → compose_joint_result(GlobalPlayer 标签)→ 落盘 result.json

长任务语义:每 tick cancellation、进度、capture finally release。
失败:非 reference 视角降级 → joint_degraded(由 run 内部处理);reference 失败 → 抛错(failed)。
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from collections.abc import Mapping
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.analysis import AnalysisJobSummary, build_match_context
from app.schemas.pipeline import PipelineStageResult
from app.services.analysis_executor_dispatch import _resolve_analysis_dir
from app.services.analysis_window import resolve_analysis_window
from app.services.frame_timing_provider import FrameTimingProvider
from app.services.calibration_service import CalibrationService
from app.services.multiview_result_composer import MultiViewResultComposer
from app.services.storage_service import StorageService
from app.services.multiview_observability import build_recovery_episode_projection
from app.services.joint_debug_renderer import JointDebugRenderInputs, render_joint_debug_artifacts
from app.services.video_service import VideoService
from app.vision.court_view import compute_expanded_detection_roi
from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
from app.vision.multiview.association_global import GlobalPlayerAssociator
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.court_frame import load_canonical_court_frame
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.multiview.guidance import (
    CrossViewGuidancePolicy,
    GuidanceGenerator,
    invert_homography,
)
from app.vision.multiview.fusion_run import default_run_output_dir
from app.vision.multiview.joint_types import JointViewInput
from app.vision.multiview.joint_view_runtime import JointViewRuntime
from app.vision.multiview.multiview_joint_run import MultiViewJointRun
from app.vision.multiview.offline_refinement import (
    RecoveredViewObservation,
    RefinementConfigSnapshot,
    RefinementViewContext,
)
from app.vision.multiview.recovery_config import P1OnlineRecoveryConfig
from app.vision.multiview.sync import load_sync_calibration
from app.vision.multiview.sync import resolve_sync_authority
from app.vision.multiview.artifact import evidence_summary_from_artifact
from app.vision.multiview.debug_trace import (
    JOINT_DEBUG_MANIFEST_FILENAME,
    JOINT_DEBUG_TRACE_FILENAME,
    build_joint_debug_manifest,
    write_joint_debug_trace,
)
from app.vision.player_tracking_engine.person_detector import EmptyPersonDetector, PersonDetector
from app.vision.player_tracking_engine.view_tracking_session import (
    build_view_tracking_config,
    build_view_tracking_session,
)

logger = logging.getLogger(__name__)


def _recovered_to_dict(r: RecoveredViewObservation) -> dict[str, object]:
    """RecoveredViewObservation → recovered_view_observations.v1 元素。"""
    return {
        "view_id": r.view_id,
        "take_timestamp_ms": r.take_timestamp_ms,
        "source_frame_index": r.source_frame_index,
        "canonical_x_ft": r.canonical_x_ft,
        "canonical_y_ft": r.canonical_y_ft,
        "bbox": r.bbox,
        "confidence": r.confidence,
        "detection_origin": r.detection_origin,
        "global_player_id": r.global_player_id,
        "canonical_tick": r.canonical_tick,
        "source_timestamp_ms": r.source_timestamp_ms,
        "mapped_take_timestamp_ms": r.mapped_take_timestamp_ms,
        "selection_error_ms": r.selection_error_ms,
        "timing_authority": r.timing_authority,
        "sync_quality": r.sync_quality,
        "target_view_timing": {
            "source_timestamp_ms": r.source_timestamp_ms,
            "mapped_take_timestamp_ms": r.mapped_take_timestamp_ms,
            "selection_error_ms": r.selection_error_ms,
            "timing_authority": r.timing_authority,
            "sync_quality": r.sync_quality,
        },
        "donor_view": r.donor_view,
        "donor_source_frame_index": r.donor_source_frame_index,
        "donor_quality": r.donor_quality,
        "expected_global_position": list(r.expected_global_position) if r.expected_global_position else None,
        "residual_ft": r.residual_ft,
    }


def _with_samples(out, f1_trajectory: dict[str, object]):
    """构造一个 compose 消费的 F1 output(用 F1 trajectory + normalized samples)。"""
    from types import SimpleNamespace

    from app.vision.multiview.joint_artifact import load_fused_trajectory

    normalized = load_fused_trajectory(f1_trajectory)
    return SimpleNamespace(
        trajectory=f1_trajectory,
        normalized=normalized,
        diagnostics=out.diagnostics,
        debug_trace=getattr(out, "debug_trace", None),
    )


def _publish_refinement_artifacts(
    *,
    storage: StorageService,
    run_dir,
    out,
    outcome,
    run_id: str,
    capture_take_id: str,
    reference_view_id: str,
    authoritative_run: bool,
    snapshot_artifact: str | None,
):
    """Publish post-snapshot F1 artifacts in the fixed order and return compose input.

    F0 and its refinement snapshot are written by the caller before recovery
    starts. The parent manifest is intentionally not written here. The caller
    owns that last publication step so a mid-flight write failure can fall back
    to F0 without exposing a partial refinement manifest.
    """
    from app.vision.multiview.joint_artifact import (
        build_refinement_manifest,
        write_fused_v2,
        write_recovered_observations,
        write_refinement_diagnostics,
    )

    f0_artifact = "fused_player_trajectory.f0.v2.json"

    refinement = build_refinement_manifest(
        status=outcome.status,
        final_source=outcome.final_source,
        first_pass_artifact=f0_artifact,
        recovered_artifact="recovered_view_observations.v1.json" if outcome.recovered else None,
        refined_artifact="fused_player_trajectory.f1.v2.json"
        if outcome.final_source == "refined_f1" else None,
        f0_snapshot_artifact=snapshot_artifact,
        diagnostics_artifact="refinement_diagnostics.json",
        reason=outcome.reason,
    )
    compose_output = out
    if outcome.recovered:
        storage.write_json_atomic(
            run_dir / "recovered_view_observations.v1.json",
            write_recovered_observations([_recovered_to_dict(item) for item in outcome.recovered]),
        )
    if outcome.candidate_samples:
        f1_trajectory = write_fused_v2(
            run_id=run_id,
            capture_take_id=capture_take_id,
            reference_view_id=reference_view_id,
            samples=outcome.candidate_samples,
            authoritative_run=authoritative_run,
        )
        storage.write_json_atomic(run_dir / "fused_player_trajectory.f1.v2.json", f1_trajectory)
        if outcome.final_source == "refined_f1":
            compose_output = _with_samples(out, f1_trajectory)
    storage.write_json_atomic(
        run_dir / "refinement_diagnostics.json",
        write_refinement_diagnostics(
            status=outcome.status,
            final_source=outcome.final_source,
            diagnostics=outcome.diagnostics,
            reason=outcome.reason,
        ),
    )
    return refinement, compose_output


def _write_failed_refinement_fallback(
    *,
    storage: StorageService,
    run_dir,
    f0_snapshot_present: bool,
    reason: str,
):
    """Write diagnostics for an execution failure while keeping F0 final."""
    from app.vision.multiview.joint_artifact import build_refinement_manifest, write_refinement_diagnostics

    refinement = build_refinement_manifest(
        status="failed_fallback",
        final_source="first_pass_f0",
        first_pass_artifact="fused_player_trajectory.f0.v2.json",
        f0_snapshot_artifact=("f0_refinement_snapshot.v1.json" if f0_snapshot_present else None),
        diagnostics_artifact="refinement_diagnostics.json",
        reason=reason,
    )
    storage.write_json_atomic(
        run_dir / "refinement_diagnostics.json",
        write_refinement_diagnostics(
            status="failed_fallback",
            final_source="first_pass_f0",
            reason=reason,
        ),
    )
    return refinement


def _deserialize_joint_view_input(payload: Mapping[str, object]) -> JointViewInput:
    """Normalize persisted API camelCase input to the executor's snake_case type."""
    return JointViewInput(
        camera_slot=str(payload.get("camera_slot") or payload.get("cameraSlot") or ""),
        capture_track_id=str(payload.get("capture_track_id") or payload.get("captureTrackId") or ""),
        camera_id=str(payload.get("camera_id") or payload.get("cameraId") or ""),
        video_id=str(payload.get("video_id") or payload.get("videoId") or ""),
        calibration_id=str(payload.get("calibration_id") or payload.get("calibrationId") or ""),
        court_orientation=payload.get("court_orientation") or payload.get("courtOrientation"),
    )


class MultiViewJointExecutor:
    """joint_tracking_v2 执行体:同步解码 + MultiViewJointRun + joint compose。"""

    def __init__(self, store, pipeline_factory) -> None:
        self.store = store
        self.pipeline_factory = pipeline_factory

    def execute(self, job: AnalysisJobSummary, token, progress_callback):
        parent = job
        storage = StorageService()
        settings = get_settings()
        capture_take_id = parent.metadata.capture_take_id
        captures: dict[str, object] = {}
        try:
            # 1) 幂等持久化 jointRunId(先于打开视频/模型),失败重试复用
            run_id = parent.jointRunId or f"mvr_{uuid4().hex[:12]}"
            if not parent.jointRunId:
                self.store.update(parent.id, jointRunId=run_id)
            self.store.update(parent.id, orchestrationStatus="joint_tracking")

            view_inputs = [
                _deserialize_joint_view_input(dict(item))
                for item in (parent.jointViewInputs or [])
            ]
            if len(view_inputs) < 2:
                raise RuntimeError(f"joint parent {parent.id} requires >=2 jointViewInputs")
            reference_view_id = parent.referenceViewId or view_inputs[0].camera_slot
            reference_input = next(item for item in view_inputs if item.camera_slot == reference_view_id)
            secondary_input = next(item for item in view_inputs if item.camera_slot != reference_view_id)
            reference_camera_id = reference_input.camera_id or reference_input.camera_slot
            secondary_camera_id = secondary_input.camera_id or secondary_input.camera_slot

            # 2) 解析视频 + 标定
            video_svc = VideoService()
            cal_svc = CalibrationService()
            videos: dict[str, object] = {}
            calibrations: dict[str, object] = {}
            for vi in view_inputs:
                video = video_svc.get_video(vi.video_id) if vi.video_id else None
                if video is None:
                    raise RuntimeError(f"joint view {vi.camera_slot} video unavailable")
                videos[vi.camera_slot] = video
                calibrations[vi.camera_slot] = (
                    cal_svc.get_calibration(vi.calibration_id) if vi.calibration_id else None
                )

            import cv2  # noqa: PLC0415

            ref_video = videos[reference_view_id]
            probe = cv2.VideoCapture(ref_video.path)
            fps = float(probe.get(cv2.CAP_PROP_FPS) or 30.0)
            width = int(probe.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            height = int(probe.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            frame_count = int(probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            probe.release()
            reference_timing_provider = FrameTimingProvider.from_media(
                ref_video.path,
                frame_count=frame_count,
                fps=fps,
                allow_nominal_fallback=False,
            )
            window = resolve_analysis_window(
                source_duration_ms=int(reference_timing_provider.duration_seconds * 1000),
                source_frame_count=frame_count,
                fps=fps,
                clip_start_ms=parent.clipStartMs,
                clip_end_ms=parent.clipEndMs,
                pre_roll_ms=getattr(settings, "pre_roll_ms", 1500),
                post_roll_ms=getattr(settings, "post_roll_ms", 500),
                timing_provider=reference_timing_provider,
            )
            window_metadata = window.metadata()

            match_ctx = build_match_context(
                parent.metadata.matchFormat if hasattr(parent.metadata, "matchFormat") else None
            )
            config = build_view_tracking_config(
                settings, match_ctx, fps=fps, frame_stride=parent.frameStride,
                frame_width=width, frame_height=height,
            )

            # 3) 每 view:session + runtime(cam_1 full / cam_2 perception)
            from app.services.dual_camera_sync import FrameTiming  # noqa: PLC0415

            runtimes: dict[str, JointViewRuntime] = {}
            cam2_frames: list[FrameTiming] = []
            timing_providers: dict[str, FrameTimingProvider] = {reference_view_id: reference_timing_provider}
            view_fps: dict[str, float] = {reference_view_id: fps}
            secondary_view_id = secondary_input.camera_slot
            orientations: dict[str, CourtOrientation] = {}
            detectors_by_view: dict[str, object] = {}
            homographies_by_view: dict[str, list[list[float]]] = {}
            view_geometry: dict[str, dict[str, object]] = {}
            recovery_config = P1OnlineRecoveryConfig()
            reference_homography = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
            for vi in view_inputs:
                cap = cv2.VideoCapture(videos[vi.camera_slot].path)
                captures[vi.camera_slot] = cap
                view_fps_value = float(cap.get(cv2.CAP_PROP_FPS) or fps)
                view_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or width)
                view_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or height)
                calibration = calibrations[vi.camera_slot]
                homography = (
                    calibration.homography.values
                    if calibration is not None and getattr(calibration, "homography", None) is not None
                    else None
                )
                roi = compute_expanded_detection_roi(None, view_width, view_height)
                detector = (
                    PersonDetector(
                        model_path=settings.default_detector_model,
                        conf_threshold=settings.detector_confidence,
                        device=settings.detector_device,
                    )
                    if settings.enable_model_inference
                    else EmptyPersonDetector()
                )
                session_config = replace(
                    config,
                    fps=view_fps_value,
                    frame_width=view_width,
                    frame_height=view_height,
                    eligibility_policy="lock_only",
                )
                session = build_view_tracking_session(
                    detector=detector,
                    homography=homography or reference_homography,
                    roi_artifact=roi,
                    config=session_config,
                )
                scope = "full" if vi.camera_slot == reference_view_id else "perception"
                runtimes[vi.camera_slot] = JointViewRuntime(
                    view_input=vi, capture=cap, fps=view_fps_value, frame_size=(view_width, view_height),
                    homography=homography or reference_homography, roi_artifact=roi, tracking_session=session, scope=scope,
                )
                orientations[vi.camera_slot] = (
                    CourtOrientation(vi.court_orientation) if vi.court_orientation else CourtOrientation.identity
                )
                view_geometry[vi.camera_slot] = {
                    "orientation": orientations[vi.camera_slot],
                    "inverse_homography": invert_homography(homography) if homography is not None else None,
                    "frame_width": view_width,
                    "frame_height": view_height,
                    "available": homography is not None and bool(vi.court_orientation),
                }
                detectors_by_view[vi.camera_slot] = detector
                homographies_by_view[vi.camera_slot] = homography or reference_homography
                if vi.camera_slot == reference_view_id:
                    reference_homography = homography or reference_homography
                else:
                    sec_fps = view_fps_value
                    sec_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                    timing_provider = FrameTimingProvider.from_media(
                        videos[vi.camera_slot].path,
                        frame_count=sec_count,
                        fps=sec_fps,
                        allow_nominal_fallback=False,
                    )
                    view_fps[vi.camera_slot] = sec_fps
                    runtimes[vi.camera_slot].fps = sec_fps
                    timing_providers[vi.camera_slot] = timing_provider
                    # SyncCalibration maps the reference take clock to the secondary
                    # camera's own normalized clock; do not subtract the reference
                    # camera's PTS from the secondary stream here.
                    cam2_frames = list(timing_provider.frames_with_origin())
                    secondary_view_id = vi.camera_slot

            # 4) clock + registry + associator + guidance
            analysis_dir = _resolve_analysis_dir(storage, parent, capture_take_id)
            take_dir = analysis_dir.parent if analysis_dir is not None else None
            sync = load_sync_calibration(take_dir) if take_dir is not None else None
            resolution = resolve_sync_authority(
                sync,
                reference_camera_id=reference_camera_id,
                secondary_camera_id=secondary_camera_id,
                timing_authority_by_view={
                    reference_camera_id: reference_timing_provider.provenance.authority,
                    secondary_camera_id: timing_providers[secondary_view_id].provenance.authority,
                },
                require_authoritative_calibration=bool(getattr(parent, "debugTraceEnabled", False)),
            )
            if getattr(parent, "debugTraceEnabled", False) and not resolution.authoritative_joint_eligible:
                raise RuntimeError(
                    "authoritative visual acceptance blocked: "
                    + (resolution.reason or "sync authority unavailable")
                )
            authority_reason = (
                resolution.reason if resolution.execution_mode != "joint_authoritative" else None
            )
            clock_sync = sync if resolution.structural_valid else None
            clock = CanonicalAnalysisClock(
                reference_view_id=reference_view_id, secondary_view_id=secondary_view_id,
                secondary_frames=cam2_frames, sync=clock_sync, secondary_camera_id=secondary_camera_id,
                reference_timing_provider=reference_timing_provider,
                secondary_timing_provider=timing_providers[secondary_view_id],
                reference_timing_authority=reference_timing_provider.provenance.authority,
                secondary_timing_authority=timing_providers[secondary_view_id].provenance.authority,
            )
            registry = GlobalPlayerRegistry(expected_player_count=match_ctx.expected_player_count)
            associator = GlobalPlayerAssociator(registry, max_association_distance_ft=3.0)
            gen = GuidanceGenerator(CrossViewGuidancePolicy())
            run = MultiViewJointRun(
                run_id=run_id, capture_take_id=capture_take_id, reference_view_id=reference_view_id,
                clock=clock, runtimes=runtimes, registry=registry, associator=associator,
                guidance_generator=gen, orientations=orientations,
                inverse_homography=invert_homography(reference_homography),
                frame_width=width, frame_height=height,
                view_geometry=view_geometry,
                recovery_config=recovery_config,
                canonical_frame_ref=load_canonical_court_frame(take_dir) if take_dir is not None else None,
                reference_timing_provider=reference_timing_provider,
                timing_authority_by_view={
                    reference_view_id: reference_timing_provider.provenance.authority,
                    secondary_view_id: timing_providers[secondary_view_id].provenance.authority,
                },
                sync_quality=resolution.sync_quality,
                execution_mode=resolution.execution_mode,
                authoritative_joint_eligible=resolution.authoritative_joint_eligible,
                debug_trace_enabled=bool(getattr(parent, "debugTraceEnabled", False)),
            )

            # 5) 长任务执行(每 tick cancellation + 进度)
            def on_progress(done: int, total: int) -> None:
                if progress_callback is None:
                    return
                now = datetime.now(UTC).isoformat()
                progress_callback(
                    PipelineStageResult(
                        id="multiview-joint", label="双摄协同跟踪", status="active",
                        detail=f"已处理 {done}/{total} 个 canonical tick",
                        started_at=now, finished_at=now,
                        progress=min(95, max(5, int(done / max(1, total) * 95))),
                        public_message=f"双摄协同跟踪 {done}/{total}",
                    )
                )

            out = run.run(
                reference_fps=fps, frame_stride=parent.frameStride,
                reference_frame_start=window.decoded_start_frame,
                reference_frame_end=window.decoded_end_frame,
                metric_frame_start=window.requested_start_frame if window.enabled else 0,
                metric_frame_end=window.requested_end_frame if window.enabled else frame_count,
                analysis_window=window_metadata,
                cancellation_token=token, progress_callback=on_progress,
            )
            out.diagnostics.update(evidence_summary_from_artifact(out.trajectory))
            out.diagnostics["timing_provenance"] = {
                slot: provider.metadata() for slot, provider in timing_providers.items()
            }
            out.diagnostics["authority_reason"] = authority_reason
            out.diagnostics["authority_reason_codes"] = list(resolution.reason_codes)
            out.diagnostics["structural_valid"] = resolution.structural_valid
            out.diagnostics["timing_authority_by_view"] = {
                slot: provider.provenance.authority for slot, provider in timing_providers.items()
            }
            out.diagnostics["sync_quality"] = resolution.sync_quality
            out.diagnostics["execution_mode"] = resolution.execution_mode
            out.diagnostics["authoritative_joint_eligible"] = resolution.authoritative_joint_eligible
            out.diagnostics["requested_mode"] = parent.executionMode
            # 参考视角源帧尺寸（composer 生成 tracking_overlay / heatmaps 需要）
            out.diagnostics["frame_size"] = {"width": width, "height": height}

            run_dir = default_run_output_dir(analysis_dir, run_id) if analysis_dir is not None else None
            if getattr(parent, "debugTraceEnabled", False):
                if out.debug_trace is None:
                    raise RuntimeError("debug trace was enabled but joint run produced no trace")
                if run_dir is None:
                    raise RuntimeError("debug trace requires a persistent JointRun diagnostic directory")
                run_dir.mkdir(parents=True, exist_ok=True)
                trace_path = write_joint_debug_trace(run_dir / JOINT_DEBUG_TRACE_FILENAME, out.debug_trace)
                manifest = build_joint_debug_manifest(
                    run_id=run_id,
                    capture_take_id=capture_take_id,
                    config={
                        "debug_trace_enabled": True,
                        "requested_mode": parent.executionMode,
                        "execution_mode": resolution.execution_mode,
                        "frame_stride": parent.frameStride,
                        "p1_online_recovery_config": recovery_config.snapshot(),
                    },
                )
                manifest_path = storage.write_json_atomic(run_dir / JOINT_DEBUG_MANIFEST_FILENAME, manifest)
                out.diagnostics["joint_debug_trace"] = {
                    "schema_version": out.debug_trace["schema_version"],
                    "path": str(trace_path),
                    "manifest_path": str(manifest_path),
                }
            recovery_evidence = getattr(out, "recovery_evidence", None) or []
            if recovery_evidence:
                storage.write_json_atomic(
                    storage.recovery_episodes_json_path(parent.id, run_id),
                    build_recovery_episode_projection(
                        {
                            "run_id": run_id,
                            "capture_take_id": capture_take_id,
                            "ticks": recovery_evidence,
                        }
                    ),
                )

            # ---- F1 离线精修(只读 immutable F0;最后才更新 manifest)----
            from app.vision.multiview.offline_refinement import run_offline_refinement
            from app.vision.multiview.joint_artifact import (
                build_refinement_manifest,
                write_f0_refinement_snapshot,
            )

            f0_artifact = "fused_player_trajectory.f0.v2.json"
            compose_output = out  # 默认用 F0
            refinement = build_refinement_manifest(
                status="skipped_no_windows",
                final_source="first_pass_f0",
                first_pass_artifact=f0_artifact,
                reason=None,
            )
            if run_dir is not None:
                try:
                    run_dir.mkdir(parents=True, exist_ok=True)
                    # F0 is published before F1 starts. It is never overwritten.
                    storage.write_json_atomic(run_dir / f0_artifact, out.trajectory)
                    snapshot_artifact = "f0_refinement_snapshot.v1.json"
                    if out.f0_snapshot is not None:
                        storage.write_json_atomic(
                            run_dir / snapshot_artifact,
                            write_f0_refinement_snapshot(out.f0_snapshot),
                        )
                    else:
                        snapshot_artifact = None

                    contexts = {}
                    for view_id in runtimes:
                        geometry = view_geometry.get(view_id, {})
                        # F1 never borrows reference geometry for a target view.
                        # An incomplete calibration is a deterministic skip.
                        if not geometry.get("available") or geometry.get("inverse_homography") is None:
                            continue
                        contexts[view_id] = RefinementViewContext(
                            view_id=view_id,
                            frame_provider=runtimes[view_id].get_frame,
                            detector=detectors_by_view[view_id],
                            homography=homographies_by_view[view_id],
                            inverse_homography=geometry["inverse_homography"],
                            orientation=orientations[view_id],
                            frame_width=int(geometry.get("frame_width") or runtimes[view_id].frame_size[0]),
                            frame_height=int(geometry.get("frame_height") or runtimes[view_id].frame_size[1]),
                            timing_metadata=timing_providers.get(view_id, reference_timing_provider).metadata(),
                        )
                    refinement_outcome = run_offline_refinement(
                        snapshot=out.f0_snapshot,
                        f0_trace=out.f0_trace,
                        f0_source_frames=out.f0_source_frames,
                        f0_global_positions=out.f0_global_positions,
                        view_contexts=contexts,
                        f0_samples=out.normalized.samples,
                        config=RefinementConfigSnapshot.from_online(recovery_config),
                        reference_view_id=reference_view_id,
                        secondary_view_id=secondary_view_id,
                        sync_quality=resolution.sync_quality,
                    )
                    refinement, compose_output = _publish_refinement_artifacts(
                        storage=storage,
                        run_dir=run_dir,
                        out=out,
                        outcome=refinement_outcome,
                        run_id=run_id,
                        capture_take_id=capture_take_id,
                        reference_view_id=reference_view_id,
                        authoritative_run=resolution.authoritative_joint_eligible,
                        snapshot_artifact=snapshot_artifact,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("offline refinement failed: %s", exc)
                    refinement = _write_failed_refinement_fallback(
                        storage=storage,
                        run_dir=run_dir,
                        f0_snapshot_present=out.f0_snapshot is not None,
                        reason=str(exc),
                    )

            # 6) compose + 落盘
            self.store.update(parent.id, orchestrationStatus="composing")
            composer = MultiViewResultComposer(storage)
            result = composer.compose_joint_result(
                job=parent, joint_output=compose_output, reference_view_id=reference_view_id,
                message=(
                    "双摄协同分析完成(joint_tracking_v2)。"
                    if out.diagnostics.get("effective_mode") == "multiview_fused"
                    else "双摄分析完成，但副摄证据不可用或覆盖不足，结果按降级模式展示。"
                ), refinement=refinement,
            )
            result = storage.publicize_pipeline_result(result)
            storage.write_json(storage.output_json_path(parent.id), result.model_dump(mode="json"))

            # Debug Replay is rendered only after the authoritative result and
            # refinement artifacts are published. Rendering consumes persisted
            # trace evidence and must never change the analysis conclusion.
            if getattr(parent, "debugTraceEnabled", False) and run_dir is not None:
                try:
                    trace_path = run_dir / JOINT_DEBUG_TRACE_FILENAME
                    trajectory_path = run_dir / "fused_player_trajectory.f1.v2.json"
                    if not trajectory_path.is_file():
                        trajectory_path = run_dir / "fused_player_trajectory.f0.v2.json"
                    render_joint_debug_artifacts(
                        JointDebugRenderInputs(
                            video_paths={view_id: video.path for view_id, video in videos.items()},
                            trace_path=trace_path,
                            trajectory_path=trajectory_path,
                            diagnostics_path=storage.fusion_diagnostics_json_path(parent.id),
                            canonical_frame_path=take_dir / "metadata" / "canonical_court_frame.json",
                            timing_mapping_path=take_dir / "timeline" / "sync_calibration.json",
                            output_video_path=storage.canonical_debug_video_path(parent.id, run_id),
                            summary_path=storage.joint_debug_summary_json_path(parent.id, run_id),
                            fps=max(1.0, fps / max(1, parent.frameStride)),
                        )
                    )
                except Exception as exc:  # noqa: BLE001 - debug is opt-in and non-blocking
                    logger.warning("joint debug replay render failed: %s", exc)
            self.store.update(parent.id, orchestrationStatus="completed")
            logger.info(
                "joint run 完成 run=%s globals=%s degraded=%s",
                run_id, out.diagnostics.get("global_player_count"), out.diagnostics.get("degraded"),
            )
            return result
        finally:
            for cap in captures.values():
                try:
                    cap.release()  # type: ignore[attr-defined]
                except Exception:  # noqa: BLE001
                    pass
