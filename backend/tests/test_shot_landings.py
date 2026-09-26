from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from app.schemas.shot_landings import ShotLanding
from app.schemas.shot_rally_events import ShotEvent, ShotRallyEventsArtifact, ShotTrajectorySummary
from app.services.shot_landings import build_shot_landings, project12_zone


def _shots(*shots: ShotEvent) -> ShotRallyEventsArtifact:
    return ShotRallyEventsArtifact(
        job_id="job-landing",
        status="available",
        detail="fixture",
        generated_at="2026-09-21T00:00:00+00:00",
        shots=list(shots),
    )


def _shot(shot_id: str, segment_ids: list[str], *, hitter: str | None = "Player_1", contact_ms: int = 1000) -> ShotEvent:
    return ShotEvent(
        shot_id=shot_id,
        start_ms=contact_ms,
        end_ms=contact_ms + 1000,
        contact_ms=contact_ms,
        hitter_player_id=hitter,
        ownership_status="confirmed" if hitter else "unassigned",
        stage="third",
        ordinal_in_rally=3,
        trajectory=ShotTrajectorySummary(available=True, segment_ids=segment_ids),
    )


def _reconstructed() -> dict:
    return {
        "schema_version": "reconstructed_ball_trajectory.v2",
        "status": "available",
        "events": [
            {"event_id": "bounce-1", "event_type": "bounce", "event_status": "confirmed", "frame_index": 36, "timestamp_sec": 1.2, "court_xy": [16.4, 41.1], "confidence": 0.91},
            {"event_id": "bounce-2", "event_type": "bounce", "event_status": "confirmed", "frame_index": 42, "timestamp_sec": 1.4, "court_xy": [10.0, 35.0], "confidence": 0.8},
            {"event_id": "hit-2", "event_type": "hit", "event_status": "confirmed", "frame_index": 60, "timestamp_sec": 2.0},
        ],
        "segments": [
            {"segment_id": "seg-2", "end_event_id": "bounce-2", "end_event_type": "bounce", "samples": [{"timestamp_sec": 1.2, "court_xy": [16.0, 40.0]}]},
            {"segment_id": "seg-1", "end_event_id": "bounce-1", "end_event_type": "bounce", "samples": [{"timestamp_sec": 1.0, "court_xy": [12.0, 31.0]}]},
            {"segment_id": "seg-hit", "end_event_id": "hit-2", "end_event_type": "hit", "samples": [{"timestamp_sec": 1.5, "court_xy": [8.0, 20.0]}]},
            {"segment_id": "seg-loss", "end_event_id": "loss-1", "end_event_type": "loss", "samples": []},
        ],
    }


def test_available_schema_rejects_missing_coordinates() -> None:
    with pytest.raises(ValidationError):
        ShotLanding(landing_id="l", shot_id="s", landing_status="available")


@pytest.mark.parametrize(
    ("u", "distance", "expected"),
    [
        (0.0, 0.0, ("K-L", 1)),
        (1 / 3, 7.0, ("T-C", 5)),
        (2 / 3, 12.0, ("D-R", 9)),
        (1.0, 17.0, ("VD-R", 12)),
        (1.0, 22.0, ("VD-R", 12)),
    ],
)
def test_project12_exact_boundaries(u: float, distance: float, expected: tuple[str, int]) -> None:
    assert project12_zone(u, distance) == expected


def test_project12_rejects_nonfinite_and_ineligible() -> None:
    assert project12_zone(float("nan"), 7) is None
    assert project12_zone(0.5, float("inf")) is None
    assert project12_zone(0.5, 8, eligible=False) is None


def test_composer_uses_first_formal_bounce_and_player_side() -> None:
    artifact = build_shot_landings(
        job_id="job-landing",
        video_id="video-1",
        shot_events=_shots(_shot("shot-001", ["seg-2", "seg-1"])),
        reconstructed_payload=_reconstructed(),
        player_trajectory_payload={"samples": [{"player_id": "Player_1", "timestamp_seconds": 1.0, "x_ft": 5.0, "y_ft": 8.0, "projection_status": "inside_court"}]},
        generated_at="2026-09-21T00:00:00+00:00",
    )
    landing = artifact.landings[0]
    assert landing.bounce_event_id == "bounce-1"
    assert (landing.landing_x_ft, landing.landing_y_ft) == (16.4, 41.1)
    assert landing.canonicalization_basis == "hitter_position_at_contact"
    assert landing.orientation_transform == "identity"
    assert landing.target_relation == "target_half"
    assert landing.zone_12 == "VD-R"
    assert artifact.summary.spatial_measurability_rate == 1.0


