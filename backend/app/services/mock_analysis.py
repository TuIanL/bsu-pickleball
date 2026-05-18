from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import logging
from threading import Lock
from uuid import uuid4

from typing import Optional

from fastapi import BackgroundTasks

from app.schemas.analysis import (
    AnalysisJobCreate,
    AnalysisJobSummary,
    AnalysisReport,
    AnalysisStage,
    AnalysisStageId,
    AnalysisUploadMetadata,
)
from app.schemas.pipeline import AnalysisPipelineResult
from app.services.analysis_pipeline import AnalysisPipeline
from app.services.storage_service import StorageService
from app.services.video_service import video_service


logger = logging.getLogger(__name__)

JOBS: dict[str, AnalysisJobSummary] = {}
REPORTS: dict[str, AnalysisReport] = {}
RESULTS: dict[str, AnalysisPipelineResult] = {}
_LOCK = Lock()
_STORAGE = StorageService()

ORDERED_STAGES: list[AnalysisStageId] = [
    "upload",
    "queue",
    "calibration",
    "video-read",
    "frame-sampling",
    "detection",
    "pose",
    "ball-tracking",
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
    "detection": ("目标检测", "预留 YOLO11 检测球员、球、球拍和场地元素"),
    "pose": ("人体姿态", "预留 RTMPose26 识别人体关键点"),
    "ball-tracking": ("球轨迹", "检测球并生成球轨迹叠加数据"),
    "tracking": ("轨迹跟踪", "关联球员、球和击球轨迹"),
    "projection": ("脚点投影", "映射画面坐标到匹克球场"),
    "metrics": ("运动指标", "计算移动距离、速度、厨房区停留和热力图"),
    "visualization": ("可视化输出", "生成可供前端展示的结果引用"),
    "report": ("报告生成", "生成报告 JSON 并交给前端展示"),
}


def build_stages(active_stage: AnalysisStageId = "report", failed: bool = False) -> list[AnalysisStage]:
    if active_stage not in ORDERED_STAGES:
        active_stage = "queue"

    active_index = ORDERED_STAGES.index(active_stage)
    stages: list[AnalysisStage] = []

    for index, stage_id in enumerate(ORDERED_STAGES):
        label, detail = STAGE_DETAILS[stage_id]
        status = "pending"

        if index < active_index or (active_stage == "report" and not failed):
            status = "done"
        elif index == active_index:
            status = "failed" if failed else "active"

        stages.append(AnalysisStage(id=stage_id, label=label, status=status, detail=detail))

    return stages


def create_mock_job(metadata: AnalysisUploadMetadata) -> AnalysisJobSummary:
    return create_analysis_job(AnalysisJobCreate(metadata=metadata))


def create_analysis_job(
    payload: AnalysisJobCreate,
    background_tasks: BackgroundTasks | None = None,
) -> AnalysisJobSummary:
    now = datetime.now(timezone.utc).isoformat()
    job_id = f"job-{uuid4().hex[:10]}"
    report_id = f"PV-{job_id.upper()}"

    if payload.videoId:
        if video_service.get_video(payload.videoId) is None:
            job = AnalysisJobSummary(
                id=job_id,
                status="failed",
                stage="video-read",
                progress=0,
                createdAt=now,
                updatedAt=now,
                metadata=payload.metadata,
                stages=build_stages("video-read", failed=True),
                reportId=report_id,
                errorMessage="Uploaded video not found",
                videoId=payload.videoId,
                calibrationId=payload.calibrationId,
                analysisMode="real" if payload.calibrationId else "limited",
            )
            return _save_job(job)

        job = AnalysisJobSummary(
            id=job_id,
            status="queued",
            stage="queue",
            progress=10,
            createdAt=now,
            updatedAt=now,
            metadata=payload.metadata,
            stages=build_stages("queue"),
            reportId=report_id,
            videoId=payload.videoId,
            calibrationId=payload.calibrationId,
            analysisMode="real" if payload.calibrationId else "limited",
        )
        _save_job(job)

        if background_tasks is not None:
            background_tasks.add_task(run_analysis_job, job_id, payload, report_id)
        else:
            run_analysis_job(job_id, payload, report_id)
        return job

    job = AnalysisJobSummary(
        id=job_id,
        status="completed",
        stage="report",
        progress=100,
        createdAt=now,
        updatedAt=now,
        metadata=payload.metadata,
        stages=build_stages("report"),
        reportId=report_id,
        analysisMode="demo",
    )
    report = build_mock_report(job, payload.metadata, report_id, now)
    _save_job(job)
    _save_report(job_id, report)
    return job


