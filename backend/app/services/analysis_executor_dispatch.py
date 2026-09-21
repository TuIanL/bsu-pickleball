"""分析执行分发（analysis_executor_dispatch）—— 按 analysisKind 选择执行体。

对应 spec `analysis-job-executor-dispatch`：

- `AnalysisJobExecutor` Protocol：`execute(job, token, progress_callback) -> AnalysisPipelineResult`；
- `SingleViewAnalysisExecutor`：封装现有 `AnalysisPipeline.run()`（行为与改造前一致）；
- `MultiViewAnalysisExecutor`：读两路 child 产物 → 构建/复用 `MultiViewFusionRun`
  （`fusionRunId` 执行前持久化，保证重启/重试幂等）→ 融合 → `MultiViewResultComposer`；
- `resolve_executor`：第一版 registry 只含 SingleView / MultiView 两个执行体，
  不做插件发现/通用 factory/第三方扩展 API。

Worker 主循环只做 `resolve_executor(kind).execute(...)`，不按类型硬编码分支。
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from app.schemas.analysis import AnalysisJobCreate, AnalysisJobSummary, build_match_context
from app.schemas.pipeline import AnalysisPipelineResult, PipelineStageResult
from app.services.multiview_result_composer import MultiViewResultComposer, build_fallback_fused_artifact
from app.services.storage_service import StorageService
from app.vision.multiview.artifact import (
    FUSED_DIAGNOSTICS_FILENAME,
    FUSED_DIAGNOSTICS_SCHEMA_VERSION,
    FUSED_TRAJECTORY_FILENAME,
    FUSED_TRAJECTORY_SCHEMA_VERSION,
    build_fused_artifact,
    build_fusion_diagnostics,
    load_fused_artifact,
    write_fused_artifact,
    write_fusion_diagnostics,
)
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.court_frame import load_canonical_court_frame
from app.vision.multiview.fusion import FusionConfig
from app.vision.multiview.fusion_run import MultiViewFusionRun, default_run_output_dir
from app.vision.multiview.pipeline import run_fusion_pipeline
from app.vision.multiview.spike_adapter import SpikeAdapterError, load_view_observations
from app.vision.multiview.sync import (
    evaluate_sync_gate,
    load_sync_calibration,
    validate_sync_authority,
)
from app.vision.multiview.view_input import MultiViewViewInput
from app.vision.match_state import MatchStateSegmentationRuntime, SegmentationInput
from app.vision.match_state.media_sampler import RGBMediaSamplingConfig, iter_capture_take_media, sample_capture_take_media
from app.vision.match_state.package import load_production_package
from app.vision.match_state.package import ModelPackageError
from app.services.formal_segmentation_service import persist_segmentation_failure, persist_segmentation_result

logger = logging.getLogger(__name__)

# 融合时刻配对容差（independent of sync valid interval）。取约 1 帧 @30fps。
DEFAULT_MAX_PAIRING_ERROR_MS = 33.3

# 由 JobStore 解析出的任务摘要类型（避免强依赖 job_orchestration 造成循环导入）。
JobSummaryLike = AnalysisJobSummary


class AnalysisJobExecutor(Protocol):
    """分析执行体协议：Worker 不关心不同类型任务怎么跑，只按 kind 分发。"""

    def execute(
        self,
        job: AnalysisJobSummary,
        token: object,
        progress_callback: Callable[[object], None],
    ) -> AnalysisPipelineResult:
        ...


def _resolve_analysis_dir(
    storage: StorageService,
    job: AnalysisJobSummary,
    capture_take_id: str | None,
) -> Path | None:
    """解析 take 的分析产物根目录（`take_dir/analysis`）；不可用返回 None。"""
    root = storage.resolve_capture_job_root(job.id, capture_take_id)
    if root is None:
        return None
    return root.parent if root.parent.exists() else root.parent


def _load_bound_window_plan(storage: StorageService, job: AnalysisJobSummary) -> list[dict[str, object]] | None:
    """Load only the immutable plan referenced by a child/Parent job."""
    if not job.windowPlanHash or not job.segmentationRunId:
        return None
    owner_id = job.parentJobId or job.id
    path = storage.formal_segmentation_artifact_path(
        owner_id,
        getattr(job.metadata, "capture_take_id", None),
        create_root=False,
    )
    if not path.is_file():
        return None
    try:
        payload = storage.read_json(path)
    except Exception:
        return None
    plan = payload.get("window_plan") if isinstance(payload, dict) else None
    if (
        not isinstance(payload, dict)
        or payload.get("run_id") != job.segmentationRunId
        or not isinstance(plan, dict)
        or plan.get("run_id") != job.segmentationRunId
        or plan.get("plan_hash") != job.windowPlanHash
        or not isinstance(plan.get("windows"), list)
    ):
        return None
    windows = plan.get("windows")
    return [dict(item) for item in windows if isinstance(item, dict)] if isinstance(windows, list) else []


class SingleViewAnalysisExecutor:
    """封装现有 AnalysisPipeline.run()：行为与改造前一致。"""

    def __init__(
        self,
        store,
        pipeline_factory: Callable[..., object],
    ) -> None:
        self.store = store
        self.pipeline_factory = pipeline_factory

    def execute(
        self,
        job: AnalysisJobSummary,
        token,
        progress_callback: Callable[[object], None],
    ) -> AnalysisPipelineResult:
        from app.services.storage_service import StorageService

        payload = AnalysisJobCreate(
            metadata=job.metadata,
            videoId=job.videoId,
            calibrationId=job.calibrationId,
            frameStride=job.frameStride,
            sourceFps=job.sourceFps or job.metadata.sourceFps,
            priority=job.priority,
            clipStartMs=getattr(job, "clipStartMs", None),
            clipEndMs=getattr(job, "clipEndMs", None),
            useRallyContext=(getattr(job, "rallyContextMode", "legacy") == "new"),
        )
        if job.metadata.capture_take_id:
            StorageService.register_capture_job_from_take(job.id, job.metadata.capture_take_id)
        elif job.metadata.session_dir:
            StorageService.register_capture_job(job.id, job.metadata.session_dir)

        pipeline = self.pipeline_factory(
            analysis_options={
                "enable_model_inference": payload.enableModelInference,
                "enable_pose_inference": payload.enablePoseInference,
            }
        )
        match_context = build_match_context(
            job.metadata.matchFormat if hasattr(job.metadata, "matchFormat") else None
        )
        bound_plan = _load_bound_window_plan(StorageService(), job)
        if job.segmentationRunId and job.windowPlanHash and bound_plan is None:
            # Formal children are bound to an immutable artifact.  A missing,
            # corrupt, or mismatched plan must never silently widen analysis to
            # the full video or to a mutable legacy timeline.
            raise RuntimeError("formal segmentation window plan unavailable or hash mismatch")
        run_kwargs = {
            "job_id": job.id,
            "video_id": payload.videoId,
            "calibration_id": payload.calibrationId,
            "frame_stride": payload.frameStride,
            "source_fps": payload.sourceFps or payload.metadata.sourceFps,
            "court_view_match_threshold": payload.courtViewMatchThreshold,
            "match_context": match_context,
            "progress_callback": progress_callback,
            "cancellation_token": token,
            # A formal plan is an analysis-time gate, not a set of independent
            # clips: keep one continuous decode so tracker identity survives
            # rally boundaries.  Legacy jobs retain their explicit clip.
            "clip_start_ms": None if bound_plan is not None else payload.clipStartMs,
            "clip_end_ms": None if bound_plan is not None else payload.clipEndMs,
            "capture_take_id": job.metadata.capture_take_id,
            "analysis_window_plan": bound_plan,
        }
        signature = inspect.signature(pipeline.run)
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
        )
        if not accepts_kwargs:
            run_kwargs = {key: value for key, value in run_kwargs.items() if key in signature.parameters}
        return pipeline.run(**run_kwargs)


def _attach_source_rally_refs(result, capture_take_id: str, planning_job_id: str):
    """为 formal window 挂上源 rally 引用与 job-bound 上下文绑定，并重建窗口计划。

    只在唯一匹配时挂引用；歧义一律降级为 unavailable 并记录诊断。这些引用字段
    不参与 plan_hash 计算，所以重建后的 `plan_hash` 与 runtime 产出的完全一致，
    Parent 绑定的 `windowPlanHash` 不受影响。
    """
    from dataclasses import replace as dataclass_replace

    from app.services.analysis_rally_context_service import (
        attach_window_context_binding,
        context_payload,
        get_context_set,
    )
    from app.vision.match_state.artifact import AnalysisWindowPlan

    from app.database import get_session_factory

    db = get_session_factory()()
    try:
        context = context_payload(get_context_set(db, planning_job_id))
        enriched = attach_window_context_binding(
            db,
            capture_take_id=capture_take_id,
            segments=result.artifact.algorithm_segments,
            context=context,
        )
    except Exception:
        logger.exception("Unable to attach rally-context binding for %s", capture_take_id)
        return result
    finally:
        db.close()

    plan = AnalysisWindowPlan.create(result.artifact.run_id, enriched)
    artifact = dataclass_replace(result.artifact, algorithm_segments=tuple(enriched), window_plan=plan)
    return dataclass_replace(result, artifact=artifact)


class SegmentationPrerequisiteExecutor:
    """Parent-owned formal segmentation prerequisite.

    Media decoding/model adapters are deliberately injected at the runtime
    boundary.  If a deployment has not installed the signed package or a
    synchronized sample sidecar, this executor returns a stable failure and
    never starts a visual child.
    """

    def __init__(self, store) -> None:
        self.store = store

    def execute(self, job: AnalysisJobSummary, token, progress_callback: Callable[[object], None]) -> AnalysisPipelineResult:
        from datetime import UTC, datetime
        from app.core.config import get_settings
        from app.schemas.metrics import PerformanceMetrics
        from app.schemas.pipeline import AnalysisArtifacts

        now = datetime.now(UTC)
        storage = StorageService()
        progress_callback(PipelineStageResult(id="segment", label="回合自动切分", status="active", detail="正在自动切分比赛回合", progress=10, started_at=now, public_message="正在自动切分比赛回合"))
        settings = get_settings()
        # Formal production flow always samples the authoritative CaptureTake
        # media.  Candidate timelines/JSON replay sidecars are intentionally
        # not consulted here; they remain an isolated QA concern.
        # Keep CaptureTake RGB frames as a one-shot stream.  The runtime
        # performs inference in small batches and only retains probabilities.
        sample_factory = lambda: _iter_capture_take_media_samples(
            job,
            package_dir=str(settings.match_state_segmentation_package_dir),
        )
        source = SegmentationInput(
            capture_take_id=job.metadata.capture_take_id or "",
            planning_job_id=job.parentJobId or job.id,
            samples=(),
            sample_factory=sample_factory,
            input_fingerprint=job.inputSignature or job.id,
            sync_calibration_revision=job.syncCalibrationRevision,
            timing_authority="source_pts",
            coverage=1.0,
        )
        result = MatchStateSegmentationRuntime().run(
            source,
            package_dir=str(settings.match_state_segmentation_package_dir),
            device=settings.match_state_segmentation_device,
            required_profile=settings.match_state_segmentation_required_profile,
        )
        # 为 formal window 挂上源 rally 引用与分析回合上下文绑定（direct_segment_link 的材料）。
        # 引用字段刻意不参与 plan_hash，因此不会改变 Parent 绑定的 windowPlanHash。
        # feature gate 关闭时完全跳过，formal 切分行为与既有版本逐字一致。
        if (
            result.artifact is not None
            and source.capture_take_id
            and getattr(job, "rallyContextMode", "legacy") == "new"
        ):
            result = _attach_source_rally_refs(result, source.capture_take_id, source.planning_job_id)
        parent = self.store.get(job.parentJobId) if job.parentJobId else None
        artifact_path = None
        if result.artifact is not None:
            try:
                from app.database import get_session_factory
                db = get_session_factory()()
                try:
                    persist_segmentation_result(db, artifact=result.artifact, storage=storage)
                    db.commit()
                finally:
                    db.close()
            except Exception as exc:  # persistence failure is an inference failure
                result = result.__class__("inference_failed", None, "inference_failed", f"切分结果发布失败: {exc}")
            if result.artifact is not None:
                artifact_path = storage.formal_segmentation_artifact_path(
                    result.artifact.planning_job_id,
                    result.artifact.capture_take_id,
                    create_root=False,
                )
        else:
            # Keep model/input/sync failures auditable without superseding any
            # previously published automatic segments for this CaptureTake.
            if source.capture_take_id:
                try:
                    from app.database import get_session_factory

                    db = get_session_factory()()
                    try:
                        persist_segmentation_failure(
                            db,
                            planning_job_id=job.parentJobId or job.id,
                            capture_take_id=source.capture_take_id,
                            status=result.status,
                            profile=settings.match_state_segmentation_required_profile,
                            input_fingerprint=source.input_fingerprint,
                            sync_calibration_revision=source.sync_calibration_revision,
                            timing_authority=source.timing_authority,
                            diagnostics={"error_code": result.error_code, "detail": result.detail},
                        )
                        db.commit()
                    finally:
                        db.close()
                except Exception:
                    logger.exception("Unable to persist formal segmentation failure for %s", source.capture_take_id)
        if parent is not None:
            updates: dict[str, object] = {
                "segmentationStatus": result.status,
                "segmentationErrorCode": result.error_code,
            }
            if result.artifact is not None:
                updates.update(
                    {
                        "segmentationRunId": result.artifact.run_id,
                        "windowPlanHash": result.artifact.window_plan.plan_hash,
                        "segmentationArtifactRef": storage.logical_artifact_reference(job.parentJobId or job.id, storage.formal_segmentation_artifact_path(job.parentJobId or job.id, parent.metadata.capture_take_id)),
                    }
                )
            self.store.update(parent.id, **updates)
        status = "completed" if result.artifact is not None else "failed"
        detail = "自动回合切分完成" if result.artifact is not None else (result.detail or "自动回合切分失败")
        progress_callback(PipelineStageResult(id="segment", label="回合自动切分", status="done" if result.artifact is not None else "failed", detail=detail, progress=100 if result.artifact is not None else 0, started_at=now, finished_at=datetime.now(UTC), error_code=result.error_code, public_message=detail))
        metrics = PerformanceMetrics(distances=[], speeds=[], kitchen_dwell=[], doubles_spacing=[], heatmap={"rows": 1, "cols": 1, "cells": []})
        artifacts = AnalysisArtifacts(
            match_state_segmentation_json_path=(
                storage.logical_artifact_reference(result.artifact.planning_job_id, artifact_path)
                if result.artifact is not None and artifact_path is not None
                else None
            ),
            match_state_segmentation_status=result.status,
            match_state_segmentation_detail=detail,
        )
        pipeline_result = AnalysisPipelineResult(
            job_id=job.id,
            status=status,
            generated_at=datetime.now(UTC),
            stages=[PipelineStageResult(id="segment", label="回合自动切分", status="done" if result.artifact is not None else "failed", detail=detail, progress=100 if result.artifact is not None else 0, error_code=result.error_code, public_message=detail)],
            metrics=metrics,
            artifacts=artifacts,
            message=detail,
        )
        storage.write_json(storage.output_json_path(job.id), pipeline_result.model_dump(mode="json"))
        return pipeline_result


def _load_capture_take_media_samples(job: AnalysisJobSummary, *, package_dir: str) -> list[dict[str, object]]:
    """Build model inputs directly from the authoritative CaptureTake media.

    This is the production path; the JSON sidecar above is only a deterministic
    replay/CPU smoke input.  Any missing track, PTS authority or calibration is
    represented as low evidence so the Runtime can classify it explicitly.
    """
    return list(_iter_capture_take_media_samples(job, package_dir=package_dir))


def _iter_capture_take_media_samples(job: AnalysisJobSummary, *, package_dir: str):
    """Yield authoritative CaptureTake RGB rows without retaining them."""
    capture_take_id = job.metadata.capture_take_id
    if not capture_take_id:
        return
    try:
        from app.database import get_session_factory
        from app.models.capture_take import CaptureTake
        from app.models.capture_track import CaptureTrack
        from app.services.frame_timing_provider import FrameTimingProvider
        from app.services.video_service import video_service
        from app.vision.multiview.sync import load_sync_calibration

        db = get_session_factory()()
        try:
            take = db.get(CaptureTake, capture_take_id)
            tracks = db.query(CaptureTrack).filter(CaptureTrack.capture_take_id == capture_take_id).all()
            if take is None:
                return
            by_slot = {getattr(track.slot, "value", str(track.slot)): track for track in tracks}
            cam_1 = by_slot.get("cam_1")
            cam_2 = by_slot.get("cam_2")
            if cam_1 is None or cam_2 is None:
                yield {"center_ms": 0, "coverage": 0.0, "input_unavailable": True}
                return
            ref_video = video_service.get_available_video(cam_1.video_id)
            sec_video = video_service.get_available_video(cam_2.video_id)
            if ref_video is None or sec_video is None:
                yield {"center_ms": 0, "coverage": 0.0, "input_unavailable": True}
                return
            import cv2

            ref_probe = cv2.VideoCapture(ref_video.path)
            sec_probe = cv2.VideoCapture(sec_video.path)
            try:
                ref_count = int(ref_probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                sec_count = int(sec_probe.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
                ref_fps = float(ref_probe.get(cv2.CAP_PROP_FPS) or 0.0)
                sec_fps = float(sec_probe.get(cv2.CAP_PROP_FPS) or 0.0)
            finally:
                ref_probe.release()
                sec_probe.release()
            ref_timing = FrameTimingProvider.from_media(
                ref_video.path, frame_count=ref_count, fps=ref_fps or 30.0, allow_nominal_fallback=False
            )
            sec_timing = FrameTimingProvider.from_media(
                sec_video.path, frame_count=sec_count, fps=sec_fps or 30.0, allow_nominal_fallback=False
            )
            if not ref_timing.frames or not sec_timing.frames:
                yield {"center_ms": 0, "coverage": 0.0, "input_unavailable": True}
                return
            take_dir = take.session_dir or take.storage_root
            sync = load_sync_calibration(take_dir) if take_dir else None
            revision = job.syncCalibrationRevision
            if sync is None or revision is None:
                yield {"center_ms": 0, "coverage": 0.0, "sync_unavailable": True}
                return
            mapping = sync.mapping_for(cam_2.camera_id)
            if mapping is None:
                yield {"center_ms": 0, "coverage": 0.0, "sync_unavailable": True}
                return
            package = load_production_package(package_dir, required_profile="match_default")
            config = RGBMediaSamplingConfig.from_contract(package.input_contract)
            duration_ms = int(take.duration_ms or ref_timing.duration_seconds * 1000)
            yield from iter_capture_take_media(
                reference_media_path=ref_video.path,
                secondary_media_path=sec_video.path,
                reference_timing=ref_timing,
                secondary_timing=sec_timing,
                sync_calibration=mapping,
                start_ms=0,
                end_ms=max(1, duration_ms),
                sync_calibration_revision=int(revision),
                config=config,
            )
        finally:
            db.close()
    except ModelPackageError as exc:
        logger.warning("Formal model package unavailable while preparing media samples: %s", exc)
        yield {"center_ms": 0, "coverage": 0.0, "model_unavailable": True, "detail": str(exc)}
    except Exception as exc:  # runtime will surface a stable unavailable status
        logger.warning("Unable to sample CaptureTake media for segmentation: %s", exc)
        yield {"center_ms": 0, "coverage": 0.0, "input_unavailable": True}


class MultiViewAnalysisExecutor:
    """多视角 Parent 执行体：fusion_ready → 融合 + Composer；fallback_ready → 单视角降级 + Composer。"""

    def __init__(
        self,
        store,
        pipeline_factory: Callable[..., object],
    ) -> None:
        self.store = store
        self.pipeline_factory = pipeline_factory

    def execute(
        self,
        job: AnalysisJobSummary,
        token,
        progress_callback: Callable[[object], None],
    ) -> AnalysisPipelineResult:
        parent = job
        storage = StorageService()
        capture_take_id = parent.metadata.capture_take_id
        analysis_dir = _resolve_analysis_dir(storage, parent, capture_take_id)
        if analysis_dir is None:
            raise RuntimeError(f"cannot resolve capture analysis dir for parent {parent.id}")
        take_dir = analysis_dir.parent

        sync = load_sync_calibration(take_dir)

        # 解析 owned children
        children: dict[str, tuple[object, AnalysisJobSummary]] = {}
        for ref in parent.sourceJobs:
            child = self.store.get(ref.jobId)
            if child is not None:
                children[ref.cameraSlot] = (ref, child)

        reference_view_id = parent.referenceViewId or (
            parent.sourceJobs[0].cameraSlot if parent.sourceJobs else None
        )
        if not reference_view_id or reference_view_id not in children:
            raise RuntimeError(f"reference view {reference_view_id} child not found for parent {parent.id}")
        if len(children) < 2:
            raise RuntimeError(f"parent {parent.id} requires at least two source children")
        self.store.update(parent.id, orchestrationStatus="fusing")

        def emit_stage(stage_id: str, label: str, status: str, detail: str, progress: int) -> None:
            from datetime import UTC, datetime

            now = datetime.now(UTC)
            progress_callback(
                PipelineStageResult(
                    id=stage_id,
                    label=label,
                    status=status,
                    detail=detail,
                    started_at=now,
                    finished_at=now,
                    progress=progress,
                    public_message=detail,
                )
            )

        emit_stage(
            "multiview-input-check",
            "素材与同步检查",
            "done",
            "双视频 / 双标定 / 同步信息检查通过",
            100,
        )
        for view_id, stage_id, label in (
            ("cam_1", "multiview-view-a", "A 机位视觉分析"),
            ("cam_2", "multiview-view-b", "B 机位视觉分析"),
        ):
            child = children.get(view_id, (None, None))[1]
            child_status = child.canonicalStatus if child is not None else "missing"
            stage_status = "done" if child_status == "succeeded" else "failed"
            emit_stage(
                stage_id,
                label,
                stage_status,
                f"{label}{'完成' if stage_status == 'done' else '未完成'}",
                100 if stage_status == "done" else 0,
            )

        secondary_view_id = next(vid for vid in children if vid != reference_view_id)
        reference_ref, reference_child = children[reference_view_id]
        secondary_ref, secondary_child = children[secondary_view_id]
        reference_camera_id = (
            reference_ref.cameraId
            or getattr(reference_child.metadata, "camera_id", None)
            or reference_view_id
        )
        secondary_camera_id = (
            secondary_ref.cameraId
            or getattr(secondary_child.metadata, "camera_id", None)
            or secondary_view_id
        )
        authority = validate_sync_authority(
            sync,
            reference_camera_id=reference_camera_id,
            secondary_camera_id=secondary_camera_id,
        )
        authority_reason = "; ".join(issue.code for issue in authority.issues) or None
        canonical_frame = load_canonical_court_frame(take_dir)

        # 构建 / 复用 MultiViewFusionRun（执行前持久化 fusionRunId，保证重启幂等）
        run_id = parent.fusionRunId or f"mvf_{uuid4().hex[:12]}"
        run_dir = default_run_output_dir(analysis_dir, run_id)
        view_inputs = [
            MultiViewViewInput(
                view_id=ref.cameraSlot,
                capture_track_id="",
                video_id=child.videoId or "",
                analysis_job_id=child.id,
                calibration_id=child.calibrationId or "",
                camera_id=ref.cameraId or getattr(child.metadata, "camera_id", None) or ref.cameraSlot,
                court_orientation=CourtOrientation(ref.courtOrientation) if ref.courtOrientation else None,
            )
            for ref, child in children.values()
        ]
        run = MultiViewFusionRun(
            run_id=run_id,
            capture_take_id=capture_take_id,
            source_analysis_job_ids=[ref.jobId for ref in parent.sourceJobs],
            view_inputs=view_inputs,
            sync_calibration_ref=sync,
            canonical_frame_ref=canonical_frame,
            output_dir=run_dir,
        )
        if not parent.fusionRunId:
            self.store.update(parent.id, fusionRunId=run_id)

        eligibility = run.check_eligibility()
        authority_ready = authority.valid
        fused_artifact: dict[str, object] | None = None
        diagnostics: dict[str, object] | None = None
        fusion_performed = False

        if eligibility.ready and authority_ready:
            emit_stage(
                "multiview-fusion",
                "多视角球员轨迹融合",
                "active",
                "正在融合两路机位轨迹证据",
                5,
            )
            # 幂等复用：fusionRunId 已存在且 fused artifact 完整 → reuse
            existing = load_fused_artifact(run_dir / FUSED_TRAJECTORY_FILENAME) if parent.fusionRunId else None
            if (
                existing is not None
                and existing.get("schema_version") == FUSED_TRAJECTORY_SCHEMA_VERSION
                and existing.get("samples") is not None
            ):
                fused_artifact = existing
                diag = run_dir / FUSED_DIAGNOSTICS_FILENAME
                diagnostics = (
                    load_fused_artifact(diag) or {"schema_version": FUSED_DIAGNOSTICS_SCHEMA_VERSION, "reused": True}
                )
                fusion_performed = True
                logger.info("复用既有 fused artifact（run=%s）", run_id)
            else:
                try:
                    fused_artifact, diagnostics = self._run_fusion(
                        run=run,
                        parent=parent,
                        children=children,
                        reference_view_id=reference_view_id,
                        sync=sync,
                        storage=storage,
                        secondary_camera_id=secondary_camera_id,
                    )
                    fusion_performed = True
                except (SpikeAdapterError, ValueError, OSError) as exc:  # noqa: BLE001
                    # 观测缺失/不可读 → 退化为 reference 单视角（job-level fallback 不变式）
                    logger.warning("融合执行失败，降级为单视角: %s", exc)
                    fused_artifact = None

        emit_stage(
            "multiview-fusion",
            "多视角球员轨迹融合",
            "done" if fusion_performed else "skipped",
            "多视角球员轨迹融合完成" if fusion_performed else "未执行融合（单视角降级）",
            100,
        )

        if fused_artifact is None:
            # job-level fallback：用 reference view 单视角观测（不假装融合）
            fused_artifact, diagnostics, reason = self._fallback_single_view(
                run=run,
                parent=parent,
                children=children,
                reference_view_id=reference_view_id,
                sync=sync,
                storage=storage,
                reason=authority_reason or eligibility.reason,
                canonical_frame=canonical_frame,
            )
            analysis_source = {
                "mode": "single_view_fallback",
                "source_job_id": children[reference_view_id][1].id,
                "source_view": reference_view_id,
                "reason": reason,
            }
            message = f"未执行多视角融合（{reason}），结果使用 {reference_view_id} 单视角数据。"
        else:
            effective_mode = str((diagnostics or {}).get("effective_mode", "multiview_fused"))
            analysis_source = {
                "mode": effective_mode,
                "source_job_id": parent.id,
                "source_view": reference_view_id,
                "reason": eligibility.reason,
            }
            message = (
                "双摄协同分析完成（多视角融合已执行）。"
                if effective_mode == "multiview_fused"
                else "双摄分析完成，但副摄证据覆盖不足，结果按降级模式展示。"
            )

        composer = MultiViewResultComposer(storage)
        reference_child = children[reference_view_id][1]
        self.store.update(parent.id, orchestrationStatus="composing")
        emit_stage(
            "multiview-metrics",
            "运动指标重算",
            "active",
            "正在基于双摄轨迹重算运动指标",
            10,
        )
        result = composer.build_pipeline_result(
            job=parent,
            fused_artifact=fused_artifact,
            diagnostics=diagnostics or {},
            analysis_source=analysis_source,
            reference_child=reference_child,
            fusion_performed=fusion_performed,
            message=message,
        )
        emit_stage("multiview-metrics", "运动指标重算", "done", "运动指标重算完成", 100)
        emit_stage("multiview-visualization", "可视化输出", "done", "双摄结果可视化产物已生成", 100)
        emit_stage("multiview-report", "报告生成", "active", "正在生成 Parent 报告", 10)
        # 持久化 Parent 的 AnalysisPipelineResult（单摄 pipeline 内部 _write_result 落盘，
        # 但 MultiView 走 executor 直接返回 → 必须在此显式落盘）。否则后端重启后
        # /result 读不到，前端拿不到 video_id 等产物 URL，视频与叠加层全部不可用。
        result = storage.publicize_pipeline_result(result)
        storage.write_json(storage.output_json_path(parent.id), result.model_dump(mode="json"))
        return result

    # ---- 融合执行 -----------------------------------------------------------

    def _run_fusion(
        self,
        *,
        run: MultiViewFusionRun,
        parent: AnalysisJobSummary,
        children: dict[str, tuple[object, AnalysisJobSummary]],
        reference_view_id: str,
        sync,
        storage: StorageService,
        secondary_camera_id: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        ref_ref, ref_child = children[reference_view_id]
        secondary_view_id = next(vid for vid in children if vid != reference_view_id)
        sec_ref, sec_child = children[secondary_view_id]

        ref_obs = load_view_observations(
            storage.player_render_trajectory_path(ref_child.id), view_id=reference_view_id
        )
        sec_obs = load_view_observations(
            storage.player_render_trajectory_path(sec_child.id), view_id=secondary_view_id
        )
        ref_orientation = CourtOrientation(ref_ref.courtOrientation) if ref_ref.courtOrientation else None
        sec_orientation = CourtOrientation(sec_ref.courtOrientation) if sec_ref.courtOrientation else None

        sync_gate, _ = evaluate_sync_gate(sync)
        config = FusionConfig(degraded_sync=(sync_gate == "fuse_degraded"))
        pipeline_result = run_fusion_pipeline(
            reference_view_id=reference_view_id,
            reference_observations=ref_obs,
            secondary_view_id=secondary_view_id,
            secondary_observations=sec_obs,
            reference_orientation=ref_orientation,
            secondary_orientation=sec_orientation,
            sync=sync,
            secondary_camera_id=secondary_camera_id,
            max_pairing_error_ms=DEFAULT_MAX_PAIRING_ERROR_MS,
            config=config,
        )
        run.pairing_plan_ref = {
            "decision_count": len(pipeline_result.pairing_plan.decisions)
            if pipeline_result.pairing_plan is not None
            else 0,
            "available_count": pipeline_result.pairing_plan.available_count
            if pipeline_result.pairing_plan is not None
            else 0,
        }
        sync_quality = sync.worst_quality() if sync else "unknown"
        fused = build_fused_artifact(
            pipeline_result.measurements,
            run_id=run.run_id,
            capture_take_id=run.capture_take_id,
            reference_view_id=reference_view_id,
            secondary_view_id=secondary_view_id,
            sync_quality=sync_quality,
            court_frame_version=config.court_frame_version,
            canonical_frame_id=run.canonical_frame_ref.frame_id if run.canonical_frame_ref else None,
        )
        diagnostics = build_fusion_diagnostics(
            pipeline_result.measurements,
            run_id=run.run_id,
            global_players=pipeline_result.global_players,
            orientations={
                reference_view_id: (ref_orientation.value if ref_orientation else "unset"),
                secondary_view_id: (sec_orientation.value if sec_orientation else "unset"),
            },
            reference_view_id=reference_view_id,
            secondary_view_id=secondary_view_id,
            pairing_plan=pipeline_result.pairing_plan,
            canonical_frame_id=run.canonical_frame_ref.frame_id if run.canonical_frame_ref else None,
            authority_reason=None,
            requested_mode=parent.executionMode,
        )
        write_fused_artifact(run.output_dir, fused)
        write_fusion_diagnostics(run.output_dir, diagnostics)
        logger.info(
            "融合完成 run=%s samples=%s global_players=%s",
            run.run_id,
            len(pipeline_result.measurements),
            len(pipeline_result.global_players),
        )
        return fused, diagnostics

    @staticmethod
    def _resolve_secondary_sync_key(sync, preferred_view_id: str) -> str:
        """Legacy test/helper compatibility; runtime paths use persisted cameraId directly."""
        if sync is None:
            return preferred_view_id
        if sync.mapping_for(preferred_view_id) is not None:
            return preferred_view_id
        non_reference = [key for key in sync.mappings if key != sync.reference_camera]
        if len(non_reference) == 1:
            return non_reference[0]
        return preferred_view_id

    # ---- 单视角降级 ----------------------------------------------------------

    def _fallback_single_view(
        self,
        *,
        run: MultiViewFusionRun,
        parent: AnalysisJobSummary,
        children: dict[str, tuple[object, AnalysisJobSummary]],
        reference_view_id: str,
        sync,
        storage: StorageService,
        reason: str,
        canonical_frame=None,
    ) -> tuple[dict[str, object], dict[str, object], str]:
        ref_ref, ref_child = children[reference_view_id]
        try:
            ref_obs = load_view_observations(
                storage.player_render_trajectory_path(ref_child.id), view_id=reference_view_id
            )
        except SpikeAdapterError as exc:
            raise RuntimeError(f"reference view {reference_view_id} observations unavailable: {exc}") from exc
        # 单视角降级无融合比对，orientation 未声明时按 identity 处理（不阻塞指标重算）
        ref_orientation = (
            CourtOrientation(ref_ref.courtOrientation) if ref_ref.courtOrientation else CourtOrientation.identity
        )
        sync_quality = sync.worst_quality() if sync else "unknown"
        fused = build_fallback_fused_artifact(
            run_id=run.run_id,
            capture_take_id=run.capture_take_id,
            reference_view_id=reference_view_id,
            observations=ref_obs,
            sync_quality=sync_quality,
            reference_orientation=ref_orientation,
            canonical_frame_id=canonical_frame.frame_id if canonical_frame else None,
        )
        diagnostics = {
            "schema_version": FUSED_DIAGNOSTICS_SCHEMA_VERSION,
            "run_id": run.run_id,
            "fallback": True,
            "reason": reason or "job-level single-view fallback",
            "reference_view_id": reference_view_id,
            "sample_count": len(ref_obs),
            "canonical_frame_id": canonical_frame.frame_id if canonical_frame else None,
            "requested_mode": parent.executionMode,
            "authority_reason": reason,
            "secondary_available_samples": 0,
            "dual_evidence_samples": 0,
            "single_view_fallback_samples": len(ref_obs),
            "predicted_samples": 0,
            "effective_multiview_ratio": 0.0,
            "effective_mode": "single_view_fallback",
        }
        write_fused_artifact(run.output_dir, fused)
        write_fusion_diagnostics(run.output_dir, diagnostics)
        logger.info("单视角降级 run=%s view=%s reason=%s", run.run_id, reference_view_id, reason)
        return fused, diagnostics, reason or "job-level single-view fallback"


def resolve_executor(
    analysis_kind: str,
    store,
    pipeline_factory: Callable[..., object],
    execution_mode: str | None = None,
    job_role: str | None = None,
) -> AnalysisJobExecutor:
    """按 analysisKind 选择执行体(single_view / multiview);multiview 再按 executionMode 分发。"""
    if job_role == "segmentation_prerequisite":
        return SegmentationPrerequisiteExecutor(store)
    if analysis_kind == "single_view":
        return SingleViewAnalysisExecutor(store, pipeline_factory)
    if analysis_kind == "multiview":
        if execution_mode == "joint_tracking_v2":
            from app.services.multiview_joint_executor import MultiViewJointExecutor

            return MultiViewJointExecutor(store, pipeline_factory)
        return MultiViewAnalysisExecutor(store, pipeline_factory)
    raise ValueError(f"unknown analysisKind: {analysis_kind!r}")
