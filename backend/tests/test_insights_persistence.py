"""Insights 产物接入与报告投影集成测试（change 任务 5.1–5.7）。

覆盖：
- generate_and_persist_insights 的固定顺序（insights 落盘 + result.json 二次持久化）；
- /report 与 /result 的 insights 状态一致性；
- AnalysisReport v1 旧报告读取兼容、新 real report 为 v2；
- 独立再生成入口（仅凭落盘产物，不触发视觉重跑）。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from test_performance_insights import _job, _result, _structured_viz  # noqa: E402

from app.schemas.analysis import AnalysisReport  # noqa: E402
from app.schemas.pipeline import AnalysisPipelineResult  # noqa: E402
from app.services.mock_analysis import DEMO_REPORT  # noqa: E402
from app.services.performance_insights.service import (  # noqa: E402
    generate_and_persist_insights,
    regenerate_insights_for_job,
)
from app.services.real_report_builder import build_real_performance_report  # noqa: E402
from app.services.storage_service import StorageService  # noqa: E402


class _FakeStorage:
    """最小 StorageService 替身（tmp_path 支撑，验证确定性路径 + 原子写语义）。"""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.output_written = 0

    def structured_visualization_data_path(self, job_id: str) -> Path:
        return self.root / job_id / "structured" / "data.json"

    def performance_insights_json_path(self, job_id: str) -> Path:
        return self.root / job_id / "performance_insights.json"

    def output_json_path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def read_json(self, path: Path) -> dict:
        import json

        return json.loads(path.read_text(encoding="utf-8"))

    def write_json_atomic(self, path: Path, payload: dict) -> Path:
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        if path == self.output_json_path(payload.get("job_id", "")) or "job_id" in payload:
            self.output_written += 1
        return path


def _prepare(tmp_path: Path) -> tuple[_FakeStorage, dict]:
    storage = _FakeStorage(tmp_path)
    job = _job()
    viz_path = storage.structured_visualization_data_path(job.id)
    viz_path.parent.mkdir(parents=True, exist_ok=True)
    import json

    viz_path.write_text(json.dumps(_structured_viz(), ensure_ascii=False), encoding="utf-8")
    # 预写基础 result.json（模拟 Worker 第①步）。
    result = _result()
    storage.write_json_atomic(storage.output_json_path(job.id), result.model_dump(mode="json"))
    storage.output_written = 0
    return storage, {"job": job, "result": result}


def test_generate_and_persist_updates_result_json(tmp_path: Path):
    """5.2 固定顺序：insights 落盘 → artifacts 更新 → result.json 重写。"""
    storage, ctx = _prepare(tmp_path)
    job, result = ctx["job"], ctx["result"]

    updated, artifact = generate_and_persist_insights(job, result, storage=storage)
    assert artifact is not None
    # insights 文件已写入确定性路径。
    insights_path = storage.performance_insights_json_path(job.id)
    assert insights_path.exists()
    # 更新后的 result 带四字段。
    assert updated.artifacts.performance_insights_status == "available"
    assert updated.artifacts.performance_insights_url == (
        f"/api/analysis/jobs/{job.id}/artifacts/performance-insights"
    )
    assert updated.artifacts.performance_insights_json_path is not None
    # result.json 已被重写（二次持久化发生）。
    assert storage.output_written >= 1
    persisted = AnalysisPipelineResult.model_validate(
        storage.read_json(storage.output_json_path(job.id))
    )
    # /result（重读 result.json）与 /report（内存 artifact）状态一致。
    assert persisted.artifacts.performance_insights_status == "available"


def test_real_report_with_insights_v2(tmp_path: Path):
    """5.5：insights 可用时 real report 为 v2 且带完整投影。"""
    storage, ctx = _prepare(tmp_path)
    job, result = ctx["job"], ctx["result"]
    updated, artifact = generate_and_persist_insights(job, result, storage=storage)
    assert artifact is not None

    report = build_real_performance_report(
        job=job,
        metadata=job.metadata,
        report_id="PV-JOB-INSIGHT01",
        generated_at="2026-08-19T10:05:00+00:00",
        result=updated,
        storage=storage,
    )
    assert report.version == "analysis-report-v2"
    assert report.performanceInsights is not None
    assert report.performanceInsights.status == "available"
    # 维度状态卡（无数值分）。
    assert report.performanceInsights.dimensions
    assert all(
        dim.status in ("strength", "stable", "needs_improvement", "insufficient_evidence", "not_applicable", "unsupported")
        for dim in report.performanceInsights.dimensions
    )
    # findings 携带证据 id。
    assert report.performanceInsights.findings
    assert all(f.evidence_ids or f.assessment == "insufficient_evidence" for f in report.performanceInsights.findings)
    # candidate facts 独立区（bounce 候选）。
    assert any(fact.kind == "bounce_candidates" for fact in report.performanceInsights.candidate_facts)
    # 数据可信度摘要。
    assert report.performanceInsights.data_quality_summary


def test_regenerate_without_rerunning_vision(tmp_path: Path):
    """5.3：再生成仅凭落盘产物，不触发视觉阶段重跑（无 pipeline 调用，result 视觉字段不变）。"""
    storage, ctx = _prepare(tmp_path)
    job, result = ctx["job"], ctx["result"]
    _, artifact = generate_and_persist_insights(job, result, storage=storage)
    assert artifact is not None

    # 再生成（缓存命中路径：同签名 + 同 rule 版本 → 返回现有产物）。
    regenerated, reason = regenerate_insights_for_job(job.id, storage=storage, job=job)
    assert regenerated is not None
    assert regenerated.evidence_input_signature == artifact.evidence_input_signature
    # result.json 的视觉产物字段保持不变（tracks/metrics 未被触碰）。
    persisted = AnalysisPipelineResult.model_validate(
        storage.read_json(storage.output_json_path(job.id))
    )
    assert persisted.metrics.model_dump() == result.metrics.model_dump()


def test_legacy_v1_report_still_readable(tmp_path: Path):
    """5.7：旧 v1 report（无 performanceInsights 字段）照常可读。"""
    legacy_payload = dict(DEMO_REPORT)
    legacy_payload["jobId"] = "job-legacy01"
    legacy_payload["reportId"] = "PV-LEGACY"
    legacy_payload["generatedAt"] = "2026-01-01T00:00:00+00:00"
    legacy_payload["metadata"] = _job().metadata.model_dump()
    report = AnalysisReport.model_validate(legacy_payload)
    assert report.version == "analysis-report-v1"
    assert report.performanceInsights is None
