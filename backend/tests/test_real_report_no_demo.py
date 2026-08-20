"""真实报告去 Demo 化守卫与端到端测试（change: add-performance-insights-and-feedback-report）。

覆盖任务 1.3 / 1.6（后端部分）：
- 1.3 import 守卫：real report builder / insights 链路模块不得引用 DEMO_REPORT / demoAnalysisReport，
  也不得 import mock_analysis（间接拿到 demo 常量）或前端 demoData；
- 1.6 端到端：真实任务报告（source=job）零 demo 性能结论、version=v2、
  insights 不可用时显式降级（不回退 demo）。
"""

from __future__ import annotations

import ast
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from app.schemas.analysis import AnalysisJobSummary, AnalysisReport, AnalysisUploadMetadata
from app.schemas.metrics import DistanceMetric, Heatmap, PerformanceMetrics, SpeedSummary, ZoneDwellMetric
from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult
from app.services.mock_analysis import DEMO_REPORT, build_demo_report, build_mock_report

BACKEND_DIR = Path(__file__).resolve().parents[1]

# real report 构建链的所有模块（新增模块时同步追加）。
REAL_REPORT_MODULES = [
    Path("app/services/real_report_builder.py"),
    Path("app/services/performance_insights/__init__.py"),
    Path("app/services/performance_insights/service.py"),
]

# 禁止引用的 demo 常量 / 模块。
FORBIDDEN_IMPORT_NAMES = {"DEMO_REPORT", "demoAnalysisReport", "demoData", "mock_analysis"}


def _collect_imported_names(path: Path) -> set[str]:
    """AST 解析模块源码，收集所有 import 引入的名字（模块名/别名/属性名）。"""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


def test_real_report_modules_never_import_demo_constants() -> None:
    """1.3 import 守卫：real 链路模块不引用 demo 常量（含间接 import mock_analysis）。"""
    for relative in REAL_REPORT_MODULES:
        path = BACKEND_DIR / relative
        assert path.exists(), f"real report 模块缺失：{relative}"
        names = _collect_imported_names(path)
        violated = names & FORBIDDEN_IMPORT_NAMES
        assert not violated, f"{relative} 引用了禁止的 demo 引用：{violated}"


def _fake_metadata() -> AnalysisUploadMetadata:
    return AnalysisUploadMetadata(
        fileName="real-match.mp4",
        matchTitle="真实对局测试",
        venue="测试球馆",
        matchDate="2026-08-19",
        matchFormat="doubles",
        cameraAngle="elevated",
        athleteLabel="测试运动员",
        level="进阶",
    )


def _fake_job(metadata: AnalysisUploadMetadata) -> AnalysisJobSummary:
    return AnalysisJobSummary(
        id="job-realtest01",
        status="completed",
        canonicalStatus="succeeded",
        displayStatus="completed",
        stage="report",
        progress=100,
        createdAt="2026-08-19T10:00:00+00:00",
        updatedAt="2026-08-19T10:05:00+00:00",
        finishedAt="2026-08-19T10:05:00+00:00",
        metadata=metadata,
        stages=[],
        reportId="PV-JOB-REALTEST01",
        analysisMode="real",
        videoId="video-1",
        calibrationId="cal-1",
    )


def _fake_result() -> AnalysisPipelineResult:
    metrics = PerformanceMetrics(
        distances=[DistanceMetric(track_id="Player_1", distance_ft=320.5)],
        speeds=[
            SpeedSummary(
                track_id="Player_1",
                average_speed_ft_per_s=4.2,
                max_speed_ft_per_s=9.8,
                segments=[],
            )
        ],
        kitchen_dwell=[ZoneDwellMetric(track_id="Player_1", kitchen_frames=40, kitchen_seconds=18.3)],
        doubles_spacing=[],
        heatmap=Heatmap(rows=6, cols=10, cells=[]),
    )
    return AnalysisPipelineResult(
        job_id="job-realtest01",
        video_id="video-1",
        calibration_id="cal-1",
        status="completed",
        generated_at=datetime.now(UTC),
        stages=[],
        tracks=[],
        metrics=metrics,
        artifacts=AnalysisArtifacts(),
        message="pipeline completed",
    )


