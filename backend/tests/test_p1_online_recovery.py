from __future__ import annotations

from app.schemas.tracking import Detection, FrameDetection, PlayerFramePosition
from app.services.dual_camera_sync import FrameTiming, SyncCalibration
from app.vision.multiview.analysis_clock import CanonicalAnalysisClock
from app.vision.multiview.association_global import GlobalPlayerAssociator, JointObservation
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry, ViewBinding
from app.vision.multiview.guidance import CrossViewGuidancePolicy, GuidanceGenerator, invert_homography
from app.vision.multiview.guided_detection import (
    GuidedCandidate,
    guided_candidate_pre_gate,
    merge_base_and_guided,
)
from app.vision.multiview.multiview_joint_run import MultiViewJointRun
from app.vision.multiview.recovery_config import P1OnlineRecoveryConfig
from app.vision.multiview.sync import MultiViewSyncCalibration
from app.vision.player_tracking_engine.multi_object_tracker import MultiObjectTracker
from app.vision.player_tracking_engine.view_tracking_session import ViewFrameResult, ViewTrackingSession

IDENTITY_H = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def test_binding_aging_and_identity_epoch_are_explicit():
    registry = GlobalPlayerRegistry()
    state = registry.ensure("g1")
    state.view_bindings["cam_1"] = ViewBinding(
        view_player_id="Player_3",
        local_identity_epoch=0,
        last_seen_take_timestamp_ms=0.0,
        quality=0.9,
    )
    registry.age_bindings(500.0, weak_after_ms=300.0, lost_after_ms=1000.0)
    assert state.view_bindings["cam_1"].visibility == "weak"
    state.view_bindings["cam_1"].local_identity_epoch = 1
    assert state.view_bindings["cam_1"].local_identity_epoch == 1


def test_guidance_requires_base_donor_in_strict_mode_and_is_bidirectional():
    registry = GlobalPlayerRegistry(anchored_dual_view_count=1, confirm_dual_view_count=1)
    registry.absorb_measurement("g1", 5.0, 8.0, 0.0)
    registry.record_dual_consistent("g1")
    state = registry.get("g1")
    assert state is not None
    state.view_bindings["cam_1"] = ViewBinding(
        view_player_id="Player_1", last_seen_take_timestamp_ms=0.0, quality=0.9,
        visibility="observed", observation_origin="base"
    )
    state.view_bindings["cam_2"] = ViewBinding(
        view_player_id="Player_1", last_seen_take_timestamp_ms=-1000.0, quality=0.9, observation_origin="base"
    )
    generator = GuidanceGenerator(CrossViewGuidancePolicy(donor_max_age_ms=2000.0))
    guidance = generator.generate_for_view(
        registry=registry,
        target_view="cam_2",
        orientation=CourtOrientation.identity,
        inverse_homography=invert_homography(IDENTITY_H),
        now_take_ms=0.0,
        tick=1,
        frame_width=640,
        frame_height=480,
        predictions={"g1": (5.0, 8.0, 1.0)},
        candidate_donor_views=("cam_1",),
        strict_donor=True,
    )
    assert guidance and guidance[0].donor_view == "cam_1"
    assert guidance[0].guidance_id
    state.view_bindings["cam_1"].observation_origin = "guided_roi"
    assert generator.generate_for_view(
        registry=registry,
        target_view="cam_2",
        orientation=CourtOrientation.identity,
        inverse_homography=invert_homography(IDENTITY_H),
        now_take_ms=0.0,
        tick=10,
        frame_width=640,
        frame_height=480,
        predictions={"g1": (5.0, 8.0, 1.0)},
        candidate_donor_views=("cam_1",),
        strict_donor=True,
    ) == []


