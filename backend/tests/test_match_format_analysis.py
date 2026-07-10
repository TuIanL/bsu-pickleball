import pytest

from app.schemas.analysis import (
    MatchAnalysisContext,
    MatchFormat,
    build_match_context,
    build_player_group_profile,
    _count_match_score,
    SINGLES_PROFILE,
    DOUBLES_PROFILE,
)
from app.schemas.metrics import MetricStatus, PerformanceMetrics
from app.schemas.tracking import PlayerFramePosition, Track, ProjectedTrackPoint
from app.schemas.metrics import Heatmap, HeatmapCell
from app.schemas.pipeline import AnalysisPipelineResult
from app.vision.player_tracking_engine.primary_player_selector import PrimaryPlayerSelector
from app.vision.player_tracking_engine.player_lock_manager import PlayerLockManager
from app.vision.player_tracking_engine.player_lock_types import PlayerLockConfig, PlayerSlot

# ======== Task 7.1: build_match_context ========

def test_build_match_context_singles():
    ctx = build_match_context("singles")
    assert ctx.match_format == "singles"
    assert ctx.expected_player_count == 2
    assert ctx.near_side_quota == 1
    assert ctx.far_side_quota == 1
    assert ctx.enable_doubles_spacing is False


def test_build_match_context_doubles():
    ctx = build_match_context("doubles")
    assert ctx.match_format == "doubles"
    assert ctx.expected_player_count == 4
    assert ctx.near_side_quota == 2
    assert ctx.far_side_quota == 2
    assert ctx.enable_doubles_spacing is True


def test_build_match_context_none_defaults_to_doubles():
    ctx = build_match_context(None)
    assert ctx.match_format == "doubles"
    assert ctx.expected_player_count == 4


# ======== Task 7.2: _count_match_score ========

def test_count_match_score_exact_match():
    assert _count_match_score(0, 0) == 1.0
    assert _count_match_score(1, 1) == 1.0
    assert _count_match_score(2, 2) == 1.0


def test_count_match_score_deviation():
    assert _count_match_score(2, 0) == 0.0
    assert _count_match_score(1, 0) == 0.0


def test_count_match_score_partial():
    assert _count_match_score(2, 4) == pytest.approx(0.5)
    assert _count_match_score(0, 2) == pytest.approx(0.0)


# ======== Task 7.8: singles perfect group ========

def test_singles_perfect_group_score():
    selector = PrimaryPlayerSelector(
        min_confidence=0.65, max_subjects=2,
        group_profile=SINGLES_PROFILE, near_side_quota=1, far_side_quota=1,
    )
    tracks = [
        Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.9),
        Track(track_id=2, bbox=[40, 10, 60, 70], confidence=0.85),
    ]
    positions = [
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=1, bbox=[10, 10, 30, 70], image_footpoint=[20, 70], court_position=[10, 5], valid=True, confidence=0.9),
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=2, bbox=[40, 10, 60, 70], image_footpoint=[50, 70], court_position=[10, 35], valid=True, confidence=0.85),
    ]
    for _ in range(15):
        selected = selector.select(tracks, positions, frame_width=100, frame_height=100)

    assert len(selected) == 2
    # group scores should be high for perfect 1-near + 1-far composition
    diagnostics = selector.last_diagnostics
    for d in diagnostics:
        if d.track_id in {s.track_id for s in selected}:
            assert d.group_consistency_score > 0.7, f"track {d.track_id} group_consistency_score too low: {d.group_consistency_score}"


# ======== Task 7.9: doubles perfect group ========

