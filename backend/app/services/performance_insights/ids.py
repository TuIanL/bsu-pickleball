"""确定性 ID 与固定排序契约（performance-insights.v1）。

所有产物 id 禁用随机值（uuid4），保证"相同输入 + 相同 rule_profile_version
→ 相同 dimensions/evidence/findings/recommendations"的确定性再生成契约
（change design.md D3）：
- evidence id：`ev:{subject}:{metric}:{window_start_ms}`（无时间窗时省略尾段）；
- finding id：`finding:{rule_id}:{subject}`；
- recommendation id：`rec:{rule_id}:{subject}`。

集合固定排序：subject 升序、dimension 按 PERFORMANCE_DIMENSIONS 固定序、id 字典序。
"""

from __future__ import annotations

from app.schemas.performance_insights import (
    PERFORMANCE_DIMENSIONS,
    DimensionAssessment,
    PerformanceEvidence,
    PerformanceFinding,
    PerformanceSubject,
    PerformanceTrainingRecommendation,
)


def evidence_id(subject_id: str, metric: str, window_start_ms: int | None = None) -> str:
    base = f"ev:{subject_id}:{metric}"
    return f"{base}:{window_start_ms}" if window_start_ms is not None else base


def finding_id(rule_id: str, subject_id: str) -> str:
    return f"finding:{rule_id}:{subject_id}"


def recommendation_id(rule_id: str, subject_id: str) -> str:
    return f"rec:{rule_id}:{subject_id}"


def _subject_sort_key(subject_id: str) -> tuple[int, int, str]:
    """canonical Player_N 按数字升序；team_near 在 team_far 前（近侧优先）；其他最后。"""
    if subject_id.startswith("Player_") and subject_id[len("Player_"):].isdigit():
        return (0, int(subject_id[len("Player_"):]), subject_id)
    if subject_id == "team_near":
        return (1, 0, subject_id)
    if subject_id == "team_far":
        return (1, 1, subject_id)
    return (2, 0, subject_id)


def dimension_sort_key(dimension: str) -> tuple[int, str]:
    """dimension 按 PERFORMANCE_DIMENSIONS 固定序；未知维度排最后。"""
    try:
        return (PERFORMANCE_DIMENSIONS.index(dimension), dimension)
    except ValueError:
        return (len(PERFORMANCE_DIMENSIONS), dimension)


def sort_subjects(subjects: list[PerformanceSubject]) -> list[PerformanceSubject]:
    return sorted(subjects, key=lambda item: _subject_sort_key(item.id))


def sort_evidence(evidence: list[PerformanceEvidence]) -> list[PerformanceEvidence]:
    return sorted(
        evidence,
        key=lambda item: (_subject_sort_key(item.subject_id), dimension_sort_key(item.dimension), item.id),
    )


def sort_findings(findings: list[PerformanceFinding]) -> list[PerformanceFinding]:
    return sorted(
        findings,
        key=lambda item: (_subject_sort_key(item.subject_id), dimension_sort_key(item.dimension), item.id),
    )


def sort_dimensions(dimensions: list[DimensionAssessment]) -> list[DimensionAssessment]:
    return sorted(
        dimensions,
        key=lambda item: (_subject_sort_key(item.subject_id), dimension_sort_key(item.dimension)),
    )


def sort_recommendations(
    recommendations: list[PerformanceTrainingRecommendation],
) -> list[PerformanceTrainingRecommendation]:
    return sorted(
        recommendations,
        key=lambda item: (_subject_sort_key(item.subject_id), dimension_sort_key(item.dimension), item.id),
    )