def test_guidance_cooldown_is_consumed_only_after_roi_invocation():
    registry = GlobalPlayerRegistry(anchored_dual_view_count=1, confirm_dual_view_count=1)
    registry.absorb_measurement("g1", 5.0, 8.0, 0.0)
    registry.record_dual_consistent("g1")
    state = registry.get("g1")
    assert state is not None
    state.view_bindings["cam_1"] = ViewBinding(
        view_player_id="Player_1", last_seen_take_timestamp_ms=0.0, quality=0.9,
        visibility="observed", observation_origin="base"
    )
    state.view_bindings["cam_2"] = ViewBinding(
        view_player_id="Player_1", last_seen_take_timestamp_ms=-1000.0, quality=0.9, observation_origin="base"
    )
    generator = GuidanceGenerator(CrossViewGuidancePolicy(guidance_cooldown_ticks=3, donor_max_age_ms=2000.0))
    kwargs = dict(
        registry=registry,
        target_view="cam_2",
        orientation=CourtOrientation.identity,
        inverse_homography=invert_homography(IDENTITY_H),
        frame_width=640,
        frame_height=480,
        predictions={"g1": (5.0, 8.0, 1.0)},
        candidate_donor_views=("cam_1",),
        strict_donor=True,
    )
    generated = generator.generate_for_view(now_take_ms=0.0, tick=1, **kwargs)
    assert generated
    # No commit: a later snapshot may still generate a guidance attempt.
    assert generator.generate_for_view(now_take_ms=10.0, tick=2, **kwargs)
    generator.commit(generated[0], 2)
    assert generator.generate_for_view(now_take_ms=20.0, tick=3, **kwargs) == []


def test_same_view_bootstrap_never_groups_two_local_players():
    registry = GlobalPlayerRegistry()
    associator = GlobalPlayerAssociator(registry, max_association_distance_ft=3.0)
    observations = [
        JointObservation("cam_1", 0, 0.0, 5.0, 8.0, view_player_id="Player_1", local_identity_epoch=0),
        JointObservation("cam_1", 0, 0.0, 5.2, 8.1, view_player_id="Player_2", local_identity_epoch=0),
    ]
    updates = associator.process_tick(observations, 0.0, {"cam_1": CourtOrientation.identity})
    assert len({update.global_id for update in updates}) == 2


def test_identity_epoch_prevents_old_mapping_continuity():
    registry = GlobalPlayerRegistry()
    associator = GlobalPlayerAssociator(registry, max_association_distance_ft=3.0)
    first = JointObservation("cam_1", 0, 0.0, 5.0, 8.0, view_player_id="Player_3", local_identity_epoch=0)
    first_update = associator.process_tick([first], 0.0, {"cam_1": CourtOrientation.identity})[0]
    registry.absorb_measurement(first_update.global_id, 5.0, 8.0, 0.0)
    second = JointObservation("cam_1", 1, 33.0, 5.1, 8.1, view_player_id="Player_3", local_identity_epoch=1)
    second_update = associator.process_tick([second], 1 / 30.0, {"cam_1": CourtOrientation.identity})[0]
    assert second_update.global_id == first_update.global_id  # geometry may independently preserve the global
    assert ("cam_1", "Player_3", 0) not in associator.mapping
    assert ("cam_1", "Player_3", 1) in associator.mapping


def test_history_mapping_rejects_geometry_infeasible_fallback():
    registry = GlobalPlayerRegistry()
    associator = GlobalPlayerAssociator(registry, max_association_distance_ft=3.0)
    first = JointObservation("cam_1", 0, 0.0, 5.0, 8.0, view_player_id="Player_4")
    first_update = associator.process_tick([first], 0.0, {"cam_1": CourtOrientation.identity})[0]
    registry.absorb_measurement(first_update.global_id, 5.0, 8.0, 0.0)
    far = JointObservation("cam_1", 1, 33.0, 100.0, 100.0, view_player_id="Player_4")
    associator.process_tick([far], 1 / 30.0, {"cam_1": CourtOrientation.identity})
    assert associator.diagnostics["continuity_rejected_geometry"] == 1


