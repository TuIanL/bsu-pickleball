"""模拟分析服务 —— 提供 MVP 阶段的任务 CRUD、后台 Worker 调度和演示报告生成。"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import logging
from threading import Lock
from uuid import uuid4

from typing import Optional

from fastapi import BackgroundTasks

from app.schemas.analysis import (
    ANALYSIS_ERROR_CODES,
    AnalysisJobCreate,
    AnalysisDeleteResult,
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
    stage_from_pipeline,
    utc_now,
)
from app.services.storage_service import StorageService
from app.services.video_service import video_service


logger = logging.getLogger(__name__)

JOBS: dict[str, AnalysisJobSummary] = {}
REPORTS: dict[str, AnalysisReport] = {}
RESULTS: dict[str, AnalysisPipelineResult] = {}
_LOCK = Lock()
_STORAGE = StorageService()
_JOB_STORE = JobStore(_STORAGE)


def _pipeline_factory() -> AnalysisPipeline:
    return AnalysisPipeline()


def _on_worker_completed(job: AnalysisJobSummary, result: AnalysisPipelineResult) -> None:
    with _LOCK:
        RESULTS[job.id] = result
    if result.status == "completed":
        report = build_mock_report(
            job=job,
            metadata=job.metadata,
            report_id=job.reportId or f"PV-{job.id.upper()}",
            generated_at=datetime.now(timezone.utc).isoformat(),
            result=result,
        )
        _save_report(job.id, report)


_WORKER = AnalysisWorkerRuntime(
    _JOB_STORE,
    pipeline_factory=_pipeline_factory,
    on_completed=_on_worker_completed,
)
_WORKER_STARTED = False


def _sync_orchestration_storage(storage: StorageService | None = None) -> None:
    global _JOB_STORE, _WORKER, _WORKER_STARTED
    target = storage or _STORAGE
    if _JOB_STORE.storage is target:
        return
    was_started = _WORKER_STARTED
    if was_started:
        _WORKER.stop()
    _JOB_STORE = JobStore(target)
    _WORKER = AnalysisWorkerRuntime(
        _JOB_STORE,
        pipeline_factory=_pipeline_factory,
        on_completed=_on_worker_completed,
    )
    _WORKER_STARTED = False
    if was_started:
        start_analysis_worker()

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
    return create_analysis_job(AnalysisJobCreate(metadata=metadata))


def create_analysis_job(
    payload: AnalysisJobCreate,
    background_tasks: BackgroundTasks | None = None,
) -> AnalysisJobSummary:
    _sync_orchestration_storage()
    now = utc_now()

    if payload.videoId:
        if video_service.get_video(payload.videoId) is None:
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
            )
            return _save_job(job)

        input_signature, config_signature = analysis_signature(payload)
        if not payload.requestNewVersion:
            existing = _JOB_STORE.find_by_signature(input_signature, config_signature)
            if existing is not None:
                return existing

        if background_tasks is not None:
            job = _JOB_STORE.create_job(payload)
            with _LOCK:
                JOBS[job.id] = job
            background_tasks.add_task(run_analysis_job, job.id, payload, job.reportId or f"PV-{job.id.upper()}")
        else:
            job = _JOB_STORE.create_job(payload)
            with _LOCK:
                JOBS[job.id] = job
            _WORKER.notify()
            from app.core.config import get_settings

            if not get_settings().enable_job_worker:
                _WORKER.run_one()
        return job

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
    )
    report = build_mock_report(job, payload.metadata, report_id, now)
    _save_job(job)
    _save_report(job_id, report)
    return job


def run_analysis_job(job_id: str, payload: AnalysisJobCreate, report_id: str) -> None:
    _sync_orchestration_storage()
    _WORKER.run_job(job_id)


def _update_job(job: AnalysisJobSummary, **updates: object) -> AnalysisJobSummary:
    payload = job.model_dump()
    payload.update(updates)
    payload["updatedAt"] = datetime.now(timezone.utc).isoformat()
    updated = AnalysisJobSummary.model_validate(payload)
    return _save_job(updated)


def _persist_stage_progress(job: AnalysisJobSummary, stage: AnalysisStage) -> AnalysisJobSummary:
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
    return merge_stage_progress(stages, stage)


def _save_job(job: AnalysisJobSummary) -> AnalysisJobSummary:
    _sync_orchestration_storage()
    saved = _JOB_STORE.save(job)
    with _LOCK:
        JOBS[saved.id] = saved
    return saved


def _save_report(job_id: str, report: AnalysisReport) -> AnalysisReport:
    with _LOCK:
        REPORTS[job_id] = report
    _STORAGE.write_json_atomic(_STORAGE.report_json_path(job_id), report.model_dump(mode="json"))
    return report


def list_analysis_jobs(storage: StorageService | None = None) -> list[AnalysisJobSummary]:
    _sync_orchestration_storage(storage)
    jobs: dict[str, AnalysisJobSummary] = {job.id: job for job in _JOB_STORE.list()}
    with _LOCK:
        jobs.update({job_id: normalize_job(job) for job_id, job in JOBS.items()})
    return sorted(jobs.values(), key=lambda job: _job_sort_key(job), reverse=True)


def _load_job_from_path(path: Path, storage: StorageService) -> AnalysisJobSummary | None:
    try:
        return AnalysisJobSummary.model_validate(storage.read_json(path))
    except Exception as exc:  # noqa: BLE001 - corrupted persisted jobs should not break the task list.
        logger.warning("Skipping unreadable analysis job summary %s: %s", path, exc)
        return None


def _job_sort_key(job: AnalysisJobSummary) -> tuple[str, str]:
    return (job.updatedAt or job.createdAt, job.createdAt)


def get_mock_job(job_id: str) -> Optional[AnalysisJobSummary]:
    _sync_orchestration_storage()
    job = _JOB_STORE.get(job_id)
    if job is None:
        cached = JOBS.get(job_id)
        if cached is None:
            return None
        job = normalize_job(cached)
    with _LOCK:
        JOBS[job_id] = job
    return job


def get_mock_report(job_id: str) -> Optional[AnalysisReport]:
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


def get_pipeline_result(job_id: str) -> Optional[AnalysisPipelineResult]:
    cached = RESULTS.get(job_id)
    if cached is not None:
        return cached

    path = _STORAGE.output_json_path(job_id)
    if not path.exists():
        return None

    result = AnalysisPipelineResult.model_validate(_STORAGE.read_json(path))
    with _LOCK:
        RESULTS[job_id] = result
    return result


def delete_analysis_job(job_id: str) -> AnalysisDeleteResult:
    _sync_orchestration_storage()
    job = get_mock_job(job_id)
    if job is None:
        return AnalysisDeleteResult(job_id=job_id, status="not_found", detail="Analysis job not found")

    if job.status in ACTIVE_COMPAT_STATUSES:
        return AnalysisDeleteResult(job_id=job_id, status="blocked", detail="Active analysis jobs cannot be deleted")

    with _LOCK:
        JOBS.pop(job_id, None)
        REPORTS.pop(job_id, None)
        RESULTS.pop(job_id, None)

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
    ]:
        if path.exists():
            _STORAGE.delete_path(path)
            deleted_paths.append(str(path))

    job_output_dir = _STORAGE.outputs_dir / job_id
    if job_output_dir.exists():
        _STORAGE.delete_path_tree(job_output_dir)

    _cleanup_shared_video_artifacts(job.videoId, excluded_job_id=job_id)
    _cleanup_shared_calibration_artifacts(job.calibrationId, excluded_job_id=job_id)

    return AnalysisDeleteResult(
        job_id=job_id,
        status="deleted",
        detail=f"Deleted analysis job and {len(deleted_paths)} persisted artifact file(s)",
    )


def cancel_analysis_job(job_id: str) -> AnalysisJobSummary | None:
    _sync_orchestration_storage()
    job, _state = _JOB_STORE.cancel(job_id)
    if job is not None:
        with _LOCK:
            JOBS[job.id] = job
        _WORKER.notify()
    return job


def start_analysis_worker() -> None:
    global _WORKER_STARTED
    _sync_orchestration_storage()
    from app.core.config import get_settings

    if get_settings().enable_job_worker:
        _WORKER.start()
        _WORKER_STARTED = True


def stop_analysis_worker() -> None:
    global _WORKER_STARTED
    _WORKER.stop()
    _WORKER_STARTED = False


def batch_delete_analysis_jobs(job_ids: list[str]) -> list[AnalysisDeleteResult]:
    return [delete_analysis_job(job_id) for job_id in job_ids]


def _remaining_jobs(excluded_job_id: str | None = None) -> list[AnalysisJobSummary]:
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
    return compute_progress_from_stages(stages)


def _current_stage_from_stages(stages: list[AnalysisStage], fallback: str = "frame-sampling") -> str:
    return current_stage_from_stages(stages, fallback=fallback)


def _first_failed_stage(stages: list[AnalysisStage]) -> str:
    return first_failed_stage(stages)


def build_mock_report(
    job: AnalysisJobSummary,
    metadata: AnalysisUploadMetadata,
    report_id: str,
    generated_at: str,
    result: AnalysisPipelineResult | None = None,
) -> AnalysisReport:
    payload = deepcopy(DEMO_REPORT)
    payload["source"] = "job"
    payload["jobId"] = job.id
    payload["reportId"] = report_id
    payload["generatedAt"] = generated_at
    payload["metadata"] = metadata.model_dump()
    payload["match"]["title"] = metadata.matchTitle
    payload["match"]["subtitle"] = f"{'双打' if metadata.matchFormat == 'doubles' else '单打'}训练样本 · {metadata.level}"
    payload["match"]["date"] = metadata.matchDate
    payload["match"]["venue"] = metadata.venue
    payload["session"]["athlete"] = metadata.athleteLabel
    payload["session"]["venue"] = metadata.venue
    payload["session"]["date"] = metadata.matchDate
    payload["session"]["level"] = metadata.level
    payload["session"]["reportId"] = report_id

    if job.analysisMode != "demo":
        _apply_pipeline_feedback(payload, job, result)

    return AnalysisReport.model_validate(payload)


def _apply_pipeline_feedback(
    payload: dict,
    job: AnalysisJobSummary,
    result: AnalysisPipelineResult | None,
) -> None:
    tracks = result.tracks if result is not None else []
    metrics = result.metrics if result is not None else None
    total_distance = sum(item.distance_ft for item in metrics.distances) if metrics else 0.0
    avg_speed = _mean([item.average_speed_ft_per_s for item in metrics.speeds]) if metrics else 0.0
    max_speed = max([item.max_speed_ft_per_s for item in metrics.speeds], default=0.0) if metrics else 0.0
    kitchen_seconds = sum(item.kitchen_seconds for item in metrics.kitchen_dwell) if metrics else 0.0
    track_count = len({track.track_id for track in tracks})
    point_count = len(tracks)
    limited = job.analysisMode == "limited" or job.calibrationId is None
    no_tracks = point_count == 0

    payload["match"]["subtitle"] = "真实上传视频 · MVP 移动分析" if not limited else "真实上传视频 · 未标定有限分析"
    payload["match"]["teams"] = payload["metadata"]["athleteLabel"]
    payload["match"]["score"] = "MVP"
    payload["match"]["currentRally"] = "移动轨迹分析" if not no_tracks else "未生成可用轨迹"
    payload["match"]["currentTime"] = "完成"
    payload["match"]["duration"] = "pipeline"

    payload["session"]["summary"] = (
        f"本次分析基于上传视频生成，检测到 {track_count} 条球员轨迹、{point_count} 个场地坐标点，"
        f"累计移动距离约 {total_distance:.1f} 英尺。"
        if not no_tracks
        else (
            "本次任务已处理上传视频，但当前 MVP 没有生成可用的场地轨迹。请检查四角标定、拍摄角度、模型依赖和视频清晰度。"
            if not limited
            else "本次任务未提供有效场地标定，因此只保留上传与任务状态，不生成场地投影移动指标。"
        )
    )
    payload["session"]["landingPoints"] = []
    payload["session"]["routes"] = []
    payload["session"]["movementPath"] = _tracks_to_movement_path(tracks)
    payload["session"]["rallies"] = []

    payload["dashboardMetrics"] = _pipeline_dashboard_metrics(
        total_distance=total_distance,
        avg_speed=avg_speed,
        max_speed=max_speed,
        kitchen_seconds=kitchen_seconds,
        point_count=point_count,
    )
    payload["reportDefinitions"] = _pipeline_report_definitions(
        total_distance=total_distance,
        avg_speed=avg_speed,
        max_speed=max_speed,
        kitchen_seconds=kitchen_seconds,
        point_count=point_count,
        limited=limited,
        no_tracks=no_tracks,
    )
    payload["playerMarkers"] = _tracks_to_player_markers(tracks)
    payload["shotTrajectories"] = []
    payload["videoOverlayLabels"] = [
        {
            "id": "source-real",
            "label": "真实上传视频",
            "tone": "training",
            "x": 50,
            "y": 18,
        },
        {
            "id": "limited" if limited else "movement",
            "label": "缺少标定" if limited else f"{point_count} 个轨迹点",
            "tone": "risk" if limited or no_tracks else "advantage",
            "x": 53,
            "y": 42,
        },
    ]
    payload["timelineMarkers"] = [
        {
            "id": "pipeline",
            "time": "完成",
            "position": 88,
            "label": result.message if result else "pipeline 结果不可用",
            "tone": "risk" if limited or no_tracks else "advantage",
        }
    ]
    payload["highlights"] = [
        {
            "id": "movement-summary",
            "title": "移动轨迹摘要",
            "time": "MVP",
            "result": "算法输出",
            "tone": "risk" if limited or no_tracks else "advantage",
            "description": payload["session"]["summary"],
        }
    ]
    payload["coachNotes"] = [
        {
            "id": "real-source",
            "tone": "training",
            "title": "数据来源已切换为上传视频",
            "body": "本页优先展示后端 pipeline 产出的人员移动、速度和轨迹指标。",
        },
        {
            "id": "movement-evidence",
            "tone": "advantage" if not no_tracks else "risk",
            "title": "移动指标" if not no_tracks else "轨迹暂不可用",
            "body": (
                f"累计移动 {total_distance:.1f} 英尺，平均速度 {avg_speed:.1f} 英尺/秒，最高速度 {max_speed:.1f} 英尺/秒。"
                if not no_tracks
                else "当前没有可用球员轨迹，建议重新标定四角或确认模型推理配置。"
            ),
        },
    ]
    payload["diagnoses"] = [
        {
            "id": "mvp-limited-diagnosis",
            "issue": "动作诊断暂不可用",
            "severity": "低",
            "evidence": "当前 MVP 未接入姿态动作诊断模型。",
            "suggestion": "先使用移动距离、速度和热力图作为训练反馈依据。",
            "expectedOutcome": "避免把样例动作诊断误认为上传视频结论。",
            "priority": "说明",
        }
    ]
    payload["trainingRecommendations"] = []
    payload["drillRecommendations"] = [
        {
            "id": "drill-court-coverage",
            "title": "场地覆盖与回位节奏",
            "goal": "围绕热区和移动路径做 5 组回位练习。",
            "duration": "18 分钟",
            "evidence": payload["session"]["summary"],
            "difficulty": "进阶",
            "linkedReport": "movement",
        }
    ]
    payload["shotRows"] = []
    payload["skillRatings"] = [
        {
            "id": "movement-coverage",
            "label": "移动数据完整度",
            "score": min(100, max(0, point_count * 8)),
            "note": "分数来自可用轨迹点数量，不代表技术评分。",
        }
    ]
    payload["progressPoints"] = [
        {
            "match": "本次上传",
            "performance": min(100, max(0, int(total_distance))),
            "errors": 0,
            "thirdShot": 0,
            "kitchen": min(100, max(0, int(kitchen_seconds * 10))),
        }
    ]


def _pipeline_dashboard_metrics(
    *,
    total_distance: float,
    avg_speed: float,
    max_speed: float,
    kitchen_seconds: float,
    point_count: int,
) -> list[dict]:
    return [
        _metric("distance", "activity", "累计移动距离", f"{total_distance:.1f} ft", "来自场地投影轨迹的累计距离", "真实视频", min(100, int(total_distance))),
        _metric("avg-speed", "timer", "平均移动速度", f"{avg_speed:.1f} ft/s", f"最高速度 {max_speed:.1f} ft/s", "pipeline", min(100, int(avg_speed * 12))),
        _metric("kitchen", "waves", "厨房区停留", f"{kitchen_seconds:.1f}s", "按投影点统计的非截击区停留时间", "真实视频", min(100, int(kitchen_seconds * 10))),
        _metric("tracks", "radar", "可用轨迹点", str(point_count), "用于生成可视化和热力图的点数量", "算法输出", min(100, point_count * 8)),
    ]


def _pipeline_report_definitions(
    *,
    total_distance: float,
    avg_speed: float,
    max_speed: float,
    kitchen_seconds: float,
    point_count: int,
    limited: bool,
    no_tracks: bool,
) -> list[dict]:
    unavailable = "当前 MVP 未生成该类动作诊断数据。"
    source_note = "未提供有效标定，移动报告处于有限模式。" if limited else "来自上传视频的 pipeline 结果。"
    if no_tracks and not limited:
        source_note = "pipeline 已完成，但没有检测到可用球员轨迹。"

    movement_metrics = _pipeline_dashboard_metrics(
        total_distance=total_distance,
        avg_speed=avg_speed,
        max_speed=max_speed,
        kitchen_seconds=kitchen_seconds,
        point_count=point_count,
    )
    return [
        {
            "type": "movement",
            "title": "移动与场地覆盖报告",
            "eyebrow": "移动分析报告",
            "summary": source_note,
            "heroMetric": f"{total_distance:.1f} ft",
            "heroMetricLabel": "累计移动距离",
            "visualization": "movement",
            "metrics": movement_metrics,
            "insights": [
                _note("movement-source", "training", "真实 pipeline 输出", source_note),
                _note("movement-speed", "advantage" if point_count else "risk", "速度与覆盖", f"平均速度 {avg_speed:.1f} ft/s，最高速度 {max_speed:.1f} ft/s。"),
            ],
            "trainingLink": "基于移动路径安排回位训练",
        },
        {
            "type": "diagnosis",
            "title": "动作诊断暂不可用",
            "eyebrow": "动作诊断报告",
            "summary": unavailable,
            "heroMetric": "N/A",
            "heroMetricLabel": "姿态诊断",
            "visualization": "diagnosis",
            "metrics": [_metric("diagnosis-na", "alert", "动作诊断", "未接入", unavailable, "MVP 限制", 0)],
            "insights": [_note("diagnosis-note", "training", "需要姿态模型", "RTMPose 或同等姿态模型接入后才能输出动作证据。")],
            "trainingLink": "先依据移动指标训练",
        },
    ]


def _metric(
    metric_id: str,
    icon: str,
    label: str,
    value: str,
    detail: str,
    trend: str,
    progress: int,
) -> dict:
    progress = min(100, max(0, progress))
    return {
        "id": metric_id,
        "icon": icon,
        "label": label,
        "value": value,
        "detail": detail,
        "trend": trend,
        "direction": "steady",
        "progress": progress,
        "sparkline": [max(0, progress - 18), max(0, progress - 10), progress, progress],
    }


def _note(note_id: str, tone: str, title: str, body: str) -> dict:
    return {"id": note_id, "tone": tone, "title": title, "body": body}


def _heatmap_to_points(heatmap) -> list[dict]:
    if heatmap is None or not heatmap.cells:
        return []
    max_count = max(cell.count for cell in heatmap.cells) or 1
    points = []
    for index, cell in enumerate(heatmap.cells):
        points.append(
            {
                "id": f"heat-{index}",
                "x": ((cell.col + 0.5) / heatmap.cols) * 100,
                "y": ((cell.row + 0.5) / heatmap.rows) * 100,
                "intensity": min(1.0, cell.count / max_count),
                "label": f"热区 {cell.row + 1}-{cell.col + 1}",
            }
        )
    return points


def _tracks_to_movement_path(tracks) -> list[dict]:
    first_track_id = tracks[0].track_id if tracks else None
    selected = [track for track in tracks if track.track_id == first_track_id][:24]
    return [
        {
            "x": 12 + (track.court_point.x / 20.0) * 76,
            "y": (track.court_point.y / 44.0) * 100,
        }
        for track in selected
    ]


def _tracks_to_player_markers(tracks) -> list[dict]:
    latest: dict[str, object] = {}
    for track in tracks:
        latest[track.track_id] = track

    colors = ["#22C55E", "#D9FF3F", "#2F80ED", "#FF9500"]
    markers = []
    for index, (track_id, track) in enumerate(list(latest.items())[:4]):
        markers.append(
            {
                "id": str(track_id),
                "label": chr(ord("A") + index),
                "team": "near" if index < 2 else "far",
                "x": 12 + (track.court_point.x / 20.0) * 76,
                "y": 7 + (track.court_point.y / 44.0) * 42,
                "color": colors[index % len(colors)],
            }
        )
    return markers


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


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
        {"type": "movement", "title": "步法移动报告", "description": "拆解回位路径、覆盖平衡和启动延迟。", "path": "/reports/movement"},
        {"type": "diagnosis", "title": "动作诊断报告", "description": "把动作问题转成证据和纠正方向。", "path": "/reports/diagnosis"},
    ],
    "coachNotes": [
        {"id": "note-advantage", "tone": "advantage", "title": "覆盖平衡接近理想", "body": "样例移动路径显示左右覆盖较均衡，可作为后续人员位移投影的展示基线。"},
        {"id": "note-risk", "tone": "risk", "title": "右侧回位仍有延迟", "body": "右侧覆盖后的恢复路径偏长，适合用移动轨迹和速度指标继续验证。"},
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
        {"id": "h1", "title": "移动覆盖摘要", "time": "08:42", "result": "轨迹样例", "tone": "advantage", "description": "人员轨迹集中在中后场，适合作为后续标准球场投影的演示入口。"}
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
    "skillRatings": [{"id": "movement-coverage", "label": "移动覆盖", "score": 61, "note": "右侧覆盖后的回位仍可优化。"}],
    "progressPoints": [{"match": "第1场", "performance": 67, "errors": 23, "thirdShot": 48, "kitchen": 52}],
}

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
