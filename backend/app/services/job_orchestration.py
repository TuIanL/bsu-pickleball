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

from datetime import datetime, timezone
import hashlib
import inspect
import json
import logging
import threading
from pathlib import Path
from typing import Callable
from uuid import uuid4

from app.core.config import get_settings
from app.schemas.analysis import (
    ANALYSIS_ERROR_CODES,
    STABLE_ANALYSIS_STAGE_IDS,
    AnalysisCanonicalStatus,
    AnalysisDeleteResult,
    AnalysisJobCreate,
    AnalysisJobStatus,
    AnalysisJobSummary,
    AnalysisStage,
    AnalysisStageId,
    AnalysisStageStatus,
    build_match_context,
)
from app.schemas.pipeline import AnalysisPipelineResult, PipelineStageResult
from app.services.storage_service import StorageService


logger = logging.getLogger(__name__)

# 终态（任务到此就结束了，不能再变）：成功 / 失败 / 已取消
TERMINAL_CANONICAL_STATUSES: set[AnalysisCanonicalStatus] = {"succeeded", "failed", "canceled"}
# 仍"活跃"的兼容状态：上传中 / 排队中 / 处理中
ACTIVE_COMPAT_STATUSES: set[AnalysisJobStatus] = {"uploaded", "queued", "processing"}
# 允许重试的阶段：视频读取 / 报告 / 可视化
RETRYABLE_STAGE_IDS = {"video-read", "report", "visualization"}

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
}


def utc_now() -> str:
    # 返回当前 UTC 时间的 ISO8601 字符串（带时区）
    return datetime.now(timezone.utc).isoformat()


def canonical_to_display_status(status: AnalysisCanonicalStatus) -> AnalysisJobStatus:
    # 把"规范状态"翻译成"对外展示状态"
    return {
        "queued": "queued",
        "running": "processing",
        "succeeded": "completed",
        "failed": "failed",
        "canceled": "canceled",
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
    }[status]


def build_stages(active_stage: AnalysisStageId = "report", failed: bool = False) -> list[AnalysisStage]:
    # 构造一组阶段：active_stage 之前的全 done，active_stage 本身为 active/failed，之后的 pending。
    if active_stage not in ORDERED_STAGES:
        active_stage = "queue"

    active_index = ORDERED_STAGES.index(active_stage)
    stages: list[AnalysisStage] = []

    for index, stage_id in enumerate(ORDERED_STAGES):
        label, detail = STAGE_DETAILS[stage_id]
        status: AnalysisStageStatus = "pending"
        progress = 0

        if index < active_index or (active_stage == "report" and not failed):
            status = "done"
            progress = 100
        elif index == active_index:
            status = "failed" if failed else "active"
            progress = 100 if failed else 10

        stages.append(
            AnalysisStage(
                id=stage_id,
                label=label,
                status=status,
                detail=detail,
                progress=progress,
                publicMessage=detail,
            )
        )

    return stages


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


def compute_progress_from_stages(stages: list[AnalysisStage]) -> int:
    # 根据各阶段状态估算总进度（0~99）：完成的算 1，进行中的按自身进度算。
    if not stages:
        return 0
    total = len(stages)
    complete_credit = sum(1 for stage in stages if stage.status in {"done", "skipped"})
    active_credit = sum((stage.progress / 100) for stage in stages if stage.status == "active")
    return min(99, int(((complete_credit + active_credit) / total) * 100))


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