def run_analysis_job(job_id: str, payload: AnalysisJobCreate, report_id: str) -> None:
    job = get_mock_job(job_id)
    if job is None:
        logger.warning("Analysis job %s disappeared before processing", job_id)
        return

    latest_job = _persist_stage_progress(job, AnalysisStage(id="video-read", label="读取视频", status="active", detail="正在读取上传视频元数据和帧流"))

    def on_pipeline_progress(stage_result) -> None:
        nonlocal latest_job
        latest_job = _persist_stage_progress(
            latest_job,
            AnalysisStage(
                id=stage_result.id,
                label=stage_result.label,
                status=stage_result.status,
                detail=stage_result.detail,
            ),
        )

    result = AnalysisPipeline(frame_stride=payload.frameStride).run(
        job_id=job_id,
        video_id=payload.videoId,
        calibration_id=payload.calibrationId,
        frame_stride=payload.frameStride,
        progress_callback=on_pipeline_progress,
    )

    with _LOCK:
        RESULTS[job_id] = result

    stages = _analysis_stages_from_pipeline(result)
    status = result.status
    error_message = None if status == "completed" else result.message
    progress = 100 if status == "completed" else _progress_from_stages(stages)
    stage = "report" if status == "completed" else _first_failed_stage(stages)

    _update_job(
        latest_job,
        status=status,
        stage=stage,
        progress=progress,
        stages=stages,
        errorMessage=error_message,
    )

    if status == "completed":
        report = build_mock_report(
            job=job,
            metadata=payload.metadata,
            report_id=report_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            result=result,
        )
        _save_report(job_id, report)


def _update_job(job: AnalysisJobSummary, **updates: object) -> AnalysisJobSummary:
    payload = job.model_dump()
    payload.update(updates)
    payload["updatedAt"] = datetime.now(timezone.utc).isoformat()
    updated = AnalysisJobSummary.model_validate(payload)
    return _save_job(updated)


def _persist_stage_progress(job: AnalysisJobSummary, stage: AnalysisStage) -> AnalysisJobSummary:
    stages = _merge_progress_stage(job.stages, stage)
    progress = max(job.progress, _progress_from_stages(stages))
    current_stage = _current_stage_from_stages(stages, fallback=stage.id)
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
    existing: dict[str, AnalysisStage] = {item.id: item for item in stages}
    existing[stage.id] = stage

    if stage.status in {"done", "skipped", "failed"} and stage.id in ORDERED_STAGES:
        stage_index = ORDERED_STAGES.index(stage.id)
        for prior_stage_id in ORDERED_STAGES[:stage_index]:
            prior = existing.get(prior_stage_id)
            if prior and prior.status == "active":
                existing[prior_stage_id] = AnalysisStage(
                    id=prior.id,
                    label=prior.label,
                    status="done",
                    detail=prior.detail,
                )

    if stage.status == "active":
        for item in list(existing.values()):
            if item.id != stage.id and item.status == "active":
                existing[item.id] = AnalysisStage(
                    id=item.id,
                    label=item.label,
                    status="done",
                    detail=item.detail,
                )

    ordered_ids = [stage_id for stage_id in ORDERED_STAGES if stage_id in existing]
    extra_ids = [stage_id for stage_id in existing if stage_id not in ORDERED_STAGES]
    return [existing[stage_id] for stage_id in ordered_ids + extra_ids]


def _save_job(job: AnalysisJobSummary) -> AnalysisJobSummary:
    with _LOCK:
        JOBS[job.id] = job
    _STORAGE.write_json(_STORAGE.job_json_path(job.id), job.model_dump(mode="json"))
    return job


def _save_report(job_id: str, report: AnalysisReport) -> AnalysisReport:
    with _LOCK:
        REPORTS[job_id] = report
    _STORAGE.write_json(_STORAGE.report_json_path(job_id), report.model_dump(mode="json"))
    return report


