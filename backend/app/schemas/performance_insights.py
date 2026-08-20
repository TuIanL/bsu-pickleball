"""performance-insights.v1 数据契约 —— 洞察事实层的权威 Pydantic schema。

分层原则（change design.md D3）：
- Evidence 是事实（可追溯到 artifact / metric / timeline）；
- Finding 是解释（对证据的领域判断，4 态 assessment）；
- DimensionAssessment 是维度状态权威（6 态，Rule Engine 输出，Projector 只展示）；
- Recommendation 是行动（可审计链 recommendation → finding → evidence → artifact）。

确定性契约（design.md D3）：
- 所有 id 采用确定性命名（ev:/finding:/rec: 前缀），禁用 uuid4；
- subjects / dimensions / evidence / findings / recommendations 固定排序
  （subject 升序、dimension 固定序、id 字典序）。

候选语义约束（design.md D3/D5）：
- semantic_level / rule_eligibility 在 schema 层约束候选证据（bounce/ball）
  不可进入规则引擎产出 finding。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 枚举与基础类型
# ---------------------------------------------------------------------------

# 六维表现维度（固定顺序，用于 DimensionAssessment 排序与前端展示）。
PERFORMANCE_DIMENSIONS: tuple[str, ...] = (
    "court_positioning",    # 场位与网前控制
    "movement_recovery",    # 移动与还原
    "placement_control",    # 落点与控球
    "rally_consistency",    # 稳定性与回合表现
    "transition_decision",  # 攻防转换与决策
    "doubles_cooperation",  # 双打协同
)

PerformanceDimension = Literal[
    "court_positioning",
    "movement_recovery",
    "placement_control",
    "rally_consistency",
    "transition_decision",
    "doubles_cooperation",
]

# 维度展示名称（中文，用于报告与 UI）。
DIMENSION_LABELS: dict[str, str] = {
    "court_positioning": "场位与网前控制",
    "movement_recovery": "移动与还原",
    "placement_control": "落点与控球",
    "rally_consistency": "稳定性与回合表现",
    "transition_decision": "攻防转换与决策",
    "doubles_cooperation": "双打协同",
}

# Evidence 来源标签（multiview 时区分融合产物与参考机位产物）。
EvidenceProvenance = Literal[
    "pipeline_metric",
    "structured_visualization",
    "manual_timeline",
    "fused_multiview",
    "reference_view",
    "derived_rule",
]

# 证据语义层级：descriptive=描述性事实；confirmed=已确认语义；candidate=候选（如 bounce）。
SemanticLevel = Literal["descriptive", "confirmed", "candidate"]

# 规则可用性：eligible=可进入规则引擎；display_only=仅展示，规则引擎入口统一过滤。
RuleEligibility = Literal["eligible", "display_only"]

# Finding 评估（4 态：具体发现的判断，不承载维度级 not_applicable）。
FindingAssessment = Literal["strength", "stable", "needs_improvement", "insufficient_evidence"]

# 维度状态（6 态：维度级权威判断，含 not_applicable / unsupported）。
DimensionStatus = Literal[
    "strength",
    "stable",
    "needs_improvement",
    "insufficient_evidence",
    "not_applicable",
    "unsupported",
]

Confidence = Literal["high", "medium", "low"]

EvidenceQuality = Literal["high", "medium", "low"]

MatchFormat = Literal["singles", "doubles"]

# 阈值来源版本（V1 为产品参考基准，非专业标准）。
THRESHOLD_SOURCE_V1 = "product_reference_v1"
ThresholdSource = Literal["product_reference_v1", "coach_validated_v2", "population_norm_v3"]

# ---------------------------------------------------------------------------
# Evidence / 时间窗
# ---------------------------------------------------------------------------


class EvidenceWindow(BaseModel):
    """证据时间窗（毫秒，前端直接用于 /analysis/{job_id}/vision?t={start_ms} 跳转）。"""

    start_ms: int
    end_ms: int
    rally_id: str | None = None


class PerformanceEvidence(BaseModel):
    """一条可追溯的表现证据（事实层）。

    id 确定性命名：`ev:{subject}:{metric}:{window_start_ms}`（无时间窗时省略尾段）。
    """

    id: str
    subject_id: str  # canonical Player_N / team_near / team_far
    dimension: PerformanceDimension
    metric: str
    value: float | None = None
    unit: str | None = None
    numerator: float | None = None
    denominator: float | None = None
    start_ms: int | None = None
    end_ms: int | None = None
    rally_id: str | None = None
    source_artifacts: list[str] = Field(default_factory=list)
    quality: EvidenceQuality = "medium"
    provenance: EvidenceProvenance = "pipeline_metric"
    semantic_level: SemanticLevel = "descriptive"
    rule_eligibility: RuleEligibility = "eligible"


# ---------------------------------------------------------------------------
# Finding / DimensionAssessment
# ---------------------------------------------------------------------------


class PerformanceFinding(BaseModel):
    """一条表现发现（解释层）。

    id 确定性命名：`finding:{rule_id}:{subject}`。
    每条非 insufficient_evidence 的 finding 必须绑定 ≥1 条真实 evidence。
    """

    id: str
    subject_id: str
    dimension: PerformanceDimension
    assessment: FindingAssessment
    title: str
    diagnosis: str
    impact: str
    evidence_ids: list[str] = Field(default_factory=list)
    priority: int = Field(ge=1, le=3, default=3)
    confidence: Confidence = "medium"
    evidence_windows: list[EvidenceWindow] = Field(default_factory=list)
    recommendation_id: str | None = None
    rule_id: str | None = None
    threshold_source: ThresholdSource | None = None


class DimensionAssessment(BaseModel):
    """维度整体状态（权威层）：由 Rule Engine 综合该维度全部 findings 与数据可用性输出。

    Report Projector 只展示、不推导维度结论。
    status 6 态：not_applicable（如单打的双打协同）、unsupported（证据能力缺失，如攻防转换）。
    """

    dimension: PerformanceDimension
    subject_id: str
    status: DimensionStatus
    confidence: Confidence = "medium"
    evidence_ids: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)
    summary: str


# ---------------------------------------------------------------------------
# Recommendation（可审计训练建议）
# ---------------------------------------------------------------------------


class PerformanceTrainingRecommendation(BaseModel):
    """训练建议（行动层）：可审计链 recommendation → finding → evidence → artifact。

    id 确定性命名：`rec:{rule_id}:{subject}`。
    无历史趋势：仅本次 baseline 与下一次可度量 target。
    """

    id: str
    subject_id: str
    dimension: PerformanceDimension
    title: str
    detail: str
    metric: str
    baseline: str
    next_target: str
    direction: Literal["increase", "decrease", "maintain"]
    finding_id: str | None = None
    rule_id: str | None = None
    threshold_source: ThresholdSource | None = None
    evidence_ids: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# DataQuality
# ---------------------------------------------------------------------------


class DataQualityCounter(BaseModel):
    """计数类数据质量字段：value=null + status=unavailable 表达"无法得知"，
    与 value=0（确实为零）严格区分。"""

    value: int | None
    status: Literal["available", "unavailable"]


class DimensionAvailability(BaseModel):
    """单个维度的数据可用性（available / not_applicable / insufficient_players 等）。"""

    dimension: PerformanceDimension
    status: Literal[
        "available",
        "not_applicable",
        "insufficient_players",
        "insufficient_data",
        "unsupported",
    ]
    detail: str | None = None


class PerformanceDataQuality(BaseModel):
    """洞察产物的数据质量摘要。"""

    valid_rally_count: DataQualityCounter
    trajectory_coverage_rate: float | None = None  # [0,1]；null=无法得知
    dimensions: list[DimensionAvailability] = Field(default_factory=list)


class PerformanceSubject(BaseModel):
    """洞察主体：canonical Player_N 或双打团队 team_near / team_far。"""

    id: str
    label: str
    kind: Literal["player", "team"]


# ---------------------------------------------------------------------------
# 顶层产物
# ---------------------------------------------------------------------------


class PerformanceInsightsArtifact(BaseModel):
    """performance_insights.json 产物（schema performance-insights.v1）。

    确定性：相同输入 + 相同 rule_profile_version → 相同内容（generated_at 除外）。
    缓存失效键 = evidence_input_signature + rule_profile_version（非 job inputSignature）。
    """

    schema_version: Literal["performance-insights.v1"] = "performance-insights.v1"
    job_id: str
    match_format: MatchFormat
    rule_profile_version: str
    generated_at: str
    evidence_input_signature: str
    data_quality: PerformanceDataQuality
    subjects: list[PerformanceSubject] = Field(default_factory=list)
    dimensions: list[DimensionAssessment] = Field(default_factory=list)
    evidence: list[PerformanceEvidence] = Field(default_factory=list)
    # 候选证据（bounce/ball，semantic_level=candidate / rule_eligibility=display_only）：
    # 与 evidence 分列存放，规则引擎入口不可消费，仅供报告"算法候选事实"区展示与审计。
    candidate_evidence: list[PerformanceEvidence] = Field(default_factory=list)
    findings: list[PerformanceFinding] = Field(default_factory=list)
    recommendations: list[PerformanceTrainingRecommendation] = Field(default_factory=list)
    primary_focus_finding_id: str | None = None


# ---------------------------------------------------------------------------
# 报告投影子集（AnalysisReport.performanceInsights 的用户可读形态）
# ---------------------------------------------------------------------------


class ProjectedDimensionCard(BaseModel):
    """六维状态卡投影：状态 + 证据充分度，无数值分。"""

    dimension: PerformanceDimension
    label: str
    subject_id: str
    status: DimensionStatus
    summary: str


class ProjectedFinding(BaseModel):
    """finding 的报告投影：含视频证据跳转入口。"""

    id: str
    subject_id: str
    dimension: PerformanceDimension
    dimension_label: str
    assessment: FindingAssessment
    priority: int
    confidence: Confidence
    title: str
    diagnosis: str
    impact: str
    evidence_ids: list[str] = Field(default_factory=list)
    evidence_windows: list[EvidenceWindow] = Field(default_factory=list)


class ProjectedRecommendation(BaseModel):
    """训练建议投影：baseline / next_target / metric / direction，无历史对比。"""

    id: str
    subject_id: str
    title: str
    detail: str
    metric: str
    baseline: str
    next_target: str
    direction: Literal["increase", "decrease", "maintain"]
    finding_id: str | None = None


class ProjectedCandidateFact(BaseModel):
    """算法候选事实（bounce/ball）：仅展示，不进入 findings。"""

    kind: Literal["bounce_candidates", "ball_trajectory"]
    count: int | None
    detail: str
    sample_windows: list[EvidenceWindow] = Field(default_factory=list)


class ReportPerformanceInsights(BaseModel):
    """AnalysisReport v2 的 performanceInsights 字段（用户可读投影子集）。"""

    status: Literal["available", "unavailable"] = "available"
    unavailable_reason: str | None = None
    match_format: MatchFormat | None = None
    rule_profile_version: str | None = None
    data_quality_summary: str | None = None
    subjects: list[PerformanceSubject] = Field(default_factory=list)
    dimensions: list[ProjectedDimensionCard] = Field(default_factory=list)
    findings: list[ProjectedFinding] = Field(default_factory=list)
    recommendations: list[ProjectedRecommendation] = Field(default_factory=list)
    candidate_facts: list[ProjectedCandidateFact] = Field(default_factory=list)
    primary_focus_finding_id: str | None = None