def test_base_evidence_wins_and_tracker_assignment_is_exact():
    base = [Detection(bbox=[10, 10, 50, 100], confidence=0.9)]
    guided = GuidedCandidate(
        detection=Detection(bbox=[10, 10, 50, 100], confidence=0.5),
        image_footpoint=(30.0, 100.0),
        canonical_position=(30.0, 100.0),
        residual_ft=0.2,
        accepted=True,
        guidance_id="g1",
    )
    assert len(merge_base_and_guided(base, [guided.detection])) == 1
    update = MultiObjectTracker().update_with_assignments(base)
    assert update.detection_to_track == {0: update.tracks[0].track_id}


def test_guided_pre_gate_uses_target_local_space_for_transforms():
    candidate = guided_candidate_pre_gate(
        Detection(bbox=[100, 100, 120, 200], confidence=0.8),
        homography=IDENTITY_H,
        predicted_local=(110.0, 200.0),
        max_residual_ft=0.1,
        frame_width=640,
        frame_height=480,
    )
    assert candidate.accepted
    assert candidate.local_position == (110.0, 200.0)


class _ControlledRuntime:
    def __init__(self, view_id: str, dropout_view: str, *, decode_failure: bool = False):
        self.view_id = view_id
        self.dropout_view = dropout_view
        self.decode_failure = decode_failure
        self.calls: list[tuple[int, bool]] = []
        self.guidance_seen = []

    def step(self, source_frame_index, timestamp_s, guidance=(), timing_context=None):
        if self.decode_failure and self.view_id == self.dropout_view and source_frame_index == 1 and guidance:
            self.calls.append((source_frame_index, False))
            self.guidance_seen.extend(guidance)
            return None
        is_guided_recovery = self.view_id == self.dropout_view and source_frame_index == 1 and bool(guidance)
        is_dropout = self.view_id == self.dropout_view and source_frame_index == 1 and not guidance
        self.calls.append((source_frame_index, is_guided_recovery))
        self.guidance_seen.extend(guidance)
        if is_dropout:
            return ViewFrameResult(
                frame_index=source_frame_index,
                timestamp=timestamp_s,
                frame_detections=[],
                frame_positions=[],
                render_raw_by_track={},
                player_motion_pixels=None,
            )
        position = PlayerFramePosition(
            frame_index=source_frame_index,
            timestamp=timestamp_s,
            track_id=1,
            bbox=[100, 100, 120, 200],
            image_footpoint=[110, 200],
            court_position=[5.0, 8.0],
            confidence=0.9,
            projection_confidence=0.9,
        )
        detection = FrameDetection(
            frame_index=source_frame_index,
            timestamp_seconds=timestamp_s,
            bbox=position.bbox,
            confidence=0.9,
            track_id="1",
            player_id="Player_1",
            source_width=640,
            source_height=480,
        )
        return ViewFrameResult(
            frame_index=source_frame_index,
            timestamp=timestamp_s,
            frame_detections=[detection],
            frame_positions=[position],
            render_raw_by_track={},
            player_motion_pixels=None,
            local_identity_by_track={1: "Player_1"},
            local_identity_epoch_by_track={1: 0},
            observation_origin_by_track={1: "guided_roi" if is_guided_recovery else "base"},
            guidance_id_by_track={1: guidance[0].guidance_id} if is_guided_recovery else {},
            donor_view_by_track={1: guidance[0].donor_view} if is_guided_recovery else {},
            expected_global_by_track={1: guidance[0].expected_global_player_id} if is_guided_recovery else {},
            pre_gate_residual_by_track={1: 0.0} if is_guided_recovery else {},
            recovery_episode_by_track={1: guidance[0].recovery_episode_id} if is_guided_recovery else {},
        )