def get_mock_job(job_id: str) -> Optional[AnalysisJobSummary]:
    cached = JOBS.get(job_id)
    if cached is not None:
        return cached

    path = _STORAGE.job_json_path(job_id)
    if not path.exists():
        return None

    job = AnalysisJobSummary.model_validate(_STORAGE.read_json(path))
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


def _analysis_stages_from_pipeline(result: AnalysisPipelineResult) -> list[AnalysisStage]:
    stages: list[AnalysisStage] = [
        AnalysisStage(id="upload", label="视频上传", status="done", detail="上传视频已保存"),
        AnalysisStage(id="queue", label="任务排队", status="done", detail="任务已进入后端分析流程"),
    ]

    seen_ids = {"upload", "queue"}
    for stage in result.stages:
        if stage.id in seen_ids:
            continue
        seen_ids.add(stage.id)
        stages.append(
            AnalysisStage(
                id=stage.id,
                label=stage.label,
                status=stage.status,
                detail=stage.detail,
            )
        )

    if "frame-sampling" not in seen_ids:
        insert_at = min(4, len(stages))
        stages.insert(
            insert_at,
            AnalysisStage(
                id="frame-sampling",
                label="抽帧采样",
                status="done" if result.video_id else "skipped",
                detail="已按配置帧间隔读取视频帧" if result.video_id else "未提供视频，跳过真实抽帧",
            ),
        )

    stages.append(
        AnalysisStage(
            id="report",
            label="报告生成",
            status="done" if result.status == "completed" else "pending",
            detail="已生成前端报告 JSON" if result.status == "completed" else "pipeline 失败，报告未生成",
        )
    )
    return stages


def _progress_from_stages(stages: list[AnalysisStage]) -> int:
    if not stages:
        return 0
    total = len(stages)
    finished = sum(1 for stage in stages if stage.status in {"done", "skipped"})
    active_credit = 0.45 if any(stage.status == "active" for stage in stages) else 0.0
    return int(((finished + active_credit) / total) * 100)


def _current_stage_from_stages(stages: list[AnalysisStage], fallback: str = "frame-sampling") -> str:
    for stage in stages:
        if stage.status == "failed":
            return stage.id
    for stage in stages:
        if stage.status == "active":
            return stage.id
    for stage in reversed(stages):
        if stage.status in {"done", "skipped"}:
            return stage.id
    return fallback


