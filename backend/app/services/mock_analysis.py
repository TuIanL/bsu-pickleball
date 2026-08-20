"""模拟分析服务 —— 提供 MVP 阶段的任务 CRUD、后台 Worker 调度和演示报告生成。

这个模块是"对外给路由层（api）用的分析服务门面"：
- 创建/查询/删除/取消分析任务；
- 把任务交给后台 Worker（AnalysisWorkerRuntime）执行；
- 当分析完成后，根据真实 pipeline 结果拼出一份"演示报告"给前端。

demo 模式下（没有真实视频）会直接返回一份写死的样例报告（DEMO_REPORT），
让前端在还没有接入真实视频时也有完整界面可看。
"""

from __future__ import annotations

import logging
import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from uuid import uuid4

from fastapi import BackgroundTasks

from app.schemas.analysis import (
    ANALYSIS_ERROR_CODES,
    AnalysisDeleteResult,
    AnalysisJobCreate,
    AnalysisJobSummary,
    AnalysisReport,
    AnalysisStage,
    AnalysisStageId,
    AnalysisUploadMetadata,
)
from app.schemas.pipeline import AnalysisPipelineResult
from app.services.analysis_pipeline import AnalysisPipeline
from app.services.job_orchestration import (
    ACTIVE_COMPAT_STATUSES,
    AnalysisWorkerRuntime,
    JobStore,
    analysis_signature,
    analysis_stages_from_pipeline,
    build_stages,
    compute_progress_from_stages,
    current_stage_from_stages,
    first_failed_stage,
    merge_stage_progress,
    normalize_job,
    utc_now,
)
from app.services.storage_service import StorageService
from app.services.video_service import video_service

logger = logging.getLogger(__name__)

# 内存中的各种缓存（MVP 阶段用，重启即丢，磁盘上有备份）
JOBS: dict[str, AnalysisJobSummary] = {}
REPORTS: dict[str, AnalysisReport] = {}
RESULTS: dict[str, AnalysisPipelineResult] = {}
_LOCK = Lock()  # 保护上面这些内存字典的线程锁
_STORAGE = StorageService()
_JOB_STORE = JobStore(_STORAGE)


def _pipeline_factory(analysis_options: dict | None = None) -> AnalysisPipeline:
    # 工厂函数：每次需要跑分析时，新建一个 AnalysisPipeline 实例。
    # 任务级推理开关（enable_model_inference / enable_pose_inference）通过 analysis_options 透传，
    # 未提供的字段沿用后端全局配置。
    return AnalysisPipeline(**(analysis_options or {}))


def _demo_settings():
    # demo 任务构建时解析推理开关的全局默认值（模块级函数避免与函数内局部 import 冲突）。
    from app.core.config import get_settings

    return get_settings()


def _on_worker_completed(job: AnalysisJobSummary, result: AnalysisPipelineResult) -> None:
    # Worker 完成回调：保存基础结果 → 生成 insights（含 result 二次持久化）→ 生成报告。
    # 顺序（change design.md D2）：基础 result → insights 落盘 → artifacts 更新 +
    # result.json 重写 + RESULTS cache 同步 → 最后 Report Projector。
    if result.status == "completed" and job.analysisMode != "demo":
        from app.services.performance_insights.service import generate_and_persist_insights

        result, _insights = generate_and_persist_insights(job, result, storage=_STORAGE)
    with _LOCK:
        RESULTS[job.id] = result
    if result.status == "completed":
        report = build_mock_report(
            job=job,
            metadata=job.metadata,
            report_id=job.reportId or f"PV-{job.id.upper()}",
            generated_at=datetime.now(UTC).isoformat(),
            result=result,
        )
        _save_report(job.id, report)


def _on_worker_terminal(job: AnalysisJobSummary) -> None:
    # 任一 job 进入终态时通知编排层：
    # - 双摄 child 终态 → 推进其 Parent（waiting_sources → fusion_ready / fallback_ready / failed）；
    # - 双摄 Parent 成功 → 编排状态置 completed。
    coordinator = _get_coordinator()
    if coordinator is not None:
        coordinator.on_job_terminal(job)
    if job.analysisKind == "multiview" and job.canonicalStatus == "succeeded":
        _JOB_STORE.update(job.id, orchestrationStatus="completed")


# 全局 Worker 运行时单例
_WORKER: AnalysisWorkerRuntime | None = None
_WORKER_STARTED = False
_COORDINATOR = None


def _get_coordinator():
    """获取/初始化多视角协调器（与 Worker 共用同一 JobStore）。"""
    global _COORDINATOR
    if _COORDINATOR is None:
        from app.services.multiview_coordinator import MultiViewAnalysisCoordinator

        _COORDINATOR = MultiViewAnalysisCoordinator(_JOB_STORE)
    return _COORDINATOR


def _build_worker(store: JobStore) -> AnalysisWorkerRuntime:
    """按给定 JobStore 构建 Worker（含编排层 terminal 回调）。"""
    global _COORDINATOR
    from app.services.multiview_coordinator import MultiViewAnalysisCoordinator

    _COORDINATOR = MultiViewAnalysisCoordinator(store)
    return AnalysisWorkerRuntime(
        store,
        pipeline_factory=_pipeline_factory,
        on_completed=_on_worker_completed,
        on_terminal=_on_worker_terminal,
    )


