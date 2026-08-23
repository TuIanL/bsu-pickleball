import numpy as np

from app.vision.multiview.association_global import (
    AssociationUpdate,
    GlobalPlayerAssociator,
    JointObservation,
)
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.global_state import GlobalPlayerRegistry
from app.vision.player_tracking_engine.player_appearance import (
    AppearanceExtractorConfig,
    ClothingAppearanceExtractor,
)


IDENTITY = CourtOrientation.identity
EXTRACTOR = ClothingAppearanceExtractor(
    AppearanceExtractorConfig(min_blur_variance=0.0, min_valid_pixels_per_region=20)
)


def _descriptor(bgr: tuple[int, int, int], shift: int = 0):
    frame = np.full((160, 100, 3), 30, dtype=np.uint8)
    for y in range(20, 145):
        delta = 8 if (y // 4) % 2 else 0
        frame[y, 20:80] = np.clip(np.asarray(bgr) + shift + delta, 0, 255)
    return EXTRACTOR.extract(frame, [20, 10, 80, 150], provenance="base")


def _observation(*, view: str, pid: str, x: float, descriptor):
    return JointObservation(
        view_id=view,
        source_frame_index=10,
        take_timestamp_ms=333.0,
        local_x_ft=x,
        local_y_ft=8.0,
        view_player_id=pid,
        track_id=10,
        confidence=0.9,
        appearance_descriptor=descriptor,
    )


def _active_registry() -> GlobalPlayerRegistry:
    registry = GlobalPlayerRegistry()
    for gid, x in (("global_player_1", 5.0), ("global_player_2", 5.1)):
        state = registry.ensure(gid)
        state.roster_status = "confirmed"
        registry.absorb_measurement(gid, x, 8.0, 0.0)
    registry.roster_state = "ROSTER_ACTIVE"
    return registry


def test_appearance_is_soft_cost_after_geometry_gate():
    registry = _active_registry()
    associator = GlobalPlayerAssociator(registry, appearance_cost_weight_ft=1.0)
    red = _descriptor((30, 50, 185))
    blue = _descriptor((185, 50, 30))
    associator._update_appearance_models([
        AssociationUpdate("global_player_1", "cam_1", _observation(view="cam_1", pid="old_1", x=5.0, descriptor=red), 1.0),
        AssociationUpdate("global_player_2", "cam_1", _observation(view="cam_1", pid="old_2", x=5.1, descriptor=blue), 1.0),
    ])
    updates = associator.process_tick(
        [_observation(view="cam_1", pid="new", x=5.05, descriptor=blue)],
        0.1,
        {"cam_1": IDENTITY},
        tick=10,
    )
    assert [update.global_id for update in updates] == ["global_player_2"]
    assert associator.diagnostics["appearance_cost_contributed"] == 1


def test_same_colour_is_non_discriminative_and_falls_back_to_geometry():
    registry = _active_registry()
    associator = GlobalPlayerAssociator(registry)
    black = _descriptor((35, 35, 35))
    associator._update_appearance_models([
        AssociationUpdate("global_player_1", "cam_1", _observation(view="cam_1", pid="old_1", x=5.0, descriptor=black), 1.0),
        AssociationUpdate("global_player_2", "cam_1", _observation(view="cam_1", pid="old_2", x=5.1, descriptor=black), 1.0),
    ])
    updates = associator.process_tick(
        [_observation(view="cam_1", pid="new", x=5.01, descriptor=black)],
        0.1,
        {"cam_1": IDENTITY},
        tick=10,
    )
    assert [update.global_id for update in updates] == ["global_player_1"]
    assert associator.diagnostics["appearance_non_discriminative"] == 1


def test_shadow_mode_records_but_does_not_change_geometry_assignment():
    registry = _active_registry()
    associator = GlobalPlayerAssociator(registry, appearance_cost_weight_ft=1.0, appearance_mode="shadow")
    red = _descriptor((30, 50, 185))
    blue = _descriptor((185, 50, 30))
    associator._update_appearance_models([
        AssociationUpdate("global_player_1", "cam_1", _observation(view="cam_1", pid="old_1", x=5.0, descriptor=red), 1.0),
        AssociationUpdate("global_player_2", "cam_1", _observation(view="cam_1", pid="old_2", x=5.1, descriptor=blue), 1.0),
    ])
    updates = associator.process_tick(
        [_observation(view="cam_1", pid="new", x=5.01, descriptor=blue)],
        0.1,
        {"cam_1": IDENTITY},
        tick=10,
    )
    assert [update.global_id for update in updates] == ["global_player_1"]
    assert associator.diagnostics["appearance_shadow_observations"] == 1
    assert associator.diagnostics.get("appearance_cost_contributed", 0) == 0


def test_cross_camera_profile_is_learned_only_from_confirmed_pairs():
    registry = _active_registry()
    associator = GlobalPlayerAssociator(registry)
    for index in range(12):
        source = _descriptor((160 + index, 45, 25))
        target = _descriptor((160 + index, 45, 25), shift=12)
        associator._update_appearance_models([
            AssociationUpdate("global_player_1", "cam_1", _observation(view="cam_1", pid="p1", x=5.0, descriptor=target), 1.0),
            AssociationUpdate("global_player_1", "cam_2", _observation(view="cam_2", pid="p1", x=5.0, descriptor=source), 1.0),
        ])
    profile = associator.appearance_diagnostics()["profiles"]["cam_2->cam_1"]
    assert profile["sample_count"] == 12
    assert profile["available"] is True