def _first_failed_stage(stages: list[AnalysisStage]) -> str:
    for stage in stages:
        if stage.status == "failed":
            return stage.id
    return "frame-sampling"


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
    payload["session"]["landingPoints"] = _heatmap_to_points(metrics.heatmap if metrics else None)
    payload["session"]["routes"] = []
    payload["session"]["movementPath"] = _tracks_to_movement_path(tracks)
    payload["session"]["rallies"] = [
        {
            "id": "mvp-movement",
            "title": "MVP 移动分析",
            "duration": "已完成" if result and result.status == "completed" else "未完成",
            "shots": 0,
            "pattern": "当前版本暂不识别击球与回合",
            "result": "移动指标可用" if not no_tracks else "轨迹不可用",
            "observation": "报告只展示上传视频可支持的移动、速度、站位和热力图指标，不编造球路或战术事件。",
        }
    ]

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
            "body": "本页优先展示后端 pipeline 产出的移动和轨迹指标，样例击球与战术内容不再混作真实结论。",
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
    unavailable = "当前 MVP 未生成该类战术/击球/动作数据。"
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
            "type": "landing",
            "title": "落点分析暂不可用",
            "eyebrow": "落点分析报告",
            "summary": unavailable,
            "heroMetric": "N/A",
            "heroMetricLabel": "球/落点检测",
            "visualization": "heat",
            "metrics": [_metric("landing-na", "alert", "落点检测", "未接入", unavailable, "MVP 限制", 0)],
            "insights": [_note("landing-note", "risk", "不编造落点", "当前只展示移动与站位指标，落点需要后续球检测能力。")],
            "trainingLink": "先查看移动覆盖报告",
        },
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
            "type": "rally",
            "title": "回合战术暂不可用",
            "eyebrow": "回合战术报告",
            "summary": unavailable,
            "heroMetric": "N/A",
            "heroMetricLabel": "回合切分",
            "visualization": "rally",
            "metrics": [_metric("rally-na", "alert", "回合识别", "未接入", unavailable, "MVP 限制", 0)],
            "insights": [_note("rally-note", "risk", "不编造战术", "回合、击球类型和战术模式需要球轨迹与击球事件识别。")],
            "trainingLink": "先完成移动覆盖训练",
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
        "currentRally": "第 24 回合 · 18 拍",
        "currentTime": "08:42",
        "duration": "12:16",
    },
    "session": {
        "athlete": "球馆体验用户 A",
        "venue": "北京体育大学匹克球训练场",
        "date": "2026-05-04",
        "level": "大众进阶",
        "reportId": "PV-20260504-018",
        "summary": "本次训练以底线相持和中场上网衔接为主，落点控制稳定，但反手回球后的回位速度仍影响下一拍质量。",
        "metrics": [],
        "landingPoints": [
            {"id": "p1", "x": 71, "y": 26, "intensity": 0.88, "label": "右侧底线深区"},
            {"id": "p2", "x": 68, "y": 42, "intensity": 0.64, "label": "右侧中场"},
            {"id": "p3", "x": 41, "y": 32, "intensity": 0.72, "label": "反手斜线压制"},
            {"id": "p4", "x": 29, "y": 67, "intensity": 0.45, "label": "网前小球"},
        ],
        "routes": [
            {
                "id": "r1",
                "from": {"id": "r1-from", "x": 24, "y": 76, "intensity": 0.4, "label": "左后场"},
                "to": {"id": "r1-to", "x": 72, "y": 27, "intensity": 0.9, "label": "右后场"},
                "label": "反手斜线压底",
                "result": "受迫回球",
            },
            {
                "id": "r2",
                "from": {"id": "r2-from", "x": 58, "y": 80, "intensity": 0.5, "label": "中后场"},
                "to": {"id": "r2-to", "x": 30, "y": 38, "intensity": 0.7, "label": "左中场"},
                "label": "正手变线",
                "result": "得分",
            },
        ],
        "movementPath": [
            {"x": 50, "y": 83},
            {"x": 38, "y": 74},
            {"x": 31, "y": 66},
            {"x": 44, "y": 58},
            {"x": 63, "y": 64},
            {"x": 54, "y": 81},
        ],
        "rallies": [
            {
                "id": "ra1",
                "title": "第 3 回合",
                "duration": "18.6 秒",
                "shots": 12,
                "pattern": "反手斜线压制 → 正手变线",
                "result": "主动得分",
                "observation": "连续三拍压向对手反手后，正手变线质量高，是本场最佳进攻回合。",
            }
        ],
    },
    "dashboardMetrics": [
        {
            "id": "overall",
            "icon": "activity",
            "label": "综合表现评分",
            "value": "82",
            "detail": "深区接发抵消了后段网前失误",
            "trend": "较上场 +8%",
            "direction": "up",
            "progress": 82,
            "sparkline": [62, 66, 70, 68, 74, 82],
        },
        {
            "id": "third",
            "icon": "waves",
            "label": "第三拍吊球成功率",
            "value": "61%",
            "detail": "右侧受压时吊球仍偏短",
            "trend": "-3%",
            "direction": "down",
            "progress": 61,
            "sparkline": [66, 68, 64, 65, 63, 61],
        },
    ],
    "reportActions": [
        {"type": "landing", "title": "落点分析报告", "description": "查看深区命中、边线风险与热力分布。", "path": "/reports/landing"},
        {"type": "movement", "title": "步法移动报告", "description": "拆解回位路径、覆盖平衡和启动延迟。", "path": "/reports/movement"},
        {"type": "rally", "title": "回合战术报告", "description": "追踪发接发、第三拍和网前模式。", "path": "/reports/rally"},
        {"type": "diagnosis", "title": "动作诊断报告", "description": "把动作问题转成证据和纠正方向。", "path": "/reports/diagnosis"},
    ],
    "coachNotes": [
        {"id": "note-advantage", "tone": "advantage", "title": "接发深度带来主动权", "body": "当接发落在对手反手深区时，你方赢下 72% 的回合。"},
        {"id": "note-risk", "tone": "risk", "title": "右侧第三拍吊球容易变短", "body": "第三拍吊球总成功率为 61%，但右侧半场下降到 43%。"},
    ],
    "reportDefinitions": [],
    "playerMarkers": [
        {"id": "a", "label": "A", "team": "near", "x": 28, "y": 72, "color": "#22C55E"},
        {"id": "b", "label": "B", "team": "near", "x": 68, "y": 76, "color": "#D9FF3F"},
        {"id": "c", "label": "C", "team": "far", "x": 34, "y": 23, "color": "#2F80ED"},
        {"id": "d", "label": "D", "team": "far", "x": 75, "y": 28, "color": "#FF9500"},
    ],
    "shotTrajectories": [
        {"id": "third-drop", "path": "M28 72 C42 48, 52 43, 66 31", "color": "#22C55E", "label": "第三拍吊球"}
    ],
    "videoOverlayLabels": [
        {"id": "drop", "label": "第三拍吊球", "tone": "training", "x": 54, "y": 42},
        {"id": "risk", "label": "高风险抽击", "tone": "risk", "x": 39, "y": 31},
    ],
    "timelineMarkers": [
        {"id": "serve", "time": "00:12", "position": 9, "label": "深区发球形成压迫", "tone": "advantage"},
        {"id": "winner", "time": "08:42", "position": 76, "label": "反手深区铺垫制胜分", "tone": "advantage"},
    ],
    "highlights": [
        {"id": "h1", "title": "长回合 #24", "time": "08:42", "result": "得分模式", "tone": "advantage", "description": "反手深区接发后，第六拍获得正手变线窗口。"}
    ],
    "diagnoses": [
        {
            "id": "backswing",
            "issue": "引拍滞后",
            "severity": "中",
            "evidence": "反手位来球中，击球前 280ms 肘部展开不足。",
            "suggestion": "在反手准备阶段提前完成肩髋转向。",
            "expectedOutcome": "提升反手迎前击球比例。",
            "priority": "优先级 1",
        }
    ],
    "trainingRecommendations": [],
    "drillRecommendations": [
        {
            "id": "drill-third-shot",
            "title": "第三拍吊球深度控制",
            "goal": "右侧半场第三拍吊球落入厨房后 1m 区域。",
            "duration": "22 分钟",
            "evidence": "右侧第三拍成功率 43%，低于整体 61%。",
            "difficulty": "高级",
            "linkedReport": "rally",
        }
    ],
    "shotRows": [
        {"id": "s1", "time": "00:12", "type": "发球", "player": "A", "placement": "中路深区", "qualityScore": 88, "qualityBand": "high", "result": "建立优势"}
    ],
    "skillRatings": [{"id": "third-shot", "label": "第三拍处理", "score": 61, "note": "稳定但受压时偏浅。"}],
    "progressPoints": [{"match": "第1场", "performance": 67, "errors": 23, "thirdShot": 48, "kitchen": 52}],
}