def _sync_orchestration_storage(storage: StorageService | None = None) -> None:
    # 内部：如果传入了不同的 storage，就重建 JobStore 和 Worker，并沿用之前的启动状态。
    global _JOB_STORE, _WORKER, _WORKER_STARTED, _COORDINATOR
    target = storage or _STORAGE
    if _JOB_STORE.storage is target:
        # storage 未变：仍需保证 Worker/Coordinator 已构建（模块级初始化可能是 None，worker 线程尚未启动）
        if _WORKER is None:
            _WORKER = _build_worker(_JOB_STORE)
        return
    was_started = _WORKER_STARTED
    if was_started and _WORKER is not None:
        _WORKER.stop()
    _JOB_STORE = JobStore(target)
    _WORKER = _build_worker(_JOB_STORE)
    _WORKER_STARTED = False
    if was_started:
        start_analysis_worker()



# 阶段顺序表（本模块用到的顺序，与 job_orchestration 里的一致）
ORDERED_STAGES: list[AnalysisStageId] = [
    "upload",
    "queue",
    "calibration",
    "video-read",
    "frame-sampling",
    "detection",
    "pose",
    "tracking",
    "projection",
    "metrics",
    "visualization",
    "report",
]

# 每个阶段的中文标签 + 说明（与 job_orchestration 类似，但 detection/pose 文案偏向"预留"）
STAGE_DETAILS: dict[AnalysisStageId, tuple[str, str]] = {
    "upload": ("视频上传", "保存视频和基础比赛信息"),
    "queue": ("任务排队", "等待视觉分析任务执行"),
    "calibration": ("场地标定", "读取或跳过四角手工标定"),
    "video-read": ("读取视频", "读取上传视频元数据和帧流"),
    "frame-sampling": ("抽帧采样", "按时间轴抽取关键帧"),
    "detection": ("目标检测", "预留 YOLO11 检测球员和场地元素"),
    "pose": ("人体姿态", "预留 RTMPose26 识别人体关键点"),
    "tracking": ("轨迹跟踪", "关联球员移动轨迹"),
    "projection": ("脚点投影", "映射画面坐标到匹克球场"),
    "metrics": ("运动指标", "计算移动距离、速度、厨房区停留和热力图"),
    "visualization": ("可视化输出", "生成可供前端展示的结果引用"),
    "report": ("报告生成", "生成报告 JSON 并交给前端展示"),
}


def create_mock_job(metadata: AnalysisUploadMetadata) -> AnalysisJobSummary:
    # 便捷入口：直接用"上传元数据"创建一个分析任务。
    return create_analysis_job(AnalysisJobCreate(metadata=metadata))


def create_analysis_job(
    payload: AnalysisJobCreate,
    background_tasks: BackgroundTasks | None = None,
) -> AnalysisJobSummary:
    # 创建分析任务的主函数。根据是否有 videoId 分两种大情况：
    #   - 有 videoId：进入"真实分析"流程（可能排队/后台跑）；
    #   - 无 videoId（demo）：直接返回一个已完成任务 + 样例报告。
    _sync_orchestration_storage()
    now = utc_now()

    if payload.analysisKind == "multiview":
        # 双摄协同分析：Coordinator 创建 1 个 public Parent + 2 个 dedicated internal child
        parent = _get_coordinator().create_multiview_job(payload)
        with _LOCK:
            JOBS[parent.id] = parent
            for ref in parent.sourceJobs:
                child = _JOB_STORE.get(ref.jobId)
                if child is not None:
                    JOBS[child.id] = child
        if _WORKER is not None:
            _WORKER.notify()
        return parent

    if payload.videoId:
        if video_service.get_video(payload.videoId) is None:
            # 视频找不到 → 直接创建一个失败任务（带清晰错误信息）
            job_id = f"job-{uuid4().hex[:10]}"
            report_id = f"PV-{job_id.upper()}"
            job = AnalysisJobSummary(
                id=job_id,
                status="failed",
                canonicalStatus="failed",
                displayStatus="failed",
                stage="video-read",
                progress=0,
                createdAt=now,
                updatedAt=now,
                finishedAt=now,
                metadata=payload.metadata,
                stages=build_stages("video-read", failed=True),
                reportId=report_id,
                errorMessage="Uploaded video not found",
                errorCode=ANALYSIS_ERROR_CODES["video_not_found"],
                publicErrorMessage="Uploaded video not found",
                internalErrorMessage=f"Unknown videoId: {payload.videoId}",
                videoId=payload.videoId,
                calibrationId=payload.calibrationId,
                analysisMode="real" if payload.calibrationId else "limited",
                frameStride=payload.frameStride,
                recordingSessionId=payload.recording_session_id,
                cameraSlot=payload.camera_slot,
            )
            return _save_job(job)

        # 视频存在：先算签名，若要求"不强制新版本"且已有相同任务，则复用之（去重）
        input_signature, config_signature = analysis_signature(payload)
        if not payload.requestNewVersion:
            existing = _JOB_STORE.find_by_signature(input_signature, config_signature)
            if existing is not None:
                return existing

        if background_tasks is not None:
            # Web 请求场景：用 FastAPI 的 BackgroundTasks 异步跑
            job = _JOB_STORE.create_job(payload)
            with _LOCK:
                JOBS[job.id] = job
            background_tasks.add_task(run_analysis_job, job.id, payload, job.reportId or f"PV-{job.id.upper()}")
        else:
            # 非 Web 场景（如脚本）：创建任务并通知 Worker；若 Worker 没启用则同步跑一个
            job = _JOB_STORE.create_job(payload)
            with _LOCK:
                JOBS[job.id] = job
            if _WORKER is not None:
                _WORKER.notify()
            from app.core.config import get_settings

            if not get_settings().enable_job_worker and _WORKER is not None:
                _WORKER.run_one()
        return job

    # 没有 videoId → demo 模式：直接造一个"已完成"的任务 + 样例报告
    job_id = f"job-{uuid4().hex[:10]}"
    report_id = f"PV-{job_id.upper()}"
    job = AnalysisJobSummary(
        id=job_id,
        status="completed",
        canonicalStatus="succeeded",
        displayStatus="completed",
        stage="report",
        progress=100,
        createdAt=now,
        updatedAt=now,
        startedAt=now,
        finishedAt=now,
        metadata=payload.metadata,
        stages=build_stages("report"),
        reportId=report_id,
        analysisMode="demo",
        frameStride=payload.frameStride,
        recordingSessionId=payload.recording_session_id,
        cameraSlot=payload.camera_slot,
        enableModelInference=(
            payload.enableModelInference
            if payload.enableModelInference is not None
            else _demo_settings().enable_model_inference
        ),
        enablePoseInference=(
            payload.enablePoseInference
            if payload.enablePoseInference is not None
            else _demo_settings().enable_pose_inference
        ),
    )
    report = build_mock_report(job, payload.metadata, report_id, now)
    _save_job(job)
    _save_report(job_id, report)
    return job


