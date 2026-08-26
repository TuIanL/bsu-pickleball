from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.schemas.analysis import AnalysisJobSummary, AnalysisUploadMetadata
from app.schemas.metric_normalization import (
    EvidenceSufficiencyProfile,
    MetricDefinition,
    MetricDefinitionProfile,
    MetricNormalizationContext,
    MetricReference,
    ScoringReferenceProfile,
    SufficiencyRule,
)
from app.schemas.metrics import Heatmap, PerformanceMetrics
from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult
from app.schemas.shot_rally_events import (
    MetricSnapshotArtifact,
    MetricSnapshotEntry,
    ShotEvent,
    ShotRallyEventsArtifact,
)
from app.services.metric_normalization import (
    DEFAULT_METRIC_DEFINITION_PROFILE,
    DEFAULT_SCORING_REFERENCE_PROFILE,
    generate_and_persist_normalized_metrics,
    normalize_metric_snapshot,
    profile_hash,
)


def _metric(
    key: str,
    value: float | int | None,
    *,
    status: str = "available",
    unit: str = "ratio",
    sample_count: int = 3,
    denominator: int | None = 3,
    evidence_ids: list[str] | None = None,
    provenance: str = "confirmed",
) -> MetricSnapshotEntry:
    return MetricSnapshotEntry(
        metric_id=f"player:Player_1:{key}",
        metric_key=key,
        scope="player",
        subject_id="Player_1",
        value=value,
        unit=unit,
        numerator=sample_count if denominator else None,
        denominator=denominator,
        sample_count=sample_count,
        status=status,
        reason=None if status == "available" else f"{status} fixture",
        provenance=provenance,
        evidence_ids=evidence_ids or ["shot-1"],
    )


def _events(*shot_ids: str) -> ShotRallyEventsArtifact:
    return ShotRallyEventsArtifact(
        job_id="job-normalization",
        status="available",
        detail="fixture",
        generated_at="2026-08-24T00:00:00+00:00",
        shots=[
            ShotEvent(
                shot_id=shot_id,
                start_ms=index * 100,
                end_ms=index * 100 + 50,
                hitter_player_id="Player_1",
                ownership_status="confirmed",
            )
            for index, shot_id in enumerate(shot_ids)
        ],
    )


def _snapshot(*metrics: MetricSnapshotEntry, status: str = "available") -> MetricSnapshotArtifact:
    return MetricSnapshotArtifact(
        job_id="job-normalization",
        status=status,
        detail="fixture",
        generated_at="2026-08-24T00:00:00+00:00",
        metrics=list(metrics),
    )


def _scoreable_setup(
    *,
    key: str = "return_depth",
    direction: str = "higher_better",
    mode: str = "expert_threshold",
    metric_unit: str = "ft",
    metric_value: float = 75.0,
    reference_kwargs: dict | None = None,
    provenance: str = "confirmed",
):
    definition = MetricDefinition(
        metric_key=key,
        source_metric_key=key,
        unit=metric_unit,
        scopes=["player"],
        metric_direction=direction,
        min_sample_count=3,
    )
    if mode == "target_range":
        reference = MetricReference(
            metric_key=key,
            reference_mode="target_range",
            metric_direction="target_range",
            reference_source="expert_fixture",
            reference_detail="test target range",
            lower_bound=0,
            upper_bound=100,
            target_min=40,
            target_max=60,
            fallback="none",
        )
        definition = definition.model_copy(update={"metric_direction": "target_range"})
    else:
        reference = MetricReference(
            metric_key=key,
            reference_mode=mode,
            metric_direction=direction,
            reference_source="expert_fixture",
            reference_detail="test reference",
            lower_bound=0,
            upper_bound=100,
            fallback="none",
            **(reference_kwargs or {}),
        )
    snapshot = _snapshot(_metric(key, metric_value, unit=metric_unit, provenance=provenance))
    return (
        snapshot,
        _events("shot-1"),
        MetricDefinitionProfile(metrics=[definition]),
        ScoringReferenceProfile(
            reference_version="test-reference-v1",
            reference_mode=mode,
            reference_source="expert_fixture",
            reference_detail="test reference",
            metrics=[reference],
        ),
    )


def test_default_profile_only_normalizes_current_canonical_metrics_as_display_only() -> None:
    snapshot = _snapshot(_metric("shot_count", 4, unit="count"))
    artifact = normalize_metric_snapshot(snapshot, events=_events("shot-1"))

    entry = artifact.metrics[0]
    assert len(DEFAULT_METRIC_DEFINITION_PROFILE.metrics) == 7
    assert entry.canonical_value == 4
    assert entry.score_eligibility == "display_only"
    assert entry.utility_score is None
    assert "descriptive_only_metric" in entry.eligibility_reasons
    assert artifact.scoring_reference_hash == profile_hash(DEFAULT_SCORING_REFERENCE_PROFILE)


