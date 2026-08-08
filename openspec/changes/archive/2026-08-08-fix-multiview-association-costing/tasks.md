## 1. 修复 rectangular / partial min_cost_matching

- [x] 1.1 将 `min_cost_matching` 重构为 maximum-cardinality feasible matching：从 `k = min(n_ref, n_sec)` 递减枚举所有 `k` 对组合（`combinations(shorter, k) × permutations(longer, k)`），过滤几何不可行 pair（`feasibility_cost > max_feasibility_cost`），记录 ranking cost 最小方案；返回首个可达的最大基数可行方案，无任何可行 pair 时返回 `[]`
- [x] 1.2 统一按 `(ref_k, sec_k)` 从矩阵取值（翻转分支 `a=secondary`、`b=reference` 时取 `[b][a]`），返回格式恒为 `(ref_key, sec_key)`；空集合短路（`not reference_keys or not secondary_keys → return []`）保持不变

## 2. 分离几何可行性门与排序代价

- [x] 2.1 更新 `min_cost_matching` 签名为 `(reference_keys, secondary_keys, ranking_cost, *, feasibility_cost=None, max_feasibility_cost=float("inf"))`：可行性门用 `feasibility_cost` 与 `max_feasibility_cost` 比较，`feasibility_cost=None` 时退化为 `ranking_cost`（保持纯几何调用方兼容）
- [x] 2.2 在 `process_tick` 中分别构造 `feasibility_cost`（纯几何 `_distance`）与 `ranking_cost`（`_pair_cost` 全量），并传入 `min_cost_matching(..., feasibility_cost=..., max_feasibility_cost=self.max_association_distance_ft)`；迁移旧 `max_cost=` 调用

## 3. 修复 prediction cost 为 per-candidate

- [x] 3.1 修改 `_pair_cost`：预测项从 `prediction_bias_ft * _distance(ref_pos, pred)`（行常数）改为 `prediction_bias_ft * _distance(sec_pos, pred)`（per-candidate，使用 secondary candidate 到该 global 预测位置的残差）
- [x] 3.2 确认 prediction 项不影响几何可行性门（可行性只由 `feasibility_cost` 判定），不再把几何合法 pair 推过 `max_feasibility_cost`；确认本 Change 不改 Pipeline 执行顺序、不新增 `predicted_positions` wiring

## 4. 新增测试

- [x] 4.1 新增 rectangular 用例：`2 ref / 1 sec`、`4 ref / 3 sec`、`1 ref / 2 sec`、空集合——断言不抛 `KeyError`、匹配数不超过较小侧、未匹配元素保持单视角
- [x] 4.2 新增 **partial feasible** 用例：`2 ref / 2 sec` 仅 1 对几何可行 → 断言返回 1 对而非 `[]`（保护 maximum-cardinality 语义）
- [x] 4.3 新增 per-candidate prediction 用例：构造两个 secondary candidate，断言 prediction 残差改变排序；断言几何合法但预测残差大的 pair 不被整体剔除
- [x] 4.4 新增 `CrossViewPlayerAssociator.process_tick()` 集成用例：`4 ref / 3 sec`、其中 3 对合法 → 断言不 crash、生成 3 个 dual-view global、漏掉的 reference 保持单视角（reference-only global）
- [x] 4.5 新增"无预测 / 纯几何等数量场景结果不变"回归断言（保护既有行为）；迁移既有 `min_cost_matching` 测试的 `max_cost=` 关键字为 `max_feasibility_cost=`
- [x] 4.6 运行 `backend/tests/test_multiview_association.py` 全部通过

## 5. 回归与验证

- [x] 5.1 运行相关多视角测试套件（`test_multiview_pipeline.py`、`test_multiview_fusion.py`、`test_multiview_fusion_run.py`、`test_multiview_ab_validate.py`）确认无回归
- [x] 5.2 确认不触碰 Pipeline 执行模型、`GlobalTrackFilter` wiring、artifact 版本、任务编排、Executor、Composer，且不改动已归档 P0 文档