def run_analysis_job(job_id: str, payload: AnalysisJobCreate, report_id: str) -> None:
    # BackgroundTasks 调用的目标：让 Worker 去执行指定任务。
    _sync_orchestration_storage()
    _WORKER.run_job(job_id)


def _update_job(job: AnalysisJobSummary, **updates: object) -> AnalysisJobSummary:
    # 内部：局部更新一个任务对象并保存（不落 JobStore，直接走 _save_job）。
    payload = job.model_dump()
    payload.update(updates)
    payload["updatedAt"] = datetime.now(UTC).isoformat()
    updated = AnalysisJobSummary.model_validate(payload)
    return _save_job(updated)


def _persist_stage_progress(job: AnalysisJobSummary, stage: AnalysisStage) -> AnalysisJobSummary:
    # 内部：把流水线阶段进度合并到任务里（早期 mock 流程用的进度更新）。
    stages = merge_stage_progress(job.stages, stage)
    progress = max(job.progress, compute_progress_from_stages(stages))
    current_stage = current_stage_from_stages(stages, fallback=stage.id)
    status = "failed" if stage.status == "failed" else "processing"
    updates: dict[str, object] = {
        "status": status,
        "stage": current_stage,
        "progress": min(progress, 99),
        "stages": stages,
    }
    if stage.status == "failed":
        updates["errorMessage"] = stage.detail
    return _update_job(job, **updates)


def _merge_progress_stage(stages: list[AnalysisStage], stage: AnalysisStage) -> list[AnalysisStage]:
    # 内部：直接透传 merge_stage_progress（兼容旧调用）。
    return merge_stage_progress(stages, stage)


def _save_job(job: AnalysisJobSummary) -> AnalysisJobSummary:
    # 内部：保存任务到 JobStore（落盘）并同步到内存缓存。
    _sync_orchestration_storage()
    saved = _JOB_STORE.save(job)
    with _LOCK:
        JOBS[saved.id] = saved
    return saved


def _save_report(job_id: str, report: AnalysisReport) -> AnalysisReport:
    # 内部：保存报告到内存 + 磁盘（原子写）。
    with _LOCK:
        REPORTS[job_id] = report
    _STORAGE.write_json_atomic(_STORAGE.report_json_path(job_id), report.model_dump(mode="json"))
    return report


def list_analysis_jobs(
    storage: StorageService | None = None,
    *,
    include_internal: bool = False,
) -> list[AnalysisJobSummary]:
    # 列出所有分析任务（磁盘 + 内存），按更新时间倒序。
    # 默认只返回 visibility=public 的 Parent/单摄任务；internal child 仅 include_internal=True（诊断）时返回。
    _sync_orchestration_storage(storage)
    jobs: dict[str, AnalysisJobSummary] = {job.id: job for job in _JOB_STORE.list()}
    with _LOCK:
        jobs.update({job_id: normalize_job(job) for job_id, job in JOBS.items()})
    all_jobs = sorted(jobs.values(), key=lambda job: _job_sort_key(job), reverse=True)
    if include_internal:
        return all_jobs
    return [job for job in all_jobs if job.visibility != "internal"]


