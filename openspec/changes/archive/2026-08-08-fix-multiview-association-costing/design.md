## Context

`CrossViewPlayerAssociator`（`backend/app/vision/multiview/association.py`）是 P0 多视角融合的身份关联核心。当前实现存在两个正确性缺陷，但**生产影响分层不同**：

1. **`min_cost_matching` 矩形匹配崩溃（P0 production correctness bug）**。当 `reference_keys > secondary_keys`（如 `2 ref / 1 sec`、`4 ref / 3 sec`）时，翻转分支 `value = cost[a][b] if flip else cost[a][b]` 两个分支完全相同；翻转后 `a` 是 secondary key，而 `cost` 以 `cost[ref][sec]` 键控 → `cost[secondary]` 直接 `KeyError`。`Cam1 见 4 人 / Cam2 见 3 人` 是双打真实赛况，**当前自动关联路径直接触发**。

2. **prediction cost 不是 per-candidate（association primitive correctness bug）**。`_pair_cost` 的 `base += prediction_bias_ft * _distance(ref_pos, pred)` 对同一 reference player 的所有 secondary candidate 是常数，不参与 candidate 排序。**但当前 P0 自动关联路径（`_run_association_pass` → `process_tick`）并不传 `predicted_positions`**，因此该 bug 当前不直接影响 P0 production；它是 primitive 契约错误，修复为后续 P1 Global-centric association 准备。

本 Change 是独立 hotfix：修 rectangular / partial 匹配、把几何可行性与排序代价分离、prediction 改 per-candidate。**不**改动 Pipeline 执行顺序、不新增 prediction wiring、不触碰后续架构演进。

## Goals / Non-Goals

**Goals:**

- 修复 `min_cost_matching` 在 `ref > sec` 时的崩溃，矩形匹配稳定运行。
- 匹配语义升级为 **maximum-cardinality feasible matching + minimum ranking cost**：优先最大化可行匹配数量，再在相同数量下取 ranking cost 最小（不要求较小侧全配）。
- 分离几何可行性门与排序代价：prediction 不得影响"该 pair 几何上是否合法"的硬门。
- prediction 项改为 per-candidate，真正参与 candidate 排序。
- 新增 rectangular / partial / per-candidate prediction / process_tick 集成测试；等数量、纯几何场景行为不变（回归保护）。

**Non-Goals:**

- 不改变 `run_fusion_pipeline` / `_run_association_pass` 执行顺序，不新增 `predicted_positions` wiring。
- 不引入 `ViewTrackingSession` 重构或 joint tracking 算法（属后续 Change）。
- 不修改 artifact 版本、任务编排、Executor、Composer。
- 不改动已归档的 P0 proposal / design / tasks。
- 不引入新外部依赖（≤6 元素直接枚举，不用 Hungarian / scipy）。

## Decisions

### D1: 修复翻转分支的索引方向

`cost` 矩阵恒以 `cost[reference][secondary]` 键控。翻转分支（`ref > sec`）中 `shorter=secondary`、`longer=reference`，zip 后 `a=secondary`、`b=reference`，正确访问应为 `cost[b][a]`。统一按 `(ref_k, sec_k)` 从 `feasibility` / `ranking_cost` 取值，返回格式恒为 `(ref_key, sec_key)`。

**替代方案**：翻转后重建 cost 矩阵为 `[sec][ref]` 键控。否决——引入矩阵拷贝与双重键控，增加出错面，且与调用方 `cost[ref][sec]` 的既有约定割裂。

### D2: maximum-cardinality feasible matching + minimum ranking cost

当前 `permutations(longer, len(shorter))` 要求较小侧**全部**参加匹配：只要有一个 pair 几何不可行，整个 permutation 判失败，最终可能返回 `[]`，与"未匹配元素保持单视角"语义矛盾。例如 `2 ref / 2 sec` 中仅 `A-X` 可行（0.5 ft），其余 >20 ft，正确结果是 `[(A, X)]`，而非 `[]`。

修复为按基数从大到小枚举：

```text
for k = min(n_ref, n_sec) ... 1:
    枚举所有 k 对组合（combinations(shorter, k) × permutations(longer, k)）
    过滤几何不可行 pair（feasibility[ref][sec] > max_feasibility_cost）
    记录 ranking cost 最小方案

    if 找到任一可行方案:
        return 该最小 cost 方案
return []    # 无任何可行 pair
```

- **优先最大化匹配数量**：能配 3 对 → 不接受只配 2 对。
- **相同数量下取 ranking cost 最小**：同基数解之间比较 `ranking_cost` 总和。
- 复杂度：≤6 元素直接枚举（最坏 6×6 约 ~10⁴ 组合），无需 Hungarian / scipy。