def _run_controlled_dropout(
    dropout_view: str,
    *,
    decode_failure: bool = False,
    missing_geometry_view: str | None = None,
):
    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={
            "cam_2": SyncCalibration(
                reference_camera="cam_1",
                camera_id="cam_2",
                offset_seconds=0.0,
                rate=1.0,
                drift_ppm=0.0,
                residual_rms_seconds=0.0,
                anchor_count=1,
                quality="good",
            )
        },
    )
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        secondary_frames=[FrameTiming(i, i / 30.0) for i in range(3)],
        sync=sync,
        secondary_camera_id="cam_2",
    )
    registry = GlobalPlayerRegistry(anchored_dual_view_count=1, confirm_dual_view_count=1)
    runtimes = {
        "cam_1": _ControlledRuntime("cam_1", dropout_view, decode_failure=decode_failure),
        "cam_2": _ControlledRuntime("cam_2", dropout_view, decode_failure=decode_failure),
    }
    run = MultiViewJointRun(
        run_id="p1-controlled",
        capture_take_id="take",
        reference_view_id="cam_1",
        clock=clock,
        runtimes=runtimes,
        registry=registry,
        associator=GlobalPlayerAssociator(registry, max_association_distance_ft=3.0),
        guidance_generator=GuidanceGenerator(CrossViewGuidancePolicy(donor_max_age_ms=1000.0)),
        orientations={"cam_1": CourtOrientation.identity, "cam_2": CourtOrientation.identity},
        inverse_homography=invert_homography(IDENTITY_H),
        frame_width=640,
        frame_height=480,
        recovery_config=P1OnlineRecoveryConfig(binding_weak_after_ms=0.0, donor_max_age_ms=1000.0),
        view_geometry={
            "cam_1": {
                "orientation": CourtOrientation.identity,
                "inverse_homography": invert_homography(IDENTITY_H),
                "frame_width": 640,
                "frame_height": 480,
                "available": missing_geometry_view != "cam_1",
            },
            "cam_2": {
                "orientation": CourtOrientation.identity,
                "inverse_homography": invert_homography(IDENTITY_H),
                "frame_width": 1280,
                "frame_height": 720,
                "available": missing_geometry_view != "cam_2",
            },
        },
    )
    return run.run(reference_frame_count=2, reference_fps=30.0), runtimes


def test_controlled_dropout_cam1_recovers_from_cam2_and_preserves_global_id():
    output, runtimes = _run_controlled_dropout("cam_1")
    assert runtimes["cam_1"].calls[-1][1] is True
    assert output.normalized.samples
    recovered = [
        sample for sample in output.normalized.samples
        if sample.view_observations.get("cam_1", {}).get("detection_origin") == "guided_roi"
    ]
    assert recovered
    assert recovered[-1].view_observations["cam_1"]["donor_view"] == "cam_2"
    assert recovered[-1].global_player_id == "global_player_1"
    assert runtimes["cam_1"].guidance_seen[0].roi[2] <= 640
    assert output.diagnostics["recovery_funnel"]["guided_recovery_success_count"] >= 1


def test_controlled_dropout_cam2_recovers_from_cam1_and_preserves_global_id():
    output, runtimes = _run_controlled_dropout("cam_2")
    assert runtimes["cam_2"].calls[-1][1] is True
    recovered = [
        sample for sample in output.normalized.samples
        if sample.view_observations.get("cam_2", {}).get("detection_origin") == "guided_roi"
    ]
    assert recovered
    assert recovered[-1].view_observations["cam_2"]["donor_view"] == "cam_1"
    assert recovered[-1].global_player_id == "global_player_1"
    assert runtimes["cam_2"].guidance_seen[0].roi[2] <= 1280
    assert output.diagnostics["recovery_funnel"]["guided_recovery_success_count"] >= 1


def _anchored_registry_for_negative_cases(*, target_visibility: str = "lost", donor_origin: str = "base"):
    registry = GlobalPlayerRegistry(anchored_dual_view_count=1, confirm_dual_view_count=1)
    registry.absorb_measurement("g1", 5.0, 8.0, 0.0)
    registry.record_dual_consistent("g1")
    state = registry.get("g1")
    assert state is not None
    state.view_bindings["cam_1"] = ViewBinding(
        view_player_id="Player_1",
        last_seen_take_timestamp_ms=0.0,
        quality=0.9,
        visibility="observed",
        observation_origin=donor_origin,
    )
    state.view_bindings["cam_2"] = ViewBinding(
        view_player_id="Player_1",
        last_seen_take_timestamp_ms=-5000.0,
        quality=0.9,
        visibility=target_visibility,
        observation_origin="base",
    )
    return registry