def test_unknown_pb_vision_metric_is_unsupported_instead_of_invented() -> None:
    snapshot = _snapshot(_metric("return_depth", 34.2, unit="ft"))
    artifact = normalize_metric_snapshot(snapshot, events=_events("shot-1"))

    entry = artifact.metrics[0]
    assert entry.score_eligibility == "unsupported"
    assert entry.canonical_value == 34.2
    assert entry.utility_score is None
    assert "metric_definition_missing" in entry.eligibility_reasons


@pytest.mark.parametrize(
    "status", ["available", "skipped", "insufficient_evidence", "not_applicable", "unavailable", "failed"]
)
def test_artifact_statuses_and_empty_metrics_are_preserved(status: str) -> None:
    snapshot = MetricSnapshotArtifact(
        job_id="job-normalization-status",
        status=status,
        detail=f"{status} fixture",
        generated_at="2026-08-24T00:00:00+00:00",
    )
    artifact = normalize_metric_snapshot(snapshot, generated_at="2026-08-24T00:00:01+00:00")

    assert artifact.status == status
    assert artifact.metrics == []
    assert status in artifact.detail or status == "available"


def test_pb_vision_external_signals_do_not_become_formal_utility() -> None:
    snapshot = _snapshot(
        _metric("shot_quality_mean", 0.71, unit="ratio"),
        _metric("coach_advice.value", 0.99, unit="ratio"),
    )
    artifact = normalize_metric_snapshot(snapshot, events=_events("shot-1"))

    by_key = {entry.metric_key: entry for entry in artifact.metrics}
    assert by_key["shot_quality_mean"].score_eligibility == "display_only"
    assert by_key["coach_advice.value"].score_eligibility == "unsupported"
    assert all(entry.utility_score is None for entry in artifact.metrics)


def test_expert_threshold_generates_internal_utility_but_no_dimension_or_overall_score() -> None:
    snapshot, events, definitions, reference = _scoreable_setup(metric_value=75)
    artifact = normalize_metric_snapshot(
        snapshot,
        events=events,
        definition_profile=definitions,
        sufficiency_profile=EvidenceSufficiencyProfile(default_rule=SufficiencyRule(min_sample_count=3)),
        reference_profile=reference,
        generated_at="2026-08-24T00:00:01+00:00",
    )

    entry = artifact.metrics[0]
    assert entry.score_eligibility == "eligible"
    assert entry.utility_score == 0.75
    assert entry.percentile is None
    assert not hasattr(entry, "dimension_score")
    assert not hasattr(artifact, "overall_score")


@pytest.mark.parametrize(
    ("direction", "value", "expected"),
    [("higher_better", 75, 0.75), ("lower_better", 25, 0.75)],
)
def test_threshold_direction_is_explicit(direction: str, value: float, expected: float) -> None:
    snapshot, events, definitions, reference = _scoreable_setup(direction=direction, metric_value=value)
    artifact = normalize_metric_snapshot(
        snapshot,
        events=events,
        definition_profile=definitions,
        reference_profile=reference,
    )

    assert artifact.metrics[0].utility_score == expected


def test_target_range_rewards_the_range_and_penalizes_outside_values() -> None:
    snapshot, events, definitions, reference = _scoreable_setup(
        mode="target_range",
        direction="target_range",
        metric_value=50,
    )
    in_range = normalize_metric_snapshot(
        snapshot,
        events=events,
        definition_profile=definitions,
        reference_profile=reference,
    )
    outside = normalize_metric_snapshot(
        snapshot.model_copy(update={"metrics": [_metric("return_depth", 20, unit="ft")]}),
        events=events,
        definition_profile=definitions,
        reference_profile=reference,
    )

    assert in_range.metrics[0].utility_score == 1.0
    assert outside.metrics[0].utility_score == 0.5


def test_empirical_percentile_requires_real_distribution_and_keeps_percentile_separate() -> None:
    snapshot, events, definitions, _ = _scoreable_setup(mode="empirical_percentile", metric_value=75)
    reference = ScoringReferenceProfile(
        reference_version="empirical-v1",
        reference_mode="empirical_percentile",
        reference_source="fixture_population",
        reference_detail="fixture population",
        metrics=[
            MetricReference(
                metric_key="return_depth",
                reference_mode="empirical_percentile",
                metric_direction="higher_better",
                reference_source="fixture_population",
                reference_detail="fixture population",
                population="amateur_doubles",
                cohort="3_5",
                population_sample_count=4,
                reference_distribution=[25, 50, 75, 100],
                fallback="none",
            )
        ],
    )
    artifact = normalize_metric_snapshot(
        snapshot,
        events=events,
        definition_profile=definitions,
        reference_profile=reference,
    )

    assert artifact.metrics[0].percentile == 62.5
    assert artifact.metrics[0].utility_score == 0.625


