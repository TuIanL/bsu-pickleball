"""Smoke check against a checked-in, de-identified real analysis artifact."""

from __future__ import annotations

import json
from pathlib import Path

from app.schemas.shot_rally_events import ShotEvent, ShotRallyEventsArtifact, ShotTrajectorySummary
from app.services.shot_landings import build_shot_landings


def test_deidentified_reconstructed_artifact_preserves_evidence_geometry_and_time() -> None:
    root = Path(__file__).parents[1] / "data" / "outputs" / "job-04692d6f43"
    reconstructed = json.loads((root / "reconstructed_ball_trajectory.json").read_text())
    players = json.loads((root / "player_render_trajectory.json").read_text())
    shots = ShotRallyEventsArtifact(
        job_id="deidentified-smoke",
        status="available",
        detail="de-identified real artifact smoke",
        generated_at="2026-09-21T00:00:00Z",
        shots=[
            ShotEvent(shot_id="smoke-outside", start_ms=600, end_ms=1200, contact_ms=600,
                ownership_status="unassigned", trajectory=ShotTrajectorySummary(available=True, segment_ids=["flight-2"])),
            ShotEvent(shot_id="smoke-inside", start_ms=4100, end_ms=4700, contact_ms=4100,
                ownership_status="unassigned", trajectory=ShotTrajectorySummary(available=True, segment_ids=["flight-6"])),
        ],
    )

    artifact = build_shot_landings(
        job_id="deidentified-smoke", video_id=None, shot_events=shots,
        reconstructed_payload=reconstructed, player_trajectory_payload=players,
        generated_at="2026-09-21T00:00:00Z",
    )

    outside, inside = artifact.landings
    assert (outside.source_segment_id, outside.source_event_id) == ("flight-2", "bounce-2")
    assert outside.timestamp_ms == 1200
    assert outside.court_location == "outside_court"
    assert outside.orientation_transform == "rotate_180"
    assert outside.landing_y_ft == -0.513
    assert (inside.source_segment_id, inside.source_event_id) == ("flight-6", "bounce-4")
    assert inside.timestamp_ms == 4700
    assert inside.orientation_transform == "identity"
    assert inside.court_location == "inside_court"