def _load_job_from_path(path: Path, storage: StorageService) -> AnalysisJobSummary | None:
    # 内部：从磁盘读一个任务 JSON（损坏的忽略）。
    try:
        return AnalysisJobSummary.model_validate(storage.read_json(path))
    except Exception as exc:  # noqa: BLE001 - corrupted persisted jobs should not break the task list.
        logger.warning("Skipping unreadable analysis job summary %s: %s", path, exc)
        return None


def _job_sort_key(job: AnalysisJobSummary) -> tuple[str, str]:
    # 内部：排序键（更新时间优先，其次创建时间）。
    return (job.updatedAt or job.createdAt, job.createdAt)


def get_mock_job(job_id: str) -> AnalysisJobSummary | None:
    # 按 job_id 取任务：先查 JobStore，再查内存，都没有返回 None。
    _sync_orchestration_storage()
    job = _JOB_STORE.get(job_id)
    if job is None:
        cached = JOBS.get(job_id)
        if cached is None:
            return None
        job = normalize_job(cached)
    # 双摄 Parent 运行中：viewRuns 惰性刷新为 child 实时进度（不落盘，避免写放大）
    if job.analysisKind == "multiview" and job.canonicalStatus not in {"succeeded", "failed", "canceled"}:
        live = _get_coordinator().live_view_runs(job)
        if live != job.viewRuns:
            job = job.model_copy(update={"viewRuns": live})
    # multiview Parent 缺 videoId（历史任务或 result 未落盘时）→ 从 reference child 虚拟解析，
    # 保证前端始终能确定视频源（防止"后端重启后视频无法播放"复发）。
    if job.analysisKind == "multiview" and not job.videoId:
        resolved = _resolve_parent_video_source(job)
        if resolved is not None:
            job = resolved
    with _LOCK:
        JOBS[job_id] = job
    return job


def _resolve_parent_video_source(job: AnalysisJobSummary) -> AnalysisJobSummary | None:
    """multiview Parent 缺失 videoId 时，从 reference child 解析（只读、不落盘）。"""
    ref_view = job.referenceViewId
    ref = next((r for r in (job.sourceJobs or []) if r.cameraSlot == ref_view), None)
    if ref is None:
        return None
    child = _JOB_STORE.get(ref.jobId)
    if child is None or not child.videoId:
        return None
    return job.model_copy(
        update={
            "videoId": child.videoId,
            "calibrationId": child.calibrationId or job.calibrationId,
        }
    )


def get_mock_report(job_id: str) -> AnalysisReport | None:
    # 按 job_id 取报告：先查内存，再查磁盘。
    cached = REPORTS.get(job_id)
    if cached is not None:
        return cached

    path = _STORAGE.report_json_path(job_id)
    if not path.exists():
        return None

    report = AnalysisReport.model_validate(_STORAGE.read_json(path))
    with _LOCK:
        REPORTS[job_id] = report
    return report


def get_pipeline_result(job_id: str) -> AnalysisPipelineResult | None:
    # 按 job_id 取流水线结果：先查内存，再查磁盘。
    cached = RESULTS.get(job_id)
    if cached is not None:
        return cached

    job = get_mock_job(job_id)
    if job is not None:
        _STORAGE.resolve_capture_job_root(job_id, job.metadata.capture_take_id)

    path = _STORAGE.output_json_path(job_id)
    if not path.exists():
        return None

    result = AnalysisPipelineResult.model_validate(_STORAGE.read_json(path))
    with _LOCK:
        RESULTS[job_id] = result
    return result


def _is_safe_artifact_root(root: Path | None, job_id: str, outputs_dir: Path) -> bool:
    """判断目录是否为该 job 的分析产物根（安全可整树删除）。

    仅接受两种形态，防止误删录制目录：
    - 非 capture：`<outputs_dir>/<job_id>`
    - capture：`<take_dir>/analysis/<job_id>`
    且 `job_id` 必须以 `job-` 前缀开头并仅含 URL 安全字符（不匹配任意目录名）。
    """
    if not root or not job_id or not re.fullmatch(r"job-[A-Za-z0-9_-]+", job_id):
        return False
    try:
        resolved = root.resolve()
    except OSError:
        return False
    if resolved == (outputs_dir / job_id).resolve():
        return True
    if resolved.name == job_id and resolved.parent.name == "analysis":
        return True
    return False