def test_empirical_reference_without_population_does_not_synthesize_percentile() -> None:
    snapshot, events, definitions, _ = _scoreable_setup(mode="empirical_percentile", metric_value=75)
    reference = ScoringReferenceProfile(
        reference_version="empirical-missing-v1",
        reference_mode="empirical_percentile",
        reference_source="missing_population",
        reference_detail="no population fixture",
        metrics=[
            MetricReference(
                metric_key="return_depth",
                reference_mode="empirical_percentile",
                metric_direction="higher_better",
                reference_source="missing_population",
                reference_detail="no population fixture",
                fallback="unsupported",
            )
        ],
    )
    artifact = normalize_metric_snapshot(
        snapshot,
        events=events,
        definition_profile=definitions,
        reference_profile=reference,
    )

    entry = artifact.metrics[0]
    assert entry.score_eligibility == "unsupported"
    assert entry.utility_score is None
    assert entry.percentile is None
    assert "reference_distribution_missing" in entry.eligibility_reasons


def test_insufficient_evidence_and_zero_denominator_never_become_zero_utility() -> None:
    snapshot, events, definitions, reference = _scoreable_setup(metric_value=75)
    low_sample = snapshot.model_copy(update={"metrics": [_metric("return_depth", 75, unit="ft", sample_count=2)]})
    zero_denominator = snapshot.model_copy(update={"metrics": [_metric("return_depth", 0, unit="ft", denominator=0)]})
    sufficiency = EvidenceSufficiencyProfile(default_rule=SufficiencyRule(min_sample_count=3))

    low = normalize_metric_snapshot(
        low_sample,
        events=events,
        definition_profile=definitions,
        sufficiency_profile=sufficiency,
        reference_profile=reference,
    )
    zero = normalize_metric_snapshot(
        zero_denominator, events=events, definition_profile=definitions, reference_profile=reference
    )

    assert low.metrics[0].score_eligibility == "insufficient_evidence"
    assert low.metrics[0].utility_score is None
    assert zero.metrics[0].score_eligibility == "not_applicable"
    assert zero.metrics[0].utility_score is None


def test_context_missing_and_singles_not_applicable_are_explicit() -> None:
    definition = MetricDefinition(
        metric_key="context_metric",
        source_metric_key="context_metric",
        unit="ratio",
        scopes=["player"],
        metric_direction="context_dependent",
        context_keys=["role"],
        min_sample_count=1,
    )
    reference = MetricReference(
        metric_key="context_metric",
        reference_mode="expert_threshold",
        metric_direction="context_dependent",
        reference_source="fixture",
        reference_detail="fixture",
        lower_bound=0,
        upper_bound=1,
        context_selector={"role": "returner"},
        fallback="none",
    )
    snapshot = _snapshot(_metric("context_metric", 0.5))
    artifact = normalize_metric_snapshot(
        snapshot,
        events=_events("shot-1"),
        definition_profile=MetricDefinitionProfile(metrics=[definition]),
        reference_profile=ScoringReferenceProfile(
            reference_version="context-v1",
            reference_mode="expert_threshold",
            reference_source="fixture",
            reference_detail="fixture",
            metrics=[reference],
        ),
    )
    assert artifact.metrics[0].score_eligibility == "unsupported"
    assert "context_missing" in artifact.metrics[0].eligibility_reasons

    doubles_definition = MetricDefinition(
        metric_key="doubles_metric",
        source_metric_key="doubles_metric",
        unit="ratio",
        scopes=["match"],
        match_formats=["doubles"],
        metric_direction="descriptive_only",
        descriptive_only=True,
    )
    doubles = normalize_metric_snapshot(
        MetricSnapshotArtifact(
            job_id="job-normalization",
            status="available",
            detail="fixture",
            generated_at="2026-08-24T00:00:00+00:00",
            metrics=[
                MetricSnapshotEntry(
                    metric_id="match:match:doubles_metric",
                    metric_key="doubles_metric",
                    scope="match",
                    subject_id="match",
                    value=0.5,
                    unit="ratio",
                    numerator=1,
                    denominator=2,
                    sample_count=2,
                    status="available",
                    provenance="confirmed",
                    evidence_ids=["shot-rally-events.v1"],
                )
            ],
        ),
        context=MetricNormalizationContext(match_format="singles"),
        definition_profile=MetricDefinitionProfile(metrics=[doubles_definition]),
    )
    assert doubles.metrics[0].score_eligibility == "not_applicable"


