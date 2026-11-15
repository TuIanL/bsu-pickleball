"""Run-range and context import, and the rule that scopes never collapse.

The payloads here are trimmed from real artifacts in the reference take
(``job-96a28d6ff0/result.json`` and the quality reports next to it). Track lists
are cut down to two samples; everything else keeps its original shape.
"""

from __future__ import annotations

import json
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

from app.research_evidence.hashing import snapshot_file
from app.research_evidence.importers import (
    NEVER_RECORDED_FIELDS,
    ArtifactImportError,
    QualityRecord,
    RunRange,
    import_four_player_quality,
    import_job_result,
    import_job_result_file,
    pair_runs_with_quality,
)

REAL_RESULT_PAYLOAD = {
    "job_id": "job-96a28d6ff0",
    "video_id": "rec-069ae78028",
    "calibration_id": "calib-7ae0e023cd",
    "status": "completed",
    "generated_at": "2026-08-08T05:14:46.429594Z",
    "message": "Pipeline completed with Player Tracking Engine output.",
    "match_context": {
        "schema_version": "match-analysis-context.v1",
        "match_format": "doubles",
        "expected_player_count": 4,
        "players_per_side": 2,
        "near_side_quota": 2,
        "far_side_quota": 2,
        "enable_doubles_spacing": True,
    },
    "observed_player_count": 4,
    "tracks": [
        {
            "frame_index": 60,
            "timestamp_seconds": 1.0,
            "track_id": "Player_1",
            "confidence": 0.41535937786102295,
            "side": "near",
        },
        {
            "frame_index": 35229,
            "timestamp_seconds": 587.15,
            "track_id": "Player_3",
            "confidence": 0.71,
            "side": "far",
        },
    ],
}


def _quality(job_id: str, verdict: str, duration: float) -> QualityRecord:
    payload = {
        "schema_version": "four-player-identification-quality.v1",
        "job_id": job_id,
        "verdict": verdict,
        "duration_seconds": duration,
        "attempted_ticks": 6266,
        "confirmed_roster_count": 4,
        "algorithm_version": "motion-aware-v1+clothing-hsv-lab.v1",
        "config_signature": None,
        "baseline_job_id": None,
        "failure_reasons": [] if verdict == "pass" else ["Player_1.longest_gap"],
    }
    return import_four_player_quality(payload)


@pytest.fixture
def tmp_path() -> Iterator[Path]:
    """Override the plugin factory: its numbered mkdir collides with the sandbox shim."""
    with tempfile.TemporaryDirectory(prefix="pe-runs-") as tmp:
        yield Path(tmp)


# --- range and context ------------------------------------------------------


def test_observed_span_is_reconstructed_from_tracks():
    record = import_job_result(REAL_RESULT_PAYLOAD)

    assert record.range is not None
    assert record.range.start_seconds == 1.0
    assert record.range.end_seconds == 587.15
    assert record.range.sample_count == 2
    assert record.range.duration_seconds == pytest.approx(586.15)


def test_range_is_labelled_as_derived_not_declared():
    """result.json has no window field, so the span must not look authoritative."""
    record = import_job_result(REAL_RESULT_PAYLOAD)

    assert record.range is not None
    assert record.range.derivation == "observed_tracks_span"


def test_context_is_preserved():
    record = import_job_result(REAL_RESULT_PAYLOAD)

    assert record.context.schema_version == "match-analysis-context.v1"
    assert record.context.match_format == "doubles"
    assert record.context.expected_player_count == 4
    assert record.context.players_per_side == 2
    assert record.observed_player_count == 4
    assert record.video_id == "rec-069ae78028"
    assert record.calibration_id == "calib-7ae0e023cd"
    assert record.status == "completed"


def test_run_never_carries_a_backfilled_revision():
    record = import_job_result(REAL_RESULT_PAYLOAD)

    for field in NEVER_RECORDED_FIELDS:
        assert field in record.missing_fields