# DEMO_REPORT 中独有的性能结论样例字符串——真实报告任何一个都不允许出现。
DEMO_ONLY_STRINGS = (
    "北京体育大学",
    "荧光队",
    "11 - 8",
    "较上场 +8%",
    "右侧覆盖后的回位仍偏慢",
    "引拍滞后",
    "样例移动路径显示",
    "球馆体验用户",
    "覆盖平衡接近理想",
)


def _report_payload_strings(report: AnalysisReport) -> set[str]:
    """递归收集报告中所有字符串值（含嵌套 dict/list）。"""
    strings: set[str] = set()

    def _walk(node: object) -> None:
        if isinstance(node, str):
            strings.add(node)
        elif isinstance(node, dict):
            for value in node.values():
                _walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                _walk(item)

    _walk(report.model_dump(mode="json"))
    return strings


def test_real_report_contains_zero_demo_conclusions() -> None:
    """1.6 端到端：真实任务报告零 demo 性能结论。"""
    metadata = _fake_metadata()
    job = _fake_job(metadata)
    report = build_mock_report(
        job=job,
        metadata=metadata,
        report_id="PV-JOB-REALTEST01",
        generated_at="2026-08-19T10:05:00+00:00",
        result=_fake_result(),
    )
    assert report.source == "job"
    assert report.version == "analysis-report-v2"

    strings = _report_payload_strings(report)
    joined = "\n".join(strings)
    for demo_string in DEMO_ONLY_STRINGS:
        assert demo_string not in joined, f"真实报告出现 demo 结论字符串：{demo_string}"


def test_real_report_insights_unavailable_degrades_explicitly() -> None:
    """pipeline 结果不可用时洞察显式降级，不回退 demo。"""
    metadata = _fake_metadata()
    job = _fake_job(metadata)
    report = build_mock_report(
        job=job,
        metadata=metadata,
        report_id="PV-JOB-REALTEST01",
        generated_at="2026-08-19T10:05:00+00:00",
        result=None,
    )
    assert report.performanceInsights is not None
    assert report.performanceInsights.status == "unavailable"
    assert report.performanceInsights.unavailable_reason


def test_real_report_with_pipeline_result_includes_insights() -> None:
    """引擎接入后：真实 pipeline 结果产出可用洞察投影（不回退 demo）。"""
    metadata = _fake_metadata()
    job = _fake_job(metadata)
    report = build_mock_report(
        job=job,
        metadata=metadata,
        report_id="PV-JOB-REALTEST01",
        generated_at="2026-08-19T10:05:00+00:00",
        result=_fake_result(),
    )
    assert report.performanceInsights is not None
    assert report.performanceInsights.status == "available"
    assert report.performanceInsights.dimensions
    assert report.performanceInsights.findings


def test_demo_report_still_uses_demo_builder() -> None:
    """demo 任务继续走 demo builder（source=demo、v1），不受拆分影响。"""
    metadata = _fake_metadata()
    job = _fake_job(metadata).model_copy(update={"analysisMode": "demo", "videoId": None, "calibrationId": None})
    report = build_demo_report(job, metadata, "PV-JOB-REALTEST01", "2026-08-19T10:05:00+00:00")
    assert report.source == "demo"
    assert report.version == "analysis-report-v1"
    # demo 报告保留 demo 内容（合法：明确标注 source=demo）。
    assert report.match.venue == "测试球馆"


def test_demo_report_payload_matches_constant() -> None:
    """DEMO_REPORT 常量保持 demo 基底（防止误删 demo 数据源）。"""
    assert DEMO_REPORT["source"] == "demo"
    assert DEMO_REPORT["version"] == "analysis-report-v1"
