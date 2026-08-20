"""真实分析报告构建器 —— source=job 报告的唯一权威构建入口。

硬约束（import 守卫测试保证）：本模块及其依赖的 performance_insights 链路
严禁 import `DEMO_REPORT` / `demoAnalysisReport`。

报告从 AnalysisPipelineResult 真实数据从零构建（version=analysis-report-v2）：
- insights 可用时：注入 performanceInsights 投影子集；
- insights 不可用时：显式降级为"移动数据 + 洞察暂不可用"，绝不回退 demo 结论。
"""

from __future__ import annotations

from app.schemas.analysis import (
    AnalysisJobSummary,
    AnalysisReport,
    AnalysisUploadMetadata,
    ReportPerformanceInsights,
)
from app.schemas.pipeline import AnalysisPipelineResult
from app.services.performance_insights.service import generate_insights_for_result


def build_real_performance_report(
    job: AnalysisJobSummary,
    metadata: AnalysisUploadMetadata,
    report_id: str,
    generated_at: str,
    result: AnalysisPipelineResult | None,
    storage=None,
) -> AnalysisReport:
    """从真实 pipeline 结果构建报告（v2）。"""
    insights_artifact, unavailable_reason = generate_insights_for_result(job, result, storage=storage)
    insights = _project_insights(insights_artifact, unavailable_reason)

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

    summary = (
        f"本次分析基于上传视频生成，检测到 {track_count} 条球员轨迹、{point_count} 个场地坐标点，"
        f"累计移动距离约 {total_distance:.1f} 英尺。"
        if not no_tracks
        else (
            "本次任务已处理上传视频，但当前没有生成可用的场地轨迹。请检查四角标定、拍摄角度、模型依赖和视频清晰度。"
            if not limited
            else "本次任务未提供有效场地标定，因此只保留上传与任务状态，不生成场地投影移动指标。"
        )
    )
    dashboard_metrics = _dashboard_metrics(
        total_distance=total_distance,
        avg_speed=avg_speed,
        max_speed=max_speed,
        kitchen_seconds=kitchen_seconds,
        point_count=point_count,
    )

    return AnalysisReport(
        version="analysis-report-v2",
        source="job",
        jobId=job.id,
        reportId=report_id,
        generatedAt=generated_at,
        metadata=metadata,
        match={
            "title": metadata.matchTitle,
            "subtitle": "真实上传视频 · MVP 移动分析" if not limited else "真实上传视频 · 未标定有限分析",
            "date": metadata.matchDate,
            "venue": metadata.venue,
            "teams": metadata.athleteLabel,
            "score": "MVP",
            "currentRally": "移动轨迹分析" if not no_tracks else "未生成可用轨迹",
            "currentTime": "完成",
            "duration": "pipeline",
        },
        session={
            "athlete": metadata.athleteLabel,
            "venue": metadata.venue,
            "date": metadata.matchDate,
            "level": metadata.level,
            "reportId": report_id,
            "summary": summary,
            "metrics": [],
            "landingPoints": [],
            "routes": [],
            "movementPath": _tracks_to_movement_path(tracks),
            "rallies": [],
        },
        dashboardMetrics=dashboard_metrics,
        reportDefinitions=_report_definitions(
            dashboard_metrics,
            total_distance=total_distance,
            avg_speed=avg_speed,
            max_speed=max_speed,
            kitchen_seconds=kitchen_seconds,
            point_count=point_count,
            limited=limited,
            no_tracks=no_tracks,
            insights_available=insights is not None and insights.status == "available",
        ),
        reportActions=[
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
        playerMarkers=_tracks_to_player_markers(
            tracks,
            doubles=(metadata.matchFormat == "doubles") if getattr(metadata, "matchFormat", None) else True,
        ),
        shotTrajectories=[],
        videoOverlayLabels=[
            {"id": "source-real", "label": "真实上传视频", "tone": "training", "x": 50, "y": 18},
            {
                "id": "limited" if limited else "movement",
                "label": "缺少标定" if limited else f"{point_count} 个轨迹点",
                "tone": "risk" if limited or no_tracks else "advantage",
                "x": 53,
                "y": 42,
            },
        ],
        timelineMarkers=[
            {
                "id": "pipeline",
                "time": "完成",
                "position": 88,
                "label": result.message if result else "pipeline 结果不可用",
                "tone": "risk" if limited or no_tracks else "advantage",
            }
        ],
        highlights=[
            {
                "id": "movement-summary",
                "title": "移动轨迹摘要",
                "time": "MVP",
                "result": "算法输出",
                "tone": "risk" if limited or no_tracks else "advantage",
                "description": summary,
            }
        ],
        coachNotes=[
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
        ],
        diagnoses=[
            {
                "id": "mvp-limited-diagnosis",
                "issue": "动作诊断暂不可用",
                "severity": "低",
                "evidence": "当前 MVP 未接入姿态动作诊断模型。",
                "suggestion": "先使用移动距离、速度和热力图作为训练反馈依据。",
                "expectedOutcome": "避免把样例动作诊断误认为上传视频结论。",
                "priority": "说明",
            }
        ],
        trainingRecommendations=[],
        drillRecommendations=[
            {
                "id": "drill-court-coverage",
                "title": "场地覆盖与回位节奏",
                "goal": "围绕热区和移动路径做 5 组回位练习。",
                "duration": "18 分钟",
                "evidence": summary,
                "difficulty": "进阶",
                "linkedReport": "movement",
            }
        ],
        shotRows=[],
        skillRatings=[
            {
                "id": "movement-coverage",
                "label": "移动数据完整度",
                "score": min(100, max(0, point_count * 8)),
                "note": "分数来自可用轨迹点数量，不代表技术评分。",
            }
        ],
        progressPoints=[
            {
                "match": "本次上传",
                "performance": min(100, max(0, int(total_distance))),
                "errors": 0,
                "thirdShot": 0,
                "kitchen": min(100, max(0, int(kitchen_seconds * 10))),
            }
        ],
        performanceInsights=insights,
    )


def _project_insights(
    artifact,
    unavailable_reason: str | None,
) -> ReportPerformanceInsights | None:
    """把 insights artifact 投影为报告可读子集；不可用时显式降级。"""
    if artifact is None:
        if unavailable_reason is None:
            return None
        return ReportPerformanceInsights(status="unavailable", unavailable_reason=unavailable_reason)
    from app.services.performance_insights.projector import project_insights_to_report

    return project_insights_to_report(artifact)


def _dashboard_metrics(
    *,
    total_distance: float,
    avg_speed: float,
    max_speed: float,
    kitchen_seconds: float,
    point_count: int,
) -> list[dict]:
    return [
        _metric(
            "distance",
            "activity",
            "累计移动距离",
            f"{total_distance:.1f} ft",
            "来自场地投影轨迹的累计距离",
            "真实视频",
            min(100, int(total_distance)),
        ),
        _metric(
            "avg-speed",
            "timer",
            "平均移动速度",
            f"{avg_speed:.1f} ft/s",
            f"最高速度 {max_speed:.1f} ft/s",
            "pipeline",
            min(100, int(avg_speed * 12)),
        ),
        _metric(
            "kitchen",
            "waves",
            "厨房区停留",
            f"{kitchen_seconds:.1f}s",
            "按投影点统计的非截击区停留时间",
            "真实视频",
            min(100, int(kitchen_seconds * 10)),
        ),
        _metric(
            "tracks",
            "radar",
            "可用轨迹点",
            str(point_count),
            "用于生成可视化和热力图的点数量",
            "算法输出",
            min(100, point_count * 8),
        ),
    ]


def _report_definitions(
    movement_metrics: list[dict],
    *,
    total_distance: float,
    avg_speed: float,
    max_speed: float,
    kitchen_seconds: float,
    point_count: int,
    limited: bool,
    no_tracks: bool,
    insights_available: bool,
) -> list[dict]:
    unavailable = "当前 MVP 未生成该类动作诊断数据。"
    source_note = "未提供有效标定，移动报告处于有限模式。" if limited else "来自上传视频的 pipeline 结果。"
    if no_tracks and not limited:
        source_note = "pipeline 已完成，但没有检测到可用球员轨迹。"

    return [
        {
            "type": "performance",
            "title": "本场表现报告",
            "eyebrow": "表现洞察报告",
            "summary": (
                "基于真实证据的表现洞察：维度状态、关键发现与下一次训练目标。"
                if insights_available
                else "洞察引擎尚未接入，当前先以移动数据作为训练反馈依据。"
            ),
            "heroMetric": f"{total_distance:.1f} ft",
            "heroMetricLabel": "累计移动距离",
            "visualization": "performance",
            "metrics": movement_metrics,
            "insights": [
                _note(
                    "performance-source",
                    "training" if not insights_available else "advantage",
                    "表现洞察" if insights_available else "洞察暂不可用",
                    (
                        "洞察由版本化规则从真实证据推导，每条发现可回溯到数据与视频片段。"
                        if insights_available
                        else "Performance Insight Engine 尚未接入，完成后将提供维度状态与训练目标。"
                    ),
                ),
            ],
            "trainingLink": "把首要问题转化为下一次训练目标",
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
                _note(
                    "movement-speed",
                    "advantage" if point_count else "risk",
                    "速度与覆盖",
                    f"平均速度 {avg_speed:.1f} ft/s，最高速度 {max_speed:.1f} ft/s。",
                ),
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
            "insights": [
                _note("diagnosis-note", "training", "需要姿态模型", "RTMPose 或同等姿态模型接入后才能输出动作证据。")
            ],
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


def _tracks_to_player_markers(tracks, doubles: bool = True) -> list[dict]:
    from app.schemas.analysis import canonical_player_side

    latest: dict[str, object] = {}
    for track in tracks:
        latest[track.track_id] = track

    colors = ["#22C55E", "#D9FF3F", "#2F80ED", "#FF9500"]
    markers = []
    ordered_ids = sorted(
        (str(track_id) for track_id in latest),
        key=lambda pid: (
            int(pid[len("Player_"):]) if pid.startswith("Player_") and pid[len("Player_"):].isdigit() else 2**31,
            pid,
        ),
    )
    for index, track_id in enumerate(ordered_ids[:4]):
        track = latest[track_id]
        team = canonical_player_side(track_id, doubles)
        if not team:
            court = getattr(track, "court_point", None)
            team = "near" if court is not None and getattr(court, "y", 22.0) < 22.0 else "far"
        markers.append(
            {
                "id": str(track_id),
                "label": chr(ord("A") + index),
                "team": team,
                "x": 12 + (track.court_point.x / 20.0) * 76,
                "y": 7 + (track.court_point.y / 44.0) * 42,
                "color": colors[index % len(colors)],
            }
        )
    return markers


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0