def test_run_without_tracks_reports_missing_range():
    payload = dict(REAL_RESULT_PAYLOAD, tracks=[])

    record = import_job_result(payload)

    assert record.range is None
    assert "range" in record.missing_fields


def test_run_without_match_context_is_reported():
    payload = {k: v for k, v in REAL_RESULT_PAYLOAD.items() if k != "match_context"}

    record = import_job_result(payload)

    assert record.context.match_format is None
    assert "match_context" in record.missing_fields


def test_invalid_run_payloads_are_rejected():
    with pytest.raises(ArtifactImportError):
        import_job_result("not a result")
    with pytest.raises(ArtifactImportError):
        import_job_result({"status": "completed"})


def test_result_import_does_not_modify_the_file(tmp_path):
    target = tmp_path / "result.json"
    target.write_text(json.dumps(REAL_RESULT_PAYLOAD), encoding="utf-8")
    before = snapshot_file(target)

    record = import_job_result_file(target)

    assert record.job_id == "job-96a28d6ff0"
    assert before.matches(snapshot_file(target))


# --- range algebra ----------------------------------------------------------


def test_range_containment_uses_inclusive_bounds():
    long_run = RunRange(1.0, 208.8, "observed_tracks_span", 10)
    short_run = RunRange(1.0, 58.8, "observed_tracks_span", 5)

    assert long_run.contains(short_run) is True
    assert short_run.contains(long_run) is False
    assert long_run.overlaps(short_run) is True


def test_disjoint_ranges_do_not_overlap():
    first = RunRange(0.0, 30.0, "observed_tracks_span", 3)
    second = RunRange(30.5, 60.0, "observed_tracks_span", 3)

    assert first.overlaps(second) is False


# --- scopes must not collapse ----------------------------------------------


def test_short_pass_and_long_fail_coexist_without_merging():
    """Real pattern in the reference take: 58.8s passes while 208.8s fails."""
    short_run = import_job_result(dict(REAL_RESULT_PAYLOAD, job_id="job-0bb3c7e440"))
    long_run = import_job_result(dict(REAL_RESULT_PAYLOAD, job_id="job-43e7475fd8"))
    qualities = [
        _quality("job-0bb3c7e440", "pass", 58.8),
        _quality("job-43e7475fd8", "fail", 208.8),
    ]

    paired = pair_runs_with_quality([short_run, long_run], qualities)

    assert len(paired) == 2
    assert [item.verdict for item in paired] == ["pass", "fail"]


def test_long_fail_does_not_erase_an_enclosed_short_pass():
    long_run = RunRange(1.0, 208.8, "observed_tracks_span", 10)
    short_run = RunRange(1.0, 58.8, "observed_tracks_span", 5)

    assert long_run.contains(short_run)
    # 覆盖关系成立，但每条结论仍只在自己的范围内成立。
    paired = pair_runs_with_quality(
        [import_job_result(dict(REAL_RESULT_PAYLOAD, job_id="a")),
         import_job_result(dict(REAL_RESULT_PAYLOAD, job_id="b"))],
        [_quality("a", "pass", short_run.duration_seconds),
         _quality("b", "fail", long_run.duration_seconds)],
    )
    assert {item.verdict for item in paired} == {"pass", "fail"}


def test_no_run_may_claim_to_cover_the_whole_take():
    short_run = import_job_result(dict(REAL_RESULT_PAYLOAD, job_id="job-7ab0b2ea60"))

    paired = pair_runs_with_quality([short_run], [_quality("job-7ab0b2ea60", "pass", 6.0)])

    assert paired[0].covers_whole_take is False
    assert paired[0].verdict == "pass"


def test_run_without_quality_report_reports_unknown_verdict():
    run = import_job_result(REAL_RESULT_PAYLOAD)

    paired = pair_runs_with_quality([run], [])

    assert paired[0].quality is None
    assert paired[0].verdict == "unknown"