DEMO_REPORT["reportDefinitions"] = [
    {
        "type": "landing",
        "title": "落点与线路报告",
        "eyebrow": "落点分析报告",
        "summary": "接发压向反手深区时优势最明显。",
        "heroMetric": "72%",
        "heroMetricLabel": "反手深区回合胜率",
        "visualization": "heat",
        "metrics": DEMO_REPORT["dashboardMetrics"],
        "insights": DEMO_REPORT["coachNotes"],
        "trainingLink": "接发压向反手深区",
    },
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
        "type": "rally",
        "title": "回合战术报告",
        "eyebrow": "回合战术报告",
        "summary": "第三拍和网前相持决定多数回合走向。",
        "heroMetric": "61%",
        "heroMetricLabel": "第三拍吊球成功率",
        "visualization": "rally",
        "metrics": DEMO_REPORT["dashboardMetrics"],
        "insights": DEMO_REPORT["coachNotes"],
        "trainingLink": "第三拍吊球深度控制",
    },
    {
        "type": "diagnosis",
        "title": "动作诊断报告",
        "eyebrow": "动作诊断报告",
        "summary": "主要问题来自反手准备节奏和长回合后的重心控制。",
        "heroMetric": "1",
        "heroMetricLabel": "已识别优先问题",
        "visualization": "diagnosis",
        "metrics": DEMO_REPORT["dashboardMetrics"],
        "insights": DEMO_REPORT["coachNotes"],
        "trainingLink": "反手轻吊稳定性",
    },
]