def merge_stage_progress(stages: list[AnalysisStage], stage: AnalysisStage) -> list[AnalysisStage]:
    # 把"新来的一个阶段"合并进已有阶段列表：更新同 id 的阶段，
    # 并做一致性修正（active 阶段开始时记录时间；结束阶段补 endedAt/进度；
    # 出现新 active 时把旧的 active 收尾为 done 等）。
    existing: dict[str, AnalysisStage] = {item.id: item for item in stages}
    prior = existing.get(stage.id)
    now = utc_now()

    payload = stage.model_dump()
    if stage.status == "active" and not payload.get("startedAt"):
        payload["startedAt"] = prior.startedAt if prior else now
    if stage.status in {"done", "skipped", "failed", "canceled"}:
        payload["startedAt"] = payload.get("startedAt") or (prior.startedAt if prior else now)
        payload["endedAt"] = payload.get("endedAt") or now
        payload["progress"] = payload.get("progress") or 100
        payload["durationMs"] = payload.get("durationMs") or _duration_ms(payload.get("startedAt"), payload.get("endedAt"))
    payload["publicMessage"] = payload.get("publicMessage") or payload.get("detail")
    existing[stage.id] = AnalysisStage.model_validate(payload)

    if stage.status in {"done", "skipped", "failed", "canceled"} and stage.id in ORDERED_STAGES:
        # 结束一个阶段时，把排在它前面、还卡在 active 的阶段补成 done
        stage_index = ORDERED_STAGES.index(stage.id)
        for prior_stage_id in ORDERED_STAGES[:stage_index]:
            prior_stage = existing.get(prior_stage_id)
            if prior_stage and prior_stage.status == "active":
                prior_payload = prior_stage.model_dump()
                prior_payload.update(
                    {
                        "status": "done",
                        "endedAt": now,
                        "durationMs": prior_stage.durationMs
                        or _duration_ms(prior_stage.startedAt, now),
                        "progress": 100,
                    }
                )
                existing[prior_stage_id] = AnalysisStage.model_validate(prior_payload)

    if stage.status == "active":
        # 新 active 出现时，把其它仍是 active 的旧阶段收尾为 done
        for item in list(existing.values()):
            if item.id != stage.id and item.status == "active":
                item_payload = item.model_dump()
                item_payload.update(
                    {
                        "status": "done",
                        "endedAt": now,
                        "durationMs": item.durationMs or _duration_ms(item.startedAt, now),
                        "progress": 100,
                    }
                )
                existing[item.id] = AnalysisStage.model_validate(item_payload)

    # 保持 ORDERED_STAGES 的顺序，最后再追加 ORDERED_STAGES 之外的额外阶段
    ordered_ids = [stage_id for stage_id in ORDERED_STAGES if stage_id in existing]
    extra_ids = [stage_id for stage_id in existing if stage_id not in ORDERED_STAGES]
    return [existing[stage_id] for stage_id in ordered_ids + extra_ids]


def analysis_signature(payload: AnalysisJobCreate) -> tuple[str, str]:
    # 计算任务的"输入签名"和"配置签名"（用于去重：相同输入+相同配置视为同一任务）。
    settings = get_settings()
    config_payload = {
        "frameStride": payload.frameStride,
        "enableModelInference": settings.enable_model_inference,
        "enablePoseInference": settings.enable_pose_inference,
        "detectorModel": settings.default_detector_model,
        "detectorDevice": settings.detector_device,
        "rtmposeConfig": settings.rtmpose_config_path,
        "rtmposeCheckpoint": settings.rtmpose_checkpoint_path,
        "rtmposeDevice": settings.rtmpose_device,
        "poseSchema": settings.pose_keypoint_schema,
        # 分析模式由是否提供标定/视频决定
        "analysisMode": "real" if payload.calibrationId else "limited" if payload.videoId else "demo",
    }
    input_payload = {
        "videoId": payload.videoId,
        "calibrationId": payload.calibrationId,
        "sourceFps": payload.sourceFps or payload.metadata.sourceFps,
        "metadata": payload.metadata.model_dump(mode="json"),
        "clipStartMs": payload.clipStartMs,
        "clipEndMs": payload.clipEndMs,
        "captureSegmentId": payload.captureSegmentId,
        "segmentVersion": payload.segmentVersion,
    }
    return _stable_hash(input_payload), _stable_hash(config_payload)


