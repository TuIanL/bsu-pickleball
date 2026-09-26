from types import SimpleNamespace
import json

import numpy as np
import pytest

from app.vision.multiview.ball_stereo.segment_reconstruction import (
    Observation, _residuals, reconstruct_segment, CubicSpline3D, _b_spline_basis,
)


def test_residual_dimension_is_constant_across_projection_singularity():
    observation = Observation(.5, 0, 0, 0, np.eye(3, 4), True)
    values = []
    for z in (0., 1.):
        controls = np.zeros((4, 3))
        controls[:, 2] = z
        values.append(_residuals(controls.ravel(), 4, [observation], None, False,
                                1., 1., 1., 1., 1., 20., 100., 1., 0., 1.))
    assert values[0].shape == values[1].shape
    assert np.isfinite(values[0]).all()


def test_cached_spline_basis_preserves_evaluation():
    rng = np.random.default_rng(2)
    for n in (4, 6, 8):
        curve = CubicSpline3D(rng.random((n, 3)))
        for t in np.linspace(.01, .99, 50):
            expected = np.array([_b_spline_basis(t, curve.knots, 3, i) for i in range(n)]) @ curve.control
            np.testing.assert_allclose(curve.evaluate(float(t)), expected)


def test_solver_cancellation_is_not_swallowed():
    from app.services.job_orchestration import JobCanceledError
    observations = [Observation(i / 10, i % 2, 1, 2, np.eye(3, 4), True) for i in range(8)]

    def cancel():
        raise JobCanceledError("cancel during optimization")

    with pytest.raises(JobCanceledError):
        reconstruct_segment(segment_id="segment", observations=observations, cancellation_check=cancel)


def test_landing_time_index_matches_scan_with_unsorted_samples():
    from app.services.shot_landings import _player_side_index, hitter_side_at_contact
    rng = np.random.default_rng(3)
    samples = [{"player_id": f"Player_{i % 4}", "timestamp_ms": int(t), "x_ft": 10,
                "y_ft": float(y)} for i, (t, y) in enumerate(zip(rng.integers(0, 10000, 800), rng.uniform(0, 44, 800)))]
    payload = {"samples": samples}
    index = _player_side_index(payload)
    for time in range(0, 10000, 77):
        matches = [(abs(s["timestamp_ms"] - time), s["y_ft"]) for s in samples
                   if s["player_id"] == "Player_1" and abs(s["timestamp_ms"] - time) <= 250]
        expected = ("near" if min(matches)[1] < 22 else "far") if matches else None
        assert hitter_side_at_contact(payload, "Player_1", time, sample_index=index) == expected


def test_playback_projection_preserves_paths_and_avoids_reading_full_source(tmp_path, monkeypatch):
    from app.services.ball_playback_artifact import playback_path, playback_payload
    from app.api import routes_analysis
    source = tmp_path / "trajectory.json"
    raw = {"segments": [{"samples": [{"court_xy": [1, 2]}]}], "events": [],
           "quality_summary": {"error": float("inf")},
           "diagnostics": {"counters": {"ticks": 4}, "candidate_filtering": [1] * 1000}}
    source.write_text(json.dumps(raw))
    compact = playback_path(source)
    payload = playback_payload(raw)
    compact.write_text(json.dumps(payload, allow_nan=False))
    assert payload["segments"] == raw["segments"]
    assert payload["quality_summary"]["error"] is None
    assert "candidate_filtering" not in payload["diagnostics"]
    assert "candidate_filtering" in raw["diagnostics"]
    storage = SimpleNamespace(reconstructed_ball_trajectory_json_path=lambda _: source,
                              resolve_capture_job_root=lambda *args: None)
    monkeypatch.setattr(routes_analysis, "_STORAGE", storage)
    monkeypatch.setattr(routes_analysis, "get_mock_job", lambda _: SimpleNamespace(
        analysisKind="multiview", metadata=SimpleNamespace(capture_take_id=None)))
    response = routes_analysis.read_analysis_artifact("job", "reconstructed-ball-trajectory")
    assert response.path == compact
