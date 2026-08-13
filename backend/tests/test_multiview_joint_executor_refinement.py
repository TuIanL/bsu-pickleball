"""Executor-level publication tests for the F1 refinement lifecycle."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.services.multiview_joint_executor import (
    _publish_refinement_artifacts,
    _write_failed_refinement_fallback,
)
from app.vision.multiview.joint_artifact import FusedSample
from app.vision.multiview.offline_refinement import (
    F0RefinementSnapshot,
    RecoveredViewObservation,
    RefinementOutcome,
)


class RecordingStorage:
    def __init__(self, *, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.writes: list[str] = []

    def write_json_atomic(self, path, payload):
        self.writes.append(path.name)
        if path.name == self.fail_on:
            raise OSError(f"injected write failure: {path.name}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        return path


def _snapshot() -> F0RefinementSnapshot:
    return F0RefinementSnapshot(
        run_id="run-1",
        capture_take_id="take-1",
        global_player_ids=("g1",),
        view_ids=("cam_1", "cam_2"),
    )


def _outcome(status: str, final_source: str, *, with_candidate: bool) -> RefinementOutcome:
    recovered = [
        RecoveredViewObservation(
            view_id="cam_1",
            take_timestamp_ms=100.0,
            source_frame_index=10,
            canonical_x_ft=5.0,
            canonical_y_ft=8.0,
            bbox=(1.0, 2.0, 3.0, 4.0),
            confidence=0.8,
            global_player_id="g1",
            canonical_tick=1,
            timing_authority="source_pts",
            sync_quality="good",
            donor_view="cam_2",
            donor_source_frame_index=20,
            donor_quality=0.9,
            expected_global_position=(5.0, 8.0),
            residual_ft=0.2,
        )
    ] if with_candidate else []
    candidates = [
        FusedSample(
            global_player_id="g1",
            take_timestamp_ms=100.0,
            reference_frame_index=10,
            x_ft=5.0,
            y_ft=8.0,
            fusion_status="dual_observed",
            metric_eligible=True,
            view_observations={
                "cam_1": {
                    "view_id": "cam_1",
                    "source_frame_index": 10,
                    "source_timestamp_ms": 100.0,
                    "mapped_take_timestamp_ms": 100.0,
                    "selection_error_ms": 0.0,
                    "timing_authority": "source_pts",
                    "sync_quality": "good",
                    "observation_origin": "offline_refinement",
                }
            },
            contributing_views=["cam_1"],
        )
    ] if with_candidate else []
    return RefinementOutcome(
        status=status,
        final_source=final_source,
        recovered=recovered,
        candidate_samples=candidates,
        diagnostics={"windows": 1 if with_candidate else 0},
        reason=None if status in {"completed", "skipped_no_windows"} else "gate_reason",
    )


def _out():
    return SimpleNamespace(
        trajectory={"schema_version": "fused_player_trajectory.v2", "samples": []},
        f0_snapshot=_snapshot(),
        diagnostics={},
    )


def test_executor_publication_completed_writes_f0_then_recovered_f1_then_diagnostics(tmp_path):
    storage = RecordingStorage()
    refinement, compose_output = _publish_refinement_artifacts(
        storage=storage,
        run_dir=tmp_path,
        out=_out(),
        outcome=_outcome("completed", "refined_f1", with_candidate=True),
        run_id="run-1",
        capture_take_id="take-1",
        reference_view_id="cam_1",
        authoritative_run=False,
        snapshot_artifact="f0_refinement_snapshot.v1.json",
    )
    assert storage.writes == [
        "recovered_view_observations.v1.json",
        "fused_player_trajectory.f1.v2.json",
        "refinement_diagnostics.json",
    ]
    assert refinement["status"] == "completed"
    assert refinement["final_source"] == "refined_f1"
    assert compose_output.trajectory["schema_version"] == "fused_player_trajectory.v2"


@pytest.mark.parametrize(
    ("status", "final_source", "with_candidate"),
    [
        ("rejected_by_safety_gate", "first_pass_f0", True),
        ("skipped_no_windows", "first_pass_f0", False),
    ],
)
def test_executor_publication_preserves_f0_final_source_for_non_adopted_states(
    tmp_path, status, final_source, with_candidate
):
    storage = RecordingStorage()
    refinement, compose_output = _publish_refinement_artifacts(
        storage=storage,
        run_dir=tmp_path,
        out=_out(),
        outcome=_outcome(status, final_source, with_candidate=with_candidate),
        run_id="run-1",
        capture_take_id="take-1",
        reference_view_id="cam_1",
        authoritative_run=False,
        snapshot_artifact="f0_refinement_snapshot.v1.json",
    )
    assert refinement["status"] == status
    assert refinement["final_source"] == "first_pass_f0"
    assert compose_output is not None
    assert "refined_artifact" not in refinement or refinement["refined_artifact"] is None
    if status == "rejected_by_safety_gate":
        assert "fused_player_trajectory.f1.v2.json" in storage.writes
    else:
        assert "fused_player_trajectory.f1.v2.json" not in storage.writes


def test_executor_publication_write_failure_is_failed_fallback_and_keeps_f0(tmp_path):
    storage = RecordingStorage(fail_on="fused_player_trajectory.f1.v2.json")
    with pytest.raises(OSError):
        _publish_refinement_artifacts(
            storage=storage,
            run_dir=tmp_path,
            out=_out(),
            outcome=_outcome("completed", "refined_f1", with_candidate=True),
            run_id="run-1",
            capture_take_id="take-1",
            reference_view_id="cam_1",
            authoritative_run=False,
            snapshot_artifact="f0_refinement_snapshot.v1.json",
        )

    fallback_storage = RecordingStorage()
    refinement = _write_failed_refinement_fallback(
        storage=fallback_storage,
        run_dir=tmp_path,
        f0_snapshot_present=True,
        reason="injected write failure",
    )
    assert refinement["status"] == "failed_fallback"
    assert refinement["final_source"] == "first_pass_f0"
    assert fallback_storage.writes == ["refinement_diagnostics.json"]
