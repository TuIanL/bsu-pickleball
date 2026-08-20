"""AnalysisReportProjector —— insights artifact → 报告用户可读投影子集。

职责边界（design D3）：Projector 只做展示投影，不做领域判断——
维度状态直接取 DimensionAssessment（Rule Engine 权威输出），
findings / recommendations / candidate facts 原样映射。
"""

from __future__ import annotations

from app.schemas.performance_insights import (
    DIMENSION_LABELS,
    PerformanceInsightsArtifact,
    ProjectedCandidateFact,
    ProjectedDimensionCard,
    ProjectedFinding,
    ProjectedRecommendation,
    ReportPerformanceInsights,
)


def project_insights_to_report(artifact: PerformanceInsightsArtifact) -> ReportPerformanceInsights:
    """把 insights artifact 投影为 AnalysisReport.performanceInsights 字段。"""
    quality = artifact.data_quality
    quality_parts: list[str] = []
    if quality.valid_rally_count.status == "available" and quality.valid_rally_count.value is not None:
        quality_parts.append(f"有效 Rally {quality.valid_rally_count.value} 个")
    else:
        quality_parts.append("无可靠 Rally 边界")
    if quality.trajectory_coverage_rate is not None:
        quality_parts.append(f"轨迹覆盖率 {quality.trajectory_coverage_rate * 100:.0f}%")
    else:
        quality_parts.append("轨迹覆盖率未知")

    dimensions = [
        ProjectedDimensionCard(
            dimension=item.dimension,
            label=DIMENSION_LABELS.get(item.dimension, item.dimension),
            subject_id=item.subject_id,
            status=item.status,
            summary=item.summary,
        )
        for item in artifact.dimensions
    ]
    findings = [
        ProjectedFinding(
            id=item.id,
            subject_id=item.subject_id,
            dimension=item.dimension,
            dimension_label=DIMENSION_LABELS.get(item.dimension, item.dimension),
            assessment=item.assessment,
            priority=item.priority,
            confidence=item.confidence,
            title=item.title,
            diagnosis=item.diagnosis,
            impact=item.impact,
            evidence_ids=list(item.evidence_ids),
            evidence_windows=list(item.evidence_windows),
        )
        for item in artifact.findings
    ]
    recommendations = [
        ProjectedRecommendation(
            id=item.id,
            subject_id=item.subject_id,
            title=item.title,
            detail=item.detail,
            metric=item.metric,
            baseline=item.baseline,
            next_target=item.next_target,
            direction=item.direction,
            finding_id=item.finding_id,
        )
        for item in artifact.recommendations
    ]
    candidate_facts = _project_candidate_facts(artifact)

    return ReportPerformanceInsights(
        status="available",
        match_format=artifact.match_format,
        rule_profile_version=artifact.rule_profile_version,
        data_quality_summary="；".join(quality_parts),
        subjects=list(artifact.subjects),
        dimensions=dimensions,
        findings=findings,
        recommendations=recommendations,
        candidate_facts=candidate_facts,
        primary_focus_finding_id=artifact.primary_focus_finding_id,
    )


def _project_candidate_facts(artifact: PerformanceInsightsArtifact) -> list[ProjectedCandidateFact]:
    """bounce/ball 候选事实投影：仅展示（candidate 语义），不进入 findings。"""
    facts: list[ProjectedCandidateFact] = []
    bounce = next(
        (e for e in artifact.candidate_evidence if e.metric == "bounce_candidate_count"), None
    )
    if bounce is not None and bounce.value:
        facts.append(
            ProjectedCandidateFact(
                kind="bounce_candidates",
                count=int(bounce.value),
                detail=(
                    f"检测到 {int(bounce.value)} 个弹跳候选（algorithm candidate，非确认落点事件），"
                    "可在视频工作台查看候选位置。"
                ),
            )
        )
    ball_rate = next(
        (e for e in artifact.candidate_evidence if e.metric == "ball_detection_rate"), None
    )
    if ball_rate is not None and ball_rate.value:
        facts.append(
            ProjectedCandidateFact(
                kind="ball_trajectory",
                count=None,
                detail=f"球轨迹检测率约 {ball_rate.value * 100:.0f}%（仅覆盖事实，不代表击球/落点结论）。",
            )
        )
    return facts
