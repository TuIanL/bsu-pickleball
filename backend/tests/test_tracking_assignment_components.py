from functools import lru_cache
import random

from app.vision.player_tracking_engine.multi_object_tracker import _maximum_cardinality_min_cost_assignment


def old_solver(ids, edges):
    @lru_cache(None)
    def solve(i, mask):
        if i == len(ids):
            return 0, 0., ()
        best = solve(i + 1, mask)
        for detection, cost in edges.get(i, []):
            if mask & (1 << detection):
                continue
            count, rest, pairs = solve(i + 1, mask | (1 << detection))
            candidate = count + 1, cost + rest, ((ids[i], detection),) + pairs
            if candidate[0] > best[0] or (candidate[0] == best[0] and (
                candidate[1] < best[1] - 1e-12 or
                (abs(candidate[1] - best[1]) <= 1e-12 and candidate[2] < best[2])
            )):
                best = candidate
        return best
    return list(solve(0, 0)[2])


def test_component_assignment_matches_prior_exact_solver_including_ties():
    rng = random.Random(30)
    for _ in range(300):
        ids = sorted(rng.sample(range(100), 7))
        edges = {i: [(j, rng.choice([0., .1, .5, 1.])) for j in range(6) if rng.random() < .25]
                 for i in range(len(ids))}
        assert _maximum_cardinality_min_cost_assignment(ids, edges) == old_solver(ids, edges)


def test_independent_actors_do_not_create_exponential_global_assignment():
    ids = list(range(200))
    edges = {i: [(i // 2 * 2, .1), (i // 2 * 2 + 1, .1)] for i in ids}
    assigned = _maximum_cardinality_min_cost_assignment(ids, edges)
    assert assigned == [(i, i) for i in ids]
