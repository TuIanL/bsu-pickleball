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
    pairs = min_cost_matching(["A", "B", "C"], ["X", "Y", "Z"], cost, max_feasibility_cost=5.0)
    assert set(pairs) == {("A", "X"), ("B", "Y"), ("C", "Z")}


def test_min_cost_matching_respects_max_feasibility_cost():
    cost = {"A": {"X": 0.4, "Y": 50.0}, "B": {"X": 50.0, "Y": 0.6}}
    pairs = min_cost_matching(["A", "B"], ["X", "Y"], cost, max_feasibility_cost=3.0)
    assert set(pairs) == {("A", "X"), ("B", "Y")}

    cost_far = {"A": {"X": 10.0, "Y": 12.0}}
    assert min_cost_matching(["A"], ["X", "Y"], cost_far, max_feasibility_cost=3.0) == []


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


# ---- rectangular / partial 匹配（fix-multiview-association-costing）----


def test_min_cost_matching_rectangular_ref_more_than_sec():
    # 2 ref / 1 sec：只可能配 1 对，不得 KeyError。
    cost = {"A": {"X": 0.5}, "B": {"X": 3.0}}
    pairs = min_cost_matching(["A", "B"], ["X"], cost, max_feasibility_cost=3.0)
    assert len(pairs) == 1
    assert pairs[0] in {("A", "X"), ("B", "X")}


def test_min_cost_matching_rectangular_4v3():
    cost = {
        "A": {"X": 0.4, "Y": 9.0, "Z": 9.0},
        "B": {"X": 9.0, "Y": 0.6, "Z": 9.0},
        "C": {"X": 9.0, "Y": 9.0, "Z": 0.3},
        "D": {"X": 9.0, "Y": 9.0, "Z": 9.0},
    }
    pairs = min_cost_matching(
        ["A", "B", "C", "D"], ["X", "Y", "Z"], cost, max_feasibility_cost=3.0
    )
    assert len(pairs) == 3
    assert set(pairs) == {("A", "X"), ("B", "Y"), ("C", "Z")}


def test_min_cost_matching_rectangular_sec_more_than_ref():
    # 1 ref / 2 sec：只配 1 对（取 ranking cost 小的）。
    cost = {"A": {"X": 0.5, "Y": 0.4}}
    pairs = min_cost_matching(["A"], ["X", "Y"], cost, max_feasibility_cost=3.0)
    assert pairs == [("A", "Y")]


def test_min_cost_matching_empty_sets():
    assert min_cost_matching([], ["X"], {}) == []
    assert min_cost_matching(["A"], [], {}) == []
    assert min_cost_matching([], [], {}) == []


def test_min_cost_matching_partial_feasible_returns_max_cardinality():
    # 2 ref / 2 sec，仅 A-X 几何可行 → 返回 1 对，而非 []（maximum-cardinality）。
    cost = {"A": {"X": 0.5, "Y": 20.0}, "B": {"X": 20.0, "Y": 20.0}}
    pairs = min_cost_matching(["A", "B"], ["X", "Y"], cost, max_feasibility_cost=3.0)
    assert pairs == [("A", "X")]


def test_min_cost_matching_ranking_vs_feasibility_separated():
    # 几何可行（feasibility=2.0 <= 3.0）但 ranking cost 高（如 prediction 惩罚 7.0）：
    # 旧语义（max_cost 作用于 ranking）会排除该 pair → 返回 []；
    # 新语义（可行性只由 feasibility 判定）→ 仍返回该 pair。
    ranking = {"A": {"X": 7.0}}
    feasibility = {"A": {"X": 2.0}}
    pairs = min_cost_matching(
        ["A"], ["X"], ranking,
        feasibility_cost=feasibility, max_feasibility_cost=3.0,
    )
    assert pairs == [("A", "X")]


def test_pair_cost_prediction_is_per_candidate():
    # prediction 残差为 per-candidate：ref 相同、pred 相同，但 candidate 不同 → cost 不同，
    # 且 per-candidate 项足够大时可翻转排序（Y 的 ranking 低于 X）。
    associator = CrossViewPlayerAssociator(prediction_bias_ft=2.0)
    associator.mapping[("cam_1", "A")] = "g1"
    pred = (20.0, 20.0)
    # X 贴近 ref 但远离 pred；Y 远离 ref 但贴近 pred。
    cost_X = associator._pair_cost((5.0, 8.0), (5.1, 8.1), "A", "cam_1", {"g1": pred})
    cost_Y = associator._pair_cost((5.0, 8.0), (20.1, 20.1), "A", "cam_1", {"g1": pred})
    assert cost_Y < cost_X


def test_pair_cost_ignores_prediction_when_unavailable():
    # 无可用预测时 _pair_cost 退化为纯几何，与既有语义一致。
    associator = CrossViewPlayerAssociator(prediction_bias_ft=2.0)
    associator.mapping[("cam_1", "A")] = "g1"
    cost = associator._pair_cost((5.0, 8.0), (5.1, 8.1), "A", "cam_1", {})
    expected = ((5.0 - 5.1) ** 2 + (8.0 - 8.1) ** 2) ** 0.5
    assert abs(cost - expected) < 1e-9


def test_process_tick_rectangular_4v3_keeps_three_dual_one_ref_only():
    # 集成不变量：视角漏掉一个球员时，其余 3 人照常建 global identity，漏掉的保持单视角。
    associator = CrossViewPlayerAssociator(max_association_distance_ft=3.0)
    ref = [
        _obs("cam_1", "A", 5.0, 8.0),
        _obs("cam_1", "B", 10.0, 15.0),
        _obs("cam_1", "C", 15.0, 22.0),
        _obs("cam_1", "D", 30.0, 40.0),  # 与任何 secondary 都远
    ]
    sec = [
        _obs("cam_2", "X", 5.2, 8.1),
        _obs("cam_2", "Y", 10.1, 15.2),
        _obs("cam_2", "Z", 15.2, 22.1),
    ]
    results = associator.process_tick(
        reference_view_id="cam_1",
        reference_observations=ref,
        secondary_view_id="cam_2",
        secondary_observations=sec,
        reference_orientation=IDENTITY,
        secondary_orientation=IDENTITY,
    )
    dual = [a for a in results if a.secondary_view_player_id is not None]
    single = [a for a in results if a.secondary_view_player_id is None]
    # 3 个 dual-view global + 1 个 reference-only global。
    assert len(dual) == 3
    assert len(single) == 1
    assert single[0].reference_view_player_id == "D"
    assert {a.reference_view_player_id for a in dual} == {"A", "B", "C"}
    assert {a.secondary_view_player_id for a in dual} == {"X", "Y", "Z"}
    # 4 个 reference 各有独立 global；漏掉的 D 不占用任何 secondary binding。
    assert len({associator.mapping[("cam_1", p)] for p in ("A", "B", "C", "D")}) == 4
    d_global = associator.mapping[("cam_1", "D")]
    bound_sec = [k for (view, pid), g in associator.mapping.items() if view == "cam_2" and g == d_global]
    assert bound_sec == []