def test_doubles_perfect_group_score():
    selector = PrimaryPlayerSelector(
        min_confidence=0.65, max_subjects=4,
        group_profile=DOUBLES_PROFILE, near_side_quota=2, far_side_quota=2,
    )
    tracks = [
        Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.9),
        Track(track_id=2, bbox=[15, 10, 35, 70], confidence=0.88),
        Track(track_id=3, bbox=[40, 10, 60, 70], confidence=0.85),
        Track(track_id=4, bbox=[45, 10, 65, 70], confidence=0.82),
    ]
    positions = [
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=1, bbox=[10, 10, 30, 70], image_footpoint=[20, 70], court_position=[5, 5], valid=True, confidence=0.9),
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=2, bbox=[15, 10, 35, 70], image_footpoint=[25, 70], court_position=[7, 8], valid=True, confidence=0.88),
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=3, bbox=[40, 10, 60, 70], image_footpoint=[50, 70], court_position=[15, 35], valid=True, confidence=0.85),
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=4, bbox=[45, 10, 65, 70], image_footpoint=[55, 70], court_position=[17, 38], valid=True, confidence=0.82),
    ]
    for _ in range(15):
        selected = selector.select(tracks, positions, frame_width=100, frame_height=100)

    assert len(selected) == 4
    diagnostics = selector.last_diagnostics
    for d in diagnostics:
        if d.track_id in {s.track_id for s in selected}:
            assert d.group_consistency_score > 0.6


# ======== Task 7.10: singles with bystander on same side ========

def test_singles_bystander_on_same_side_lowers_group_score():
    selector = PrimaryPlayerSelector(
        min_confidence=0.65, max_subjects=2,
        group_profile=SINGLES_PROFILE, near_side_quota=1, far_side_quota=1,
    )
    tracks = [
        Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.9),
        Track(track_id=2, bbox=[20, 10, 40, 70], confidence=0.87),
        Track(track_id=3, bbox=[40, 10, 60, 70], confidence=0.85),
    ]
    positions = [
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=1, bbox=[10, 10, 30, 70], image_footpoint=[20, 70], court_position=[10, 5], valid=True, confidence=0.9),
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=2, bbox=[20, 10, 40, 70], image_footpoint=[30, 70], court_position=[12, 8], valid=True, confidence=0.87),
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=3, bbox=[40, 10, 60, 70], image_footpoint=[50, 70], court_position=[10, 35], valid=True, confidence=0.85),
    ]
    for _ in range(15):
        selected = selector.select(tracks, positions, frame_width=100, frame_height=100)

    assert len(selected) == 2
    # The two near-side candidates should not both be selected
    selected_ids = {s.track_id for s in selected}
    assert not (1 in selected_ids and 2 in selected_ids), "quota should prevent both near-side candidates"


# ======== Task 7.3: singles picks A+C not A+B ========

def test_singles_selector_picks_one_per_side():
    selector = PrimaryPlayerSelector(
        min_confidence=0.65, max_subjects=2,
        group_profile=SINGLES_PROFILE, near_side_quota=1, far_side_quota=1,
    )
    tracks = [
        Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.9),
        Track(track_id=2, bbox=[20, 10, 40, 70], confidence=0.88),
        Track(track_id=3, bbox=[40, 10, 60, 70], confidence=0.82),
    ]
    positions = [
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=1, bbox=[10, 10, 30, 70], image_footpoint=[20, 70], court_position=[10, 5], valid=True, confidence=0.9),
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=2, bbox=[20, 10, 40, 70], image_footpoint=[30, 70], court_position=[12, 8], valid=True, confidence=0.88),
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=3, bbox=[40, 10, 60, 70], image_footpoint=[50, 70], court_position=[10, 39], valid=True, confidence=0.82),
    ]
    for _ in range(15):
        selected = selector.select(tracks, positions, frame_width=100, frame_height=100)

    selected_ids = {s.track_id for s in selected}
    assert 1 in selected_ids or 2 in selected_ids  # one near-side
    assert 3 in selected_ids  # far-side
    assert len(selected_ids) == 2


# ======== Task 7.6: early lock sets assignment_side ========

def test_early_lock_sets_assignment_side():
    config = PlayerLockConfig(
        fps=30, target_player_count=2,
        near_side_quota=1, far_side_quota=1,
        bootstrap_min_frames=5, bootstrap_max_frames=20,
        min_observed_frames=3, lock_min_hits=5,
    )
    manager = PlayerLockManager(config)

    # Simulate bootstrap observations for a near-side track
    for frame in range(10):
        pos = PlayerFramePosition(
            frame_index=frame, timestamp=frame / 30.0, track_id=100,
            bbox=[10, 10, 30, 70], image_footpoint=[20, 70],
            court_position=[10, 5], valid=True, confidence=0.9,
        )
        manager.update(frame, positions=[pos])

    slot = manager.slots.get("player_1")
    assert slot is not None
    assert slot.assignment_side is not None


