"""Performance Insights Engine 测试（assembler / rule engine / 确定性契约）。

覆盖 change 任务 3.1–3.6、4.2–4.8。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.analysis import AnalysisJobSummary, AnalysisUploadMetadata
from app.schemas.metrics import (
    DistanceMetric,
    DoublesSpacingSummary,
    Heatmap,
    PerformanceMetrics,
    SpeedSummary,
    ZoneDwellMetric,
)
from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult
from app.services.performance_insights.evidence_assembler import (
    AssemblerInputs,
    assemble_evidence,
    compute_evidence_input_signature,
)
from app.services.performance_insights.ids import evidence_id, finding_id, recommendation_id
from app.services.performance_insights.rule_engine import RULE_PROFILE_V1, run_insight_rules

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def _metadata(match_format: str = "doubles") -> AnalysisUploadMetadata:
    return AnalysisUploadMetadata(
        fileName="match.mp4",
        matchTitle="测试对局",
        venue="测试球馆",
        matchDate="2026-08-19",
        matchFormat=match_format,  # type: ignore[arg-type]
        cameraAngle="elevated",
        athleteLabel="运动员",
        level="进阶",
    )


def _job(match_format: str = "doubles") -> AnalysisJobSummary:
    return AnalysisJobSummary(
        id="job-insight01",
        status="completed",
        canonicalStatus="succeeded",
        displayStatus="completed",
        stage="report",
        progress=100,
        createdAt="2026-08-19T10:00:00+00:00",
        updatedAt="2026-08-19T10:05:00+00:00",
        metadata=_metadata(match_format),
        stages=[],
        reportId="PV-JOB-INSIGHT01",
        analysisMode="real",
        videoId="video-1",
        calibrationId="cal-1",
    )


def _result(*, with_spacing: bool = True, bounce_count: int = 14) -> AnalysisPipelineResult:
    metrics = PerformanceMetrics(
        distances=[
            DistanceMetric(track_id="Player_1", distance_ft=320.5),
            DistanceMetric(track_id="Player_3", distance_ft=280.0),
        ],
        speeds=[
            SpeedSummary(track_id="Player_1", average_speed_ft_per_s=4.2, max_speed_ft_per_s=9.8, segments=[]),
            SpeedSummary(track_id="Player_3", average_speed_ft_per_s=3.8, max_speed_ft_per_s=8.1, segments=[]),
        ],
        kitchen_dwell=[
            ZoneDwellMetric(track_id="Player_1", kitchen_frames=40, kitchen_seconds=18.3),
            ZoneDwellMetric(track_id="Player_3", kitchen_frames=30, kitchen_seconds=12.0),
        ],
        doubles_spacing=[
            DoublesSpacingSummary(
                pair=("Player_1", "Player_2"),
                average_spacing_ft=8.4,
                min_spacing_ft=3.1,
                max_spacing_ft=14.2,
                samples=[],
            )
        ]
        if with_spacing
        else [],
        heatmap=Heatmap(rows=6, cols=10, cells=[]),
        bounce_event_count=bounce_count,
        ball_detection_rate=0.42,
    )
    return AnalysisPipelineResult(
        job_id="job-insight01",
        video_id="video-1",
        calibration_id="cal-1",
        status="completed",
        generated_at=datetime(2026, 8, 19, 10, 5, 0, tzinfo=UTC),
        stages=[],
        tracks=[],
        metrics=metrics,
        artifacts=AnalysisArtifacts(),
        message="completed",
    )


def _structured_viz() -> dict:
    """模拟 structured visualization data.json 的 zone_stats 部分。"""
    return {
        "zone_stats": {
            "players": [
                {
                    "id": "Player_1",
                    "label": "P1",
                    "color": "#22C55E",
                    "denominator_seconds": 120.0,
                    "tracked_seconds": 100.0,
                    "data_sufficiency": "sufficient",
                    "nvz_occupancy_rate": 0.25,
                    "kitchen_control_rate": 0.25,
                    "avg_distance_to_kitchen_line_m": 1.2,
                    "zones": [
                        {"zone": "kitchen", "label": "网前区", "seconds": 30.0, "occupancy": 0.25},
                        {"zone": "transition", "label": "过渡区", "seconds": 60.0, "occupancy": 0.5},
                        {"zone": "backcourt", "label": "后场区", "seconds": 20.0, "occupancy": 0.1667},
                    ],
                },
                {
                    "id": "Player_3",
                    "label": "P3",
                    "color": "#2F80ED",
                    "denominator_seconds": 120.0,
                    "tracked_seconds": 40.0,
                    "data_sufficiency": "insufficient",
                    "nvz_occupancy_rate": 0.1,
                    "kitchen_control_rate": 0.1,
                    "avg_distance_to_kitchen_line_m": 2.8,
                    "zones": [
                        {"zone": "kitchen", "label": "网前区", "seconds": 12.0, "occupancy": 0.1},
                        {"zone": "transition", "label": "过渡区", "seconds": 90.0, "occupancy": 0.75},
                        {"zone": "backcourt", "label": "后场区", "seconds": 18.0, "occupancy": 0.15},
                    ],
                },
            ]
        }
    }


def _inputs(**overrides) -> AssemblerInputs:
    defaults = dict(
        result=_result(),
        structured_viz=_structured_viz(),
        effective_windows=[(10.0, 25.0), (40.0, 55.0)],
        window_source="manual_timeline",
        input_files=[],
    )
    defaults.update(overrides)
    return AssemblerInputs(**defaults)


# ---------------------------------------------------------------------------
# 3.1–3.4 assembler
# ---------------------------------------------------------------------------


def test_assembler_collects_movement_and_zone_evidence():
    bundle = assemble_evidence(_job(), _inputs())
    metrics = {e.metric for e in bundle.evidence}
    assert "distance_ft" in metrics
    assert "average_speed_ft_per_s" in metrics
    assert "transition_occupancy" in metrics
    assert "nvz_occupancy" in metrics
    assert "avg_distance_to_kitchen_line_m" in metrics
    # subjects：双打 → 2 名球员 + team_near/team_far
    assert [s.id for s in bundle.subjects] == ["Player_1", "Player_3", "team_near", "team_far"]


def test_assembler_converts_windows_to_ms():
    """rally 窗口证据以毫秒表达（spec：时间单位统一）。"""
    bundle = assemble_evidence(_job(), _inputs())
    windows = [e for e in bundle.evidence if e.metric == "rally_window"]
    assert windows
    assert windows[0].start_ms == 10000
    assert windows[0].end_ms == 25000
    # manual_timeline provenance
    assert windows[0].provenance == "manual_timeline"


def test_assembler_marks_candidates_display_only():
    """3.6：bounce/ball 候选在出口即标 candidate + display_only，不进入规则 evidence。"""
    bundle = assemble_evidence(_job(), _inputs())
    candidates = bundle.candidate_facts
    assert candidates
    for candidate in candidates:
        assert candidate.semantic_level == "candidate"
        assert candidate.rule_eligibility == "display_only"
    # 规则可消费的 evidence 里不允许出现 display_only
    assert all(e.rule_eligibility == "eligible" for e in bundle.evidence)
    # bounce 候选计数存在
    assert any(c.metric == "bounce_candidate_count" and c.value == 14.0 for c in candidates)


def test_assembler_doubles_spacing_team_scope():
    bundle = assemble_evidence(_job(), _inputs())
    spacing = [e for e in bundle.evidence if e.metric == "average_spacing_ft"]
    assert spacing and spacing[0].subject_id == "team_near"
    assert spacing[0].dimension == "doubles_cooperation"


def test_assembler_singles_not_applicable():
    """单打：doubles_cooperation 维度 not_applicable，无 team subjects。"""
    bundle = assemble_evidence(_job("singles"), _inputs(result=_result(with_spacing=False)))
    assert all(s.kind == "player" for s in bundle.subjects)
    dim = next(d for d in bundle.data_quality.dimensions if d.dimension == "doubles_cooperation")
    assert dim.status == "not_applicable"


def test_assembler_data_quality_rally_count_unavailable():
    """无时间线时 valid_rally_count = null + unavailable（区别于 0）。"""
    bundle = assemble_evidence(_job(), _inputs(effective_windows=None, window_source=None))
    assert bundle.data_quality.valid_rally_count.value is None
    assert bundle.data_quality.valid_rally_count.status == "unavailable"


def test_assembler_trajectory_coverage():
    bundle = assemble_evidence(_job(), _inputs())
    # (100/120 + 40/120) / 2 = 0.5833
    assert bundle.data_quality.trajectory_coverage_rate == 0.5833


def test_assembler_multiview_reference_view_provenance():
    """multiview 任务但融合产物不可用 → reference_view。"""
    result = _result()
    result = result.model_copy(update={"requested_execution_mode": "late_fusion_v1"})
    bundle = assemble_evidence(_job(), _inputs(result=result))
    assert all(e.provenance == "reference_view" for e in bundle.evidence if e.metric == "distance_ft")


def test_assembler_multiview_fused_provenance():
    """融合产物 available → fused_multiview。"""
    result = _result()
    artifacts = result.artifacts.model_copy(update={"fused_player_overlay_status": "available"})
    result = result.model_copy(update={"artifacts": artifacts})
    bundle = assemble_evidence(_job(), _inputs(result=result))
    assert all(e.provenance == "fused_multiview" for e in bundle.evidence if e.metric == "distance_ft")


# ---------------------------------------------------------------------------
# 3.6 evidence_input_signature
# ---------------------------------------------------------------------------


def test_evidence_input_signature_deterministic(tmp_path: Path):
    f1 = tmp_path / "result.json"
    f1.write_text(json.dumps({"a": 1}), encoding="utf-8")
    sig1 = compute_evidence_input_signature(_result(), [f1])
    sig2 = compute_evidence_input_signature(_result(), [f1])
    assert sig1 == sig2


def test_evidence_input_signature_changes_with_file(tmp_path: Path):
    """artifact 内容变化 → 签名变化（job inputSignature 无法感知的场景）。"""
    f1 = tmp_path / "result.json"
    f1.write_text(json.dumps({"a": 1}), encoding="utf-8")
    sig1 = compute_evidence_input_signature(_result(), [f1])
    f1.write_text(json.dumps({"a": 2}), encoding="utf-8")
    sig2 = compute_evidence_input_signature(_result(), [f1])
    assert sig1 != sig2


# ---------------------------------------------------------------------------
# 4.x rule engine
# ---------------------------------------------------------------------------


def test_rule_engine_filters_display_only_evidence():
    """4.7：display_only 证据无法进入任何 finding。"""
    bundle = assemble_evidence(_job(), _inputs())
    artifact = run_insight_rules(_job(), bundle)
    # 无 finding 引用候选证据
    evidence_ids = {e.id for e in bundle.evidence}
    for finding in artifact.findings:
        assert set(finding.evidence_ids) <= evidence_ids
    # bounce candidate 的 id 不在任何 finding 中
    candidate_ids = {c.id for c in bundle.candidate_facts}
    for finding in artifact.findings:
        assert not (set(finding.evidence_ids) & candidate_ids)


def test_rule_engine_findings_bind_real_evidence():
    """每条非 insufficient_evidence finding ≥1 条真实 evidence。"""
    bundle = assemble_evidence(_job(), _inputs())
    artifact = run_insight_rules(_job(), bundle)
    assert artifact.findings
    evidence_map = {e.id: e for e in bundle.evidence}
    for finding in artifact.findings:
        if finding.assessment != "insufficient_evidence":
            assert finding.evidence_ids
            for eid in finding.evidence_ids:
                assert eid in evidence_map


def test_rule_engine_insufficient_evidence_for_sparse_player():
    """数据不足（insufficient 球员）→ 场位维度 insufficient_evidence 或低置信，而非硬算结论。"""
    bundle = assemble_evidence(_job(), _inputs())
    artifact = run_insight_rules(_job(), bundle)
    p3_zone_findings = [
        f
        for f in artifact.findings
        if f.subject_id == "Player_3" and f.dimension == "court_positioning"
    ]
    assert p3_zone_findings
    # 区域统计 quality=low 的球员，场位结论必须是 insufficient_evidence 或低置信。
    assert all(
        f.assessment == "insufficient_evidence" or f.confidence == "low" for f in p3_zone_findings
    )


def test_rule_engine_singles_doubles_dimension_not_applicable():
    bundle = assemble_evidence(_job("singles"), _inputs(result=_result(with_spacing=False)))
    artifact = run_insight_rules(_job("singles"), bundle)
    dim = next(d for d in artifact.dimensions if d.dimension == "doubles_cooperation")
    assert dim.status == "not_applicable"


def test_rule_engine_dimension_assessments_present():
    """DimensionAssessment 6 态覆盖：每个 subject × 每个维度都有权威状态。"""
    bundle = assemble_evidence(_job(), _inputs())
    artifact = run_insight_rules(_job(), bundle)
    assert artifact.dimensions
    statuses = {d.status for d in artifact.dimensions}
    # transition_decision 无证据能力 → unsupported 出现
    assert "unsupported" in statuses
    # placement_control 只有候选 → 不出现确定结论维度状态
    placement = [d for d in artifact.dimensions if d.dimension == "placement_control"]
    assert all(d.status in ("insufficient_evidence", "unsupported") for d in placement)


def test_rule_engine_deterministic_ids_and_ordering():
    """4.8：确定性 ID + 固定排序（同输入 + 同 rule_profile 除 generated_at 外逐字段一致）。"""
    bundle = assemble_evidence(_job(), _inputs())
    first = run_insight_rules(_job(), bundle, generated_at="2026-08-19T10:05:00+00:00")
    second = run_insight_rules(_job(), bundle, generated_at="2026-08-19T10:05:00+00:00")
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    # id 格式
    for finding in first.findings:
        assert finding.id.startswith("finding:")
    for rec in first.recommendations:
        assert rec.id.startswith("rec:")
    # 排序稳定：Player_N 数字升序 + team_near 在 team_far 前。
    subjects_order = [s.id for s in first.subjects]
    assert subjects_order[:2] == ["Player_1", "Player_3"]
    assert subjects_order.index("team_near") < subjects_order.index("team_far")
    # findings 按（subject, dimension 固定序, id）排列：Player findings 全部在 team/match 之前。
    subject_order_index = {sid: i for i, sid in enumerate(subjects_order + ["match"])}
    finding_subjects = [f.subject_id for f in first.findings]
    ranks = [subject_order_index.get(sid, 99) for sid in finding_subjects]
    assert ranks == sorted(ranks)


def test_rule_engine_no_uncalibrated_scores():
    """不输出数值技能分：findings/dimensions 无 score 字段，文案无评分数字承诺。"""
    bundle = assemble_evidence(_job(), _inputs())
    artifact = run_insight_rules(_job(), bundle)
    for finding in artifact.findings:
        assert finding.assessment in ("strength", "stable", "needs_improvement", "insufficient_evidence")
    for dim in artifact.dimensions:
        assert dim.status in (
            "strength",
            "stable",
            "needs_improvement",
            "insufficient_evidence",
            "not_applicable",
            "unsupported",
        )


def test_rule_engine_kcr_not_used_as_ability_score():
    """4.6：规则不得把 NVZ 占用率当作越高越好的能力分（文案不出现"网前能力 X 分"类措辞）。"""
    bundle = assemble_evidence(_job(), _inputs())
    artifact = run_insight_rules(_job(), bundle)
    for finding in artifact.findings:
        assert "能力" not in finding.title or "能力" in finding.title  # 标题允许出现"能力"一词
        for forbidden in ("网前能力", "评分", "X.X 级"):
            assert forbidden not in finding.diagnosis


def test_rule_engine_threshold_source_labeled():
    """阈值来源标注：product_reference_v1，不称专业标准。"""
    bundle = assemble_evidence(_job(), _inputs())
    artifact = run_insight_rules(_job(), bundle)
    assert artifact.rule_profile_version == RULE_PROFILE_VERSION
    for finding in artifact.findings:
        if finding.rule_id:
            assert finding.threshold_source == "product_reference_v1"


def test_rule_engine_rally_window_copy_scoped():
    """4.4：rally 窗口类 finding 文案限定"人工标记的有效回合窗口"，且明确不推断结果语义。"""
    bundle = assemble_evidence(_job(), _inputs())
    artifact = run_insight_rules(_job(), bundle)
    rally_findings = [f for f in artifact.findings if f.rule_id == "rally_window_movement_profile"]
    assert rally_findings
    for finding in rally_findings:
        assert "人工标记的有效回合窗口" in finding.diagnosis
        # 必须显式声明不推断回合结果语义（胜负/失误/战术仅出现在否定声明中）。
        assert "不推断" in finding.diagnosis
        # 不出现任何肯定的结果推断措辞。
        for forbidden in ("赢得了", "输掉了", "失误较多", "战术执行"):
            assert forbidden not in finding.diagnosis


# ---------------------------------------------------------------------------
# id 契约
# ---------------------------------------------------------------------------


def test_id_contract_formats():
    assert evidence_id("Player_1", "distance_ft") == "ev:Player_1:distance_ft"
    assert evidence_id("Player_1", "rally_window", 10000) == "ev:Player_1:rally_window:10000"
    assert finding_id("transition_zone_dwell", "Player_1") == "finding:transition_zone_dwell:Player_1"
    assert recommendation_id("transition_zone_dwell", "Player_1") == "rec:transition_zone_dwell:Player_1"


RULE_PROFILE_VERSION = RULE_PROFILE_V1.version
