## 1. stale 门控单视图豁免（D1）

- [x] 1.1 `global_state.py` `update_stale_eligibility`：新增"任一 view binding 为 observed/weak 且 last_seen 新鲜（now - last_seen <= stale_last_seen_s）→ 不置 stale"豁免分支；全视图过期才 stale
- [x] 1.2 新增单测 `test_single_view_active_not_stale`：构造仅 cam_1 binding（observed）的 roster 玩家 → `update_stale_eligibility` 后 `association_eligible=True`、`predict_all()` 返回其预测
- [x] 1.3 新增单测 `test_all_views_expired_stale`：cam_1/cam_2 binding 均过期 → `association_eligible=False`（既有 stale 语义不回归）

## 2. fusion 单视图 sample 产出（D2）

- [x] 2.1 验证 `association_global.process_tick` 在 D1 生效后：单视图活跃玩家进入 `predict_all` → `min_cost_matching` 可分配其 cam_1 观测（continuity/普通匹配）
- [x] 2.2 验证 `multiview_joint_run.py` 既有 sample 生成路径（`fused.items()` → `fusion_status=single_view_fallback`）对单视图玩家产出 sample，无需改生成逻辑
- [x] 2.3 新增单测 `test_single_view_fallback_samples`：单视图观测 N 帧 → fused trajectory 产出 N 个 `single_view_fallback` sample 且按 global_player_id 归因
- [x] 2.4 若 2.1/2.2 验证发现分配路径阻塞（如 continuity 几何门拒绝、slot conflict），补修 `association_global.py` 对应分支并加单测

## 3. overlay 单视图渲染（D3）

- [x] 3.1 验证 `fused_overlay_builder` 对 `single_view_fallback` sample 的 `view_observations.reference` 读取：reference available → 分支决策链命中 `base_observed`
- [x] 3.2 若数据源构造处（`multiview_result_composer` / builder）对单视图 sample 读取有缺口，补一行透传
- [x] 3.3 新增单测 `test_overlay_single_view_real_box`：cam_1 base_observed 高置信（conf>=0.5）+ cam_2 binding 缺失 → overlay 产出 `base_observed`/`REAL_BOX`
- [x] 3.4 新增单测 `test_overlay_single_view_recover_after_gap`：单视图玩家断帧数帧后恢复观测 → overlay 重新渲染（不永久隐藏）

## 4. diagnostics 可观测性

- [x] 4.1 `fused_diagnostics` 增加 `single_view_fallback` 按 global_player_id 归因（`single_view_fallback_by_player` 或等价字段）
- [x] 4.2 新增单测 `test_diagnostics_single_view_attribution`：结构性单视图玩家（P2）的 fallback 计数可归因，区别于偶发单视图帧

## 5. 回归与验收

- [x] 5.1 跑 `pytest backend/tests/` 全量回归（重点 multiview 相关测试：`test_multiview_*`、`test_global_roster`、`test_*_overlay*`）
- [x] 5.2 跑 `npm test` 前端回归（确认无 schema 变更不回归）
- [x] 5.3（执行完成，验收结论：D1 未解决 P2 断点，详见下方注记） 用 job-60fcf4de8c 同源 session（sync_20260720_122645_317228）重跑 joint job 验收：fused trajectory 含 global_player_4 连续 sample、fused_diagnostics.single_view_fallback>0 且归因于 P2、overlay P2 全程可见（REAL_BOX 为主）
- [x] 5.4（执行完成，P2 26.2s 后仍缺失，D1 非根因） 验收产物对比：P2 的 metrics（速度/覆盖/停留）不再为空，overlay 27s 处 P2 框可见