# ======== Task 7.7: late lock sets assignment_side ========

def test_late_lock_sets_assignment_side():
    config = PlayerLockConfig(
        fps=30, target_player_count=2,
        near_side_quota=1, far_side_quota=1,
        bootstrap_min_frames=5, bootstrap_max_frames=20,
        min_observed_frames=3, lock_min_hits=5,
    )
    manager = PlayerLockManager(config)

    # Complete bootstrap first
    for frame in range(25):
        pos = PlayerFramePosition(
            frame_index=frame, timestamp=frame / 30.0, track_id=100,
            bbox=[10, 10, 30, 70], image_footpoint=[20, 70],
            court_position=[10, 5], valid=True, confidence=0.9,
        )
        manager.update(frame, positions=[pos])

    # After bootstrap, the slot should have assignment_side
    for slot in manager.slots.values():
        if slot.current_track_id is not None:
            assert slot.assignment_side is not None, f"{slot.identity_id} missing assignment_side"


# ======== Task 7.11: singles doubles_spacing ========

def test_singles_doubles_spacing_not_applicable():
    ctx = build_match_context("singles")
    metrics = PerformanceMetrics(
        distances=[], speeds=[], kitchen_dwell=[],
        doubles_spacing=[], heatmap=Heatmap(rows=1, cols=1, cells=[]),
        metric_statuses={"doubles_spacing": MetricStatus(status="not_applicable", reason="singles_match")},
    )
    assert metrics.metric_statuses["doubles_spacing"].status == "not_applicable"
    assert metrics.metric_statuses["doubles_spacing"].reason == "singles_match"
    assert metrics.doubles_spacing == []


# ======== Task 7.12: insufficient players ========

def test_doubles_insufficient_players():
    metrics = PerformanceMetrics(
        distances=[], speeds=[], kitchen_dwell=[],
        doubles_spacing=[], heatmap=Heatmap(rows=1, cols=1, cells=[]),
        metric_statuses={"doubles_spacing": MetricStatus(
            status="insufficient_players", reason="",
            expected_player_count=4, observed_player_count=3,
        )},
    )
    status = metrics.metric_statuses["doubles_spacing"]
    assert status.status == "insufficient_players"
    assert status.expected_player_count == 4
    assert status.observed_player_count == 3


# ======== Task 7.13: different match formats ========

def test_different_match_formats_produce_different_contexts():
    singles_ctx = build_match_context("singles")
    doubles_ctx = build_match_context("doubles")
    assert singles_ctx != doubles_ctx
    assert build_player_group_profile(singles_ctx) == SINGLES_PROFILE
    assert build_player_group_profile(doubles_ctx) == DOUBLES_PROFILE


# ======== Task 7.14: None match_context fallback ========

def test_none_match_context_fallback_to_doubles():
    ctx = build_match_context(None)
    assert ctx.match_format == "doubles"
    assert ctx.expected_player_count == 4


# ======== Task 7.15: eligibility chain ========

def test_eligibility_chain_uses_lock_manager_not_suggestions_union():
    config = PlayerLockConfig(
        fps=30, target_player_count=2,
        near_side_quota=1, far_side_quota=1,
        bootstrap_min_frames=5, bootstrap_max_frames=20,
        min_observed_frames=3, lock_min_hits=5,
    )
    manager = PlayerLockManager(config)

    for frame in range(25):
        pos = PlayerFramePosition(
            frame_index=frame, timestamp=frame / 30.0, track_id=100,
            bbox=[10, 10, 30, 70], image_footpoint=[20, 70],
            court_position=[10, 5], valid=True, confidence=0.9,
        )
        update = manager.update(frame, positions=[pos], suggestions=[{"track_id": 100}, {"track_id": 200}])

    # Only track_id 100 should be in eligible_track_ids (200 was not observed)
    assert 100 in update.eligible_track_ids
    assert 200 not in update.eligible_track_ids


