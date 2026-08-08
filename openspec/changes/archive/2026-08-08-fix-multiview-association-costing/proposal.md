## Why

`CrossViewPlayerAssociator` 存在两个正确性缺陷，但生产影响分层不同：

- **`min_cost_matching` rectangular 崩溃是 P0 production correctness bug**：当 `avail_ref > avail_sec` 且两边都非空时（如双打真实赛况 `2 ref / 1 sec`、`4 ref / 3 sec`），翻转分支访问 `cost[secondary][reference]` 不存在的键 → `KeyError`，当前自动关联路径直接触发。
- **prediction cost 非 per-candidate 是 association primitive correctness bug**：`_pair_cost` 的 prediction 项对同一 reference player 的所有 secondary candidate 是常数，不参与候选排序；**但当前 P0 自动关联路径（`_run_association_pass` → `process_tick`）尚未消费 `predicted_positions`**，因此该 bug 当前不直接影响 P0 production，是函数契约错误，为后续 P1 Global-centric association 做准备。

两者都不属于后续架构演进，应作为独立 hotfix 先修，且**不改动 Pipeline 执行顺序、不新增 prediction wiring**。

## What Changes

- 修复 `min_cost_matching` rectangular（矩形）匹配：翻转分支的索引方向错误（`ref > sec` 时 `KeyError`）。修复后匹配语义升级为 **maximum-cardinality feasible matching + minimum ranking cost**——优先最大化可行匹配数量，再在相同数量下取 ranking cost 最小；`2 ref / 1 sec`、`4 ref / 3 sec`、`1 ref / 2 sec`、部分可行（如 `2 ref / 2 sec` 仅 1 对可行 → 返回 1 对而非 `[]`）、空集合均须稳定运行，未匹配元素保持单视角。
- 修复 prediction cost 为 **per-candidate**：prediction 项改为 `secondary observation → predicted position` 残差参与 ranking cost，而非对同一 reference player 恒定的常数。
- **分离几何可行性门与排序代价**：几何可行性门 `cross_view_distance <= max_feasibility_cost` 为硬门，不受 prediction 影响；ranking cost 只在几何可行的候选之间排序。
- 更新 `min_cost_matching` 签名为 `(reference_keys, secondary_keys, ranking_cost, *, feasibility_cost=None, max_feasibility_cost=inf)`，明确 `ranking_cost` / `feasibility_cost` / `max_feasibility_cost` 命名。
- 新增 rectangular / partial / per-candidate prediction / `process_tick` 集成测试；等数量、纯几何场景行为不变（回归保护）。
- 更新 `multiview-player-association` capability：最大基数可行匹配 + 几何可行性门独立于预测 + per-candidate ranking cost。

## Capabilities

### New Capabilities
<!-- 无新 capability -->

### Modified Capabilities
- `multiview-player-association`: 关联代价契约变化 —— 修复 rectangular 匹配崩溃并升级为 maximum-cardinality feasible matching；prediction 项改为 per-candidate；明确 geometric feasibility gate 与 ranking cost 分离，prediction 不得影响几何可行性判定。

## Impact

- **代码**：`backend/app/vision/multiview/association.py`（`min_cost_matching` 重构为 maximum-cardinality + 签名更新；`_pair_cost` per-candidate）
- **测试**：`backend/tests/test_multiview_association.py`（新增 rectangular / partial / prediction / 集成用例，迁移 `max_cost=` 关键字）
- **调用方**：`process_tick` 是 `min_cost_matching` 唯一生产调用点，更新其调用参数；`run_fusion_pipeline` / `_run_association_pass` 当前自动关联路径**不传** `predicted_positions`，本 Change 不新增 prediction wiring
- **影响分级**：
  - rectangular bug → **P0 production correctness fix**（当前自动双摄关联路径直接受益，消除 crash）
  - prediction cost bug → **association primitive correctness fix**（当前 P0 自动关联路径尚未消费 global prediction，先修对函数契约，为 P1 准备）
- **不涉及**：Pipeline 执行模型、`GlobalTrackFilter` wiring、`ViewTrackingSession` 重构、`joint_tracking_v2`、artifact / orchestration；不触碰已归档 P0 proposal / design / tasks