**替代方案**：调用方先按几何阈值预过滤候选再调用最小代价匹配。否决——把"可行性"逻辑散落到调用方，且无法保证 maximum-cardinality（贪心过滤会牺牲匹配数）。

### D3: 分离几何可行性门与排序代价（签名）

```python
def min_cost_matching(
    reference_keys,
    secondary_keys,
    ranking_cost,              # 排序代价：几何 + per-candidate prediction
    *,
    feasibility_cost=None,     # 几何距离矩阵；缺省 = ranking_cost（保持纯几何调用方兼容）
    max_feasibility_cost=float("inf"),
) -> list[tuple[str, str]]:
```

- 可行性门：`feasibility_cost[ref][sec] > max_feasibility_cost` → 该 pair 不可行，剔除。
- 排序：只在可行候选之间，按 `ranking_cost[ref][sec]` 求和取最小。
- 明确区分 `ranking_cost` / `feasibility_cost` / `max_feasibility_cost` 三个命名，避免旧的 `max_cost` 与 `cost` 语义混淆（旧 `max_cost` 实际是 feasibility threshold，但名字误导）。

调用方（`process_tick`）分别构造：
- `feasibility_cost[ref][sec] = _distance(ref_pos[ref], sec_pos[sec])`（纯几何）
- `ranking_cost[ref][sec] = _pair_cost(...)`（几何 + per-candidate prediction）

现有 `min_cost_matching` 测试调用 `max_cost=` 关键字：迁移为 `max_feasibility_cost=`（本 Change 拥有这些测试，一并更新）。

### D4: prediction 项 per-candidate

`_pair_cost` 的预测项从 `distance(ref_pos, pred)`（对同 ref player 恒定的行常数）改为 `distance(sec_pos, pred)`（per-candidate）：

```python
base = _distance(ref_pos, sec_pos)                        # 几何项
pred = predicted_positions.get(existing_global) if existing_global is not None else None
if pred is not None:
    base += prediction_bias_ft * _distance(sec_pos, pred)  # per-candidate 预测残差
```

`distance(sec_pos, pred)` 随 candidate 变化，真正影响排序。

### D5: reference→prediction residual 的省略理由（修正 D4 旧论断）

旧论断"reference residual 是行常数，对 argmin 无贡献，故省略"**仅在 full assignment（方阵、所有 reference 必配）下成立**。在 rectangular / partial matching 中，系统需要决定"哪个 reference 保持未匹配"，此时不同 reference 的 row constant 不同，会实际影响"留下谁"。

本 hotfix **仍省略** reference→prediction residual，但理由改为：

> P0 hotfix 仅修复 secondary candidate 排序语义；reference→prediction residual 在 full assignment 中为 row constant，在 rectangular / partial assignment 中可能影响 unmatched-reference selection。为控制本 Change 行为范围暂不引入，后续 Global-centric association 再统一设计。

**替代方案**：本次一并引入 reference→prediction residual。否决——放大 Change 行为范围，且 P0 自动关联路径尚未消费 prediction，缺乏验证信号。

## Risks / Trade-offs

- **[Risk] maximum-cardinality 改变部分匹配场景的返回数量**（过去返回 `[]`，现在返回 1+ 对）→ 这是修复的预期效果而非回归。缓解：新增 `2 ref / 2 sec 仅 1 对可行 → 返回 1 对` 测试 + `process_tick` 集成测试（`4 ref / 3 sec` 3 对可行 → 3 个 dual-view + 1 个 reference-only），固化产品不变量。
- **[Risk] per-candidate prediction 改变等数量场景的排序结果**（当既有 global 有预测时）→ 缓解：`prediction_bias_ft` 默认值不变；新增"无预测 / 纯几何等数量场景结果不变"回归断言；`_run_association_pass` 不传 prediction，P0 自动路径不受影响。
- **[Risk] `max_cost` → `max_feasibility_cost` 关键字改名破坏既有测试调用** → 本 Change 拥有这些测试，任务中显式迁移调用；生产唯一调用点 `process_tick` 一并更新。
- **[Risk] 枚举规模**：`ref=6/sec=5` 时最大基数 k=5 → `C(6,5)·P(6,5)=720`；最坏全枚举 ~10⁴ 组合，在既有 ≤6 元素暴力枚举边界内，性能无虞。

## Migration Plan

- 单一提交，修改 `backend/app/vision/multiview/association.py` + `backend/tests/test_multiview_association.py`。
- 无数据迁移、无 schema 变化、无外部依赖、不改 Pipeline 执行顺序。
- 回滚 = revert 该提交；既有产物不受影响（本 Change 不触产物格式）。

## Open Questions

无阻塞项。reference→prediction residual（D5）是否在 P1 Global-centric association 中引入，留待该 Change 设计。