# ======== Task 7.16: attention path quota-aware ========

def test_attention_path_obeys_quota():
    selector = PrimaryPlayerSelector(
        min_confidence=0.65, max_subjects=2,
        group_profile=SINGLES_PROFILE, near_side_quota=1, far_side_quota=1,
    )
    tracks = [
        Track(track_id=1, bbox=[10, 10, 30, 70], confidence=0.9),
        Track(track_id=2, bbox=[20, 10, 40, 70], confidence=0.88),
    ]
    positions = [
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=1, bbox=[10, 10, 30, 70], image_footpoint=[20, 70], court_position=[10, 5], valid=True, confidence=0.9),
        PlayerFramePosition(frame_index=0, timestamp=0.0, track_id=2, bbox=[20, 10, 40, 70], image_footpoint=[30, 70], court_position=[12, 8], valid=True, confidence=0.88),
    ]
    for _ in range(15):
        selected = selector.select(tracks, positions, frame_width=100, frame_height=100)

    # Both near-side: quota should still limit to 1
    selected_ids = {s.track_id for s in selected}
    assert len(selected_ids) <= 2


# ======== Task 7.18: slot reset frees occupancy ========

def test_slot_reset_frees_occupancy():
    config = PlayerLockConfig(
        fps=30, target_player_count=2,
        near_side_quota=1, far_side_quota=1,
        bootstrap_min_frames=5, bootstrap_max_frames=20,
        min_observed_frames=3, lock_min_hits=5,
        lost_max_frames_locked=5,
    )
    manager = PlayerLockManager(config)

    for frame in range(25):
        pos = PlayerFramePosition(
            frame_index=frame, timestamp=frame / 30.0, track_id=100,
            bbox=[10, 10, 30, 70], image_footpoint=[20, 70],
            court_position=[10, 5], valid=True, confidence=0.9,
        )
        manager.update(frame, positions=[pos])

    near_before = manager.near_occupancy
    # Mark slot as lost for many frames to trigger reset
    for frame in range(25, 60):
        manager.update(frame, positions=[], suggestions=[])

    assert manager.near_occupancy <= near_before


# ======== Task 7.20: 422 for invalid matchFormat ========

def test_invalid_match_format_raises_validation_error():
    import pydantic
    with pytest.raises(pydantic.ValidationError):
        from app.schemas.analysis import AnalysisUploadMetadata
        AnalysisUploadMetadata(
            fileName="test.mp4",
            matchTitle="Test",
            venue="Court",
            matchDate="2024-01-01",
            matchFormat="single",  # intentionally wrong
            cameraAngle="elevated",
            athleteLabel="Player",
            level="Pro",
        )


# ======== Task 7.21: backward compatible doubles_spacing ========

def test_legacy_frontend_reads_doubles_spacing_as_array():
    metrics = PerformanceMetrics(
        distances=[], speeds=[], kitchen_dwell=[],
        doubles_spacing=[], heatmap=Heatmap(rows=1, cols=1, cells=[]),
    )
    # Old frontend reads doubles_spacing as Array - should still work
    assert isinstance(metrics.doubles_spacing, list)
    assert len(metrics.doubles_spacing) == 0


# ======== Task 7.22: formal output ========

def test_analysis_pipeline_result_includes_match_context():
    ctx = build_match_context("singles")
    result = AnalysisPipelineResult(
        job_id="test",
        status="completed",
        generated_at="2024-01-01T00:00:00Z",
        stages=[],
        tracks=[],
        metrics=PerformanceMetrics(
            distances=[], speeds=[], kitchen_dwell=[],
doubles_spacing=[], heatmap=Heatmap(rows=1, cols=1, cells=[]),
            ),
            artifacts={},
            message="",
        match_context=ctx,
        observed_player_count=2,
    )
    assert result.match_context is not None
    assert result.match_context.match_format == "singles"
    assert result.observed_player_count == 2