def delete_analysis_job(job_id: str, *, allow_internal: bool = False) -> AnalysisDeleteResult:
    # 删除分析任务：从内存和磁盘清掉所有相关产物。
    _sync_orchestration_storage()
    job = get_mock_job(job_id)
    if job is None:
        return AnalysisDeleteResult(job_id=job_id, status="not_found", detail="Analysis job not found")

    # 内部 Source Job 只能由 Parent cascade 删除（外部 API blocked）
    if job.visibility == "internal" and not allow_internal:
        return AnalysisDeleteResult(
            job_id=job_id, status="blocked", detail="internal source job cannot be deleted directly"
        )

    # 活跃中的任务不允许删除
    if job.status in ACTIVE_COMPAT_STATUSES:
        return AnalysisDeleteResult(job_id=job_id, status="blocked", detail="Active analysis jobs cannot be deleted")

    # 双摄 Parent：先级联删除 owned child 分析产物 + fusion run 产物（绝不碰录制资产）
    if job.analysisKind == "multiview":
        _get_coordinator().delete_cascade(job)

    _STORAGE.resolve_capture_job_root(job_id, job.metadata.capture_take_id)

    with _LOCK:
        JOBS.pop(job_id, None)
        REPORTS.pop(job_id, None)
        RESULTS.pop(job_id, None)

    # 同时从 JobStore 删除，防止 list_analysis_jobs 重新加载
    _JOB_STORE.delete(job_id)

    # 逐个删除各类产物文件，并记录被删路径
    deleted_paths = []
    for path in [
        _STORAGE.job_json_path(job_id),
        _STORAGE.report_json_path(job_id),
        _STORAGE.output_json_path(job_id),
        _STORAGE.tracking_json_path(job_id),
        _STORAGE.tracking_overlay_json_path(job_id),
        _STORAGE.ball_overlay_json_path(job_id),
        _STORAGE.pose_overlay_json_path(job_id),
        _STORAGE.serve_events_json_path(job_id),
        _STORAGE.serve_debug_candidates_json_path(job_id),
        _STORAGE.serve_score_series_json_path(job_id),
        _STORAGE.serve_clips_manifest_json_path(job_id),
        _STORAGE.serve_debug_overlay_video_path(job_id),
    ]:
        if path.exists():
            _STORAGE.delete_path(path)
            deleted_paths.append(str(path))

    # 删除该 job 的完整产物目录：capture job 为 <take_dir>/analysis/<job_id>（含 analysis_overlay.mp4、
    # position_visualizations/、fused_* 等清单外产物），非 capture 为 <outputs_dir>/<job_id>。
    # 删除前做路径安全校验，避免误删录制目录。
    artifact_root = _STORAGE.capture_job_root(job_id) or (_STORAGE.outputs_dir / job_id)
    if _is_safe_artifact_root(artifact_root, job_id, _STORAGE.outputs_dir):
        if artifact_root.exists():
            _STORAGE.delete_path_tree(artifact_root)
            deleted_paths.append(str(artifact_root))

    # 上传分析的私有视频允许随任务回收；CaptureTake/录制 session 产生的媒体和
    # 标定属于录制资产，删除分析时必须保留，尤其是双摄 child 的级联删除路径。
    capture_derived = bool(
        getattr(job.metadata, "capture_take_id", None)
        or getattr(job.metadata, "recording_session_id", None)
        or getattr(job, "recordingSessionId", None)
    )
    if not capture_derived:
        _cleanup_shared_video_artifacts(job.videoId, excluded_job_id=job_id)
        _cleanup_shared_calibration_artifacts(job.calibrationId, excluded_job_id=job_id)

    return AnalysisDeleteResult(
        job_id=job_id,
        status="deleted",
        detail=f"Deleted analysis job and {len(deleted_paths)} persisted artifact file(s)",
    )


def cancel_analysis_job(job_id: str) -> AnalysisJobSummary | None:
    # 取消任务：交给 JobStore.cancel，并唤醒 Worker；双摄 Parent 级联取消 owned children。
    _sync_orchestration_storage()
    job = get_mock_job(job_id)
    if job is not None and job.visibility == "internal":
        # 内部 Source Job 不能被用户直接取消（Coordinator 内部才允许）
        raise ValueError("internal source job cannot be canceled directly")
    job, _state = _JOB_STORE.cancel(job_id)
    if job is not None:
        if job.analysisKind == "multiview" and job.canonicalStatus == "canceled":
            _get_coordinator().cancel_cascade(job)
        with _LOCK:
            JOBS[job.id] = job
        if _WORKER is not None:
            _WORKER.notify()
    return job


def start_analysis_worker() -> None:
    # 启动后台分析 Worker（受配置 enable_job_worker 控制）。
    global _WORKER_STARTED
    _sync_orchestration_storage()
    from app.core.config import get_settings

    # 启动对账：推进遗留双摄 Parent（child 已完成但 Parent 仍 waiting_sources）
    _get_coordinator().reconcile_all()

    if get_settings().enable_job_worker and _WORKER is not None:
        _WORKER.start()
        _WORKER_STARTED = True


def stop_analysis_worker() -> None:
    # 停止后台分析 Worker。
    global _WORKER_STARTED
    if _WORKER is not None:
        _WORKER.stop()
    _WORKER_STARTED = False


