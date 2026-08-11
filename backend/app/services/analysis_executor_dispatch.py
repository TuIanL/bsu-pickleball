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
from app.schemas.pipeline import AnalysisPipelineResult
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
            "clip_start_ms": payload.clipStartMs,
            "clip_end_ms": payload.clipEndMs,
            "capture_take_id": job.metadata.capture_take_id,
        }
        signature = inspect.signature(pipeline.run)
        accepts_kwargs = any(
            parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()
        )
        if not accepts_kwargs:
            run_kwargs = {key: value for key, value in run_kwargs.items() if key in signature.parameters}
        return pipeline.run(**run_kwargs)


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
        result = composer.build_pipeline_result(
            job=parent,
            fused_artifact=fused_artifact,
            diagnostics=diagnostics or {},
            analysis_source=analysis_source,
            reference_child=reference_child,
            fusion_performed=fusion_performed,
            message=message,
        )
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
) -> AnalysisJobExecutor:
    """按 analysisKind 选择执行体(single_view / multiview);multiview 再按 executionMode 分发。"""
    if analysis_kind == "single_view":
        return SingleViewAnalysisExecutor(store, pipeline_factory)
    if analysis_kind == "multiview":
        if execution_mode == "joint_tracking_v2":
            from app.services.multiview_joint_executor import MultiViewJointExecutor

            return MultiViewJointExecutor(store, pipeline_factory)
        return MultiViewAnalysisExecutor(store, pipeline_factory)
    raise ValueError(f"unknown analysisKind: {analysis_kind!r}")
