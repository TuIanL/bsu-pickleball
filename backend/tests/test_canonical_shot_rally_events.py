from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from app.schemas.analysis import AnalysisJobSummary, AnalysisUploadMetadata
from app.schemas.metrics import Heatmap, PerformanceMetrics
from app.schemas.pipeline import AnalysisArtifacts, AnalysisPipelineResult
from app.schemas.shot_rally_events import PRODUCT_REFERENCE_V1, MetricSnapshotArtifact, ShotRallyEventsArtifact
from app.services import canonical_shot_rally_events as composer


def _segment(
    segment_id: str,
    shot_id: str,
    event_id: str,
    timestamp_sec: float,
    *,
    player_id: str | None = "Player_1",
    ownership_status: str = "confirmed",
) -> dict:
    return {
        "segment_id": segment_id,
        "shot_id": shot_id,
        "start_event_id": event_id,
        "start_event_type": "hit",
        "status": "reconstructed",
        "quality": {"overall": 0.8, "display_level": "high"},
        "hitter_player_id": player_id,
        "ownership_status": ownership_status,
        "ownership_confidence": 0.9 if player_id else None,
        "samples": [
            {"timestamp_sec": timestamp_sec, "court_xy": [2.0, 5.0], "source": "detected", "confidence": 0.9},
            {"timestamp_sec": timestamp_sec + 0.2, "court_xy": [3.0, 7.0], "source": "detected", "confidence": 0.9},
        ],
    }


def _payload(segments: list[dict], *, event_times: dict[str, float]) -> dict:
    return {
        "schema_version": "reconstructed_ball_trajectory.v2",
        "job_id": "job-canonical-test",
        "status": "available",
        "detail": "fixture",
        "player_roster": [
            {"player_id": "Player_1", "render_slot": "near_1", "initial_side": "near"},
            {"player_id": "Player_2", "render_slot": "far_1", "initial_side": "far"},
        ],
        "events": [
            {
                "event_id": event_id,
                "event_type": "hit",
                "timestamp_sec": timestamp,
                "confidence": 0.9,
            }
            for event_id, timestamp in event_times.items()
        ],
        "segments": segments,
    }


def test_composer_deduplicates_segments_and_preserves_uncertainty() -> None:
    payload = _payload(
        [
            _segment("flight-1", "shot-001", "hit-1", 1.0),
            _segment("flight-2", "shot-001", "hit-1", 1.2),
            _segment("flight-3", "shot-002", "hit-2", 2.0, player_id=None, ownership_status="ambiguous"),
            {"segment_id": "flight-missing", "shot_id": None, "samples": []},
        ],
        event_times={"hit-1": 1.0, "hit-2": 2.0},
    )

    events = composer.build_shot_rally_events(
        job_id="job-canonical-test",
        video_id="video-1",
        match_format="doubles",
        reconstructed_payload=payload,
        generated_at="2026-08-24T00:00:00+00:00",
    )

    assert events.status == "available"
    assert [shot.shot_id for shot in events.shots] == ["shot-001", "shot-002"]
    assert events.diagnostics.duplicate_shot_ids == ["shot-001"]
    assert events.diagnostics.missing_shot_ids == ["flight-missing"]
    assert events.shots[0].rally_id is None
    assert events.shots[0].ordinal_in_rally is None
    assert events.shots[1].ownership_status == "ambiguous"
    assert events.shots[1].hitter_player_id is None
    assert events.shots[0].trajectory.path_distance_ft == 6.708


def test_composer_uses_authoritative_rally_boundaries_and_stable_ordinals(monkeypatch) -> None:
    monkeypatch.setattr(
        composer,
        "_load_rally_boundaries",
        lambda _capture_take_id: (
            [
                {
                    "rally_id": "rally-0001",
                    "ordinal": 1,
                    "start_ms": 900,
                    "end_ms": 3500,
                }
            ],
            [],
        ),
    )
    segments = [
        _segment("flight-1", "shot-001", "hit-1", 1.0),
        _segment("flight-2", "shot-002", "hit-2", 2.0, player_id="Player_2"),
        _segment("flight-3", "shot-003", "hit-3", 3.0, player_id="Player_1"),
    ]
    payload = _payload(segments, event_times={"hit-1": 1.0, "hit-2": 2.0, "hit-3": 3.0})
    first = composer.build_shot_rally_events(
        job_id="job-canonical-test",
        video_id="video-1",
        match_format="doubles",
        reconstructed_payload=payload,
        capture_take_id="ct-1",
        generated_at="2026-08-24T00:00:00+00:00",
    )
    second = composer.build_shot_rally_events(
        job_id="job-canonical-test",
        video_id="video-1",
        match_format="doubles",
        reconstructed_payload=payload,
        capture_take_id="ct-1",
        generated_at="2026-08-24T00:00:00+00:00",
    )

    assert [shot.ordinal_in_rally for shot in first.shots] == [1, 2, 3]
    assert [shot.stage for shot in first.shots] == ["serve", "return", "third"]
    assert first.model_dump(exclude={"generated_at"}) == second.model_dump(exclude={"generated_at"})

    snapshot = composer.build_metric_snapshot(
        first,
        match_format="singles",
        generated_at="2026-08-24T00:00:00+00:00",
    )
    third = next(
        metric
        for metric in snapshot.metrics
        if metric.metric_key == "third_shot_count" and metric.scope == "match"
    )
    doubles = next(metric for metric in snapshot.metrics if metric.metric_key == "doubles_cooperation")
    assert third.value == 1
    assert third.evidence_ids == ["shot-003"]
    assert doubles.status == "not_applicable"
    assert doubles.value is None
    assert snapshot.thresholds == PRODUCT_REFERENCE_V1
    valid_evidence_ids = {shot.shot_id for shot in first.shots} | {rally.rally_id for rally in first.rallies}
    valid_evidence_ids.add("shot-rally-events.v1")
    assert all(
        evidence_id in valid_evidence_ids
        for metric in snapshot.metrics
        for evidence_id in metric.evidence_ids
    )


