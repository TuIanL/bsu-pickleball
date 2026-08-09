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
from datetime import UTC, datetime
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.analysis import AnalysisJobSummary, build_match_context
from app.schemas.pipeline import PipelineStageResult
from app.services.analysis_executor_dispatch import _resolve_analysis_dir
from app.services.calibration_service import CalibrationService
from app.services.multiview_result_composer import MultiViewResultComposer
from app.services.storage_service import StorageService
from app.services.video_service import VideoService
from app.vision.court_view import compute_expanded_detection_roi
from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
from app.vision.multiview.association_global import GlobalPlayerAssociator
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.multiview.guidance import (
    CrossViewGuidancePolicy,
    GuidanceGenerator,
    invert_homography,
)
from app.vision.multiview.joint_types import JointViewInput
from app.vision.multiview.joint_view_runtime import JointViewRuntime
from app.vision.multiview.multiview_joint_run import MultiViewJointRun
from app.vision.multiview.sync import load_sync_calibration
from app.vision.player_tracking_engine.person_detector import EmptyPersonDetector, PersonDetector
from app.vision.player_tracking_engine.view_tracking_session import (
    build_view_tracking_config,
    build_view_tracking_session,
)

logger = logging.getLogger(__name__)


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

            view_inputs = [JointViewInput(**dict(item)) for item in (parent.jointViewInputs or [])]
            if len(view_inputs) < 2:
                raise RuntimeError(f"joint parent {parent.id} requires >=2 jointViewInputs")
            reference_view_id = parent.referenceViewId or view_inputs[0].camera_slot

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
            secondary_camera_id = reference_view_id
            orientations: dict[str, CourtOrientation] = {}
            detectors_by_view: dict[str, object] = {}
            homographies_by_view: dict[str, list[list[float]]] = {}
            reference_homography = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]
            for vi in view_inputs:
                cap = cv2.VideoCapture(videos[vi.camera_slot].path)
                captures[vi.camera_slot] = cap
                calibration = calibrations[vi.camera_slot]
                homography = (
                    calibration.homography.values
                    if calibration is not None and getattr(calibration, "homography", None) is not None
                    else reference_homography
                )
                roi = compute_expanded_detection_roi(None, width, height)
                detector = (
                    PersonDetector(
                        model_path=settings.default_detector_model,
                        conf_threshold=settings.detector_confidence,
                        device=settings.detector_device,
                    )
                    if settings.enable_model_inference
                    else EmptyPersonDetector()
                )
                session = build_view_tracking_session(
                    detector=detector, homography=homography, roi_artifact=roi, config=config,
                )
                scope = "full" if vi.camera_slot == reference_view_id else "perception"
                runtimes[vi.camera_slot] = JointViewRuntime(
                    view_input=vi, capture=cap, fps=fps, frame_size=(width, height),
                    homography=homography, roi_artifact=roi, tracking_session=session, scope=scope,
                )
                orientations[vi.camera_slot] = (
                    CourtOrientation(vi.court_orientation) if vi.court_orientation else CourtOrientation.identity
                )
                detectors_by_view[vi.camera_slot] = detector
                homographies_by_view[vi.camera_slot] = homography
                if vi.camera_slot == reference_view_id:
                    reference_homography = homography
                else:
                    sec_fps = float(cap.get(cv2.CAP_PROP_FPS) or fps)
                    sec_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                    cam2_frames = [FrameTiming(i, i / sec_fps) for i in range(sec_count)]
                    secondary_camera_id = vi.camera_slot

            # 4) clock + registry + associator + guidance
            analysis_dir = _resolve_analysis_dir(storage, parent, capture_take_id)
            take_dir = analysis_dir.parent if analysis_dir is not None else None
            sync = load_sync_calibration(take_dir) if take_dir is not None else None
            clock = CanonicalAnalysisClock(
                reference_view_id=reference_view_id, secondary_view_id=secondary_camera_id,
                secondary_frames=cam2_frames, sync=sync, secondary_camera_id=secondary_camera_id,
            )
            registry = GlobalPlayerRegistry()
            associator = GlobalPlayerAssociator(registry, max_association_distance_ft=3.0)
            gen = GuidanceGenerator(CrossViewGuidancePolicy())
            run = MultiViewJointRun(
                run_id=run_id, capture_take_id=capture_take_id, reference_view_id=reference_view_id,
                clock=clock, runtimes=runtimes, registry=registry, associator=associator,
                guidance_generator=gen, orientations=orientations,
                inverse_homography=invert_homography(reference_homography),
                frame_width=width, frame_height=height,
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
                reference_frame_count=(frame_count // parent.frameStride) + 1,
                reference_fps=fps, frame_stride=parent.frameStride,
                cancellation_token=token, progress_callback=on_progress,
            )

            # ---- F1 离线精修(只读 F0;写 immutable F0 + recovered/F1 artifact + manifest)----
            from app.vision.multiview.offline_refinement import run_offline_refinement
            from app.vision.multiview.joint_artifact import build_refinement_manifest

            f0_artifact = "fused_player_trajectory.f0.v2.json"
            refinement = build_refinement_manifest(
                status="skipped_no_windows", final_source="first_pass_f0", first_pass_artifact=f0_artifact,
            )
            if out.f0_trace:
                try:
                    refinement_outcome = run_offline_refinement(
                        f0_trace=out.f0_trace,
                        f0_source_frames=out.f0_source_frames,
                        f0_global_positions=out.f0_global_positions,
                        frame_provider=lambda vid, idx: runtimes[vid].get_frame(idx) if vid in runtimes else None,
                        detector=detectors_by_view.get(secondary_camera_id),
                        homography=homographies_by_view.get(secondary_camera_id, reference_homography),
                        inverse_homography=invert_homography(reference_homography),
                        orientation_by_view=orientations,
                        frame_width=width, frame_height=height,
                    )
                    refinement = build_refinement_manifest(
                        status=refinement_outcome.status,
                        final_source=refinement_outcome.final_source,
                        first_pass_artifact=f0_artifact,
                        recovered_artifact="recovered_view_observations.v1.json" if refinement_outcome.recovered else None,
                        refined_artifact="fused_player_trajectory.f1.v2.json"
                        if refinement_outcome.final_source == "refined_f1" else None,
                        reason=refinement_outcome.reason,
                    )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("offline refinement failed: %s", exc)
                    refinement = build_refinement_manifest(
                        status="failed_fallback", final_source="first_pass_f0", first_pass_artifact=f0_artifact,
                    )

            # 6) compose + 落盘
            self.store.update(parent.id, orchestrationStatus="composing")
            composer = MultiViewResultComposer(storage)
            result = composer.compose_joint_result(
                job=parent, joint_output=out, reference_view_id=reference_view_id,
                message="双摄协同分析完成(joint_tracking_v2)。", refinement=refinement,
            )
            result = storage.publicize_pipeline_result(result)
            storage.write_json(storage.output_json_path(parent.id), result.model_dump(mode="json"))
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
