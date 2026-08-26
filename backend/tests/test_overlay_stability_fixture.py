from __future__ import annotations

import json
from pathlib import Path


FIXTURE = Path(__file__).parent / "fixtures" / "overlay_stability" / "stabilize-overlays-and-ball-trajectories.v1.json"


def test_stability_fixture_captures_reference_view_and_regression_windows():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert payload["reference_view_id"] == "cam_1"
    assert payload["processed_tick"] == {
        "source_fps": 60,
        "frame_stride": 2,
        "window_start_sec": 0.0,
        "window_end_sec": 60.0,
    }
    assert payload["player_window"]["players"] == ["Player_2", "Player_4"]
    assert payload["trajectory_boundary"]["left_primary_view_id"] == "cam_2"
    assert payload["trajectory_boundary"]["right_primary_view_id"] == "cam_1"
