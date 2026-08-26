"""任务编排引擎 —— 管理分析任务的生命周期（排队、调度、状态追踪、取消和重试）。

"任务（job）"就是一次分析请求。本模块负责：
- 用 JobStore 把任务存起来（内存 + 磁盘 JSON），支持增删改查；
- 把任务在执行中经历的"阶段（stage）"进度汇总；
- 用 AnalysisWorkerRuntime 在后台线程里真正跑分析流水线；
- 处理取消、超时、失败重试等。

注意：这里不直接做"视频分析"，那是 analysis_pipeline 的事；
这里只管"任务怎么排、怎么跑、跑到哪了"。
"""

from __future__ import annotations

import hashlib
import inspect
import json
import logging
import os
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.analysis import (
    ANALYSIS_ERROR_CODES,
    STABLE_ANALYSIS_STAGE_IDS,
    AnalysisCanonicalStatus,
    AnalysisJobCreate,
    AnalysisJobStatus,
    AnalysisJobSummary,
    AnalysisStage,
    AnalysisStageId,
    AnalysisStageStatus,
    build_match_context,
)
from app.schemas.pipeline import AnalysisPipelineResult, PipelineStageResult
from app.services.analysis_progress import (
    ProgressMode,
    StageTransitionError,
    aggregate_progress,
    build_stage_snapshot,
    merge_stage_event,
    normalize_stage_snapshot,
    resolve_progress_mode,
    stage_definition,
    stage_definitions,
    stage_ids,
)
from app.services.analysis_control_plane import AnalysisControlPlane
from app.services.storage_service import StorageService
from app.vision.multiview.recovery_config import P1OnlineRecoveryConfig

logger = logging.getLogger(__name__)


def _is_local_process_alive(pid: int | None) -> bool:
    """Return whether a locally recorded worker process still exists.

    A CPU-bound native extension can hold the GIL long enough to delay the
    in-process heartbeat thread.  In external-worker mode that is not proof
    that the worker process disappeared, so callers must not revoke its lease
    solely from a stale timestamp while its PID is still alive.
    """
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        # We cannot inspect another user's process, but it is definitely not
        # safe to declare that live process lost.
        return True
    return True


# 终态（任务到此就结束了，不能再变）：成功 / 失败 / 已取消
TERMINAL_CANONICAL_STATUSES: set[AnalysisCanonicalStatus] = {"succeeded", "failed", "canceled", "interrupted"}
# 仍"活跃"的兼容状态：上传中 / 排队中 / 处理中
ACTIVE_COMPAT_STATUSES: set[AnalysisJobStatus] = {"uploaded", "queued", "processing"}
# 允许重试的阶段：视频读取 / 报告 / 可视化
RETRYABLE_STAGE_IDS = {"video-read", "report", "visualization", "multiview-ball-analysis"}

# 阶段顺序（与 STABLE_ANALYSIS_STAGE_IDS 保持一致）
ORDERED_STAGES: list[AnalysisStageId] = list(STABLE_ANALYSIS_STAGE_IDS)

# 每个阶段的"中文标签 + 说明"
STAGE_DETAILS: dict[AnalysisStageId, tuple[str, str]] = {
    "upload": ("视频上传", "保存视频和基础比赛信息"),
    "queue": ("任务排队", "等待视觉分析任务执行"),
    "calibration": ("场地标定", "读取或跳过四角手工标定"),
    "video-read": ("读取视频", "读取上传视频元数据和帧流"),
    "frame-sampling": ("抽帧采样", "按时间轴抽取关键帧"),
    "detection": ("目标检测", "运行或跳过人体检测模型"),
    "pose": ("人体姿态", "运行或跳过 RTMPose26 关键点识别"),
    "tracking": ("轨迹跟踪", "关联球员移动轨迹"),
    "projection": ("脚点投影", "映射画面坐标到匹克球场"),
    "metrics": ("运动指标", "计算移动距离、速度、厨房区停留和热力图"),
    "visualization": ("可视化输出", "生成可供前端展示的结果引用"),
    "report": ("报告生成", "生成报告 JSON 并交给前端展示"),
    "multiview-ball-analysis": ("双摄球路分析", "基于共享同步帧生成球路与立体证据"),
}


def utc_now() -> str:
    # 返回当前 UTC 时间的 ISO8601 字符串（带时区）
    return datetime.now(UTC).isoformat()


def canonical_to_display_status(status: AnalysisCanonicalStatus) -> AnalysisJobStatus:
    # 把"规范状态"翻译成"对外展示状态"
    return {
        "queued": "queued",
        "running": "processing",
        "succeeded": "completed",
        "failed": "failed",
        "canceled": "canceled",
        "interrupted": "interrupted",
    }[status]


def display_to_canonical_status(status: AnalysisJobStatus) -> AnalysisCanonicalStatus:
    # 把"对外展示状态"翻译回"规范状态"
    return {
        "uploaded": "queued",
        "queued": "queued",
        "processing": "running",
        "completed": "succeeded",
        "failed": "failed",
        "canceled": "canceled",
        "interrupted": "interrupted",
    }[status]


def build_stages(
    active_stage: AnalysisStageId = "report",
    failed: bool = False,
    *,
    mode: ProgressMode = "single_view",
) -> list[AnalysisStage]:
    """构造当前执行模式的完整顶层阶段快照。"""
    return build_stage_snapshot(mode, str(active_stage), failed=failed)


def stage_details_for(mode: ProgressMode, stage_id: str) -> tuple[str, str]:
    try:
        definition = stage_definition(mode, stage_id)
        return definition.label, definition.detail
    except StageTransitionError:
        return STAGE_DETAILS.get(stage_id, (stage_id, ""))