def test_negative_both_views_lost_and_pre_tick_target_observed_do_not_generate_guidance():
    generator = GuidanceGenerator(CrossViewGuidancePolicy(donor_max_age_ms=2000.0))
    both_lost = _anchored_registry_for_negative_cases(target_visibility="lost")
    both_lost.get("g1").view_bindings["cam_1"].visibility = "lost"  # type: ignore[union-attr]
    assert generator.generate_for_view(
        registry=both_lost,
        target_view="cam_2",
        orientation=CourtOrientation.identity,
        inverse_homography=invert_homography(IDENTITY_H),
        now_take_ms=0.0,
        tick=1,
        frame_width=640,
        frame_height=480,
        predictions={"g1": (5.0, 8.0, 1.0)},
        candidate_donor_views=("cam_1",),
    ) == []

    observed = _anchored_registry_for_negative_cases(target_visibility="observed")
    assert generator.generate_for_view(
        registry=observed,
        target_view="cam_2",
        orientation=CourtOrientation.identity,
        inverse_homography=invert_homography(IDENTITY_H),
        now_take_ms=0.0,
        tick=2,
        frame_width=640,
        frame_height=480,
        predictions={"g1": (5.0, 8.0, 1.0)},
        candidate_donor_views=("cam_1",),
    ) == []


def test_target_frame_unavailable_does_not_consume_cooldown():
    registry = _anchored_registry_for_negative_cases()
    generator = GuidanceGenerator(CrossViewGuidancePolicy(guidance_cooldown_ticks=3, donor_max_age_ms=2000.0))
    kwargs = dict(
        registry=registry,
        target_view="cam_2",
        orientation=CourtOrientation.identity,
        inverse_homography=invert_homography(IDENTITY_H),
        frame_width=640,
        frame_height=480,
        predictions={"g1": (5.0, 8.0, 1.0)},
        candidate_donor_views=("cam_1",),
    )
    assert generator.generate_for_view(target_frame_available=False, now_take_ms=0.0, tick=1, **kwargs) == []
    assert generator.generate_for_view(target_frame_available=True, now_take_ms=0.0, tick=2, **kwargs)


def test_decode_failure_and_missing_geometry_are_structured_skips_without_recovery():
    output, runtimes = _run_controlled_dropout("cam_1", decode_failure=True)
    assert runtimes["cam_1"].guidance_seen
    assert output.diagnostics["counters"]["cam_1:recovery_decode_error"] == 1
    assert not [
        sample for sample in output.normalized.samples
        if sample.view_observations.get("cam_1", {}).get("detection_origin") == "guided_roi"
    ]

    missing, _ = _run_controlled_dropout("cam_1", missing_geometry_view="cam_1")
    assert missing.diagnostics["counters"]["cam_1:recovery_skip_missing_target_geometry"] >= 1


def test_wrong_roi_person_is_rejected_before_tracker_and_lock_reject_stays_out_of_joint():
    rejected = guided_candidate_pre_gate(
        Detection(bbox=[500, 400, 540, 470], confidence=0.8),
        homography=IDENTITY_H,
        predicted_local=(100.0, 100.0),
        max_residual_ft=0.1,
        frame_width=640,
        frame_height=480,
    )
    assert rejected.accepted is False
    assert rejected.reject_reason == "residual_too_large"

    result = ViewFrameResult(
        frame_index=0,
        timestamp=0.0,
        frame_detections=[
            FrameDetection(
                frame_index=0,
                timestamp_seconds=0.0,
                bbox=[10, 10, 20, 30],
                confidence=0.8,
                track_id="1",
                player_id=None,
                source_width=640,
                source_height=480,
            )
        ],
        frame_positions=[
            PlayerFramePosition(
                frame_index=0,
                timestamp=0.0,
                track_id=1,
                bbox=[10, 10, 20, 30],
                image_footpoint=[15, 30],
                court_position=[5.0, 8.0],
                confidence=0.8,
                projection_confidence=0.8,
            )
        ],
        render_raw_by_track={},
        player_motion_pixels=None,
    )
    assert MultiViewJointRun._result_to_observations("cam_1", result, 0.0) == []


