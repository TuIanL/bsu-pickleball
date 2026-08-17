## Why

job-60fcf4de8c 双摄分析（男双 sync_20260720_122645_317228）复现：截图 27s 起 P2 长时间消失，仅剩 P1/P3/P4 三个框。数据定位（tracking_overlay / fused_player_overlay / fused_player_trajectory 三方对账）证实 **P2 的 cam_1 检测自 19.5s 起连续且 90% 帧 conf≥0.5，并非检测丢失**，而是融合层结构性丢弃：`global_player_4 (Player_2)` 仅有 cam_1 binding（visibility=lost、cam_2 无 binding），fusion 不为其产出任何 measurement（fused trajectory 只含 global_player_1/2/3），overlay 在 26.2s 断帧窗口后因无融合证据供给而永久不渲染。上一 change（fix-multiview-player-identity / fix-multiview-cam1-bootstrap-4player）解决了 bootstrap 漏锁第 4 人，但未打通"仅单视图 binding 的 roster 球员仍需参与融合与展示"这条路径。

## What Changes

- **后端：fusion 对单视图 binding 的 roster 球员强制产出 `single_view_fallback` measurement**。`GlobalPlayerRegistry.predict_all()` 的 stale 门控对"仅有单视图 binding 且该视图持续观测"的 roster 球员豁免（或提供 single-view continuity 路径），使 `global_player_N` 进入 `fused` dict 并在每 canonical tick 产出 `fusion_status=single_view_fallback` 样本（现有 `fusion_status_counts.single_view_fallback=2` 反映该路径形同虚设）。同步保证 `metric_eligible` 语义正确（单视图真实观测可进指标）。
- **后端：overlay 数据源包含单视图 fusion 样本**。`multiview_result_composer` / fused overlay builder 的输入从"final fused trajectory + roster map"扩展为含 single_view_fallback 样本后，P2 类玩家在 cam_1 单边观测时按 `base_observed`（REAL_BOX）渲染，不再依赖 cross_view donor。
- **后端：单视图玩家的 stale/recovery 语义澄清**。`update_stale_eligibility` 对仅有单视图 binding 且该视图持续可观测的玩家 SHALL NOT 仅因跨视图缺失而置 `association_eligible=False`；`lost_after_ms`/`weak_after_ms` 的 binding 判定与该玩家的融合/展示资格解耦（binding lost ≠ 融合资格 lost）。
- **回归防护**：新增单视图 binding 玩家的融合连续性单测（单视图观测 N 帧 → fused trajectory 产出 single_view_fallback 样本序列）、overlay 渲染单测（cam_1 base_observed 高置信 → overlay 有 REAL_BOX，即使 cam_2 binding 缺失）、fused_diagnostics 单测（`single_view_fallback` 计数>0 且按 player 可归因）。

## Capabilities

### New Capabilities

- `multiview-single-view-continuity`: 覆盖"仅单视图 binding 的 roster 球员在融合与展示层的连续性"——single_view_fallback 强制产出、stale 门控豁免、binding lost 与融合资格解耦、overlay 单视图渲染、回归防护。

### Modified Capabilities

- `multiview-player-trajectory-fusion`: 位置融合状态机的 `single_view_fallback` 场景 SHALL 覆盖"仅单视图 binding 的 roster 玩家"（现 spec 已有场景定义但实现未生效），补充"每 canonical tick 强制产出"与 metric_eligible 语义。
- `multiview-fused-player-overlay`: Evidence 分支决策链 SHALL 明确"reference view 单边 strong observation 即可渲染 REAL_BOX，即使该玩家无 cross-view binding"；现 spec 依赖 fused trajectory 证据供给，未覆盖单视图玩家的持续渲染。
- `multiview-global-player-roster`: stale 判定 SHALL 区分"单视图持续观测"与"跨视图缺失"——仅跨视图缺失 SHALL NOT 使单视图活跃玩家退出普通关联。
- `multiview-global-player-state`: "缺 view binding 时仍以既有 binding 维持全局状态"的既有 requirement SHALL 扩展为可观测约束（关联资格不因此丢失）。

## Impact

- **后端文件**：
  - `backend/app/vision/multiview/global_state.py`（`update_stale_eligibility`、`predict_all` 单视图豁免）
  - `backend/app/vision/multiview/association_global.py`（`fuse_assignments` 单视图 assignment 放行）
  - `backend/app/vision/multiview/multiview_joint_run.py`（samples 产出路径）
  - `backend/app/vision/multiview/fused_overlay_builder.py`（overlay 数据源 + 渲染判定）
  - `backend/app/services/multiview_result_composer.py`（composer 数据源透传）
- **测试**：新增/修改 `backend/tests/`（fusion 单视图连续性、overlay 单视图渲染、fused_diagnostics 计数、stale 豁免）。
- **规格**：新增 `multiview-single-view-continuity` spec；修改 `multiview-player-trajectory-fusion`、`multiview-fused-player-overlay`、`multiview-global-player-roster`、`multiview-global-player-state` 四个 spec 的 delta。
- **风险**：单视图 sample 强制产出可能让"双视图确认"质量语义弱化（单视图观测质量低于 dual）——以 `fusion_status=single_view_fallback` 明确标注、`metric_eligible` 可选门控（默认允许，配置可关）兜底；stale 豁免可能让短暂离场玩家占据关联预算——以"该视图持续观测（last_seen 新鲜）"为豁免前提，离场即失去豁免。