def recover_zombie_jobs() -> int:
    """启动时回收僵尸任务：把长时间无进度更新的 running 任务标记为 failed。

    被 reload 风暴、进程崩溃或 Worker 线程异常中断留下的 running 任务，
    claim_next() 永远不会重新认领（它只认领 queued），必须显式置为终态。
    这里的判断依据是 updatedAt 距离当前时间超过阈值（默认 120 秒）。
    """
    import logging
    from datetime import datetime

    from app.core.config import get_settings

    logger = logging.getLogger(__name__)
    settings = get_settings()
    threshold_seconds = max(60, settings.job_zombie_timeout_seconds)
    now = datetime.now(UTC)
    recovered = 0

    _sync_orchestration_storage()
    for job in _JOB_STORE.list():
        if job.canonicalStatus != "running":
            continue
        try:
            updated = datetime.fromisoformat(job.updatedAt or job.createdAt)
        except (ValueError, TypeError):
            continue
        if (now - updated).total_seconds() <= threshold_seconds:
            continue

        logger.warning(
            "标记僵尸任务 %s 为 failed（%s 未更新，阈值=%ss）",
            job.id,
            updated.isoformat(),
            threshold_seconds,
        )
        try:
            _JOB_STORE.mark_failed(
                job,
                stages=job.stages,
                message="分析任务因后端异常中断（热重载风暴或 Worker 崩溃），请重新提交。",
                error_code="ZOMBIE_RECOVERED",
            )
            recovered += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("无法回收僵尸任务 %s: %s", job.id, exc)

    if recovered:
        logger.info("启动时回收了 %s 个僵尸任务", recovered)

    # 对账双摄 Parent/Child 依赖（child 已完成但 Parent 仍 waiting_sources 的情况）
    _get_coordinator().reconcile_all()
    return recovered


def batch_delete_analysis_jobs(job_ids: list[str]) -> list[AnalysisDeleteResult]:
    # 批量删除多个任务。
    return [delete_analysis_job(job_id) for job_id in job_ids]


def delete_analysis_by_recording_session(
    session_id: str,
    session_capture_take_id: str | None = None,
) -> list[AnalysisDeleteResult]:
    # 删除某个双摄录制会话派生的所有分析任务（multiview Parent 级联 internal child + fusion run 产物，
    # 以及单摄任务），不触碰录制本身（session / 双路视频 / CaptureTake / sync_calibration）。
    # 匹配规则：recordingSessionId 或 metadata.recording_session_id 命中 session_id，
    # 或 metadata.capture_take_id 命中该会话的 CaptureTake（补强归属）。
    matched: dict[str, AnalysisJobSummary] = {}
    for job in list_analysis_jobs():
        metadata = getattr(job, "metadata", None)
        job_session = job.recordingSessionId or getattr(metadata, "recording_session_id", None)
        job_take = getattr(metadata, "capture_take_id", None)
        if job_session == session_id or (session_capture_take_id and job_take == session_capture_take_id):
            matched[job.id] = job
    return [delete_analysis_job(job_id) for job_id in sorted(matched)]


def _remaining_jobs(excluded_job_id: str | None = None) -> list[AnalysisJobSummary]:
    # 内部：找出"除了被排除的那个之外"的所有任务（用于判断共享资源是否还被引用）。
    by_id: dict[str, AnalysisJobSummary] = {}
    with _LOCK:
        for job in JOBS.values():
            if job.id != excluded_job_id:
                by_id[job.id] = job

    jobs_dir = _STORAGE.outputs_dir / "jobs"
    if jobs_dir.exists():
        for path in sorted(jobs_dir.glob("*.json")):
            try:
                job = AnalysisJobSummary.model_validate(_STORAGE.read_json(path))
            except Exception:  # noqa: BLE001 - unreadable legacy jobs should be ignored here.
                continue
            if job.id != excluded_job_id:
                by_id.setdefault(job.id, normalize_job(job))
    return list(by_id.values())


def _cleanup_shared_video_artifacts(video_id: str | None, *, excluded_job_id: str | None = None) -> None:
    # 内部：如果没有其它任务还在用这个 video_id，就把视频文件和元数据删掉。
    if not video_id:
        return
    if any(job.videoId == video_id for job in _remaining_jobs(excluded_job_id)):
        return

    metadata_path = _STORAGE.video_metadata_path(video_id)
    if metadata_path.exists():
        try:
            metadata = _STORAGE.read_json(metadata_path)
            raw_video_path = Path(str(metadata.get("path", "")))
            if raw_video_path.exists():
                raw_video_path.unlink()
        except Exception:  # noqa: BLE001 - fallback to cached video metadata below.
            pass

    video = video_service.get_video(video_id)
    if video is not None:
        video_path = Path(video.path)
        if video_path.exists():
            video_path.unlink()

    if metadata_path.exists():
        metadata_path.unlink()

    with _LOCK:
        try:
            from app.services.video_service import VIDEOS

            VIDEOS.pop(video_id, None)
        except Exception:  # noqa: BLE001 - cache cleanup should not fail deletion.
            pass


def _cleanup_shared_calibration_artifacts(calibration_id: str | None, *, excluded_job_id: str | None = None) -> None:
    # 内部：若没有其它任务用这个标定，则删除标定文件与预览图。
    if not calibration_id:
        return
    if any(job.calibrationId == calibration_id for job in _remaining_jobs(excluded_job_id)):
        return

    calibration_path = _STORAGE.calibration_json_path(calibration_id)
    if calibration_path.exists():
        calibration_path.unlink()

    preview_path = _STORAGE.preview_image_path(calibration_id)
    if preview_path.exists():
        preview_path.unlink()

    try:
        from app.services.calibration_service import CALIBRATIONS

        with _LOCK:
            CALIBRATIONS.pop(calibration_id, None)
    except Exception:  # noqa: BLE001 - cache cleanup should not fail deletion.
        pass