def normalize_job(job: AnalysisJobSummary) -> AnalysisJobSummary:
    # 统一化一个任务：保证 canonicalStatus / status / displayStatus 三者一致。
    canonical = job.canonicalStatus or display_to_canonical_status(job.status)
    if canonical_to_display_status(canonical) != job.status:
        canonical = display_to_canonical_status(job.status)
    display = canonical_to_display_status(canonical)
    payload = job.model_dump()
    payload["canonicalStatus"] = canonical
    payload["status"] = display
    payload["displayStatus"] = display
    mode = resolve_progress_mode(payload.get("analysisKind"), payload.get("executionMode"))
    normalized_stages = normalize_stage_snapshot(job.stages, mode)
    if canonical == "succeeded":
        normalized_stages = [
            stage.model_copy(update={"status": "done", "progress": 100})
            for stage in normalized_stages
        ]
    payload["stages"] = normalized_stages
    declared_stage = str(payload.get("stage") or "")
    if canonical == "succeeded" or declared_stage not in stage_ids(mode):
        payload["stage"] = current_stage_from_stages(
            normalized_stages,
            fallback=stage_ids(mode)[-1] if canonical == "succeeded" else stage_ids(mode)[0],
        )
    if payload.get("analysisKind") != "multiview" or not payload.get("viewRuns"):
        payload["viewRuns"] = None
    # 兼容字段：排队时间、错误信息相互补齐
    if payload.get("queuedAt") is None and canonical == "queued":
        payload["queuedAt"] = job.createdAt
    if payload.get("publicErrorMessage") is None and job.errorMessage:
        payload["publicErrorMessage"] = job.errorMessage
    if payload.get("errorMessage") is None and job.publicErrorMessage:
        payload["errorMessage"] = job.publicErrorMessage
    return AnalysisJobSummary.model_validate(payload)


def stage_from_pipeline(stage: PipelineStageResult) -> AnalysisStage:
    # 把一个"流水线阶段结果"转换成对外展示用的 AnalysisStage。
    started = stage.started_at.isoformat() if stage.started_at else None
    finished = stage.finished_at.isoformat() if stage.finished_at else None
    progress = stage.progress
    status: AnalysisStageStatus
    if stage.status == "partial":
        status = "done"
    elif stage.status == "unavailable":
        status = "skipped"
    else:
        status = stage.status
    if progress == 0 and status in {"done", "skipped"}:
        progress = 100
    if progress == 0 and status == "active":
        progress = 10
    return AnalysisStage(
        id=stage.id,
        label=stage.label,
        status=status,
        detail=stage.public_message or stage.detail,
        startedAt=started,
        endedAt=finished,
        durationMs=stage.duration_ms,
        progress=progress,
        errorCode=stage.error_code,
        publicMessage=stage.public_message or stage.detail,
        internalMessage=stage.internal_message,
        retryCount=stage.retry_count,
        counters=stage.counters,
    )


def compute_progress_from_stages(
    stages: list[AnalysisStage],
    *,
    mode: ProgressMode = "single_view",
    previous_progress: int = 0,
    view_progress: dict[str, object] | None = None,
    terminal_status: str | None = None,
) -> int:
    return aggregate_progress(
        stages,
        mode,
        previous_progress=previous_progress,
        view_progress=view_progress,
        terminal_status=terminal_status,
    )


def current_stage_from_stages(stages: list[AnalysisStage], fallback: str = "queue") -> str:
    # 找出"当前阶段"：优先失败的，其次进行中的，再其次最后一个完成/跳过的。
    for stage in stages:
        if stage.status == "failed":
            return stage.id
    for stage in stages:
        if stage.status == "active":
            return stage.id
    for stage in reversed(stages):
        if stage.status in {"done", "skipped", "canceled"}:
            return stage.id
    return fallback


def first_failed_stage(stages: list[AnalysisStage]) -> str:
    # 返回第一个失败阶段的 id（没有则返回 "queue"）。
    for stage in stages:
        if stage.status == "failed":
            return stage.id
    return "queue"


def merge_stage_progress(
    stages: list[AnalysisStage],
    stage: AnalysisStage,
    *,
    mode: ProgressMode = "single_view",
) -> list[AnalysisStage]:
    """合并阶段事件；未知阶段只记日志，不污染对外顶层阶段图。"""
    try:
        return merge_stage_event(stages, stage, mode)
    except StageTransitionError as exc:
        logger.warning("Ignoring invalid %s stage event %s: %s", mode, stage.id, exc)
        return normalize_stage_snapshot(stages, mode)


def analysis_signature(payload: AnalysisJobCreate) -> tuple[str, str]:
    # 计算任务的"输入签名"和"配置签名"（用于去重：相同输入+相同配置视为同一任务）。
    settings = get_settings()
    config_payload = {
        "frameStride": payload.frameStride,
        "enableModelInference": (
            payload.enableModelInference
            if payload.enableModelInference is not None
            else settings.enable_model_inference
        ),
        "enablePoseInference": (
            payload.enablePoseInference if payload.enablePoseInference is not None else settings.enable_pose_inference
        ),
        "detectorModel": settings.default_detector_model,
        "detectorDevice": settings.detector_device,
        "rtmposeConfig": settings.rtmpose_config_path,
        "rtmposeCheckpoint": settings.rtmpose_checkpoint_path,
        "rtmposeDevice": settings.rtmpose_device,
        "poseSchema": settings.pose_keypoint_schema,
        # 分析模式由是否提供标定/视频决定
        "analysisMode": "real" if payload.calibrationId else "limited" if payload.videoId else "demo",
    }
    # Joint recovery parameters are part of reproducibility/idempotency. Keep the
    # field absent for legacy single-view and late-fusion jobs so their signatures
    # remain unchanged.
    if payload.multiview and payload.multiview.executionMode == "joint_tracking_v2":
        config_payload["p1OnlineRecovery"] = P1OnlineRecoveryConfig().snapshot()
        config_payload["debugTraceEnabled"] = bool(payload.multiview.debugTraceEnabled)
    if payload.multiview:
        config_payload["sceneCalibrationMode"] = payload.multiview.sceneCalibrationMode
        config_payload["sceneCalibrationRevision"] = payload.multiview.sceneCalibrationRevision
        config_payload["sceneViewIds"] = sorted(payload.multiview.sceneViewIds)
    input_payload = {
        "videoId": payload.videoId,
        "calibrationId": payload.calibrationId,
        "sourceFps": payload.sourceFps or payload.metadata.sourceFps,
        "metadata": payload.metadata.model_dump(mode="json"),
        "clipStartMs": payload.clipStartMs,
        "clipEndMs": payload.clipEndMs,
        "captureSegmentId": payload.captureSegmentId,
        "segmentVersion": payload.segmentVersion,
        # 执行模式进入输入签名:同一 take 的 late_fusion_v1 / joint_tracking_v2 视为不同任务(A/B 不被去重)
        "executionMode": payload.multiview.executionMode if payload.multiview else None,
        "sceneCalibrationMode": payload.multiview.sceneCalibrationMode if payload.multiview else None,
        "sceneCalibrationRevision": payload.multiview.sceneCalibrationRevision if payload.multiview else None,
        "sceneViewIds": sorted(payload.multiview.sceneViewIds) if payload.multiview else [],
    }
    return _stable_hash(input_payload), _stable_hash(config_payload)