def test_metric_snapshot_does_not_turn_zero_denominator_into_zero_rate(monkeypatch) -> None:
    monkeypatch.setattr(composer, "_load_rally_boundaries", lambda _capture_take_id: ([], []))
    events = composer.build_shot_rally_events(
        job_id="job-empty",
        video_id="video-1",
        match_format="doubles",
        reconstructed_payload={
            "schema_version": "reconstructed_ball_trajectory.v2",
            "status": "no_candidates",
            "detail": "没有可重建的清洗轨迹",
            "events": [],
            "segments": [],
        },
        generated_at="2026-08-24T00:00:00+00:00",
    )
    snapshot = composer.build_metric_snapshot(events, match_format="doubles", generated_at="2026-08-24T00:00:00+00:00")
    shot_count = next(metric for metric in snapshot.metrics if metric.metric_key == "shot_count")
    rally_count = next(metric for metric in snapshot.metrics if metric.metric_key == "rally_count")
    assert shot_count.value is None
    assert shot_count.status == "insufficient_evidence"
    assert rally_count.value is None
    assert rally_count.status == "insufficient_evidence"


def test_artifact_envelopes_keep_empty_arrays_and_all_degradation_states() -> None:
    states = ["available", "skipped", "insufficient_evidence", "not_applicable", "unavailable", "failed"]
    for state in states:
        events = ShotRallyEventsArtifact(
            job_id="job-status",
            status=state,
            detail=f"{state} detail",
            generated_at="2026-08-24T00:00:00+00:00",
        )
        snapshot = MetricSnapshotArtifact(
            job_id="job-status",
            status=state,
            detail=f"{state} detail",
            generated_at="2026-08-24T00:00:00+00:00",
        )
        assert events.rallies == []
        assert events.shots == []
        assert snapshot.metrics == []


class _FakeStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    def resolve_capture_job_root(self, _job_id: str, _capture_take_id: str | None = None) -> None:
        return None

    def reconstructed_ball_trajectory_json_path(self, job_id: str) -> Path:
        return self.root / job_id / "reconstructed_ball_trajectory.json"

    def serve_events_json_path(self, job_id: str) -> Path:
        return self.root / job_id / "serve_events.json"

    def shot_rally_events_json_path(self, job_id: str) -> Path:
        return self.root / job_id / "shot_rally_events.json"

    def metric_snapshot_json_path(self, job_id: str) -> Path:
        return self.root / job_id / "metric_snapshot.json"

    def output_json_path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def write_json(self, path: Path, payload: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        return path

    def publicize_pipeline_result(self, result: AnalysisPipelineResult) -> AnalysisPipelineResult:
        return result


def test_generate_and_persist_updates_result_artifacts_without_blocking_pipeline(tmp_path: Path) -> None:
    storage = _FakeStorage(tmp_path)
    job = AnalysisJobSummary(
        id="job-persist-canonical",
        status="completed",
        canonicalStatus="succeeded",
        displayStatus="completed",
        stage="report",
        progress=100,
        createdAt="2026-08-24T00:00:00+00:00",
        updatedAt="2026-08-24T00:00:00+00:00",
        metadata=AnalysisUploadMetadata(
            fileName="match.mp4",
            matchTitle="Canonical",
            venue="Court",
            matchDate="2026-08-24",
            matchFormat="singles",
            cameraAngle="elevated",
            athleteLabel="Player 1",
            level="MVP",
        ),
        stages=[],
        analysisMode="real",
        videoId="video-1",
        calibrationId="cal-1",
    )
    result = AnalysisPipelineResult(
        job_id=job.id,
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
    storage.write_json(
        storage.reconstructed_ball_trajectory_json_path(job.id),
        _payload([_segment("flight-1", "shot-001", "hit-1", 1.0)], event_times={"hit-1": 1.0}),
    )

    updated, events, snapshot = composer.generate_and_persist_canonical_events(job, result, storage=storage)

    assert events.status == "available"
    assert snapshot.schema_version == "metric-snapshot.v1"
    assert updated.artifacts.shot_rally_events_status == "available"
    assert updated.artifacts.metric_snapshot_status == "available"
    assert storage.shot_rally_events_json_path(job.id).exists()
    assert storage.metric_snapshot_json_path(job.id).exists()
    persisted = AnalysisPipelineResult.model_validate(
        json.loads(storage.output_json_path(job.id).read_text())
    )
    assert persisted.job_id == job.id
