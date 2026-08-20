"""InsightRuleEngine v1 —— 版本化洞察规则（解释层，维度状态权威）。

红线（change design.md D5 / specs）：
- 入口统一过滤 `rule_eligibility = display_only` 的证据（bounce/ball 候选无法进入任何规则）；
- 禁止把 nvz_occupancy / kitchen_control_rate 当作"越高越好"的能力评分输入；
- 阈值 `threshold_source = product_reference_v1`（产品参考基准，非专业标准）；
- rally 窗口类 finding 文案限定"在人工标记的有效回合窗口中"，不推断胜负/失误/战术；
- 不输出数值技能分 / 历史趋势 / 战术结论；
- 数据不足输出 insufficient_evidence，某类 artifact 缺失只降级对应维度。

确定性：所有 id 由 ids.py 确定性生成；集合固定排序；generated_at 由调用方传入。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.analysis import AnalysisJobSummary
from app.schemas.performance_insights import (
    DIMENSION_LABELS,
    PERFORMANCE_DIMENSIONS,
    DataQualityCounter,
    DimensionAssessment,
    DimensionStatus,
    PerformanceDimension,
    PerformanceEvidence,
    PerformanceFinding,
    PerformanceInsightsArtifact,
    PerformanceSubject,
    PerformanceTrainingRecommendation,
    THRESHOLD_SOURCE_V1,
)
from app.services.performance_insights.evidence_assembler import EvidenceBundle
from app.services.performance_insights.ids import (
    dimension_sort_key,
    finding_id,
    recommendation_id,
    sort_dimensions,
    sort_findings,
    sort_recommendations,
    sort_subjects,
    _subject_sort_key,
)

# ---------------------------------------------------------------------------
# Rule Profile v1（versioned product heuristic）
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InsightRuleProfile:
    """版本化规则档案：所有阈值集中声明，threshold_source 标注来源。"""

    version: str
    threshold_source: str
    # transition_zone_dwell：过渡区占用率高于该值 → 待改进。
    transition_occupancy_high: float
    # kitchen_line_proximity：平均站位距厨房线（米）高于该值 → 待改进；低于一半 → 稳定。
    kitchen_line_distance_far_m: float
    # doubles_spacing_stability：平均间距健康区间 [low, high]（英尺）。
    doubles_spacing_low_ft: float
    doubles_spacing_high_ft: float
    # doubles_spacing_extremes：最小间距低于 / 最大间距高于该值 → 待改进。
    doubles_min_spacing_ft: float
    doubles_max_spacing_ft: float
    # movement_load：全场人均移动距离（英尺）低于该值 → 负载偏低（描述，不作能力评价）。
    movement_load_low_ft: float


RULE_PROFILE_V1 = InsightRuleProfile(
    version="insight-rule-profile.v1",
    threshold_source=THRESHOLD_SOURCE_V1,
    transition_occupancy_high=0.45,
    kitchen_line_distance_far_m=2.0,
    doubles_spacing_low_ft=6.0,
    doubles_spacing_high_ft=12.0,
    doubles_min_spacing_ft=3.0,
    doubles_max_spacing_ft=16.0,
    movement_load_low_ft=150.0,
)


# ---------------------------------------------------------------------------
# 规则执行
# ---------------------------------------------------------------------------


def run_insight_rules(
    job: AnalysisJobSummary,
    bundle: EvidenceBundle,
    *,
    profile: InsightRuleProfile = RULE_PROFILE_V1,
    generated_at: str | None = None,
) -> PerformanceInsightsArtifact:
    """对 Evidence Bundle 执行规则，产出 insights artifact（确定性）。"""
    from datetime import UTC, datetime

    timestamp = generated_at or datetime.now(UTC).isoformat()

    # 4.7 入口过滤：display_only 证据（bounce/ball 候选）无法进入任何规则。
    eligible = [e for e in bundle.evidence if e.rule_eligibility == "eligible"]
    evidence_by_key: dict[tuple[str, str], list[PerformanceEvidence]] = {}
    for evidence in eligible:
        evidence_by_key.setdefault((evidence.subject_id, evidence.metric), []).append(evidence)

    subjects = bundle.subjects
    player_subjects = [s for s in subjects if s.kind == "player"]
    team_subjects = [s for s in subjects if s.kind == "team"]

    findings: list[PerformanceFinding] = []
    recommendations: list[PerformanceTrainingRecommendation] = []

    for subject in player_subjects:
        findings.extend(_player_findings(subject.id, evidence_by_key, profile))
    for subject in team_subjects:
        findings.extend(_team_findings(subject.id, evidence_by_key, profile))
    if not any(f.rule_id == "data_coverage_quality" for f in findings):
        findings.extend(_data_quality_findings(bundle, evidence_by_key))
    if evidence_by_key.get(("match", "rally_window")):
        findings.extend(_rally_window_findings(evidence_by_key, bundle))

    recommendations = _build_recommendations(findings, eligible, profile)
    dimensions = _build_dimension_assessments(subjects, findings, bundle)

    # finding → recommendation 反向引用。
    recommendation_by_finding = {rec.finding_id: rec.id for rec in recommendations if rec.finding_id}
    for finding in findings:
        if finding.id in recommendation_by_finding:
            finding.recommendation_id = recommendation_by_finding[finding.id]

    primary_focus = _primary_focus_finding_id(findings)

    return PerformanceInsightsArtifact(
        job_id=job.id,
        match_format=bundle.match_format,  # type: ignore[arg-type]
        rule_profile_version=profile.version,
        generated_at=timestamp,
        evidence_input_signature=bundle.evidence_input_signature,
        data_quality=bundle.data_quality,
        subjects=sort_subjects(subjects),
        dimensions=sort_dimensions(dimensions),
        evidence=bundle.evidence,  # assembler 已确定性排序，规则引擎不增删 evidence
        candidate_evidence=bundle.candidate_facts,  # 候选事实分列存放（规则不可消费）
        findings=sort_findings(findings),
        recommendations=sort_recommendations(recommendations),
        primary_focus_finding_id=primary_focus,
    )


def _find(evidence_by_key, subject_id: str, metric: str) -> PerformanceEvidence | None:
    entries = evidence_by_key.get((subject_id, metric)) or []
    return entries[0] if entries else None


def _player_findings(
    subject_id: str,
    evidence_by_key: dict[tuple[str, str], list[PerformanceEvidence]],
    profile: InsightRuleProfile,
) -> list[PerformanceFinding]:
    findings: list[PerformanceFinding] = []

    # ── transition_zone_dwell ──
    transition = _find(evidence_by_key, subject_id, "transition_occupancy")
    if transition is not None:
        value = transition.value or 0.0
        if transition.quality == "low":
            findings.append(
                _finding(
                    rule="transition_zone_dwell",
                    subject=subject_id,
                    assessment="insufficient_evidence",
                    title="过渡区停留数据有限",
                    diagnosis=f"该球员有效时间内轨迹覆盖率不足，过渡区占用率 {value * 100:.0f}% 仅基于现有帧估算，不足以给出确定结论。",
                    impact="建议延长有效跟踪时间或补充标定后再评估。",
                    evidence=[transition],
                    priority=3,
                    confidence="low",
                    profile=profile,
                )
            )
        elif value > profile.transition_occupancy_high:
            findings.append(
                _finding(
                    rule="transition_zone_dwell",
                    subject=subject_id,
                    assessment="needs_improvement",
                    title="过渡区停留比例较高",
                    diagnosis=(
                        f"该球员在有效比赛时间中，过渡区（厨房线与后场之间）停留占用约 {value * 100:.0f}%，"
                        f"高于产品参考基准 {profile.transition_occupancy_high * 100:.0f}%。"
                    ),
                    impact="停留在过渡区意味着既未建立网前压制也未完成后场站位，回球选择与防守覆盖都会受限。",
                    evidence=[transition],
                    priority=2,
                    confidence="medium" if transition.quality == "high" else "low",
                    profile=profile,
                )
            )
        else:
            findings.append(
                _finding(
                    rule="transition_zone_dwell",
                    subject=subject_id,
                    assessment="stable",
                    title="过渡区停留处于参考区间",
                    diagnosis=f"该球员过渡区停留占用约 {value * 100:.0f}%，未超过产品参考基准 {profile.transition_occupancy_high * 100:.0f}%。",
                    impact="场上位置分布未显示明显的中场滞留问题。",
                    evidence=[transition],
                    priority=3,
                    confidence="medium" if transition.quality == "high" else "low",
                    profile=profile,
                )
            )

    # ── kitchen_line_proximity（只用距离作为位置证据，不把 NVZ 占用率当能力分）──
    distance = _find(evidence_by_key, subject_id, "avg_distance_to_kitchen_line_m")
    if distance is not None:
        value = distance.value or 0.0
        if distance.quality == "low":
            findings.append(
                _finding(
                    rule="kitchen_line_proximity",
                    subject=subject_id,
                    assessment="insufficient_evidence",
                    title="站位距离数据有限",
                    diagnosis=f"该球员平均站位距厨房线 {value:.1f}m，但有效帧覆盖不足，结论置信度低。",
                    impact="建议补充有效跟踪时间后再评估站位习惯。",
                    evidence=[distance],
                    priority=3,
                    confidence="low",
                    profile=profile,
                )
            )
        elif value > profile.kitchen_line_distance_far_m:
            findings.append(
                _finding(
                    rule="kitchen_line_proximity",
                    subject=subject_id,
                    assessment="needs_improvement",
                    title="平均站位距厨房线较远",
                    diagnosis=(
                        f"该球员平均站位距所属半场厨房线 {value:.1f}m，高于产品参考基准 "
                        f"{profile.kitchen_line_distance_far_m:.1f}m（描述性位置事实，非能力评分）。"
                    ),
                    impact="站位远离厨房线时，网前争夺与截击参与机会减少。",
                    evidence=[distance],
                    priority=2,
                    confidence="medium" if distance.quality == "high" else "low",
                    profile=profile,
                )
            )
        else:
            findings.append(
                _finding(
                    rule="kitchen_line_proximity",
                    subject=subject_id,
                    assessment="stable",
                    title="平均站位贴近厨房线参考区间",
                    diagnosis=f"该球员平均站位距所属半场厨房线 {value:.1f}m，处于产品参考基准 {profile.kitchen_line_distance_far_m:.1f}m 以内。",
                    impact="站位习惯支持参与网前回合。",
                    evidence=[distance],
                    priority=3,
                    confidence="medium" if distance.quality == "high" else "low",
                    profile=profile,
                )
            )

    # ── movement_load ──
    distance_ev = _find(evidence_by_key, subject_id, "distance_ft")
    speed_ev = _find(evidence_by_key, subject_id, "average_speed_ft_per_s")
    if distance_ev is not None and speed_ev is not None:
        load_value = distance_ev.value or 0.0
        if load_value < profile.movement_load_low_ft:
            findings.append(
                _finding(
                    rule="movement_load",
                    subject=subject_id,
                    assessment="insufficient_evidence",
                    title="移动负载偏低",
                    diagnosis=f"该球员累计移动 {load_value:.0f} 英尺、平均速度 {speed_ev.value:.1f} ft/s，低于产品参考的活跃区间（{profile.movement_load_low_ft:.0f} 英尺）。",
                    impact="可能是跟踪覆盖不足或该球员本场的实际参与度低，需结合有效时间判断。",
                    evidence=[distance_ev, speed_ev],
                    priority=3,
                    confidence="low",
                    profile=profile,
                )
            )
        else:
            findings.append(
                _finding(
                    rule="movement_load",
                    subject=subject_id,
                    assessment="stable",
                    title="移动负载处于活跃区间",
                    diagnosis=f"该球员累计移动 {load_value:.0f} 英尺，平均速度 {speed_ev.value:.1f} ft/s。",
                    impact="移动投入度未显示明显不足。",
                    evidence=[distance_ev, speed_ev],
                    priority=3,
                    confidence="medium",
                    profile=profile,
                )
            )

    return findings


def _team_findings(
    subject_id: str,
    evidence_by_key: dict[tuple[str, str], list[PerformanceEvidence]],
    profile: InsightRuleProfile,
) -> list[PerformanceFinding]:
    findings: list[PerformanceFinding] = []
    avg = _find(evidence_by_key, subject_id, "average_spacing_ft")
    min_ev = _find(evidence_by_key, subject_id, "min_spacing_ft")
    max_ev = _find(evidence_by_key, subject_id, "max_spacing_ft")
    if avg is None:
        return findings

    # ── doubles_spacing_stability ──
    value = avg.value or 0.0
    if profile.doubles_spacing_low_ft <= value <= profile.doubles_spacing_high_ft:
        findings.append(
            _finding(
                rule="doubles_spacing_stability",
                subject=subject_id,
                assessment="stable",
                title="搭档平均间距处于参考区间",
                diagnosis=f"搭档平均间距 {value:.1f} 英尺，处于产品参考区间 {profile.doubles_spacing_low_ft:.0f}–{profile.doubles_spacing_high_ft:.0f} 英尺。",
                impact="横向覆盖分配未见明显失衡。",
                evidence=[avg],
                priority=3,
                confidence="medium",
                profile=profile,
            )
        )
    else:
        findings.append(
            _finding(
                rule="doubles_spacing_stability",
                subject=subject_id,
                assessment="needs_improvement",
                title="搭档平均间距偏离参考区间",
                diagnosis=(
                    f"搭档平均间距 {value:.1f} 英尺，{'低于' if value < profile.doubles_spacing_low_ft else '高于'}"
                    f"产品参考区间 {profile.doubles_spacing_low_ft:.0f}–{profile.doubles_spacing_high_ft:.0f} 英尺。"
                ),
                impact="间距过近会压缩横向覆盖，过远则留下中路空当。",
                evidence=[avg],
                priority=2,
                confidence="medium",
                profile=profile,
            )
        )

    # ── doubles_spacing_extremes ──
    if min_ev is not None and (min_ev.value or 0.0) < profile.doubles_min_spacing_ft:
        findings.append(
            _finding(
                rule="doubles_spacing_extremes",
                subject=subject_id,
                assessment="needs_improvement",
                title="出现间距过近的时段",
                diagnosis=f"搭档最小间距 {min_ev.value:.1f} 英尺，低于产品参考下限 {profile.doubles_min_spacing_ft:.0f} 英尺。",
                impact="过近站位会让对手的斜线球同时穿越两人覆盖区。",
                evidence=[min_ev],
                priority=2,
                confidence="medium",
                profile=profile,
            )
        )
    if max_ev is not None and (max_ev.value or 0.0) > profile.doubles_max_spacing_ft:
        findings.append(
            _finding(
                rule="doubles_spacing_extremes",
                subject=subject_id,
                assessment="needs_improvement",
                title="出现间距过远的时段",
                diagnosis=f"搭档最大间距 {max_ev.value:.1f} 英尺，高于产品参考上限 {profile.doubles_max_spacing_ft:.0f} 英尺。",
                impact="过远站位会在中路留下明显空当。",
                evidence=[max_ev],
                priority=2,
                confidence="medium",
                profile=profile,
            )
        )
    return findings


def _data_quality_findings(
    bundle: EvidenceBundle,
    evidence_by_key: dict[tuple[str, str], list[PerformanceEvidence]],
) -> list[PerformanceFinding]:
    coverage = bundle.data_quality.trajectory_coverage_rate
    rally_count = bundle.data_quality.valid_rally_count
    coverage_evidence = _find(evidence_by_key, "match", "trajectory_coverage_rate")
    if coverage is not None and coverage >= 0.5:
        assessment = "stable"
        title = "数据可信度较高"
        diagnosis = f"球员轨迹覆盖率约 {coverage * 100:.0f}%，可用于本次表现洞察。"
        impact = "洞察基于较完整的跟踪数据。"
    else:
        assessment = "insufficient_evidence"
        title = "数据可信度有限"
        diagnosis = (
            f"球员轨迹覆盖率约 {coverage * 100:.0f}%（或无法统计），洞察结论置信度受限。"
            if coverage is not None
            else "无法统计轨迹覆盖率，洞察结论置信度受限。"
        )
        impact = "建议改善拍摄角度或标定质量后重新分析。"
    rally_note = (
        f"有效 Rally 窗口 {rally_count.value} 个。" if rally_count.status == "available" and rally_count.value else "无可靠 Rally 边界。"
    )
    bound_evidence = [coverage_evidence] if coverage_evidence is not None else []
    return [
        _finding(
            rule="data_coverage_quality",
            subject="match",
            assessment=assessment,
            title=title,
            diagnosis=f"{diagnosis}{rally_note}",
            impact=impact,
            evidence=bound_evidence,
            priority=3,
            confidence="medium" if assessment == "stable" else "low",
            profile=RULE_PROFILE_V1,
        )
    ]


def _rally_window_findings(
    evidence_by_key: dict[tuple[str, str], list[PerformanceEvidence]],
    bundle: EvidenceBundle,
) -> list[PerformanceFinding]:
    """4.4 条件规则：仅人工时间线存在时启用；文案限定"在人工标记的有效回合窗口中"。"""
    windows = evidence_by_key.get(("match", "rally_window")) or []
    if not windows:
        return []
    total_seconds = sum((w.end_ms or 0) - (w.start_ms or 0) for w in windows) / 1000.0
    return [
        _finding(
            rule="rally_window_movement_profile",
            subject="match",
            assessment="stable",
            title="有效回合窗口已建立",
            diagnosis=(
                f"在人工标记的有效回合窗口中，共 {len(windows)} 个回合、净比赛时间约 {total_seconds:.0f} 秒；"
                "本条仅描述窗口事实，不推断回合胜负、失误类型或战术效果。"
            ),
            impact="窗口为有效时间口径（KCR 分母等）提供权威边界。",
            evidence=windows,
            priority=3,
            confidence="high",
            profile=RULE_PROFILE_V1,
        )
    ]


def _build_recommendations(
    findings: list[PerformanceFinding],
    eligible_evidence: list[PerformanceEvidence],
    profile: InsightRuleProfile,
) -> list[PerformanceTrainingRecommendation]:
    """needs_improvement findings → 可审计训练建议（baseline / next_target / metric / direction）。"""
    evidence_by_id = {e.id: e for e in eligible_evidence}
    recommendations: list[PerformanceTrainingRecommendation] = []

    templates: dict[str, dict] = {
        "transition_zone_dwell": {
            "title": "接发后推进与网前转换训练",
            "detail": "重点训练接发后立即前压与第三拍后的网前转换，减少过渡区停留。",
            "metric": "transition_occupancy",
            "direction": "decrease",
            "target_factor": 0.8,
        },
        "kitchen_line_proximity": {
            "title": "网前站位推进训练",
            "detail": "在 dink 回合中保持站位贴近厨房线，逐步缩短平均站位距离。",
            "metric": "avg_distance_to_kitchen_line_m",
            "direction": "decrease",
            "target_offset_m": 0.5,
        },
        "doubles_spacing_stability": {
            "title": "搭档横向间距协同训练",
            "detail": "以参考区间为目标做同步横移练习，保持两人间距稳定。",
            "metric": "average_spacing_ft",
            "direction": "maintain",
            "target_min": profile.doubles_spacing_low_ft,
            "target_max": profile.doubles_spacing_high_ft,
        },
        "doubles_spacing_extremes": {
            "title": "间距极值控制训练",
            "detail": "针对过近/过远时段做中路补位与让位沟通练习。",
            "metric": "max_spacing_ft",
            "direction": "maintain",
            "target_max": profile.doubles_max_spacing_ft,
        },
    }

    for finding in findings:
        if finding.assessment != "needs_improvement" or finding.rule_id not in templates:
            continue
        template = templates[finding.rule_id]
        baseline_value = None
        for eid in finding.evidence_ids:
            evidence = evidence_by_id.get(eid)
            if evidence is not None and evidence.value is not None:
                baseline_value = evidence.value
                break
        if baseline_value is None:
            continue

        if finding.rule_id == "transition_zone_dwell":
            baseline = f"过渡区占用 {baseline_value * 100:.0f}%"
            next_target = f"降低到 {baseline_value * template['target_factor'] * 100:.0f}% 以下"
        elif finding.rule_id == "kitchen_line_proximity":
            baseline = f"平均站位距厨房线 {baseline_value:.1f}m"
            next_target = f"缩短到 {max(0.5, baseline_value - template['target_offset_m']):.1f}m 以下"
        elif finding.rule_id == "doubles_spacing_stability":
            baseline = f"平均间距 {baseline_value:.1f} ft"
            next_target = f"稳定在 {template['target_min']:.0f}–{template['target_max']:.0f} ft"
        else:
            baseline = f"最大间距 {baseline_value:.1f} ft"
            next_target = f"控制在 {template['target_max']:.0f} ft 以内"

        recommendations.append(
            PerformanceTrainingRecommendation(
                id=recommendation_id(finding.rule_id or "", finding.subject_id),
                subject_id=finding.subject_id,
                dimension=finding.dimension,
                title=template["title"],
                detail=template["detail"],
                metric=template["metric"],
                baseline=baseline,
                next_target=next_target,
                direction=template["direction"],
                finding_id=finding.id,
                rule_id=finding.rule_id,
                threshold_source=profile.threshold_source,
                evidence_ids=list(finding.evidence_ids),
            )
        )
    return recommendations


def _build_dimension_assessments(
    subjects: list[PerformanceSubject],
    findings: list[PerformanceFinding],
    bundle: EvidenceBundle,
) -> list[DimensionAssessment]:
    """维度状态权威输出（Projector 只展示不推导）。

    聚合：每 subject × 每维度，取该维度 findings 的最严重 assessment；
    无 findings 时按 data_quality 维度可用性降级（not_applicable / insufficient_data / unsupported）。
    """
    dimension_findings: dict[tuple[str, str], list[PerformanceFinding]] = {}
    for finding in findings:
        dimension_findings.setdefault((finding.subject_id, finding.dimension), []).append(finding)

    availability_by_dim = {item.dimension: item.status for item in bundle.data_quality.dimensions}

    severity_order = {"needs_improvement": 0, "strength": 1, "stable": 2, "insufficient_evidence": 3}
    assessments: list[DimensionAssessment] = []

    for subject in subjects:
        for dimension in PERFORMANCE_DIMENSIONS:
            dims = dimension_findings.get((subject.id, dimension)) or []
            availability = availability_by_dim.get(dimension)

            if dimension == "doubles_cooperation" and bundle.match_format == "singles":
                status: DimensionStatus = "not_applicable"
                summary = "单打任务，双打协同维度不适用。"
            elif dimension == "transition_decision":
                status = "unsupported"
                summary = "攻防转换与决策需要更完整的击球上下文，当前证据能力暂不评价。"
            elif not dims:
                if availability == "not_applicable":
                    status = "not_applicable"
                    summary = "该维度不适用于本场任务。"
                elif availability == "unsupported":
                    status = "unsupported"
                    summary = "当前证据能力不支持该维度评价。"
                elif dimension == "placement_control":
                    status = "insufficient_evidence"
                    summary = "球/弹跳数据仅为候选（candidate），不构成落点统计语义。"
                else:
                    status = "insufficient_evidence"
                    summary = "该维度数据不足，暂不评价。"
            else:
                worst = min(
                    (f for f in dims if f.assessment in severity_order),
                    key=lambda f: severity_order[f.assessment],
                    default=None,
                )
                if worst is None:
                    status = "insufficient_evidence"
                    summary = "该维度证据不足，暂不评价。"
                else:
                    status = worst.assessment  # type: ignore[assignment]
                    summary = worst.diagnosis
            confidence = "medium"
            if dims:
                confidence = min((f.confidence for f in dims), key=lambda c: {"high": 0, "medium": 1, "low": 2}[c])
            assessments.append(
                DimensionAssessment(
                    dimension=dimension,
                    subject_id=subject.id,
                    status=status,
                    confidence=confidence,
                    evidence_ids=sorted({eid for f in dims for eid in f.evidence_ids}),
                    finding_ids=sorted(f.id for f in dims),
                    summary=summary,
                )
            )
    return assessments


def _primary_focus_finding_id(findings: list[PerformanceFinding]) -> str | None:
    """首要问题：priority 最小的 needs_improvement finding（无则 None）。"""
    candidates = [f for f in findings if f.assessment == "needs_improvement"]
    if not candidates:
        return None
    return min(candidates, key=lambda f: (f.priority, f.id)).id


def _finding(
    *,
    rule: str,
    subject: str,
    assessment: str,
    title: str,
    diagnosis: str,
    impact: str,
    evidence: list[PerformanceEvidence],
    priority: int,
    confidence: str,
    profile: InsightRuleProfile,
) -> PerformanceFinding:
    return PerformanceFinding(
        id=finding_id(rule, subject),
        subject_id=subject,
        dimension=_dimension_for_rule(rule),
        assessment=assessment,  # type: ignore[arg-type]
        title=title,
        diagnosis=diagnosis,
        impact=impact,
        evidence_ids=[e.id for e in evidence],
        priority=priority,
        confidence=confidence,  # type: ignore[arg-type]
        evidence_windows=[
            {"start_ms": e.start_ms, "end_ms": e.end_ms, "rally_id": e.rally_id}
            for e in evidence
            if e.start_ms is not None and e.end_ms is not None
        ],
        rule_id=rule,
        threshold_source=profile.threshold_source,  # type: ignore[arg-type]
    )


def _dimension_for_rule(rule: str) -> PerformanceDimension:
    mapping: dict[str, PerformanceDimension] = {
        "transition_zone_dwell": "court_positioning",
        "kitchen_line_proximity": "court_positioning",
        "movement_load": "movement_recovery",
        "movement_coverage_balance": "movement_recovery",
        "data_coverage_quality": "rally_consistency",
        "doubles_spacing_stability": "doubles_cooperation",
        "doubles_spacing_extremes": "doubles_cooperation",
        "rally_window_movement_profile": "rally_consistency",
    }
    return mapping.get(rule, "movement_recovery")