class JobStore:
    """分析任务控制面：SQLite 是权威，JSON 是兼容快照和调试出口。"""

    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()
        self._lock = threading.RLock()
        settings = self.storage.settings
        configured_path = getattr(settings, "analysis_control_database_path", None)
        control_path = (
            settings.resolve_path(configured_path)
            if configured_path is not None
            else settings.resolve_path(settings.outputs_dir).parent / "analysis_control.sqlite3"
        )
        self.control_plane = AnalysisControlPlane(control_path)
        self._jobs: dict[str, AnalysisJobSummary] = {}
        self._import_legacy_jobs()

    def _model(self, payload: dict[str, object]) -> AnalysisJobSummary:
        return normalize_job(AnalysisJobSummary.model_validate(payload))

    def _payload(self, job: AnalysisJobSummary) -> dict[str, object]:
        return self._model(job.model_dump(mode="json")).model_dump(mode="json")

    def _persist_payload(self, payload: dict[str, object] | None) -> AnalysisJobSummary | None:
        if payload is None:
            return None
        job = self._model(payload)
        with self._lock:
            self._jobs[job.id] = job
            self.storage.write_json_atomic(self.storage.job_json_path(job.id), job.model_dump(mode="json"))
        return job

    def _import_legacy_jobs(self) -> int:
        payloads: list[dict[str, object]] = []
        jobs_dir = self.storage.jobs_dir()
        if jobs_dir.exists():
            for path in sorted(jobs_dir.glob("*.json")):
                try:
                    payloads.append(self._payload(AnalysisJobSummary.model_validate(self.storage.read_json(path))))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Skipping unreadable legacy analysis job %s: %s", path, exc)
        return self.control_plane.import_legacy(payloads)

    def create_job(
        self, payload: AnalysisJobCreate, *, job_id: str | None = None, report_id: str | None = None
    ) -> AnalysisJobSummary:
        now = utc_now()
        input_sig, config_sig = analysis_signature(payload)
        job_id = job_id or f"job-{uuid4().hex[:10]}"
        report_id = report_id or f"PV-{job_id.upper()}"
        mode = "real" if payload.calibrationId else "limited" if payload.videoId else "demo"
        settings = get_settings()
        progress_mode = resolve_progress_mode(
            payload.analysisKind,
            payload.multiview.executionMode if payload.multiview else None,
        )
        initial_stage = "queue" if progress_mode == "single_view" else stage_ids(progress_mode)[0]
        job = AnalysisJobSummary(
            id=job_id,
            status="queued",
            canonicalStatus="queued",
            displayStatus="queued",
            stage=initial_stage,
            progress=10,
            createdAt=now,
            updatedAt=now,
            queuedAt=now,
            priority=payload.priority,
            inputSignature=input_sig,
            configSignature=config_sig,
            frameStride=payload.frameStride,
            sourceFps=payload.sourceFps or payload.metadata.sourceFps,
            metadata=payload.metadata,
            stages=build_stages(initial_stage, mode=progress_mode),
            reportId=report_id,
            videoId=payload.videoId,
            calibrationId=payload.calibrationId,
            analysisMode=mode,
            recordingSessionId=payload.recording_session_id,
            cameraSlot=payload.camera_slot,
            enableModelInference=(
                payload.enableModelInference
                if payload.enableModelInference is not None
                else settings.enable_model_inference
            ),
            enablePoseInference=(
                payload.enablePoseInference
                if payload.enablePoseInference is not None
                else settings.enable_pose_inference
            ),
            clipStartMs=payload.clipStartMs,
            clipEndMs=payload.clipEndMs,
            analysisKind=payload.analysisKind,
            executionMode=payload.multiview.executionMode if payload.multiview else "late_fusion_v1",
            orchestrationStatus="waiting_sources" if payload.analysisKind == "multiview" else "none",
            debugTraceEnabled=bool(payload.multiview.debugTraceEnabled) if payload.multiview else False,
            sceneCalibrationRevision=(
                payload.multiview.sceneCalibrationRevision
                if payload.multiview and payload.multiview.sceneCalibrationMode == "metric"
                else None
            ),
            sceneCalibrationMode=payload.multiview.sceneCalibrationMode if payload.multiview else "approximate",
            sceneCalibrationStatus=(
                "ready"
                if payload.multiview and payload.multiview.sceneCalibrationMode == "metric"
                else "missing"
            ),
        )
        return self.save(job)

    def save(self, job: AnalysisJobSummary) -> AnalysisJobSummary:
        normalized = normalize_job(job)
        payload = normalized.model_dump(mode="json")
        self.control_plane.upsert(payload)
        return self._persist_payload(payload) or normalized

    def update(self, job_id: str, **updates: object) -> AnalysisJobSummary | None:
        expected_status = updates.pop("_expected_canonical_status", None)
        expected_worker_run_id = updates.pop("_expected_worker_run_id", None)

        def mutator(payload: dict[str, object]) -> dict[str, object] | None:
            current_status = payload.get("canonicalStatus")
            requested_status = updates.get("canonicalStatus")
            requested_display = updates.get("status") or updates.get("displayStatus")
            if current_status in TERMINAL_CANONICAL_STATUSES:
                if requested_status is not None and requested_status != current_status:
                    return None
                if requested_display in ACTIVE_COMPAT_STATUSES:
                    return None
            payload.update(updates)
            payload["updatedAt"] = utc_now()
            return self._payload(self._model(payload))

        return self._persist_payload(
            self.control_plane.mutate(
                job_id,
                mutator,
                expected_status=str(expected_status) if expected_status is not None else None,
                expected_worker_run_id=str(expected_worker_run_id) if expected_worker_run_id is not None else None,
            )
        )

    def get(self, job_id: str) -> AnalysisJobSummary | None:
        self._import_legacy_jobs()
        try:
            return self._persist_payload(self.control_plane.get(job_id))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Unable to read analysis job %s from control plane: %s", job_id, exc)
            return None

    def list(self) -> list[AnalysisJobSummary]:
        self._import_legacy_jobs()
        jobs: list[AnalysisJobSummary] = []
        for payload in self.control_plane.list():
            try:
                job = self._model(payload)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping invalid analysis control payload: %s", exc)
                continue
            with self._lock:
                self._jobs[job.id] = job
            jobs.append(job)
        return jobs

    def find_by_signature(self, input_signature: str, config_signature: str) -> AnalysisJobSummary | None:
        for job in self.list():
            if (
                job.inputSignature == input_signature
                and job.configSignature == config_signature
                and job.canonicalStatus in {"queued", "succeeded"}
            ):
                return job
        return None

    def is_runnable(self, job: AnalysisJobSummary) -> bool:
        if job.canonicalStatus != "queued":
            return False
        if job.analysisKind == "single_view":
            return True
        if job.analysisKind == "multiview":
            if job.executionMode == "joint_tracking_v2":
                return job.orchestrationStatus == "joint_ready"
            return job.orchestrationStatus in {"fusion_ready", "fallback_ready"}
        return False

    def claim_next(self, worker_id: str) -> AnalysisJobSummary | None:
        def selector(payload: dict[str, object]) -> bool:
            job = self._model(payload)
            return self.is_runnable(job) and not job.cancelRequestedAt

        def mutator(payload: dict[str, object]) -> dict[str, object]:
            return self._claim_payload(self._model(payload), worker_id).model_dump(mode="json")

        return self._persist_payload(self.control_plane.mutate_next(selector, mutator))

    def claim(self, job_id: str, worker_id: str) -> AnalysisJobSummary | None:
        def mutator(payload: dict[str, object]) -> dict[str, object] | None:
            job = self._model(payload)
            if not self.is_runnable(job) or job.cancelRequestedAt:
                return None
            return self._claim_payload(job, worker_id).model_dump(mode="json")

        return self._persist_payload(self.control_plane.mutate(job_id, mutator, expected_status="queued"))

    def _claim_payload(
        self, job: AnalysisJobSummary, worker_id: str, worker_run_id: str | None = None
    ) -> AnalysisJobSummary:
        now = utc_now()
        mode = resolve_progress_mode(job.analysisKind, job.executionMode)
        claim_stage_id = "video-read" if mode == "single_view" else stage_ids(mode)[0]
        claim_label, claim_detail = stage_details_for(mode, claim_stage_id)
        payload = job.model_dump(mode="json")
        payload.update(
            {
                "canonicalStatus": "running",
                "status": "processing",
                "displayStatus": "processing",
                "stage": claim_stage_id,
                "progress": max(job.progress, 12),
                "startedAt": now,
                "updatedAt": now,
                "workerId": worker_id,
                "workerPid": os.getpid(),
                "workerRunId": worker_run_id or f"{worker_id}-{uuid4().hex}",
                "claimedAt": now,
                "workerHeartbeatAt": now,
                "lastProgressAt": now,
                "attempt": job.attempt + 1,
                "interruptedAt": None,
                "interruptionCode": None,
                "stages": merge_stage_progress(
                    job.stages,
                    AnalysisStage(
                        id=claim_stage_id,
                        label=claim_label,
                        status="active",
                        detail=claim_detail,
                        progress=10,
                    ),
                    mode=mode,
                ),
            }
        )
        return self._model(payload)

    def heartbeat(self, job_id: str, worker_run_id: str, *, heartbeat_at: str | None = None) -> bool:
        heartbeat_at = heartbeat_at or utc_now()

        def mutator(payload: dict[str, object]) -> dict[str, object]:
            payload["workerHeartbeatAt"] = heartbeat_at
            return self._payload(self._model(payload))

        updated = self.control_plane.mutate(
            job_id,
            mutator,
            expected_status="running",
            expected_worker_run_id=worker_run_id,
            require_worker_run_id=True,
        )
        if updated is None:
            return False
        try:
            self._persist_payload(updated)
        except OSError as exc:
            # SQLite 控制面已经成功写入 heartbeat；兼容 JSON 快照不是
            # liveness 的权威来源，不能因为一次文件系统写入失败而让
            # heartbeat 线程退出并把仍在运行的任务误判为失联。
            logger.warning(
                "Unable to refresh legacy JSON snapshot for heartbeat of job %s; "
                "control-plane heartbeat was persisted: %s",
                job_id,
                exc,
            )
        return True

    def is_lease_current(self, job_id: str, worker_run_id: str | None) -> bool:
        if not worker_run_id:
            return False
        payload = self.control_plane.get(job_id)
        return bool(
            payload
            and payload.get("canonicalStatus") == "running"
            and payload.get("workerRunId") == worker_run_id
        )

    def cancel(self, job_id: str) -> tuple[AnalysisJobSummary | None, str]:
        job = self.get(job_id)
        if job is None:
            return None, "not_found"
        if job.canonicalStatus in TERMINAL_CANONICAL_STATUSES:
            return job, "terminal"
        now = utc_now()
        if job.canonicalStatus == "queued":
            mode = resolve_progress_mode(job.analysisKind, job.executionMode)
            label, _detail = stage_details_for(mode, job.stage)
            canceled_stages = merge_stage_progress(
                job.stages,
                AnalysisStage(
                    id=job.stage,
                    label=label,
                    status="canceled",
                    detail="任务已在排队阶段取消",
                    progress=100,
                    errorCode=ANALYSIS_ERROR_CODES["job_canceled"],
                ),
                mode=mode,
            )
            updated = self._terminal_job(
                job,
                "canceled",
                stages=canceled_stages,
                error_code=ANALYSIS_ERROR_CODES["job_canceled"],
                message="任务已取消",
                finished_at=now,
                canceled_at=now,
                cancel_requested_at=now,
            )
            return updated, "canceled"
        updated = self.update(
            job_id,
            cancelRequestedAt=job.cancelRequestedAt or now,
            _expected_canonical_status="running",
            _expected_worker_run_id=job.workerRunId,
        )
        return updated or self.get(job_id), "requested"

    def mark_stage(self, job: AnalysisJobSummary, stage: AnalysisStage) -> AnalysisJobSummary:
        mode = resolve_progress_mode(job.analysisKind, job.executionMode)
        stages = merge_stage_progress(job.stages, stage, mode=mode)
        progress = compute_progress_from_stages(
            stages,
            mode=mode,
            previous_progress=job.progress,
            view_progress=job.viewRuns,
        )
        updates: dict[str, object] = {
            "canonicalStatus": "running",
            "status": "processing",
            "displayStatus": "processing",
            "stage": current_stage_from_stages(stages, fallback=stage.id),
            "progress": progress,
            "stages": stages,
            "lastProgressAt": utc_now(),
        }
        if stage.status == "failed":
            updates.update(
                {
                    "canonicalStatus": "failed",
                    "status": "failed",
                    "displayStatus": "failed",
                    "errorCode": stage.errorCode or ANALYSIS_ERROR_CODES["stage_failed"],
                    "errorMessage": stage.publicMessage or stage.detail,
                    "publicErrorMessage": stage.publicMessage or stage.detail,
                    "internalErrorMessage": stage.internalMessage,
                    "finishedAt": utc_now(),
                }
            )
        updated = self.update(
            job.id,
            **updates,
            _expected_canonical_status="running" if job.canonicalStatus == "running" else None,
            _expected_worker_run_id=job.workerRunId,
        )
        return updated or self.get(job.id) or job

    def mark_succeeded(self, job: AnalysisJobSummary, stages: list[AnalysisStage]) -> AnalysisJobSummary:
        mode = resolve_progress_mode(job.analysisKind, job.executionMode)
        report_id = stage_ids(mode)[-1]
        report_label, report_detail = stage_details_for(mode, report_id)
        report_stage = AnalysisStage(
            id=report_id,
            label=report_label,
            status="done",
            detail="已生成前端报告 JSON" if report_id == "report" else report_detail,
            progress=100,
        )
        merged = merge_stage_progress(stages, report_stage, mode=mode)
        return self._terminal_job(job, "succeeded", stages=merged, progress=100)

    def mark_failed(
        self,
        job: AnalysisJobSummary,
        *,
        stages: list[AnalysisStage],
        message: str,
        error_code: str | None = None,
        internal_message: str | None = None,
    ) -> AnalysisJobSummary:
        mode = resolve_progress_mode(job.analysisKind, job.executionMode)
        return self._terminal_job(
            job,
            "failed",
            stages=stages,
            error_code=error_code or ANALYSIS_ERROR_CODES["stage_failed"],
            message=message,
            internal_message=internal_message,
            stage=first_failed_stage(stages),
            progress=compute_progress_from_stages(stages, mode=mode, previous_progress=job.progress),
        )

    def mark_canceled(self, job: AnalysisJobSummary, *, message: str = "任务已取消") -> AnalysisJobSummary:
        mode = resolve_progress_mode(job.analysisKind, job.executionMode)
        label, _detail = stage_details_for(mode, job.stage)
        canceled_stage = AnalysisStage(
            id=job.stage,
            label=label,
            status="canceled",
            detail=message,
            progress=100,
            errorCode=ANALYSIS_ERROR_CODES["job_canceled"],
        )
        stages = merge_stage_progress(job.stages, canceled_stage, mode=mode)
        return self._terminal_job(
            job,
            "canceled",
            stages=stages,
            error_code=ANALYSIS_ERROR_CODES["job_canceled"],
            message=message,
            canceled_at=utc_now(),
        )

    def mark_interrupted(
        self,
        job: AnalysisJobSummary,
        *,
        reason: str = "worker_heartbeat_timeout",
        message: str = "Worker 在规定时间内没有心跳，任务已失联；已保留最后进度，请重新分析。",
    ) -> AnalysisJobSummary:
        return self._terminal_job(
            job,
            "interrupted",
            stages=job.stages,
            error_code=ANALYSIS_ERROR_CODES.get(reason, ANALYSIS_ERROR_CODES["worker_lost"]),
            message=message,
            finished_at=utc_now(),
            interrupted_at=utc_now(),
            interruption_code=reason,
        )

    def recover_stale_running(self, timeout_seconds: float) -> int:
        now = datetime.now(UTC)
        recovered = 0
        for job in self.list():
            if job.canonicalStatus != "running":
                continue
            raw_heartbeat = job.workerHeartbeatAt or job.updatedAt or job.createdAt
            try:
                heartbeat = datetime.fromisoformat(raw_heartbeat)
            except (TypeError, ValueError):
                continue
            if (now - heartbeat).total_seconds() <= timeout_seconds:
                continue

            # 外置 Worker 的 Python heartbeat 线程可能被长时间的 NumPy / SciPy
            # 原生计算饿死；PID 仍存活时不能把正在收尾的任务抢先置为 interrupted。
            # embedded 模式中 workerPid 等于当前 API 进程，此时仍沿用 heartbeat
            # 超时判定，避免卡住的同进程线程永久占用任务。
            if job.workerPid and job.workerPid != os.getpid() and _is_local_process_alive(job.workerPid):
                logger.warning(
                    "Analysis job %s heartbeat is stale, but external worker pid %s is alive; keeping lease",
                    job.id,
                    job.workerPid,
                )
                continue

            reason = "worker_heartbeat_timeout" if job.workerHeartbeatAt else "worker_lost"
            updated = self._terminal_job(
                job,
                "interrupted",
                stages=job.stages,
                error_code=ANALYSIS_ERROR_CODES[reason],
                message="Worker 在规定时间内没有心跳，任务已失联；已保留最后进度，请重新分析。",
                finished_at=utc_now(),
                interrupted_at=utc_now(),
                interruption_code=reason,
            )
            if updated.canonicalStatus == "interrupted":
                recovered += 1
        return recovered

    def delete(self, job_id: str) -> bool:
        with self._lock:
            self._jobs.pop(job_id, None)
        deleted = self.control_plane.delete(job_id)
        path = self.storage.job_json_path(job_id)
        if path.exists():
            path.unlink()
            deleted = True
        return deleted

    def _terminal_job(
        self,
        job: AnalysisJobSummary,
        canonical_status: AnalysisCanonicalStatus,
        *,
        stages: list[AnalysisStage],
        error_code: str | None = None,
        message: str | None = None,
        internal_message: str | None = None,
        stage: str | None = None,
        progress: int | None = None,
        finished_at: str | None = None,
        canceled_at: str | None = None,
        cancel_requested_at: str | None = None,
        interrupted_at: str | None = None,
        interruption_code: str | None = None,
    ) -> AnalysisJobSummary:
        now = finished_at or utc_now()
        display = canonical_to_display_status(canonical_status)
        terminal_updates = {
            "canonicalStatus": canonical_status,
            "status": display,
            "displayStatus": display,
            "stage": stage or current_stage_from_stages(stages, fallback=job.stage),
            "progress": 100
            if progress is None and canonical_status == "succeeded"
            else progress
            if progress is not None
            else job.progress,
            "updatedAt": now,
            "finishedAt": now,
            "stages": stages,
            "errorCode": error_code,
            "errorMessage": message,
            "publicErrorMessage": message,
            "internalErrorMessage": internal_message,
            "cancelRequestedAt": cancel_requested_at or job.cancelRequestedAt,
            "canceledAt": canceled_at or job.canceledAt,
            "interruptedAt": interrupted_at or job.interruptedAt,
            "interruptionCode": interruption_code or job.interruptionCode,
        }

        def mutator(current: dict[str, object]) -> dict[str, object]:
            # The executor may hold a snapshot from before another process has
            # persisted immutable task references (for example scene revision).
            # Start from the current control-plane row so terminal updates cannot
            # overwrite those references with stale defaults from the snapshot.
            payload = dict(current)
            payload.update(terminal_updates)
            return self._payload(self._model(payload))

        updated = self.control_plane.mutate(
            job.id,
            mutator,
            expected_status=job.canonicalStatus,
            expected_worker_run_id=job.workerRunId,
        )
        return self._persist_payload(updated) or self.get(job.id) or job


