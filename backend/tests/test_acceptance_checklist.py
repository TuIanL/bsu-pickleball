"""全链路验收清单（change 任务 7.1）。

一条链路串起：job + result + structured viz → Evidence Assembler → Rule Engine
→ 落盘 → Report Projector → AnalysisReport v2，逐条验证 specs/performance-insights
的四条硬不变量与降级语义。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests"))

from test_performance_insights import _job, _result, _structured_viz  # noqa: E402
from test_real_report_no_demo import DEMO_ONLY_STRINGS  # noqa: E402

from app.services.performance_insights.service import generate_and_persist_insights  # noqa: E402
from app.services.real_report_builder import build_real_performance_report  # noqa: E402


class _FakeStorage:
    """最小 StorageService 替身（与 test_insights_persistence 保持一致的语义）。"""

    def __init__(self, root: Path) -> None:
        self.root = root

    def structured_visualization_data_path(self, job_id: str) -> Path:
        return self.root / job_id / "structured" / "data.json"

    def performance_insights_json_path(self, job_id: str) -> Path:
        return self.root / job_id / "performance_insights.json"

    def output_json_path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def read_json(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def write_json_atomic(self, path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path


def _run_full_chain(tmp_path: Path, *, with_viz: bool = True):
    storage = _FakeStorage(tmp_path)
    job = _job()
    if with_viz:
        import json

        viz_path = storage.structured_visualization_data_path(job.id)
        viz_path.parent.mkdir(parents=True, exist_ok=True)
        viz_path.write_text(json.dumps(_structured_viz(), ensure_ascii=False), encoding="utf-8")
    result = _result()
    updated, artifact = generate_and_persist_insights(job, result, storage=storage)
    report = build_real_performance_report(
        job=job,
        metadata=job.metadata,
        report_id="PV-JOB-INSIGHT01",
        generated_at="2026-08-19T10:05:00+00:00",
        result=updated,
        storage=storage,
    )
    return report, artifact


def test_acceptance_zero_demo_conclusions(tmp_path: Path):
    """验收 1：真实报告 0 demo 结论（端到端含 insights 投影）。"""
    report, _ = _run_full_chain(tmp_path)
    assert report.source == "job"

    def _walk(node):
        if isinstance(node, str):
            yield node
        elif isinstance(node, dict):
            for value in node.values():
                yield from _walk(value)
        elif isinstance(node, (list, tuple)):
            for item in node:
                yield from _walk(item)

    joined = "\n".join(_walk(report.model_dump(mode="json")))
    for demo_string in DEMO_ONLY_STRINGS:
        assert demo_string not in joined, f"真实报告出现 demo 结论：{demo_string}"


def test_acceptance_every_finding_binds_traceable_evidence(tmp_path: Path):
    """验收 2+3：每条 finding ≥1 真实 evidence，且 evidence 可追溯 artifact/metric。"""
    _, artifact = _run_full_chain(tmp_path)
    evidence_map = {e.id: e for e in artifact.evidence}
    for finding in artifact.findings:
        if finding.assessment != "insufficient_evidence":
            assert finding.evidence_ids, f"finding {finding.id} 无证据绑定"
        for eid in finding.evidence_ids:
            evidence = evidence_map[eid]
            assert evidence.metric, f"evidence {eid} 无 metric"
            assert evidence.source_artifacts, f"evidence {eid} 无 source_artifacts"
            assert evidence.provenance in (
                "pipeline_metric",
                "structured_visualization",
                "manual_timeline",
                "fused_multiview",
                "reference_view",
                "derived_rule",
            )


def test_acceptance_insufficient_evidence_and_degradation(tmp_path: Path):
    """验收 4+7：数据不足输出 insufficient_evidence；缺失数据只降级维度不整体失败。"""
    # 无 structured viz（zone stats 缺失）：insights 仍生成，场位维度降级。
    report, artifact = _run_full_chain(tmp_path, with_viz=False)
    assert artifact is not None
    assert report.performanceInsights is not None
    assert report.performanceInsights.status == "available"
    court = [d for d in artifact.data_quality.dimensions if d.dimension == "court_positioning"]
    assert court and court[0].status == "insufficient_data"
    # 维度状态降级为 insufficient_evidence，而不是报错或硬算。
    dims = [d for d in artifact.dimensions if d.dimension == "court_positioning"]
    assert all(d.status in ("insufficient_evidence", "unsupported") for d in dims)
    # 稀疏球员（quality=low）的 finding 走 insufficient_evidence（见 test_performance_insights）。


def test_acceptance_singles_not_applicable_and_doubles_scope(tmp_path: Path):
    """验收 5+6：单打 doubles 维度 not_applicable；双打 player/team 双 scope。"""
    report, artifact = _run_full_chain(tmp_path)
    # 双打：player + team subjects 共存，team findings 存在。
    subject_ids = {s.id for s in artifact.subjects}
    assert any(sid.startswith("Player_") for sid in subject_ids)
    assert "team_near" in subject_ids
    assert any(f.subject_id == "team_near" for f in artifact.findings)

    # 单打链路：doubles_cooperation = not_applicable，无 team subjects。
    from test_performance_insights import _inputs
    from app.services.performance_insights.evidence_assembler import assemble_evidence
    from app.services.performance_insights.rule_engine import run_insight_rules

    singles_job = _job("singles")
    bundle = assemble_evidence(singles_job, _inputs(result=_result(with_spacing=False)))
    singles_artifact = run_insight_rules(singles_job, bundle, generated_at="2026-08-19T10:05:00+00:00")
    assert all(s.kind == "player" for s in singles_artifact.subjects)
    dim = next(d for d in singles_artifact.dimensions if d.dimension == "doubles_cooperation")
    assert dim.status == "not_applicable"


def test_acceptance_no_uncalibrated_scores_or_fake_trends(tmp_path: Path):
    """验收（specs 禁止未校准评分与伪造趋势）：投影无数值分、无历史对比。"""
    report, _ = _run_full_chain(tmp_path)
    insights = report.performanceInsights
    assert insights is not None
    # 维度卡只有 status + summary，无 score 字段。
    for dimension in insights.dimensions:
        assert not hasattr(dimension, "score") or dimension.score is None
    # 建议只有 baseline + next_target。
    for recommendation in insights.recommendations:
        assert recommendation.baseline
        assert recommendation.next_target
        assert not hasattr(recommendation, "history") or recommendation.history is None