def test_guided_base_anchor_and_overlapping_guidance_are_not_promoted():
    # The run's anchor gate is base-only; a guided/base pair remains unanchored.
    class _OriginRuntime:
        def __init__(self, view_id: str, origin: str):
            self.view_id = view_id
            self.origin = origin

        def step(self, source_frame_index, timestamp_s, guidance=(), timing_context=None):
            position = PlayerFramePosition(
                frame_index=source_frame_index,
                timestamp=timestamp_s,
                track_id=1,
                bbox=[100, 100, 120, 200],
                image_footpoint=[110, 200],
                court_position=[5.0, 8.0],
                confidence=0.9,
                projection_confidence=0.9,
            )
            detection = FrameDetection(
                frame_index=source_frame_index,
                timestamp_seconds=timestamp_s,
                bbox=position.bbox,
                confidence=0.9,
                track_id="1",
                player_id="Player_1",
                source_width=640,
                source_height=480,
            )
            return ViewFrameResult(
                frame_index=source_frame_index,
                timestamp=timestamp_s,
                frame_detections=[detection],
                frame_positions=[position],
                render_raw_by_track={},
                player_motion_pixels=None,
                local_identity_by_track={1: "Player_1"},
                observation_origin_by_track={1: self.origin},
            )

    sync = MultiViewSyncCalibration(
        reference_camera="cam_1",
        mappings={"cam_2": SyncCalibration("cam_1", "cam_2", 0.0, 1.0, 0.0, 0.0, 1, "good")},
    )
    clock = CanonicalAnalysisClock(
        reference_view_id="cam_1",
        secondary_view_id="cam_2",
        secondary_frames=[FrameTiming(0, 0.0)],
        sync=sync,
        secondary_camera_id="cam_2",
    )
    registry = GlobalPlayerRegistry(anchored_dual_view_count=1, confirm_dual_view_count=1)
    run = MultiViewJointRun(
        run_id="guided-anchor-negative",
        capture_take_id="take",
        reference_view_id="cam_1",
        clock=clock,
        runtimes={"cam_1": _OriginRuntime("cam_1", "base"), "cam_2": _OriginRuntime("cam_2", "guided_roi")},
        registry=registry,
        associator=GlobalPlayerAssociator(registry, max_association_distance_ft=3.0),
        guidance_generator=GuidanceGenerator(),
        orientations={"cam_1": CourtOrientation.identity, "cam_2": CourtOrientation.identity},
        inverse_homography=IDENTITY_H,
        frame_width=640,
        frame_height=480,
    )
    run.run(reference_frame_count=1, reference_fps=30.0)
    assert all(not state.cross_view_anchored for state in registry.players.values())

    first = GuidedCandidate(
        detection=Detection(bbox=[10, 10, 50, 100], confidence=0.7),
        image_footpoint=(30.0, 100.0),
        canonical_position=(30.0, 100.0),
        residual_ft=0.4,
        accepted=True,
        guidance_id="g1",
    )
    second = GuidedCandidate(
        detection=Detection(bbox=[10, 10, 50, 100], confidence=0.8),
        image_footpoint=(30.0, 100.0),
        canonical_position=(30.0, 100.0),
        residual_ft=0.5,
        accepted=True,
        guidance_id="g2",
    )
    merged, evidence = ViewTrackingSession._merge_detection_evidence([], [first, second])
    assert len(merged) == 1
    assert len(evidence) == 1
    assert second.reject_reason == "duplicate_of_guided"