class CancellationToken:
    # 取消令牌：供流水线在运行过程中检查"这个任务是不是被取消了"。
    def __init__(self, store: JobStore, job_id: str) -> None:
        self.store = store
        self.job_id = job_id

    def is_cancel_requested(self) -> bool:
        job = self.store.get(self.job_id)
        return bool(job and job.cancelRequestedAt and job.canonicalStatus not in TERMINAL_CANONICAL_STATUSES)

    def raise_if_cancelled(self) -> None:
        if self.is_cancel_requested():
            raise JobCanceledError("Analysis job cancellation requested")


class JobCanceledError(RuntimeError):
    # 任务被取消时抛出的异常
    pass


class WorkerLeaseLostError(RuntimeError):
    """Worker 无法继续证明自己拥有当前任务租约。"""


class StageTimeoutError(RuntimeError):
    # 某个阶段超时时抛出的异常
    pass


class ResourceLimiter:
    # 资源限制器：用信号量（Semaphore）限制同时运行的 CPU/GPU 任务数。
    def __init__(self, max_cpu_jobs: int = 1, max_gpu_jobs: int = 1) -> None:
        self.cpu = threading.Semaphore(max(1, max_cpu_jobs))
        self.gpu = threading.Semaphore(max(1, max_gpu_jobs))

    def run_cpu(self, fn: Callable[[], AnalysisPipelineResult]) -> AnalysisPipelineResult:
        # 在 CPU 信号量保护下执行 fn（默认实现只用到 CPU 限制）
        with self.cpu:
            return fn()


