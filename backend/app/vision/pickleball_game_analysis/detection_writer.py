"""JSON writers for ball trajectory and bounce artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.vision.pickleball_game_analysis.bounce_detector import BounceDetectorConfig
from app.vision.pickleball_game_analysis.schemas import (
    BallFrameSample,
    BounceEvent,
    TrajectoryPoint,
    coordinate_system_metadata,
    event_to_payload,
    sample_to_payload,
    to_jsonable,
)
from app.vision.pickleball_game_analysis.trajectory_cleaner import TrajectoryCleanerConfig


def build_raw_trajectory_payload(
    *,
    job_id: str,
    samples: list[BallFrameSample],
    status: str = "available",
    detail: str = "ball trajectory generated",
    court_width: float = 20.0,
    court_length: float = 44.0,
) -> dict[str, Any]:
    return {
        "schema_version": "ball_trajectory.v1",
        "job_id": job_id,
        "status": status,
        "detail": detail,
        "coordinate_system": coordinate_system_metadata(court_width, court_length),
        "samples": [sample_to_payload(sample) for sample in samples],
    }


def build_cleaned_trajectory_payload(
    *,
    job_id: str,
    samples: list[TrajectoryPoint],
    config: TrajectoryCleanerConfig | None = None,
    status: str = "available",
    detail: str = "cleaned ball trajectory generated",
    court_width: float = 20.0,
    court_length: float = 44.0,
) -> dict[str, Any]:
    config = config or TrajectoryCleanerConfig()
    return {
        "schema_version": "cleaned_ball_trajectory.v1",
        "job_id": job_id,
        "status": status,
        "detail": detail,
        "coordinate_system": coordinate_system_metadata(court_width, court_length),
        "filtering": {
            "outlier_removal": True,
            "interpolation": True,
            "max_interpolation_gap": config.max_interpolation_gap,
            "outlier_step_floor_px": config.outlier_step_floor_px,
        },
        "samples": [sample_to_payload(sample) for sample in samples],
    }


def build_bounce_events_payload(
    *,
    job_id: str,
    events: list[BounceEvent],
    config: BounceDetectorConfig | None = None,
    status: str | None = None,
    detail: str | None = None,
    court_width: float = 20.0,
    court_length: float = 44.0,
) -> dict[str, Any]:
    config = config or BounceDetectorConfig()
    resolved_status = status or ("available" if events else "no_candidates")
    resolved_detail = detail or (
        f"detected {len(events)} bounce event candidates" if events else "bounce detector ran with no candidates"
    )
    return {
        "schema_version": "bounce_events.v1",
        "job_id": job_id,
        "status": resolved_status,
        "detail": resolved_detail,
        "coordinate_system": coordinate_system_metadata(court_width, court_length),
        "detection_method": "trajectory_lag20",
        "config": {
            "fps": config.fps,
            "window_size": config.window_size,
            "center_offset": config.center_offset,
            "min_event_gap_sec": config.min_event_gap_sec,
            "min_score": config.min_score,
            "court_margin_ft": config.court_margin_ft,
        },
        "events": [event_to_payload(event) for event in events],
    }


def write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(payload), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def write_raw_trajectory(path: Path, *, job_id: str, samples: list[BallFrameSample], **kwargs: Any) -> Path:
    return write_json(path, build_raw_trajectory_payload(job_id=job_id, samples=samples, **kwargs))


def write_cleaned_trajectory(path: Path, *, job_id: str, samples: list[TrajectoryPoint], **kwargs: Any) -> Path:
    return write_json(path, build_cleaned_trajectory_payload(job_id=job_id, samples=samples, **kwargs))


def write_bounce_events(path: Path, *, job_id: str, events: list[BounceEvent], **kwargs: Any) -> Path:
    return write_json(path, build_bounce_events_payload(job_id=job_id, events=events, **kwargs))