def _analysis_stages_from_pipeline(result: AnalysisPipelineResult) -> list[AnalysisStage]:
    # 内部：把流水线阶段转成对外展示阶段，并补一个 report 阶段。
    stages = analysis_stages_from_pipeline(result)
    stages.append(
        AnalysisStage(
            id="report",
            label="报告生成",
            status="done" if result.status == "completed" else "pending",
            detail="已生成前端报告 JSON" if result.status == "completed" else "pipeline 失败，报告未生成",
            progress=100 if result.status == "completed" else 0,
        )
    )
    return stages


def _progress_from_stages(stages: list[AnalysisStage]) -> int:
    # 内部：透传 compute_progress_from_stages。
    return compute_progress_from_stages(stages)


def _current_stage_from_stages(stages: list[AnalysisStage], fallback: str = "frame-sampling") -> str:
    # 内部：透传 current_stage_from_stages（默认 fallback 改为 frame-sampling）。
    return current_stage_from_stages(stages, fallback=fallback)


def _first_failed_stage(stages: list[AnalysisStage]) -> str:
    # 内部：透传 first_failed_stage。
    return first_failed_stage(stages)


def build_demo_report(
    job: AnalysisJobSummary,
    metadata: AnalysisUploadMetadata,
    report_id: str,
    generated_at: str,
) -> AnalysisReport:
    """demo 任务专用报告：深拷贝样例报告并填入任务元信息（source=demo）。

    仅在 analysisMode=demo 时调用；真实任务走 build_real_performance_report。
    """
    payload = deepcopy(DEMO_REPORT)
    payload["source"] = "demo"
    payload["jobId"] = job.id
    payload["reportId"] = report_id
    payload["generatedAt"] = generated_at
    payload["metadata"] = metadata.model_dump()
    payload["match"]["title"] = metadata.matchTitle
    payload["match"]["subtitle"] = (
        f"{'双打' if metadata.matchFormat == 'doubles' else '单打'}训练样本 · {metadata.level}"
    )
    payload["match"]["date"] = metadata.matchDate
    payload["match"]["venue"] = metadata.venue
    payload["session"]["athlete"] = metadata.athleteLabel
    payload["session"]["venue"] = metadata.venue
    payload["session"]["date"] = metadata.matchDate
    payload["session"]["level"] = metadata.level
    payload["session"]["reportId"] = report_id
    return AnalysisReport.model_validate(payload)


def build_mock_report(
    job: AnalysisJobSummary,
    metadata: AnalysisUploadMetadata,
    report_id: str,
    generated_at: str,
    result: AnalysisPipelineResult | None = None,
) -> AnalysisReport:
    """报告构建统一入口（按任务模式分发）。

    - demo 任务 → build_demo_report（样例报告，source=demo）；
    - 真实任务 → real_report_builder.build_real_performance_report
      （从真实 pipeline 数据从零构建 v2 报告，绝不继承 DEMO_REPORT）。
    """
    if job.analysisMode == "demo":
        return build_demo_report(job, metadata, report_id, generated_at)
    from app.services.real_report_builder import build_real_performance_report

    return build_real_performance_report(
        job=job,
        metadata=metadata,
        report_id=report_id,
        generated_at=generated_at,
        result=result,
        storage=_STORAGE,
    )