def test_candidate_and_dangling_evidence_are_not_eligible() -> None:
    snapshot, events, definitions, reference = _scoreable_setup(provenance="candidate")
    candidate = normalize_metric_snapshot(
        snapshot, events=events, definition_profile=definitions, reference_profile=reference
    )
    assert candidate.metrics[0].score_eligibility == "display_only"
    assert "semantic_level_candidate" in candidate.metrics[0].eligibility_reasons

    dangling = snapshot.model_copy(
        update={"metrics": [_metric("return_depth", 75, unit="ft", evidence_ids=["missing-shot"])]}
    )
    failed = normalize_metric_snapshot(
        dangling, events=events, definition_profile=definitions, reference_profile=reference
    )
    assert failed.metrics[0].score_eligibility == "failed"
    assert failed.metrics[0].evidence_ids == []
    assert "evidence_id_unresolvable" in failed.metrics[0].eligibility_reasons


def test_normalization_is_deterministic_except_generated_at() -> None:
    snapshot, events, definitions, reference = _scoreable_setup(metric_value=75)
    first = normalize_metric_snapshot(
        snapshot,
        events=events,
        definition_profile=definitions,
        reference_profile=reference,
        generated_at="2026-08-24T00:00:01+00:00",
    )
    second = normalize_metric_snapshot(
        snapshot,
        events=events,
        definition_profile=definitions,
        reference_profile=reference,
        generated_at="2026-08-24T00:00:02+00:00",
    )
    assert first.model_dump(exclude={"generated_at"}) == second.model_dump(exclude={"generated_at"})
    assert first.metrics[0].metric_id == second.metrics[0].metric_id


class _FakeStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def resolve_capture_job_root(self, _job_id: str, _capture_take_id: str | None = None) -> None:
        return None

    def normalized_metrics_json_path(self, job_id: str) -> Path:
        return self.root / job_id / "normalized_metrics.json"

    def write_json_atomic(self, path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def publicize_pipeline_result(self, result: AnalysisPipelineResult) -> AnalysisPipelineResult:
        return result


def _job_and_result(job_id: str) -> tuple[AnalysisJobSummary, AnalysisPipelineResult]:
    job = AnalysisJobSummary(
        id=job_id,
        status="completed",
        canonicalStatus="succeeded",
        displayStatus="completed",
        stage="report",
        progress=100,
        createdAt="2026-08-24T00:00:00+00:00",
        updatedAt="2026-08-24T00:00:00+00:00",
        metadata=AnalysisUploadMetadata(
            fileName="match.mp4",
            matchTitle="Normalization",
            venue="Court",
            matchDate="2026-08-24",
            matchFormat="singles",
            cameraAngle="elevated",
            athleteLabel="Player 1",
            level="MVP",
        ),
        stages=[],
        analysisMode="real",
        videoId="video-normalization",
        calibrationId="cal-1",
    )
    result = AnalysisPipelineResult(
        job_id=job_id,
        video_id=job.videoId,
        calibration_id=job.calibrationId,
        status="completed",
        generated_at=datetime(2026, 8, 24, tzinfo=UTC),
        stages=[],
        tracks=[],
        metrics=PerformanceMetrics(
            distances=[],
            speeds=[],
            kitchen_dwell=[],
            doubles_spacing=[],
            heatmap=Heatmap(rows=1, cols=1, cells=[]),
        ),
        artifacts=AnalysisArtifacts(),
        message="completed",
    )
    return job, result


def test_persistence_writes_optional_artifact_and_updates_result(tmp_path: Path) -> None:
    storage = _FakeStorage(tmp_path)
    job, result = _job_and_result("job-normalization-persist")
    snapshot, events, definitions, reference = _scoreable_setup(metric_value=75)
    snapshot = snapshot.model_copy(update={"job_id": job.id})
    events = events.model_copy(update={"job_id": job.id})

    # Use the public function with an explicit profile by calling the pure engine
    # first; persistence uses the production default profile and remains optional.
    normalized, artifact = generate_and_persist_normalized_metrics(
        job,
        result,
        events=events,
        snapshot=snapshot,
        storage=storage,
    )

    assert artifact.schema_version == "normalized-metric-snapshot.v1"
    assert normalized.artifacts.normalized_metrics_status == "available"
    assert normalized.artifacts.normalized_metrics_url.endswith("/normalized-metrics")
    assert storage.normalized_metrics_json_path(job.id).exists()


def test_persistence_failure_is_optional_and_preserves_completed_result(tmp_path: Path) -> None:
    storage = _FakeStorage(tmp_path)
    job, result = _job_and_result("job-normalization-failure")

    normalized, artifact = generate_and_persist_normalized_metrics(
        job,
        result,
        storage=storage,
    )

    assert artifact.status == "failed"
    assert normalized.status == "completed"
    assert normalized.artifacts.normalized_metrics_status == "failed"
    assert normalized.artifacts.normalized_metrics_url.endswith("/normalized-metrics")
    assert storage.normalized_metrics_json_path(job.id).exists()