class AnalysisWorkerRuntime:
    # Worker 运行时：在后台线程里不断领取任务并执行分析流水线。
    # external 模式下本对象运行在独立 OS 进程；embedded 模式保留给兼容调用。
    def __init__(
        self,
        store: JobStore,
        *,
        pipeline_factory: Callable[[], object],
        on_completed: Callable[[AnalysisJobSummary, AnalysisPipelineResult], None],
        worker_id: str = "local-worker",
        resource_limiter: ResourceLimiter | None = None,
        on_terminal: Callable[[AnalysisJobSummary], None] | None = None,
    ) -> None:
        settings = get_settings()
        self.store = store
        self.pipeline_factory = pipeline_factory
        self.on_completed = on_completed
        self.worker_id = worker_id
        self.settings = settings
        self.resource_limiter = resource_limiter or ResourceLimiter(settings.max_cpu_jobs, settings.max_gpu_jobs)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()  # 通知线程停止
        self._wake_event = threading.Event()  # 通知线程"有新活了，别睡了"
        self._running_lock = threading.Lock()  # 保证同一时刻只跑一个任务
        self.on_terminal = on_terminal  # 任一 job 进入终态时回调（编排层用）

    def start(self) -> None:
        # 启动后台线程（如果还没在跑）。
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, name=self.worker_id, daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        # 停止后台线程。
        self._stop_event.set()
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout)

    def notify(self) -> None:
        # 唤醒线程（有新任务入队时调用）。
        self._wake_event.set()

    def run_one(self) -> AnalysisJobSummary | None:
        # 尝试执行一个任务（非阻塞拿锁，拿不到说明正在跑，返回 None）。
        if not self._running_lock.acquire(blocking=False):
            return None
        try:
            job = self.store.claim_next(self.worker_id)
            if job is None:
                return None
            return self._execute(job)
        finally:
            self._running_lock.release()

    def run_job(self, job_id: str) -> AnalysisJobSummary | None:
        # 指定 job_id 执行一个任务。
        if not self._running_lock.acquire(blocking=False):
            return None
        try:
            job = self.store.claim(job_id, self.worker_id)
            if job is None:
                return self.store.get(job_id)
            return self._execute(job)
        finally:
            self._running_lock.release()

    def _loop(self) -> None:
        # 后台线程主循环：不断领取任务；没任务就睡 0.5 秒等唤醒。
        while not self._stop_event.is_set():
            ran = self.run_one()
            if ran is None:
                self._wake_event.wait(self.settings.analysis_worker_poll_interval_seconds)
                self._wake_event.clear()

    def _execute(self, job: AnalysisJobSummary) -> AnalysisJobSummary:
        """为单次执行建立独立 heartbeat 循环，再进入原有 Pipeline 执行体。"""
        heartbeat_stop = threading.Event()
        heartbeat_failed = threading.Event()
        heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(job, heartbeat_stop, heartbeat_failed),
            name=f"{self.worker_id}-heartbeat-{job.id}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            return self._execute_pipeline(job, heartbeat_failed)
        finally:
            heartbeat_stop.set()
            heartbeat_thread.join(timeout=max(1.0, self.settings.analysis_worker_heartbeat_interval_seconds * 2))

    def _heartbeat_loop(
        self,
        job: AnalysisJobSummary,
        stop_event: threading.Event,
        failed_event: threading.Event,
    ) -> None:
        """heartbeat 不依赖阶段回调，覆盖长时间没有进度事件的模型阶段。"""
        run_id = job.workerRunId
        if not run_id or not self.store.heartbeat(job.id, run_id):
            failed_event.set()
            self._stop_event.set()
            logger.warning("Worker %s lost lease before executing job %s", self.worker_id, job.id)
            return
        while not stop_event.wait(self.settings.analysis_worker_heartbeat_interval_seconds):
            if not self.store.heartbeat(job.id, run_id):
                failed_event.set()
                self._stop_event.set()
                logger.warning("Worker %s lost lease while executing job %s", self.worker_id, job.id)
                return

    def _execute_pipeline(
        self,
        job: AnalysisJobSummary,
        heartbeat_failed: threading.Event,
    ) -> AnalysisJobSummary:
        # 真正执行一个任务：构造取消令牌 → 跑流水线 → 根据结果更新任务状态。
        # 含重试、取消、超时、异常兜底。
        token = CancellationToken(self.store, job.id)
        latest = job
        retry_attempts = 0

        def progress_callback(stage_result: PipelineStageResult) -> None:
            # 流水线每完成一个阶段就回调这里，更新任务阶段进度。
            nonlocal latest
            if heartbeat_failed.is_set() or not self.store.is_lease_current(job.id, job.workerRunId):
                raise WorkerLeaseLostError(f"Worker lease lost for job {job.id}")
            token.raise_if_cancelled()
            latest = self.store.mark_stage(latest, stage_from_pipeline(stage_result))
            self._raise_if_stage_timed_out(latest)

        def run_executor() -> AnalysisPipelineResult:
            # 按 analysisKind + executionMode 分发执行体（SingleView / MultiView late|joint）。
            from app.services.analysis_executor_dispatch import resolve_executor

            executor = resolve_executor(
                job.analysisKind, self.store, self.pipeline_factory,
                execution_mode=getattr(job, "executionMode", None),
            )
            return executor.execute(job, token, progress_callback)

        try:
            token.raise_if_cancelled()
            while True:
                try:
                    result = self.resource_limiter.run_cpu(run_executor)
                    break
                except WorkerLeaseLostError:
                    raise
                except StageTimeoutError:
                    raise
                except JobCanceledError:
                    raise
                except Exception:
                    # 可重试阶段才重试，超过最大次数就抛
                    if latest.stage not in RETRYABLE_STAGE_IDS or retry_attempts >= self.settings.job_max_retries:
                        raise
                    retry_attempts += 1
                    retry_mode = resolve_progress_mode(latest.analysisKind, latest.executionMode)
                    retry_label, _detail = stage_details_for(retry_mode, latest.stage)
                    retry_stage = AnalysisStage(
                        id=latest.stage,
                        label=retry_label,
                        status="active",
                        detail="阶段执行失败，正在按策略重试",
                        progress=latest.progress,
                        retryCount=retry_attempts,
                        publicMessage="阶段执行失败，正在按策略重试",
                    )
                    latest = self.store.mark_stage(latest, retry_stage)
            if heartbeat_failed.is_set() or not self.store.is_lease_current(job.id, job.workerRunId):
                raise WorkerLeaseLostError(f"Worker lease lost for job {job.id}")
            if token.is_cancel_requested():
                self._cleanup_tmp(job.id)
                return self._notify_terminal(self.store.mark_canceled(latest))
            progress_mode = resolve_progress_mode(job.analysisKind, job.executionMode)
            stages = analysis_stages_from_pipeline(result, mode=progress_mode)
            if result.status == "completed":
                latest = self.store.mark_succeeded(latest, stages)
                self._notify_terminal(latest)
                self.on_completed(latest, result)
                return latest
            self._cleanup_tmp(job.id)
            return self._notify_terminal(self.store.mark_failed(latest, stages=stages, message=result.message))
        except WorkerLeaseLostError as exc:
            logger.warning("Analysis job %s execution lease lost: %s", job.id, exc)
            return self.store.get(job.id) or latest
        except JobCanceledError:
            self._cleanup_tmp(job.id)
            return self._notify_terminal(self.store.mark_canceled(latest))
        except StageTimeoutError as exc:
            logger.warning("Analysis job %s timed out at stage %s", job.id, latest.stage)
            mode = resolve_progress_mode(latest.analysisKind, latest.executionMode)
            timeout_label, _detail = stage_details_for(mode, latest.stage)
            timed_out_stage = AnalysisStage(
                id=latest.stage,
                label=timeout_label,
                status="failed",
                detail="分析阶段超时",
                progress=100,
                errorCode=ANALYSIS_ERROR_CODES["stage_timeout"],
                publicMessage="分析阶段超时，请缩短视频、提高抽帧间隔或检查模型运行环境。",
                internalMessage=str(exc),
                retryCount=retry_attempts,
            )
            stages = merge_stage_progress(latest.stages, timed_out_stage, mode=mode)
            self._cleanup_tmp(job.id)
            return self._notify_terminal(
                self.store.mark_failed(
                    latest,
                    stages=stages,
                    message="分析阶段超时，请缩短视频、提高抽帧间隔或检查模型运行环境。",
                    error_code=ANALYSIS_ERROR_CODES["stage_timeout"],
                    internal_message=str(exc),
                )
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Analysis job %s failed in worker", job.id)
            mode = resolve_progress_mode(latest.analysisKind, latest.executionMode)
            failed_label, _detail = stage_details_for(mode, latest.stage)
            failed_stage = AnalysisStage(
                id=latest.stage,
                label=failed_label,
                status="failed",
                detail="分析任务执行失败",
                progress=100,
                errorCode=ANALYSIS_ERROR_CODES["internal_error"],
                publicMessage="分析任务执行失败，请检查输入视频和模型配置。",
                internalMessage=str(exc),
                retryCount=retry_attempts,
            )
            stages = merge_stage_progress(latest.stages, failed_stage, mode=mode)
            self._cleanup_tmp(job.id)
            return self._notify_terminal(
                self.store.mark_failed(
                    latest,
                    stages=stages,
                    message="分析任务执行失败，请检查输入视频和模型配置。",
                    error_code=ANALYSIS_ERROR_CODES["internal_error"],
                    internal_message=str(exc),
                )
            )

    def _notify_terminal(self, job: AnalysisJobSummary) -> AnalysisJobSummary:
        """任一 job 进入终态时通知编排层（如推进双摄 Parent），失败不影响主流程。"""
        if self.on_terminal is not None:
            try:
                self.on_terminal(job)
            except Exception:  # noqa: BLE001
                logger.exception("on_terminal callback failed for job %s", job.id)
        return job

    def _raise_if_stage_timed_out(self, job: AnalysisJobSummary) -> None:
        # 内部：检查当前 active 阶段是否超过配置的最大时长，超时则抛 StageTimeoutError。
        timeout_seconds = self.settings.job_stage_timeout_seconds
        if timeout_seconds <= 0:
            return
        active_stage = next((stage for stage in job.stages if stage.status == "active"), None)
        if active_stage is None or active_stage.startedAt is None:
            return
        try:
            started = datetime.fromisoformat(active_stage.startedAt)
        except ValueError:
            return
        elapsed = (datetime.now(UTC) - started).total_seconds()
        if elapsed > timeout_seconds:
            raise StageTimeoutError(f"Stage {active_stage.id} exceeded {timeout_seconds}s")

    def _cleanup_tmp(self, job_id: str) -> None:
        # 内部：任务结束后清理临时目录。
        tmp_path = self.store.storage.tmp_dir / job_id
        if tmp_path.exists():
            self.store.storage.delete_path_tree(tmp_path)


def analysis_stages_from_pipeline(
    result: AnalysisPipelineResult,
    *,
    mode: ProgressMode = "single_view",
) -> list[AnalysisStage]:
    """把 pipeline/Composer 结果投影为当前模式的完整顶层阶段图。"""
    first_stage = stage_ids(mode)[0]
    bootstrap_stage = "video-read" if mode == "single_view" else first_stage
    stages = build_stage_snapshot(mode, bootstrap_stage)
    # 结果已经是终态快照时，前置素材检查视为完成；运行中的结果仍由回调更新。
    if mode != "single_view":
        stages = merge_stage_progress(
            stages,
            AnalysisStage(
                id=first_stage,
                label=stage_definition(mode, first_stage).label,
                status="done",
                detail=stage_definition(mode, first_stage).detail,
                progress=100,
            ),
            mode=mode,
        )
    for pipeline_stage in result.stages:
        stage_id = pipeline_stage.id
        if stage_id not in stage_ids(mode):
            continue
        stages = merge_stage_progress(stages, stage_from_pipeline(pipeline_stage), mode=mode)

    if mode == "single_view" and "frame-sampling" in stage_ids(mode):
        frame_stage = next((stage for stage in stages if stage.id == "frame-sampling"), None)
        if frame_stage is not None and frame_stage.status == "pending":
            stages = merge_stage_progress(
                stages,
                AnalysisStage(
                    id="frame-sampling",
                    label="抽帧采样",
                    status="done" if result.video_id else "skipped",
                    detail="已按配置帧间隔读取视频帧" if result.video_id else "未提供视频，跳过真实抽帧",
                    progress=100,
                ),
                mode=mode,
            )
    return normalize_stage_snapshot(stages, mode)


def _duration_ms(started: str | None, ended: str | None) -> int | None:
    # 内部：算两个 ISO 时间字符串之间相差的毫秒数。
    if not started or not ended:
        return None
    try:
        return max(0, int((datetime.fromisoformat(ended) - datetime.fromisoformat(started)).total_seconds() * 1000))
    except ValueError:
        return None


def _stable_hash(payload: object) -> str:
    # 内部：把一个对象稳定地序列化成 JSON 再做 SHA256（用于签名/去重）。
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