def test_composer_rotates_near_target_and_preserves_outside_coordinate() -> None:
    payload = _reconstructed()
    payload["events"][0]["court_xy"] = [20.4, 3.0]
    artifact = build_shot_landings(
        job_id="job-landing", video_id=None,
        shot_events=_shots(_shot("shot-001", ["seg-1"], hitter="Player_2")),
        reconstructed_payload=payload,
        player_trajectory_payload={"samples": [{"player_id": "Player_2", "timestamp_seconds": 1.0, "x_ft": 10, "y_ft": 35, "projection_status": "inside_court"}]},
        generated_at="2026-09-21T00:00:00+00:00",
    )
    landing = artifact.landings[0]
    assert landing.court_location == "outside_court"
    assert landing.orientation_transform == "rotate_180"
    assert landing.landing_x_ft == 20.4
    assert landing.target_x_ft == pytest.approx(-0.4)
    assert landing.zone_12 is None


def test_composer_fails_closed_without_side_or_direction() -> None:
    payload = _reconstructed()
    payload["segments"][1]["samples"] = [{"timestamp_sec": 1.0, "court_xy": [16.0, 40.5]}]
    artifact = build_shot_landings(
        job_id="job-landing", video_id=None,
        shot_events=_shots(_shot("shot-001", ["seg-1"], hitter=None)),
        reconstructed_payload=payload,
        generated_at="2026-09-21T00:00:00+00:00",
    )
    landing = artifact.landings[0]
    assert landing.canonicalization_basis == "unavailable"
    assert landing.target_x_ft is None
    assert landing.zone_12 is None


def test_no_bounce_missing_coordinate_ambiguous_and_dangling_states() -> None:
    payload = _reconstructed()
    payload["events"].append({"event_id": "bounce-no-xy", "event_type": "bounce", "event_status": "confirmed", "frame_index": 70, "timestamp_sec": 2.3, "court_xy": None, "confidence": 0.7})
    payload["events"].append({"event_id": "bounce-amb", "event_type": "bounce", "event_status": "ambiguous", "frame_index": 75, "timestamp_sec": 2.5, "court_xy": [10, 30], "confidence": 0.4})
    payload["segments"].extend([
        {"segment_id": "seg-no-xy", "end_event_id": "bounce-no-xy", "end_event_type": "bounce", "samples": []},
        {"segment_id": "seg-amb", "end_event_id": "bounce-amb", "end_event_type": "bounce", "samples": []},
    ])
    artifact = build_shot_landings(
        job_id="job-landing", video_id=None,
        shot_events=_shots(
            _shot("shot-hit", ["seg-hit"]),
            _shot("shot-no-xy", ["seg-no-xy"]),
            _shot("shot-amb", ["seg-amb"]),
            _shot("shot-loss", ["seg-loss"]),
            _shot("shot-dangling", ["missing-seg"]),
        ),
        reconstructed_payload=payload,
        generated_at="2026-09-21T00:00:00+00:00",
    )
    by_id = {item.shot_id: item for item in artifact.landings}
    assert by_id["shot-hit"].landing_status == "no_bounce_before_next_contact"
    assert by_id["shot-no-xy"].landing_status == "bounce_without_court_coordinate"
    assert by_id["shot-amb"].landing_status == "ambiguous_bounce"
    assert by_id["shot-loss"].landing_status == "unavailable"
    assert by_id["shot-dangling"].landing_status == "unavailable"
    assert artifact.diagnostics.missing_segment_ids == ["missing-seg"]


def test_composer_is_deterministic_and_preserves_evidence_links() -> None:
    kwargs = dict(
        job_id="job-landing", video_id="video-1",
        shot_events=_shots(_shot("shot-001", ["seg-1"])),
        reconstructed_payload=_reconstructed(),
        player_trajectory_payload={"samples": [{"player_id": "Player_1", "timestamp_seconds": 1.0, "x_ft": 5, "y_ft": 8}]},
        generated_at="2026-09-21T00:00:00+00:00",
    )
    first = build_shot_landings(**deepcopy(kwargs))
    second = build_shot_landings(**deepcopy(kwargs))
    assert first.model_dump() == second.model_dump()
    landing = first.landings[0]
    assert landing.shot_id == "shot-001"
    assert landing.source_segment_id == "seg-1"
    assert landing.source_event_id == "bounce-1"


@pytest.mark.parametrize("point, expected", [
    ((0, 50), "outside_court"), ((20, -6), "outside_court"),
    ((-6, 0), "outside_court"), ((26, 44), "outside_court"),
    ((0.05, 50), "outside_court"), ((-0.08, -0.08), "outside_court"),
    ((0, 22), "unknown"), ((10, 44.05), "unknown"),
    ((0.05, 22), "unknown"), ((10, 30), "inside_court"),
])
def test_court_boundary_uses_finite_edges(point, expected):
    from app.services.shot_landings import classify_court_location
    assert classify_court_location(*point) == expected
