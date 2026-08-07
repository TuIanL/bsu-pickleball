"""跨视角关联 —— CrossViewPlayerAssociator：几何匹配、身份分离、迟滞、禁用 side。"""

from __future__ import annotations

from app.vision.multiview.association import CrossViewPlayerAssociator, min_cost_matching
from app.vision.multiview.court_frame import CourtOrientation
from app.vision.multiview.types import ViewObservation


def _obs(view_id, player_id, x, y):
    return ViewObservation(
        view_id=view_id,
        source_frame_index=0,
        timestamp_seconds=0.0,
        local_x_ft=x,
        local_y_ft=y,
        view_player_id=player_id,
    )


IDENTITY = CourtOrientation.identity


def _results_by_ref(associator, ref_obs, sec_obs):
    return {
        a.reference_view_player_id: a
        for a in associator.process_tick(
            reference_view_id="cam_1",
            reference_observations=ref_obs,
            secondary_view_id="cam_2",
            secondary_observations=sec_obs,
            reference_orientation=IDENTITY,
            secondary_orientation=IDENTITY,
        )
    }


def test_min_cost_matching_picks_cheapest_pairs():
    cost = {
        "A": {"X": 0.4, "Y": 18.0, "Z": 27.0},
        "B": {"X": 17.0, "Y": 0.6, "Z": 9.0},
        "C": {"X": 26.0, "Y": 8.0, "Z": 0.3},
    }
    pairs = min_cost_matching(["A", "B", "C"], ["X", "Y", "Z"], cost, max_cost=5.0)
    assert set(pairs) == {("A", "X"), ("B", "Y"), ("C", "Z")}


def test_min_cost_matching_respects_max_cost():
    cost = {"A": {"X": 0.4, "Y": 50.0}, "B": {"X": 50.0, "Y": 0.6}}
    pairs = min_cost_matching(["A", "B"], ["X", "Y"], cost, max_cost=3.0)
    assert set(pairs) == {("A", "X"), ("B", "Y")}

    cost_far = {"A": {"X": 10.0, "Y": 12.0}}
    assert min_cost_matching(["A"], ["X", "Y"], cost_far, max_cost=3.0) == []


def test_same_physical_player_maps_to_same_global():
    associator = CrossViewPlayerAssociator(max_association_distance_ft=3.0)
    ref = [_obs("cam_1", "ref_A", 5.0, 8.0), _obs("cam_1", "ref_B", 15.0, 35.0)]
    sec = [_obs("cam_2", "sec_X", 5.2, 8.1), _obs("cam_2", "sec_Y", 15.1, 35.2)]
    results = _results_by_ref(associator, ref, sec)

    # ref_A 与 sec_X 同一 global；ref_B 与 sec_Y 同一 global。
    assert associator.mapping[("cam_1", "ref_A")] == associator.mapping[("cam_2", "sec_X")]
    assert associator.mapping[("cam_1", "ref_B")] == associator.mapping[("cam_2", "sec_Y")]
    assert associator.mapping[("cam_1", "ref_A")] != associator.mapping[("cam_1", "ref_B")]
    assert results["ref_A"].secondary_view_player_id == "sec_X"
    assert results["ref_B"].secondary_view_player_id == "sec_Y"


def test_cam1_player1_and_cam2_player1_not_equal():
    # 即便两边都叫 "Player_1"，只要 canonical 距离远，就不共享 global。
    associator = CrossViewPlayerAssociator(max_association_distance_ft=3.0)
    ref = [_obs("cam_1", "Player_1", 5.0, 8.0)]
    sec = [_obs("cam_2", "Player_1", 15.0, 35.0)]
    results = associator.process_tick(
        reference_view_id="cam_1",
        reference_observations=ref,
        secondary_view_id="cam_2",
        secondary_observations=sec,
        reference_orientation=IDENTITY,
        secondary_orientation=IDENTITY,
    )
    # 距离远超阈值 → 不跨视角匹配；ref Player_1 保持单视角 global。
    assert results
    cam2_p1 = associator.mapping.get(("cam_2", "Player_1"))
    assert cam2_p1 is None or cam2_p1 != associator.mapping.get(("cam_1", "Player_1"))


def test_association_never_uses_side_field():
    # ViewObservation 不携带 side；关联器签名与实现均无 side 输入。
    import inspect

    source = inspect.getsource(CrossViewPlayerAssociator)
    assert "side" not in source


def test_hysteresis_keeps_existing_then_reassociates():
    associator = CrossViewPlayerAssociator(max_association_distance_ft=3.0, hysteresis_frames=3)
    # Tick 1：正常配对 A↔X。
    ref1 = [_obs("cam_1", "A", 5.0, 8.0)]
    sec1 = [_obs("cam_2", "X", 5.2, 8.1)]
    _results_by_ref(associator, ref1, sec1)
    assert associator.mapping[("cam_1", "A")] == associator.mapping[("cam_2", "X")]

    # Tick 2：X 现在贴近别处，Y 与 A 更近；但证据不足，保持 A↔X。
    ref2 = [_obs("cam_1", "A", 5.0, 8.0)]
    sec2 = [_obs("cam_2", "X", 15.0, 35.0), _obs("cam_2", "Y", 5.3, 8.2)]
    _results_by_ref(associator, ref2, sec2)
    assert associator.mapping[("cam_1", "A")] == associator.mapping[("cam_2", "X")]

    # Tick 4（Y 连续 3 帧为最优）：强证据触发 reassociate A↔Y。
    for _ in range(3):
        _results_by_ref(associator, ref2, sec2)
    assert associator.mapping[("cam_1", "A")] == associator.mapping[("cam_2", "Y")]


def test_reference_observation_always_participates():
    associator = CrossViewPlayerAssociator(max_association_distance_ft=3.0)
    ref = [_obs("cam_1", "A", 5.0, 8.0)]
    sec = []  # 副视角该 tick 无观测
    results = associator.process_tick(
        reference_view_id="cam_1",
        reference_observations=ref,
        secondary_view_id="cam_2",
        secondary_observations=sec,
        reference_orientation=IDENTITY,
        secondary_orientation=IDENTITY,
    )
    assert any(a.reference_view_player_id == "A" for a in results)