class JobStore:
    # 任务的持久化存储：内存字典 + 磁盘 JSON（带线程锁保证并发安全）。
    def __init__(self, storage: StorageService | None = None) -> None:
        self.storage = storage or StorageService()
        self._lock = threading.RLock()  # 可重入锁：同一线程可多次加锁
        self._jobs: dict[str, AnalysisJobSummary] = {}

    def create_job(self, payload: AnalysisJobCreate, *, job_id: str | None = None, report_id: str | None = None) -> AnalysisJobSummary:
        # 新建一个任务，初始状态为 queued（排队中）。
        now = utc_now()
        input_sig, config_sig = analysis_signature(payload)
        job_id = job_id or f"job-{uuid4().hex[:10]}"
        report_id = report_id or f"PV-{job_id.upper()}"
        mode = "real" if payload.calibrationId else "limited" if payload.videoId else "demo"
        job = AnalysisJobSummary(
            id=job_id,
            status="queued",
            canonicalStatus="queued",
            displayStatus="queued",
            stage="queue",
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
            stages=build_stages("queue"),
            reportId=report_id,
            videoId=payload.videoId,
            calibrationId=payload.calibrationId,
            analysisMode=mode,
        )
        return self.save(job)

    def save(self, job: AnalysisJobSummary) -> AnalysisJobSummary:
        # 保存任务：先统一化，再写内存 + 落盘（原子写）。
        normalized = normalize_job(job)
        with self._lock:
            self._jobs[normalized.id] = normalized
            self.storage.write_json_atomic(
                self.storage.job_json_path(normalized.id),
                normalized.model_dump(mode="json"),
            )
        return normalized

    def update(self, job_id: str, **updates: object) -> AnalysisJobSummary | None:
        # 局部更新任务的若干字段（其它字段保持原样）。
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return None
            payload = job.model_dump()
            payload.update(updates)
            payload["updatedAt"] = utc_now()
            return self.save(AnalysisJobSummary.model_validate(payload))

    def get(self, job_id: str) -> AnalysisJobSummary | None:
        # 取任务：先查内存，再查磁盘。
        with self._lock:
            cached = self._jobs.get(job_id)
            if cached is not None:
                return cached

            path = self.storage.job_json_path(job_id)
            if not path.exists():
                return None
            try:
                job = normalize_job(AnalysisJobSummary.model_validate(self.storage.read_json(path)))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Skipping unreadable analysis job summary %s: %s", path, exc)
                return None
            self._jobs[job_id] = job
            return job

    def list(self) -> list[AnalysisJobSummary]:
        # 列出所有任务：磁盘 jobs 目录 + 内存中未落盘的，按更新时间倒序。
        jobs: dict[str, AnalysisJobSummary] = {}
        jobs_dir = self.storage.jobs_dir()
        if jobs_dir.exists():
            for path in sorted(jobs_dir.glob("*.json")):
                job = self._load_job_from_path(path)
                if job is not None:
                    jobs[job.id] = job
        with self._lock:
            jobs.update(self._jobs)
        return sorted(jobs.values(), key=lambda job: (job.updatedAt or job.createdAt, job.createdAt), reverse=True)

    def find_by_signature(self, input_signature: str, config_signature: str) -> AnalysisJobSummary | None:
        # 按"输入+配置签名"查找一个"非终态"的已有任务（用于去重）。
        for job in self.list():
            if (
                job.inputSignature == input_signature
                and job.configSignature == config_signature
                and job.canonicalStatus in {"queued", "succeeded"}
            ):
                return job
        return None

    def claim_next(self, worker_id: str) -> AnalysisJobSummary | None:
        # Worker 来"领取"下一个可执行的排队任务：按优先级、排队时间排序，取最高。
        with self._lock:
            queued = [job for job in self.list() if job.canonicalStatus == "queued" and not job.cancelRequestedAt]
            if not queued:
                return None
            queued.sort(key=lambda job: (-job.priority, job.queuedAt or job.createdAt, job.id))
            return self._claim(queued[0], worker_id)

    def claim(self, job_id: str, worker_id: str) -> AnalysisJobSummary | None:
        # 指定 job_id 领取（用于手动触发某个任务）。
        with self._lock:
            job = self.get(job_id)
            if job is None or job.canonicalStatus != "queued" or job.cancelRequestedAt:
                return None
            return self._claim(job, worker_id)

    def _claim(self, job: AnalysisJobSummary, worker_id: str) -> AnalysisJobSummary:
        # 内部：把任务从 queued 置为 running（processing），并标记阶段开始。
        now = utc_now()
        payload = job.model_dump()
        payload.update(
            {
                "canonicalStatus": "running",
                "status": "processing",
                "displayStatus": "processing",
                "stage": "video-read",
                "progress": max(job.progress, 12),
                "startedAt": now,
                "updatedAt": now,
                "workerId": worker_id,
                "attempt": job.attempt + 1,
                "stages": merge_stage_progress(
                    job.stages,
                    AnalysisStage(
                        id="video-read",
                        label=STAGE_DETAILS["video-read"][0],
                        status="active",
                        detail="正在读取上传视频元数据和帧流",
                        progress=10,
                    ),
                ),
            }
        )
        return self.save(AnalysisJobSummary.model_validate(payload))

    def cancel(self, job_id: str) -> tuple[AnalysisJobSummary | None, str]:
        # 取消任务：返回 (任务, 状态)。状态可能是 not_found / terminal / canceled / requested。
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return None, "not_found"
            if job.canonicalStatus in TERMINAL_CANONICAL_STATUSES:
                return job, "terminal"
            now = utc_now()
            if job.canonicalStatus == "queued":
                # 还在排队就直接置为已取消
                canceled_stages = merge_stage_progress(
                    job.stages,
                    AnalysisStage(
                        id=job.stage,
                        label=STAGE_DETAILS.get(job.stage, (job.stage, ""))[0],
                        status="canceled",
                        detail="任务已在排队阶段取消",
                        progress=100,
                        errorCode=ANALYSIS_ERROR_CODES["job_canceled"],
                    ),
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
            # 已在运行：只记录"取消请求"，由 Worker 在循环中检查并真正停止
            updated = self.update(job_id, cancelRequestedAt=job.cancelRequestedAt or now)
            return updated, "requested"

    def mark_stage(self, job: AnalysisJobSummary, stage: AnalysisStage) -> AnalysisJobSummary:
        # 更新任务的某个阶段进度；若该阶段失败，则把整个任务置为失败。
        stages = merge_stage_progress(job.stages, stage)
        updates: dict[str, object] = {
            "canonicalStatus": "running",
            "status": "processing",
            "displayStatus": "processing",
            "stage": current_stage_from_stages(stages, fallback=stage.id),
            "progress": compute_progress_from_stages(stages),
            "stages": stages,
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
        updated = self.update(job.id, **updates)
        return updated or job

    def mark_succeeded(self, job: AnalysisJobSummary, stages: list[AnalysisStage]) -> AnalysisJobSummary:
        # 标记任务成功：补上 report 阶段为 done，整体置为 succeeded。
        report_stage = AnalysisStage(
            id="report",
            label=STAGE_DETAILS["report"][0],
            status="done",
            detail="已生成前端报告 JSON",
            progress=100,
        )
        merged = merge_stage_progress(stages, report_stage)
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
        # 标记任务失败。
        return self._terminal_job(
            job,
            "failed",
            stages=stages,
            error_code=error_code or ANALYSIS_ERROR_CODES["stage_failed"],
            message=message,
            internal_message=internal_message,
            stage=first_failed_stage(stages),
            progress=compute_progress_from_stages(stages),
        )

    def mark_canceled(self, job: AnalysisJobSummary, *, message: str = "任务已取消") -> AnalysisJobSummary:
        # 标记任务已取消。
        canceled_stage = AnalysisStage(
            id=job.stage,
            label=STAGE_DETAILS.get(job.stage, (job.stage, ""))[0],
            status="canceled",
            detail=message,
            progress=100,
            errorCode=ANALYSIS_ERROR_CODES["job_canceled"],
        )
        stages = merge_stage_progress(job.stages, canceled_stage)
        return self._terminal_job(
            job,
            "canceled",
            stages=stages,
            error_code=ANALYSIS_ERROR_CODES["job_canceled"],
            message=message,
            canceled_at=utc_now(),
        )

    def delete(self, job_id: str) -> bool:
        # 删除任务：内存和磁盘都清掉。
        with self._lock:
            self._jobs.pop(job_id, None)
            path = self.storage.job_json_path(job_id)
            if path.exists():
                path.unlink()
                return True
            return False

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
    ) -> AnalysisJobSummary:
        # 内部：把一个任务置为"终态"（成功/失败/取消），统一更新各类时间戳与状态字段。
        now = finished_at or utc_now()
        display = canonical_to_display_status(canonical_status)
        payload = job.model_dump()
        payload.update(
            {
                "canonicalStatus": canonical_status,
                "status": display,
                "displayStatus": display,
                "stage": stage or current_stage_from_stages(stages, fallback=job.stage),
                "progress": 100 if progress is None and canonical_status in {"succeeded", "canceled"} else progress if progress is not None else job.progress,
                "updatedAt": now,
                "finishedAt": now,
                "stages": stages,
                "errorCode": error_code,
                "errorMessage": message,
                "publicErrorMessage": message,
                "internalErrorMessage": internal_message,
                "cancelRequestedAt": cancel_requested_at or job.cancelRequestedAt,
                "canceledAt": canceled_at or job.canceledAt,
            }
        )
        return self.save(AnalysisJobSummary.model_validate(payload))

    def _load_job_from_path(self, path: Path) -> AnalysisJobSummary | None:
        # 内部：从磁盘读一个任务 JSON（损坏的跳过，不报错）。
        try:
            job = normalize_job(AnalysisJobSummary.model_validate(self.storage.read_json(path)))
        except Exception as exc:  # noqa: BLE001 - corrupted persisted jobs should not break the task list.
            logger.warning("Skipping unreadable analysis job summary %s: %s", path, exc)
            return None
        with self._lock:
            self._jobs[job.id] = job
        return job


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
    def __init__(
        self,
        store: JobStore,
        *,
        pipeline_factory: Callable[[], object],
        on_completed: Callable[[AnalysisJobSummary, AnalysisPipelineResult], None],
        worker_id: str = "local-worker",
        resource_limiter: ResourceLimiter | None = None,
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
                self._wake_event.wait(0.5)
                self._wake_event.clear()

    def _execute(self, job: AnalysisJobSummary) -> AnalysisJobSummary:
        # 真正执行一个任务：构造取消令牌 → 跑流水线 → 根据结果更新任务状态。
        # 含重试、取消、超时、异常兜底。
        token = CancellationToken(self.store, job.id)
        payload = AnalysisJobCreate(
            metadata=job.metadata,
            videoId=job.videoId,
            calibrationId=job.calibrationId,
            frameStride=job.frameStride,
            sourceFps=job.sourceFps or job.metadata.sourceFps,
            priority=job.priority,
            clipStartMs=getattr(job, 'clipStartMs', None),
            clipEndMs=getattr(job, 'clipEndMs', None),
        )
        latest = job
        retry_attempts = 0

        def progress_callback(stage_result: PipelineStageResult) -> None:
            # 流水线每完成一个阶段就回调这里，更新任务阶段进度。
            nonlocal latest
            token.raise_if_cancelled()
            latest = self.store.mark_stage(latest, stage_from_pipeline(stage_result))
            self._raise_if_stage_timed_out(latest)

        try:
            token.raise_if_cancelled()

            def run_pipeline() -> AnalysisPipelineResult:
                # 调用流水线（兼容旧版本：没有 cancellation_token 参数时退化为不带它调用）。
                if job.metadata.capture_take_id:
                    from app.services.storage_service import StorageService
                    StorageService.register_capture_job_from_take(job.id, job.metadata.capture_take_id)
                elif job.metadata.session_dir:
                    from app.services.storage_service import StorageService
                    StorageService.register_capture_job(job.id, job.metadata.session_dir)
                pipeline = self.pipeline_factory()
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
                }
                signature = inspect.signature(pipeline.run)
                accepts_kwargs = any(
                    parameter.kind is inspect.Parameter.VAR_KEYWORD
                    for parameter in signature.parameters.values()
                )
                if not accepts_kwargs:
                    run_kwargs = {
                        key: value
                        for key, value in run_kwargs.items()
                        if key in signature.parameters
                    }
                return pipeline.run(**run_kwargs)

            while True:
                try:
                    result = self.resource_limiter.run_cpu(run_pipeline)
                    break
                except StageTimeoutError:
                    raise
                except JobCanceledError:
                    raise
                except Exception:
                    # 可重试阶段才重试，超过最大次数就抛
                    if latest.stage not in RETRYABLE_STAGE_IDS or retry_attempts >= self.settings.job_max_retries:
                        raise
                    retry_attempts += 1
                    retry_stage = AnalysisStage(
                        id=latest.stage,
                        label=STAGE_DETAILS.get(latest.stage, (latest.stage, ""))[0],
                        status="active",
                        detail="阶段执行失败，正在按策略重试",
                        progress=latest.progress,
                        retryCount=retry_attempts,
                        publicMessage="阶段执行失败，正在按策略重试",
                    )
                    latest = self.store.mark_stage(latest, retry_stage)
            if token.is_cancel_requested():
                self._cleanup_tmp(job.id)
                return self.store.mark_canceled(latest)
            stages = analysis_stages_from_pipeline(result)
            if result.status == "completed":
                latest = self.store.mark_succeeded(latest, stages)
                self.on_completed(latest, result)
                return latest
            self._cleanup_tmp(job.id)
            return self.store.mark_failed(latest, stages=stages, message=result.message)
        except JobCanceledError:
            self._cleanup_tmp(job.id)
            return self.store.mark_canceled(latest)
        except StageTimeoutError as exc:
            logger.warning("Analysis job %s timed out at stage %s", job.id, latest.stage)
            timed_out_stage = AnalysisStage(
                id=latest.stage,
                label=STAGE_DETAILS.get(latest.stage, (latest.stage, ""))[0],
                status="failed",
                detail="分析阶段超时",
                progress=100,
                errorCode=ANALYSIS_ERROR_CODES["stage_timeout"],
                publicMessage="分析阶段超时，请缩短视频、提高抽帧间隔或检查模型运行环境。",
                internalMessage=str(exc),
                retryCount=retry_attempts,
            )
            stages = merge_stage_progress(latest.stages, timed_out_stage)
            self._cleanup_tmp(job.id)
            return self.store.mark_failed(
                latest,
                stages=stages,
                message="分析阶段超时，请缩短视频、提高抽帧间隔或检查模型运行环境。",
                error_code=ANALYSIS_ERROR_CODES["stage_timeout"],
                internal_message=str(exc),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("Analysis job %s failed in worker", job.id)
            failed_stage = AnalysisStage(
                id=latest.stage,
                label=STAGE_DETAILS.get(latest.stage, (latest.stage, ""))[0],
                status="failed",
                detail="分析任务执行失败",
                progress=100,
                errorCode=ANALYSIS_ERROR_CODES["internal_error"],
                publicMessage="分析任务执行失败，请检查输入视频和模型配置。",
                internalMessage=str(exc),
                retryCount=retry_attempts,
            )
            stages = merge_stage_progress(latest.stages, failed_stage)
            self._cleanup_tmp(job.id)
            return self.store.mark_failed(
                latest,
                stages=stages,
                message="分析任务执行失败，请检查输入视频和模型配置。",
                error_code=ANALYSIS_ERROR_CODES["internal_error"],
                internal_message=str(exc),
            )

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
        elapsed = (datetime.now(timezone.utc) - started).total_seconds()
        if elapsed > timeout_seconds:
            raise StageTimeoutError(f"Stage {active_stage.id} exceeded {timeout_seconds}s")

    def _cleanup_tmp(self, job_id: str) -> None:
        # 内部：任务结束后清理临时目录。
        tmp_path = self.store.storage.tmp_dir / job_id
        if tmp_path.exists():
            self.store.storage.delete_path_tree(tmp_path)


def analysis_stages_from_pipeline(result: AnalysisPipelineResult) -> list[AnalysisStage]:
    # 把流水线结果里的阶段，转换成对外展示的阶段列表（补上 upload/queue 两个前置阶段）。
    stages: list[AnalysisStage] = [
        AnalysisStage(id="upload", label="视频上传", status="done", detail="上传视频已保存", progress=100),
        AnalysisStage(id="queue", label="任务排队", status="done", detail="任务已进入后端分析流程", progress=100),
    ]
    seen_ids = {"upload", "queue"}
    for stage in result.stages:
        if stage.id in seen_ids:
            continue
        seen_ids.add(stage.id)
        stages.append(stage_from_pipeline(stage))

    if "frame-sampling" not in seen_ids:
        insert_at = min(4, len(stages))
        stages.insert(
            insert_at,
            AnalysisStage(
                id="frame-sampling",
                label="抽帧采样",
                status="done" if result.video_id else "skipped",
                detail="已按配置帧间隔读取视频帧" if result.video_id else "未提供视频，跳过真实抽帧",
                progress=100,
            ),
        )
    return stages


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
