"""PerformanceEvidenceAssembler —— 从已落盘产物只读组装 Evidence Bundle（事实层）。

输入（change design.md D3）：
- AnalysisPipelineResult（内存或 result.json）—— movement / spacing / ball 摘要；
- structured visualization data.json —— zone stats（三区占用、NVZ 占用、厨房线距离）；
- 有效时间窗口（clip / manual timeline / 回退）—— rally 窗口证据。

边界规则：
- `timestamp_seconds` 在本边界统一转毫秒，Rule Engine 不处理秒/毫秒混合；
- bounce/ball 候选在出口即标 `semantic_level=candidate, rule_eligibility=display_only`；
- multiview：只消费 public Parent 最终产物；融合轨迹标 `fused_multiview`，
  参考机位产物标 `reference_view`；
- evidence_input_signature：输入产物清单（路径 + mtime + size）的结构化 sha256，
  非 AnalysisJobSummary.inputSignature 的复用。
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

from app.schemas.analysis import AnalysisJobSummary
from app.schemas.performance_insights import (
    DataQualityCounter,
    DimensionAvailability,
    PerformanceDataQuality,
    PerformanceEvidence,
    PerformanceSubject,
)
from app.schemas.pipeline import AnalysisPipelineResult
from app.services.performance_insights.ids import evidence_id, sort_evidence, sort_subjects

# 数据充分性阈值（与 zone_stats.DATA_SUFFICIENCY_THRESHOLD 对齐）。
DATA_SUFFICIENCY_THRESHOLD = 0.3


@dataclass
class AssemblerInputs:
    """Assembler 的只读输入（全部来自已落盘产物或内存 result）。"""

    result: AnalysisPipelineResult
    structured_viz: dict | None = None
    # 有效时间窗口（秒，半开区间）；None = 无比赛数据（回退总时长口径）。
    effective_windows: list[tuple[float, float]] | None = None
    # 窗口来源："clip" | "manual_timeline" | None（回退总时长）。
    window_source: str | None = None
    # 输入产物文件清单（用于 evidence_input_signature；V1 = 路径 + mtime + size）。
    input_files: list[Path] = field(default_factory=list)


@dataclass
class EvidenceBundle:
    """Assembler 输出：subject + evidence + data_quality + 输入签名。"""

    subjects: list[PerformanceSubject]
    evidence: list[PerformanceEvidence]
    data_quality: PerformanceDataQuality
    evidence_input_signature: str
    match_format: str
    # 候选事实（display_only evidence 的摘要，供报告"算法候选事实"区使用）。
    candidate_facts: list[PerformanceEvidence] = field(default_factory=list)


def _window_start_ms(window: tuple[float, float]) -> int:
    return int(round(window[0] * 1000))


def _window_end_ms(window: tuple[float, float]) -> int:
    return int(round(window[1] * 1000))


def compute_evidence_input_signature(result: AnalysisPipelineResult, input_files: list[Path]) -> str:
    """输入产物指纹：result 内容（剔除 insights 自身字段，避免自引用失效）+ 文件清单的结构化 sha256。

    非 AnalysisJobSummary.inputSignature 的复用——job signature 描述"输入视频 + 配置"，
    无法感知 artifact 修复/重生成导致的 evidence 变化。
    注意：input_files 不应包含 result.json 本身（insights 持久化会重写它，导致签名自引用漂移）。
    """
    digest = hashlib.sha256()
    result_payload = result.model_dump(mode="json")
    artifacts = result_payload.get("artifacts") or {}
    for key in list(artifacts):
        if key.startswith("performance_insights_"):
            artifacts.pop(key)
    payload = {
        "job_id": result.job_id,
        "result": result_payload,
        "files": [
            {
                "path": str(path),
                "mtime": path.stat().st_mtime if path.exists() else None,
                "size": path.stat().st_size if path.exists() else None,
            }
            for path in input_files
        ],
    }
    digest.update(json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8"))
    return digest.hexdigest()


def _multiview_provenance(result: AnalysisPipelineResult) -> str:
    """multiview provenance 判定：只看 public Parent 最终产物状态。"""
    artifacts = result.artifacts
    if getattr(artifacts, "fused_player_overlay_status", None) == "available":
        return "fused_multiview"
    # multiview 任务但融合产物不可用 → 视为参考机位产物（Parent 以 reference view 为准）。
    if result.requested_execution_mode or result.effective_multiview_mode:
        return "reference_view"
    return "pipeline_metric"


def _subjects_from_result(result: AnalysisPipelineResult, match_format: str) -> list[PerformanceSubject]:
    """subjects：canonical Player_N（player）+ 双打时的 team_near / team_far。

    track id 以 metrics（distances/speeds/kitchen_dwell）为权威——tracks 点列表可能为空。
    """
    subjects: list[PerformanceSubject] = []
    track_ids: set[str] = set()
    for item in result.metrics.distances:
        track_ids.add(item.track_id)
    for item in result.metrics.speeds:
        track_ids.add(item.track_id)
    for item in result.metrics.kitchen_dwell:
        track_ids.add(item.track_id)
    for track_id in sorted(track_ids):
        label = f"P{track_id[len('Player_'):]}" if track_id.startswith("Player_") else track_id
        subjects.append(PerformanceSubject(id=track_id, label=label, kind="player"))
    if match_format == "doubles" and len(track_ids) >= 2:
        subjects.append(PerformanceSubject(id="team_near", label="近侧组合", kind="team"))
        subjects.append(PerformanceSubject(id="team_far", label="远侧组合", kind="team"))
    return sort_subjects(subjects)


def _zone_stats_players(structured_viz: dict | None) -> list[dict]:
    if not structured_viz:
        return []
    zone_stats = structured_viz.get("zone_stats") or {}
    return zone_stats.get("players") or []


def _zone_occupancy(player: dict, zone: str) -> float | None:
    for entry in player.get("zones") or []:
        if entry.get("zone") == zone:
            return float(entry.get("occupancy") or 0.0)
    return None


def assemble_evidence(job: AnalysisJobSummary, inputs: AssemblerInputs) -> EvidenceBundle:
    """组装 Evidence Bundle（只读，无副作用）。"""
    result = inputs.result
    match_format = (job.metadata.matchFormat or "doubles") if job.metadata else "doubles"
    subjects = _subjects_from_result(result, match_format)
    provenance = _multiview_provenance(result)
    zone_players = _zone_stats_players(inputs.structured_viz)

    evidence: list[PerformanceEvidence] = []
    candidate_facts: list[PerformanceEvidence] = []

    # ── 1. movement evidence（per player，pipeline_metric）──
    for item in result.metrics.distances:
        evidence.append(
            PerformanceEvidence(
                id=evidence_id(item.track_id, "distance_ft"),
                subject_id=item.track_id,
                dimension="movement_recovery",
                metric="distance_ft",
                value=round(item.distance_ft, 2),
                unit="ft",
                source_artifacts=["result"],
                provenance=provenance,
            )
        )
    for item in result.metrics.speeds:
        evidence.append(
            PerformanceEvidence(
                id=evidence_id(item.track_id, "average_speed_ft_per_s"),
                subject_id=item.track_id,
                dimension="movement_recovery",
                metric="average_speed_ft_per_s",
                value=round(item.average_speed_ft_per_s, 2),
                unit="ft/s",
                source_artifacts=["result"],
                provenance=provenance,
            )
        )
        evidence.append(
            PerformanceEvidence(
                id=evidence_id(item.track_id, "max_speed_ft_per_s"),
                subject_id=item.track_id,
                dimension="movement_recovery",
                metric="max_speed_ft_per_s",
                value=round(item.max_speed_ft_per_s, 2),
                unit="ft/s",
                source_artifacts=["result"],
                provenance=provenance,
            )
        )

    # ── 2. zone stats evidence（per player，structured_visualization）──
    for player in zone_players:
        subject_id = str(player.get("id") or "")
        if not subject_id:
            continue
        tracked = float(player.get("tracked_seconds") or 0.0)
        denominator = float(player.get("denominator_seconds") or 0.0)
        sufficiency = player.get("data_sufficiency")
        quality = "high" if sufficiency == "sufficient" else "low"

        transition = _zone_occupancy(player, "transition")
        if transition is not None:
            evidence.append(
                PerformanceEvidence(
                    id=evidence_id(subject_id, "transition_occupancy"),
                    subject_id=subject_id,
                    dimension="court_positioning",
                    metric="transition_occupancy",
                    value=round(transition, 4),
                    numerator=round(transition * denominator, 2) if denominator > 0 else None,
                    denominator=round(denominator, 2) if denominator > 0 else None,
                    source_artifacts=["structured-visualization-data"],
                    quality=quality,
                    provenance="structured_visualization",
                )
            )
        nvz = float(player.get("kitchen_control_rate") or 0.0)
        evidence.append(
            PerformanceEvidence(
                id=evidence_id(subject_id, "nvz_occupancy"),
                subject_id=subject_id,
                dimension="court_positioning",
                metric="nvz_occupancy",
                value=round(nvz, 4),
                numerator=round(nvz * denominator, 2) if denominator > 0 else None,
                denominator=round(denominator, 2) if denominator > 0 else None,
                source_artifacts=["structured-visualization-data"],
                quality=quality,
                provenance="structured_visualization",
            )
        )
        avg_distance = player.get("avg_distance_to_kitchen_line_m")
        if avg_distance is not None:
            evidence.append(
                PerformanceEvidence(
                    id=evidence_id(subject_id, "avg_distance_to_kitchen_line_m"),
                    subject_id=subject_id,
                    dimension="court_positioning",
                    metric="avg_distance_to_kitchen_line_m",
                    value=float(avg_distance),
                    unit="m",
                    source_artifacts=["structured-visualization-data"],
                    quality=quality,
                    provenance="structured_visualization",
                )
            )

    # ── 3. doubles spacing evidence（per pair，pipeline_metric）──
    for summary in result.metrics.doubles_spacing:
        pair_id = f"team_near"  # spacing 摘要按 pair 输出；V1 统一挂 team scope
        evidence.append(
            PerformanceEvidence(
                id=evidence_id(pair_id, "average_spacing_ft"),
                subject_id=pair_id,
                dimension="doubles_cooperation",
                metric="average_spacing_ft",
                value=round(summary.average_spacing_ft, 2),
                unit="ft",
                source_artifacts=["result"],
                provenance=provenance,
            )
        )
        evidence.append(
            PerformanceEvidence(
                id=evidence_id(pair_id, "min_spacing_ft"),
                subject_id=pair_id,
                dimension="doubles_cooperation",
                metric="min_spacing_ft",
                value=round(summary.min_spacing_ft, 2),
                unit="ft",
                source_artifacts=["result"],
                provenance=provenance,
            )
        )
        evidence.append(
            PerformanceEvidence(
                id=evidence_id(pair_id, "max_spacing_ft"),
                subject_id=pair_id,
                dimension="doubles_cooperation",
                metric="max_spacing_ft",
                value=round(summary.max_spacing_ft, 2),
                unit="ft",
                source_artifacts=["result"],
                provenance=provenance,
            )
        )

    # ── 4. rally 窗口证据（全局，manual_timeline / clip）──
    if inputs.effective_windows:
        window_provenance = "manual_timeline" if inputs.window_source == "manual_timeline" else "pipeline_metric"
        for index, window in enumerate(inputs.effective_windows):
            evidence.append(
                PerformanceEvidence(
                    id=evidence_id("match", "rally_window", _window_start_ms(window)),
                    subject_id="match",
                    dimension="rally_consistency",
                    metric="rally_window",
                    start_ms=_window_start_ms(window),
                    end_ms=_window_end_ms(window),
                    source_artifacts=["timeline-events"] if window_provenance == "manual_timeline" else ["result"],
                    provenance=window_provenance,
                )
            )

    # ── 5. ball/bounce 候选事实（display_only，schema 约束级排除出规则）──
    if result.metrics.bounce_event_count > 0:
        candidate_facts.append(
            PerformanceEvidence(
                id=evidence_id("match", "bounce_candidate_count"),
                subject_id="match",
                dimension="placement_control",
                metric="bounce_candidate_count",
                value=float(result.metrics.bounce_event_count),
                source_artifacts=["bounce-events"],
                provenance=provenance,
                semantic_level="candidate",
                rule_eligibility="display_only",
            )
        )
    if result.metrics.ball_detection_rate > 0:
        candidate_facts.append(
            PerformanceEvidence(
                id=evidence_id("match", "ball_detection_rate"),
                subject_id="match",
                dimension="placement_control",
                metric="ball_detection_rate",
                value=round(result.metrics.ball_detection_rate, 4),
                source_artifacts=["ball-trajectory"],
                provenance=provenance,
                semantic_level="candidate",
                rule_eligibility="display_only",
            )
        )

    # ── 6. data quality ──
    rally_count = len(inputs.effective_windows) if inputs.effective_windows else None
    coverage = _trajectory_coverage(zone_players)
    dimensions = _dimension_availability(result, match_format, zone_players, inputs)
    data_quality = PerformanceDataQuality(
        valid_rally_count=DataQualityCounter(
            value=rally_count,
            status="available" if rally_count is not None else "unavailable",
        ),
        trajectory_coverage_rate=coverage,
        dimensions=dimensions,
    )
    # 轨迹覆盖率 evidence（data_coverage_quality finding 的绑定证据）。
    if coverage is not None:
        evidence.append(
            PerformanceEvidence(
                id=evidence_id("match", "trajectory_coverage_rate"),
                subject_id="match",
                dimension="rally_consistency",
                metric="trajectory_coverage_rate",
                value=coverage,
                source_artifacts=["structured-visualization-data"],
                provenance="structured_visualization",
            )
        )

    return EvidenceBundle(
        subjects=subjects,
        evidence=sort_evidence(evidence),
        data_quality=data_quality,
        evidence_input_signature=compute_evidence_input_signature(result, inputs.input_files),
        match_format=match_format,
        candidate_facts=sort_evidence(candidate_facts),
    )


def _trajectory_coverage(zone_players: list[dict]) -> float | None:
    """轨迹覆盖率：各球员 tracked/denominator 的平均；无数据返回 None（无法得知）。"""
    rates: list[float] = []
    for player in zone_players:
        denominator = float(player.get("denominator_seconds") or 0.0)
        tracked = float(player.get("tracked_seconds") or 0.0)
        if denominator > 0:
            rates.append(min(1.0, tracked / denominator))
    return round(sum(rates) / len(rates), 4) if rates else None


def _dimension_availability(
    result: AnalysisPipelineResult,
    match_format: str,
    zone_players: list[dict],
    inputs: AssemblerInputs,
) -> list[DimensionAvailability]:
    """每维度数据可用性（available / not_applicable / insufficient_players / insufficient_data / unsupported）。"""
    track_count = len({track.track_id for track in result.tracks})
    has_zone_stats = bool(zone_players)

    availability = [
        DimensionAvailability(
            dimension="court_positioning",
            status="available" if has_zone_stats else "insufficient_data",
            detail=None if has_zone_stats else "缺少区域占用统计（structured visualization data 未生成）",
        ),
        DimensionAvailability(
            dimension="movement_recovery",
            status="available" if track_count > 0 else "insufficient_data",
            detail=None if track_count > 0 else "没有可用球员轨迹",
        ),
        DimensionAvailability(
            dimension="placement_control",
            status="insufficient_data",
            detail="弹跳/球数据仅为候选（candidate），不构成落点统计语义",
        ),
        DimensionAvailability(
            dimension="rally_consistency",
            status="available" if inputs.effective_windows else "insufficient_data",
            detail=None if inputs.effective_windows else "无人工时间线 rally 窗口",
        ),
        DimensionAvailability(
            dimension="transition_decision",
            status="unsupported",
            detail="需要更完整击球上下文，当前证据能力不支持",
        ),
    ]
    if match_format == "singles":
        availability.append(
            DimensionAvailability(dimension="doubles_cooperation", status="not_applicable", detail="单打任务")
        )
    else:
        availability.append(
            DimensionAvailability(
                dimension="doubles_cooperation",
                status="available" if result.metrics.doubles_spacing else "insufficient_players",
                detail=None if result.metrics.doubles_spacing else "双打间距数据不可用（识别球员不足）",
            )
        )
    return availability
