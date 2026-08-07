"""Repro: run ball trajectory reconstruction on job-8a492fdbb7 artifacts with a timeout + profile."""
import cProfile
import io
import json
import pstats
import sys
import time
from pathlib import Path

sys.path.insert(0, "backend")

OUT = Path("backend/data/outputs/job-8a492fdbb7")

from app.vision.pickleball_game_analysis.schemas import BounceEvent, TrajectoryPoint  # noqa: E402
from app.vision.pickleball_game_analysis.reconstruction_engine import reconstruct_ball_trajectory  # noqa: E402


def load_cleaned_points():
    data = json.load(open(OUT / "cleaned_ball_trajectory.json"))
    pts = []
    for s in data["samples"]:
        pts.append(
            TrajectoryPoint(
                frame_index=s["frame_index"],
                timestamp_sec=s["timestamp_sec"],
                image_xy=tuple(s["image_xy"]) if s.get("image_xy") else None,
                court_xy=tuple(s["court_xy"]) if s.get("court_xy") else None,
                confidence=s.get("confidence"),
                interpolated=s.get("interpolated", False),
                source=s.get("source", "cleaned"),
                in_bounds=s.get("in_bounds"),
                diagnostics=s.get("diagnostics") or {},
            )
        )
    return pts


def load_bounce_events():
    data = json.load(open(OUT / "bounce_events.json"))
    evs = []
    for e in data["events"]:
        evs.append(
            BounceEvent(
                event_id=e["event_id"],
                frame_index=e["frame_index"],
                timestamp_sec=e["timestamp_sec"],
                image_xy=tuple(e["image_xy"]),
                court_xy=tuple(e["court_xy"]) if e.get("court_xy") else None,
                confidence=e["confidence"],
                detection_method=e.get("detection_method", "trajectory_lag20"),
                diagnostics=e.get("diagnostics") or {},
                rally_id=e.get("rally_id"),
            )
        )
    return evs


def load_serve_events():
    data = json.load(open(OUT / "serve_events.json"))
    return data.get("events") or []


def main():
    cleaned = load_cleaned_points()
    bounces = load_bounce_events()
    serves = load_serve_events()
    homography = None  # try without first; add real one if needed
    calib = json.load(open("backend/data/calibrations/calib-a91d819fc8.json"))
    homography = calib["homography"]["values"]

    print(f"cleaned={len(cleaned)} bounce_events={len(bounces)} serve_events={len(serves)}")
    print("starting reconstruction...")
    t0 = time.time()
    profiler = cProfile.Profile()
    profiler.enable()
    result = reconstruct_ball_trajectory(
        job_id="repro",
        cleaned_points=cleaned,
        bounce_events=bounces,
        serve_events=serves,
        homography=homography,
        fps=60.0,
        player_context=None,
    )
    profiler.disable()
    elapsed = time.time() - t0
    print(f"done in {elapsed:.2f}s")
    print("status:", result.get("status"))
    print("detail:", result.get("detail"))
    print("segments:", len(result.get("segments") or []), "events:", len(result.get("events") or []))
    stream = io.StringIO()
    pstats.Stats(profiler, stream=stream).sort_stats("cumulative").print_stats(25)
    print(stream.getvalue())


if __name__ == "__main__":
    main()
