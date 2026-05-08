from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4

from typing import Optional

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

JOBS: dict[str, AnalysisJobSummary] = {}
REPORTS: dict[str, AnalysisReport] = {}
RESULTS: dict[str, AnalysisPipelineResult] = {}

ORDERED_STAGES: list[AnalysisStageId] = [
    "upload",
    "queue",
    "frame-sampling",
    "detection",
    "pose",
    "tracking",
    "court-calibration",
    "event-analysis",
    "report",
]

STAGE_DETAILS: dict[AnalysisStageId, tuple[str, str]] = {
    "upload": ("视频上传", "保存视频和基础比赛信息"),
    "queue": ("任务排队", "等待视觉分析任务执行"),
    "frame-sampling": ("抽帧采样", "按时间轴抽取关键帧"),
    "detection": ("目标检测", "预留 YOLO11 检测球员、球、球拍和场地元素"),
    "pose": ("人体姿态", "预留 RTMPose26 识别人体关键点"),
    "tracking": ("轨迹跟踪", "关联球员、球和击球轨迹"),
    "court-calibration": ("场地标定", "映射画面坐标到匹克球场"),
    "event-analysis": ("事件分析", "识别击球、落点、回合和风险模式"),
    "report": ("报告生成", "生成报告 JSON 并交给前端展示"),
}


def build_stages(active_stage: AnalysisStageId = "report") -> list[AnalysisStage]:
    active_index = ORDERED_STAGES.index(active_stage)
    stages: list[AnalysisStage] = []

    for index, stage_id in enumerate(ORDERED_STAGES):
        label, detail = STAGE_DETAILS[stage_id]
        status = "pending"

        if index < active_index or active_stage == "report":
            status = "done"
        elif index == active_index:
            status = "active"

        stages.append(AnalysisStage(id=stage_id, label=label, status=status, detail=detail))

    return stages


def create_mock_job(metadata: AnalysisUploadMetadata) -> AnalysisJobSummary:
    return create_analysis_job(AnalysisJobCreate(metadata=metadata))


def create_analysis_job(payload: AnalysisJobCreate) -> AnalysisJobSummary:
    now = datetime.now(timezone.utc).isoformat()
    job_id = f"job-{uuid4().hex[:10]}"
    report_id = f"PV-{job_id.upper()}"
    result: AnalysisPipelineResult | None = None
    status = "completed"
    error_message = None

    if payload.videoId:
        result = AnalysisPipeline(frame_stride=payload.frameStride).run(
            job_id=job_id,
            video_id=payload.videoId,
            calibration_id=payload.calibrationId,
            frame_stride=payload.frameStride,
        )
        status = result.status
        error_message = None if result.status == "completed" else result.message

    job = AnalysisJobSummary(
        id=job_id,
        status=status,
        stage="report",
        progress=100 if status == "completed" else 0,
        createdAt=now,
        updatedAt=datetime.now(timezone.utc).isoformat(),
        metadata=payload.metadata,
        stages=build_stages("report" if status == "completed" else "frame-sampling"),
        reportId=report_id,
        errorMessage=error_message,
        videoId=payload.videoId,
        calibrationId=payload.calibrationId,
    )
    report = build_mock_report(job, payload.metadata, report_id, now)

    JOBS[job_id] = job
    REPORTS[job_id] = report
    if result is not None:
        RESULTS[job_id] = result

    return job


def get_mock_job(job_id: str) -> Optional[AnalysisJobSummary]:
    return JOBS.get(job_id)


def get_mock_report(job_id: str) -> Optional[AnalysisReport]:
    return REPORTS.get(job_id)


def get_pipeline_result(job_id: str) -> Optional[AnalysisPipelineResult]:
    cached = RESULTS.get(job_id)
    if cached is not None:
        return cached
    return None


def build_mock_report(
    job: AnalysisJobSummary,
    metadata: AnalysisUploadMetadata,
    report_id: str,
    generated_at: str,
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

    return AnalysisReport.model_validate(payload)


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