# 演示用样例报告（写死的占位数据，demo 模式直接返回它）。
DEMO_REPORT = {
    "version": "analysis-report-v1",
    "source": "demo",
    "reportId": "PV-20260504-018",
    "generatedAt": "2026-05-04T12:30:00+08:00",
    "metadata": {
        "fileName": "demo-pickleball-match.mp4",
        "fileSize": 248000000,
        "matchTitle": "北京体育大学训练场对局样本",
        "venue": "北京体育大学匹克球训练场",
        "matchDate": "2026-05-04",
        "matchFormat": "doubles",
        "cameraAngle": "elevated",
        "athleteLabel": "球馆体验用户 A",
        "level": "大众进阶",
    },
    "match": {
        "title": "北京体育大学训练场对局样本",
        "subtitle": "智能比赛分析 · 双打训练样本",
        "date": "2026-05-04",
        "venue": "北京体育大学匹克球训练场",
        "teams": "荧光队 对阵 蓝队",
        "score": "11 - 8",
        "currentRally": "移动轨迹样本",
        "currentTime": "08:42",
        "duration": "12:16",
    },
    "session": {
        "athlete": "球馆体验用户 A",
        "venue": "北京体育大学匹克球训练场",
        "date": "2026-05-04",
        "level": "大众进阶",
        "reportId": "PV-20260504-018",
        "summary": "本次样例聚焦人员移动、站位覆盖和回位节奏，用于展示当前保留的视觉分析工作流。",
        "metrics": [],
        "landingPoints": [],
        "routes": [],
        "movementPath": [
            {"x": 50, "y": 83},
            {"x": 38, "y": 74},
            {"x": 31, "y": 66},
            {"x": 44, "y": 58},
            {"x": 63, "y": 64},
            {"x": 54, "y": 81},
        ],
        "rallies": [],
    },
    "dashboardMetrics": [
        {
            "id": "overall",
            "icon": "activity",
            "label": "综合表现评分",
            "value": "82",
            "detail": "移动覆盖抵消了后段网前站位波动",
            "trend": "较上场 +8%",
            "direction": "up",
            "progress": 82,
            "sparkline": [62, 66, 70, 68, 74, 82],
        },
        {
            "id": "third",
            "icon": "waves",
            "label": "回位效率",
            "value": "61%",
            "detail": "右侧覆盖后的回位仍偏慢",
            "trend": "-3%",
            "direction": "down",
            "progress": 61,
            "sparkline": [66, 68, 64, 65, 63, 61],
        },
    ],
    "reportActions": [
        {
            "type": "performance",
            "title": "本场表现报告",
            "description": "总结优势与首要问题，并转化为下一次训练目标。",
            "path": "/reports/performance",
        },
        {
            "type": "movement",
            "title": "步法移动报告",
            "description": "拆解回位路径、覆盖平衡和启动延迟。",
            "path": "/reports/movement",
        },
        {
            "type": "diagnosis",
            "title": "动作诊断报告",
            "description": "把动作问题转成证据和纠正方向。",
            "path": "/reports/diagnosis",
        },
    ],
    "coachNotes": [
        {
            "id": "note-advantage",
            "tone": "advantage",
            "title": "覆盖平衡接近理想",
            "body": "样例移动路径显示左右覆盖较均衡，可作为后续人员位移投影的展示基线。",
        },
        {
            "id": "note-risk",
            "tone": "risk",
            "title": "右侧回位仍有延迟",
            "body": "右侧覆盖后的恢复路径偏长，适合用移动轨迹和速度指标继续验证。",
        },
    ],
    "reportDefinitions": [],
    "playerMarkers": [
        {"id": "a", "label": "A", "team": "near", "x": 28, "y": 72, "color": "#22C55E"},
        {"id": "b", "label": "B", "team": "near", "x": 68, "y": 76, "color": "#D9FF3F"},
        {"id": "c", "label": "C", "team": "far", "x": 34, "y": 23, "color": "#2F80ED"},
        {"id": "d", "label": "D", "team": "far", "x": 75, "y": 28, "color": "#FF9500"},
    ],
    "shotTrajectories": [],
    "videoOverlayLabels": [
        {"id": "movement", "label": "人员移动轨迹", "tone": "training", "x": 54, "y": 42},
        {"id": "coverage", "label": "右侧覆盖偏慢", "tone": "risk", "x": 39, "y": 31},
    ],
    "timelineMarkers": [
        {"id": "calibration", "time": "00:12", "position": 9, "label": "场地标定完成", "tone": "advantage"},
        {"id": "movement", "time": "08:42", "position": 76, "label": "移动覆盖摘要", "tone": "advantage"},
    ],
    "highlights": [
        {
            "id": "h1",
            "title": "移动覆盖摘要",
            "time": "08:42",
            "result": "轨迹样例",
            "tone": "advantage",
            "description": "人员轨迹集中在中后场，适合作为后续标准球场投影的演示入口。",
        }
    ],
    "diagnoses": [
        {
            "id": "backswing",
            "issue": "引拍滞后",
            "severity": "中",
            "evidence": "当前样例仅保留姿态诊断占位，真实任务需等待姿态模型输出。",
            "suggestion": "在反手准备阶段提前完成肩髋转向。",
            "expectedOutcome": "后续用姿态关键点替换样例说明。",
            "priority": "优先级 1",
        }
    ],
    "trainingRecommendations": [],
    "drillRecommendations": [
        {
            "id": "drill-recovery",
            "title": "右侧覆盖后回位节奏",
            "goal": "围绕右侧覆盖后的第一步恢复做 5 组移动练习。",
            "duration": "22 分钟",
            "evidence": "样例移动路径显示右侧覆盖后的恢复路径偏长。",
            "difficulty": "进阶",
            "linkedReport": "movement",
        }
    ],
    "shotRows": [],
    "skillRatings": [
        {"id": "movement-coverage", "label": "移动覆盖", "score": 61, "note": "右侧覆盖后的回位仍可优化。"}
    ],
    "progressPoints": [{"match": "第1场", "performance": 67, "errors": 23, "thirdShot": 48, "kitchen": 52}],
}

# 给样例报告补上 reportDefinitions（移动报告 + 诊断报告两个占位）。
DEMO_REPORT["reportDefinitions"] = [
    {
        "type": "movement",
        "title": "移动与覆盖平衡报告",
        "eyebrow": "步法移动报告",
        "summary": "反手回球后的恢复路径仍有绕行。",
        "heroMetric": "48 / 52",
        "heroMetricLabel": "左右覆盖平衡",
        "visualization": "movement",
        "metrics": DEMO_REPORT["dashboardMetrics"],
        "insights": DEMO_REPORT["coachNotes"],
        "trainingLink": "过渡区重置",
    },
    {
        "type": "diagnosis",
        "title": "动作诊断报告",
        "eyebrow": "动作诊断报告",
        "summary": "主要问题来自反手准备节奏和连续移动后的重心控制。",
        "heroMetric": "1",
        "heroMetricLabel": "已识别优先问题",
        "visualization": "diagnosis",
        "metrics": DEMO_REPORT["dashboardMetrics"],
        "insights": DEMO_REPORT["coachNotes"],
        "trainingLink": "反手侧移动稳定性",
    },
]
