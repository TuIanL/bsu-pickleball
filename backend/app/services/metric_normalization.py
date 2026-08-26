"""Deterministic normalization of descriptive metric snapshots.

The service intentionally produces only metric-level utility inputs.  It does
not calculate dimension scores, an overall score, or a player skill rating.
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from datetime import UTC, datetime

from app.schemas.metric_normalization import (
    EvidenceSufficiencyProfile,
    MetricDefinition,
    MetricDefinitionProfile,
    MetricNormalizationContext,
    MetricReference,
    NormalizedMetricArtifact,
    NormalizedMetricCoverage,
    NormalizedMetricEntry,
    ScoreEligibility,
    ScoringReferenceProfile,
    SufficiencyRule,
)
from app.schemas.shot_rally_events import (
    ArtifactStatus,
    MetricSnapshotArtifact,
    MetricSnapshotEntry,
    ShotRallyEventsArtifact,
)

logger = logging.getLogger(__name__)

METRIC_DEFINITION_VERSION = "metric-definition-profile.v1"
SUFFICIENCY_VERSION = "evidence-sufficiency-profile.v1"
REFERENCE_VERSION = "scoring-reference-profile.v1"
CALCULATION_VERSION = "metric-normalization.v1"


def _default_metric_definitions() -> list[MetricDefinition]:
    """Whitelist only metrics already emitted by metric-snapshot.v1.

    These current metrics are descriptive-only.  Adding a scoreable metric
    requires a later, explicit reference entry and an auditable source.
    """

    common = {"scopes": ["match", "team", "player"], "match_formats": ["singles", "doubles"]}
    return [
        MetricDefinition(
            metric_key="shot_count",
            source_metric_key="shot_count",
            unit="count",
            metric_direction="descriptive_only",
            descriptive_only=True,
            definition_detail="击球数量是参与度事实，不是能力分。",
            **common,
        ),
        MetricDefinition(
            metric_key="rally_count",
            source_metric_key="rally_count",
            unit="count",
            scopes=["match"],
            metric_direction="descriptive_only",
            descriptive_only=True,
            min_sample_count=3,
            definition_detail="回合数量是样本规模事实，不是能力分。",
        ),
        MetricDefinition(
            metric_key="serve_count",
            source_metric_key="serve_count",
            unit="count",
            metric_direction="descriptive_only",
            descriptive_only=True,
            definition_detail="发球次数不表示发球质量。",
            **common,
        ),
        MetricDefinition(
            metric_key="return_count",
            source_metric_key="return_count",
            unit="count",
            metric_direction="descriptive_only",
            descriptive_only=True,
            definition_detail="接发次数不表示接发质量。",
            **common,
        ),
        MetricDefinition(
            metric_key="third_shot_count",
            source_metric_key="third_shot_count",
            unit="count",
            metric_direction="descriptive_only",
            descriptive_only=True,
            definition_detail="第三拍数量不表示第三拍成功率。",
            **common,
        ),
        MetricDefinition(
            metric_key="shot_quality_mean",
            source_metric_key="shot_quality_mean",
            unit="ratio",
            scopes=["match", "player"],
            metric_direction="descriptive_only",
            descriptive_only=True,
            min_sample_count=3,
            definition_detail="当前 ShotQuality 仅作为描述性执行信号。",
        ),
        MetricDefinition(
            metric_key="doubles_cooperation",
            source_metric_key="doubles_cooperation",
            unit="ratio",
            scopes=["match", "team"],
            match_formats=["doubles"],
            metric_direction="descriptive_only",
            descriptive_only=True,
            definition_detail="双打协同当前仅保留描述性事实。",
        ),
    ]


DEFAULT_METRIC_DEFINITION_PROFILE = MetricDefinitionProfile(metrics=_default_metric_definitions())

DEFAULT_EVIDENCE_SUFFICIENCY_PROFILE = EvidenceSufficiencyProfile(
    default_rule=SufficiencyRule(min_sample_count=1),
    rules={
        "rally_count": SufficiencyRule(min_sample_count=3),
        "serve_count": SufficiencyRule(min_sample_count=3),
        "shot_quality_mean": SufficiencyRule(min_sample_count=3),
    },
)

DEFAULT_SCORING_REFERENCE_PROFILE = ScoringReferenceProfile(
    reference_version=REFERENCE_VERSION,
    reference_mode="expert_threshold",
    reference_source="unconfigured",
    reference_detail="首版没有启用正式能力评分参考；当前白名单指标保持 descriptive_only。",
    metrics=[],
)


def profile_hash(profile: ScoringReferenceProfile) -> str:
    """Return a stable hash for the exact reference profile parameters."""

    payload = profile.model_dump(mode="json", exclude_none=True)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _clamp(value: float, lower: float = 0.0, upper: float = 1.0) -> float:
    return round(max(lower, min(upper, value)), 6)


def _canonical_value(
    metric: MetricSnapshotEntry, definition: MetricDefinition
) -> tuple[float | int | None, str | None]:
    """Normalize units without guessing conversions.

    Current canonical metrics already use the definition unit.  A future unit
    conversion must be added explicitly rather than silently changing scale.
    """

    if metric.value is None:
        return None, "source_value_missing"
    if metric.unit != definition.unit:
        return None, "unit_mismatch"
    return metric.value, None


def _source_status_eligibility(status: ArtifactStatus) -> tuple[ScoreEligibility, str]:
    if status == "insufficient_evidence":
        return "insufficient_evidence", "source_insufficient_evidence"
    if status == "not_applicable":
        return "not_applicable", "source_not_applicable"
    if status in {"failed"}:
        return "failed", "source_failed"
    if status in {"unavailable", "skipped"}:
        return "unsupported", f"source_{status}"
    return "eligible", ""


def _known_evidence_ids(events: ShotRallyEventsArtifact | None) -> set[str]:
    known = {"shot-rally-events.v1", "metric-snapshot.v1"}
    if events is None:
        return known
    for shot in events.shots:
        known.add(shot.shot_id)
        known.update(window.id for window in shot.evidence_windows)
    for rally in events.rallies:
        known.add(rally.rally_id)
        known.update(window.id for window in rally.evidence_windows)
    return known


def _resolve_evidence_ids(
    metric: MetricSnapshotEntry, events: ShotRallyEventsArtifact | None
) -> tuple[list[str], list[str]]:
    known = _known_evidence_ids(events)
    valid = sorted({item for item in metric.evidence_ids if item in known})
    invalid = sorted({item for item in metric.evidence_ids if item not in known})
    return valid, invalid


def _context_matches(reference: MetricReference, context: MetricNormalizationContext) -> bool:
    if not reference.context_selector:
        return False
    values = {
        "match_format": context.match_format,
        "role": context.role,
        "stage": context.stage,
        **{key: str(value) for key, value in context.metadata.items()},
    }
    return all(values.get(key) == expected for key, expected in reference.context_selector.items())


def _utility_score(
    value: float, reference: MetricReference, context: MetricNormalizationContext
) -> tuple[float | None, float | None, str | None]:
    """Map one canonical value to utility and optional percentile."""

    if reference.metric_direction == "context_dependent" and not _context_matches(reference, context):
        return None, None, "context_missing"

    if reference.reference_mode == "empirical_percentile":
        distribution = sorted(reference.reference_distribution)
        if len(distribution) < 2 or not reference.population or not reference.cohort:
            return None, None, "reference_distribution_missing"
        below = sum(item < value for item in distribution)
        equal = sum(item == value for item in distribution)
        percentile = _clamp((below + equal * 0.5) / len(distribution) * 100.0, 0.0, 100.0)
        if reference.metric_direction == "lower_better":
            percentile = round(100.0 - percentile, 6)
        return _clamp(percentile / 100.0), round(percentile, 6), None

    if reference.reference_mode == "target_range" or reference.metric_direction == "target_range":
        target_min = reference.target_min
        target_max = reference.target_max
        if target_min is None or target_max is None:
            return None, None, "target_range_missing"
        if target_min <= value <= target_max:
            return 1.0, None, None
        if value < target_min:
            outer = reference.lower_bound
            if outer is None or outer >= target_min:
                return None, None, "target_range_lower_bound_missing"
            return _clamp((value - outer) / (target_min - outer)), None, None
        outer = reference.upper_bound
        if outer is None or outer <= target_max:
            return None, None, "target_range_upper_bound_missing"
        return _clamp((outer - value) / (outer - target_max)), None, None

    lower = reference.lower_bound
    upper = reference.upper_bound
    if lower is None or upper is None or lower >= upper:
        return None, None, "threshold_bounds_missing"
    if reference.metric_direction == "higher_better":
        return _clamp((value - lower) / (upper - lower)), None, None
    if reference.metric_direction == "lower_better":
        return _clamp((upper - value) / (upper - lower)), None, None
    if reference.metric_direction == "context_dependent":
        return None, None, "context_reference_not_configured"
    return None, None, "unsupported_reference_direction"


def _unique_reasons(reasons: Iterable[str]) -> list[str]:
    return sorted({reason for reason in reasons if reason})


def _entry_metric_id(metric: MetricSnapshotEntry, reference_version: str | None) -> str:
    ref = reference_version or "none"
    return f"normalized:{metric.metric_id}:{ref}:{CALCULATION_VERSION}"


def _normalize_entry(
    metric: MetricSnapshotEntry,
    *,
    definition: MetricDefinition | None,
    sufficiency: SufficiencyRule,
    reference: MetricReference | None,
    definition_version: str,
    sufficiency_version: str,
    reference_version: str | None,
    context: MetricNormalizationContext,
    events: ShotRallyEventsArtifact | None,
) -> NormalizedMetricEntry:
    definition_missing = definition is None
    definition = definition or MetricDefinition(
        metric_key=metric.metric_key,
        source_metric_key=metric.metric_key,
        unit=metric.unit,
        scopes=[metric.scope],
        metric_direction="descriptive_only",
        descriptive_only=True,
        definition_detail="没有当前白名单定义",
    )
    raw_value = metric.value
    canonical_value, canonical_error = _canonical_value(metric, definition)
    valid_evidence, invalid_evidence = _resolve_evidence_ids(metric, events)
    reasons: list[str] = []
    eligibility, source_reason = _source_status_eligibility(metric.status)
    if source_reason:
        reasons.append(source_reason)

    if metric.scope not in definition.scopes:
        eligibility = "unsupported"
        reasons.append("scope_not_supported")
    if context.match_format is not None and context.match_format not in definition.match_formats:
        eligibility = "not_applicable"
        reasons.append("match_format_not_applicable")
    if definition_missing:
        eligibility = "unsupported"
        reasons.append("metric_definition_missing")
    if canonical_error:
        eligibility = "failed"
        reasons.append(canonical_error)
    if invalid_evidence:
        eligibility = "failed"
        reasons.append("evidence_id_unresolvable")
    if not valid_evidence and metric.status == "available":
        eligibility = "failed"
        reasons.append("evidence_missing")
    if metric.status == "available" and metric.denominator == 0:
        eligibility = sufficiency.zero_denominator_status
        reasons.append("zero_denominator")
    if metric.status == "available" and metric.sample_count < max(
        definition.min_sample_count, sufficiency.min_sample_count
    ):
        eligibility = "insufficient_evidence"
        reasons.append("sample_count_below_minimum")
    if sufficiency.min_denominator is not None and (metric.denominator or 0) < sufficiency.min_denominator:
        eligibility = "insufficient_evidence"
        reasons.append("denominator_below_minimum")
    if definition.metric_direction == "context_dependent" and not context.metadata:
        eligibility = "unsupported"
        reasons.append("context_missing")
    provenance_lower = metric.provenance.lower()
    if eligibility == "eligible" and ("candidate" in provenance_lower or "display_only" in provenance_lower):
        eligibility = "display_only"
        reasons.append("semantic_level_candidate")
    if eligibility == "eligible" and definition.descriptive_only:
        eligibility = "display_only"
        reasons.append("descriptive_only_metric")

    utility: float | None = None
    percentile: float | None = None
    actual_reference_mode = reference.reference_mode if reference else None
    if eligibility == "eligible":
        if reference is None:
            eligibility = "unsupported"
            reasons.append("reference_profile_missing")
        elif reference.metric_direction != definition.metric_direction:
            eligibility = "unsupported"
            reasons.append("reference_direction_mismatch")
        elif canonical_value is None or not isinstance(canonical_value, (int, float)):
            eligibility = "failed"
            reasons.append("canonical_value_missing")
        else:
            utility, percentile, utility_error = _utility_score(float(canonical_value), reference, context)
            if utility_error:
                eligibility = "unsupported"
                reasons.append(utility_error)

    if eligibility != "eligible":
        utility = None
        percentile = None

    return NormalizedMetricEntry(
        metric_id=_entry_metric_id(metric, reference_version),
        source_metric_id=metric.metric_id,
        metric_key=metric.metric_key,
        scope=metric.scope,
        subject_id=metric.subject_id,
        source_status=metric.status,
        raw_value=raw_value,
        canonical_value=canonical_value,
        unit=definition.unit,
        metric_direction=definition.metric_direction,
        reference_mode=actual_reference_mode,
        utility_score=utility,
        percentile=percentile,
        numerator=metric.numerator,
        denominator=metric.denominator,
        sample_count=metric.sample_count,
        confidence=metric.confidence,
        score_eligibility=eligibility,
        eligibility_reasons=_unique_reasons(reasons),
        provenance=metric.provenance,
        source_artifact="metric-snapshot.v1",
        evidence_ids=valid_evidence,
        definition_version=definition_version,
        evidence_sufficiency_version=sufficiency_version,
        reference_version=reference_version,
    )


def _coverage(entries: list[NormalizedMetricEntry]) -> NormalizedMetricCoverage:
    counts = {
        status: 0
        for status in ("eligible", "display_only", "insufficient_evidence", "not_applicable", "unsupported", "failed")
    }
    for entry in entries:
        counts[entry.score_eligibility] += 1
    return NormalizedMetricCoverage(
        metric_count=len(entries),
        eligible_metric_count=counts["eligible"],
        display_only_metric_count=counts["display_only"],
        insufficient_metric_count=counts["insufficient_evidence"],
        not_applicable_metric_count=counts["not_applicable"],
        unsupported_metric_count=counts["unsupported"],
        failed_metric_count=counts["failed"],
        eligible_metric_keys=sorted({entry.metric_key for entry in entries if entry.score_eligibility == "eligible"}),
        missing_metric_keys=sorted({entry.metric_key for entry in entries if entry.score_eligibility != "eligible"}),
    )


def normalize_metric_snapshot(
    snapshot: MetricSnapshotArtifact,
    *,
    events: ShotRallyEventsArtifact | None = None,
    context: MetricNormalizationContext | None = None,
    definition_profile: MetricDefinitionProfile = DEFAULT_METRIC_DEFINITION_PROFILE,
    sufficiency_profile: EvidenceSufficiencyProfile = DEFAULT_EVIDENCE_SUFFICIENCY_PROFILE,
    reference_profile: ScoringReferenceProfile = DEFAULT_SCORING_REFERENCE_PROFILE,
    generated_at: str | None = None,
) -> NormalizedMetricArtifact:
    """Normalize a snapshot without calculating a dimension or overall score."""

    context = context or MetricNormalizationContext()
    generated_at = generated_at or datetime.now(UTC).isoformat()
    reference_version = reference_profile.reference_version
    references = reference_profile.by_key()
    definitions = definition_profile.by_key()
    entries: list[NormalizedMetricEntry] = []
    diagnostics: list[str] = []
    for metric in sorted(
        snapshot.metrics, key=lambda item: (item.scope, item.subject_id, item.metric_key, item.metric_id)
    ):
        definition = definitions.get(metric.metric_key)
        entry = _normalize_entry(
            metric,
            definition=definition,
            sufficiency=sufficiency_profile.rule_for(metric.metric_key),
            reference=references.get(metric.metric_key),
            definition_version=definition_profile.profile_version,
            sufficiency_version=sufficiency_profile.profile_version,
            reference_version=reference_version,
            context=context,
            events=events,
        )
        entries.append(entry)
        if entry.score_eligibility != "eligible":
            diagnostics.extend(f"{entry.metric_id}:{reason}" for reason in entry.eligibility_reasons)

    status = snapshot.status
    if snapshot.status == "available":
        eligible_count = sum(item.score_eligibility == "eligible" for item in entries)
        detail = f"已规范化 {len(entries)} 条 metric；eligible={eligible_count}，不包含 Dimension/Overall Score"
    else:
        detail = f"输入 Metric Snapshot 不可用于规范化：{snapshot.detail}"
    return NormalizedMetricArtifact(
        job_id=snapshot.job_id,
        video_id=snapshot.video_id,
        status=status,
        detail=detail,
        generated_at=generated_at,
        metric_definition_version=definition_profile.profile_version,
        evidence_sufficiency_version=sufficiency_profile.profile_version,
        scoring_reference_version=reference_version,
        scoring_reference_hash=profile_hash(reference_profile),
        metrics=entries,
        score_coverage=_coverage(entries),
        diagnostics=sorted(set(diagnostics)),
    )


def normalize_metric_snapshot_from_payload(payload: dict, **kwargs) -> NormalizedMetricArtifact:
    """Convenience adapter used by post-pipeline persistence and tests."""

    snapshot = MetricSnapshotArtifact.model_validate(payload)
    events_payload = kwargs.pop("events_payload", None)
    events = ShotRallyEventsArtifact.model_validate(events_payload) if events_payload else None
    return normalize_metric_snapshot(snapshot, events=events, **kwargs)


def _normalized_artifact_updates(
    result,
    storage,
    *,
    status: ArtifactStatus,
    detail: str,
):
    path = storage.normalized_metrics_json_path(result.job_id)
    artifacts = result.artifacts.model_copy(
        update={
            "normalized_metrics_json_path": str(path) if path.exists() else None,
            "normalized_metrics_url": (
                f"/api/analysis/jobs/{result.job_id}/artifacts/normalized-metrics" if path.exists() else None
            ),
            "normalized_metrics_status": status,
            "normalized_metrics_detail": detail,
        }
    )
    return result.model_copy(update={"artifacts": artifacts})


def generate_and_persist_normalized_metrics(
    job,
    result,
    *,
    events: ShotRallyEventsArtifact | None = None,
    snapshot: MetricSnapshotArtifact | None = None,
    storage=None,
) -> tuple[object, NormalizedMetricArtifact]:
    """Generate the optional normalized artifact after canonical metrics exist."""

    if storage is None:
        from app.services.storage_service import StorageService

        storage = StorageService()
    storage.resolve_capture_job_root(job.id, job.metadata.capture_take_id)
    generated_at = datetime.now(UTC).isoformat()
    try:
        if events is None:
            events_path = storage.shot_rally_events_json_path(job.id)
            if events_path.exists():
                events = ShotRallyEventsArtifact.model_validate(storage.read_json(events_path))
        if snapshot is None:
            snapshot_path = storage.metric_snapshot_json_path(job.id)
            if not snapshot_path.exists():
                raise FileNotFoundError("metric_snapshot.json not found")
            snapshot = MetricSnapshotArtifact.model_validate(storage.read_json(snapshot_path))
        match_format = getattr(job.metadata, "matchFormat", None)
        context = MetricNormalizationContext(
            match_format=match_format if match_format in {"singles", "doubles"} else None,
            metadata={"match_format": match_format} if match_format else {},
        )
        artifact = normalize_metric_snapshot(
            snapshot,
            events=events,
            context=context,
            generated_at=generated_at,
        )
        storage.write_json_atomic(storage.normalized_metrics_json_path(job.id), artifact.model_dump(mode="json"))
    except Exception as exc:  # noqa: BLE001 - this optional artifact cannot block the visual pipeline
        logger.exception("normalized metric artifact generation failed for %s", job.id)
        artifact = NormalizedMetricArtifact(
            job_id=job.id,
            video_id=result.video_id,
            status="failed",
            detail=f"规范化指标生成失败：{exc}",
            generated_at=generated_at,
            metric_definition_version=METRIC_DEFINITION_VERSION,
            evidence_sufficiency_version=SUFFICIENCY_VERSION,
            scoring_reference_version=REFERENCE_VERSION,
            scoring_reference_hash=profile_hash(DEFAULT_SCORING_REFERENCE_PROFILE),
            diagnostics=["normalization_exception"],
        )
        try:
            storage.write_json_atomic(storage.normalized_metrics_json_path(job.id), artifact.model_dump(mode="json"))
        except Exception:  # noqa: BLE001 - preserve the original optional-artifact failure
            logger.exception("failed to persist normalized metric failure state for %s", job.id)

    updated = storage.publicize_pipeline_result(
        _normalized_artifact_updates(
            result,
            storage,
            status=artifact.status,
            detail=artifact.detail,
        )
    )
    return updated, artifact
