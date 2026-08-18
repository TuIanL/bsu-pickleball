# fix-multiview-reacquire-after-fusion-pollution

## Why

男双双摄 joint 任务中 `global_player_4`（cam_1/Player_2）在 26.2s 永久消失：cam_2 周期性输出空间离群观测（[7.4,33.6] vs 真实 [19.9,-3.1]，差 40ft），冲突仲裁按 raw confidence 选择了 cam_2（0.81 > 0.31），错误 measurement 污染 Global Kalman；恢复后的正确观测与污染预测相距 ~14ft，超过 8ft reacquire 硬门，且 historical binding 复用同一硬门被拒 → roster 满 → unresolved → 永久丢失。这是连续双故障（conflict 仲裁错误 → estimator 污染 → reacquire 硬门拒绝），与 stale 机制无关（D1 已修复 stale 但未解决此断点）。

## What Changes

- **D1 prediction-aware conflict arbitration**：`fuse_assignments()` 冲突时**显式计算** `r_cam1 = dist(cam1, pre_tick_pred)` 与 `r_cam2 = dist(cam2, pre_tick_pred)`，以 per-view prediction residual 仲裁，raw confidence 仅作证据之一。不依赖 `pair_consistency()` 的单一 `residual_to_prediction_ft`（其语义是两路最小值，非 per-view）。
- **D2 global measurement innovation guard（结构化返回）**：`GlobalPlayerRegistry.absorb_measurement()` 前置 innovation guard，返回 `MeasurementUpdateResult(accepted/rejected, x, y, innovation_ft, gate_ft, reason)`。**rejected 时 SHALL NOT 刷新 `last_seen_s`、SHALL NOT 增加 `roster_confirm_ticks`、SHALL NOT 更新 position/velocity**——reject 是"没看见"，不是"看见但不用"。
- **D3 trusted historical-identity reanchor（决策与执行分离）**：associator 只产生关联决策 `AssociationUpdate(..., reanchor=True)`，**SHALL NOT 在 `process_tick()` 内直接 reseed/absorb**；`MultiViewJointRun` 在 fusion 后对 reanchor update 执行 `registry.reseed(...)`（position=观测、velocity=0、covariance=初始值）——保持 JointRun 为唯一 state update owner。
- **D4 可诊断事件分层**：associator `diagnostics` 保持纯计数；新增 `last_tick_fusion_decisions` 承载结构化明细（cam1_xy/cam2_xy/inter_view_distance/r_cam1/r_cam2/intrinsic/gate/selected_source）；`artifact.py` 仅汇总计数与少量归因，不重推导 runtime 逻辑。
- **修复 spec/实现偏差**：`multiview-player-trajectory-fusion` 冲突检测需求已要求"按全局预测或高质量单视角选择输出"，实现需对齐。

## Capabilities

### New Capabilities

（无——conflict arbitration 属于 `multiview-player-trajectory-fusion` 既有职责，不另建 capability，避免双 source of truth。）

### Modified Capabilities

- `multiview-player-trajectory-fusion`：冲突检测需求对齐 D1（冲突选择以 per-view pre-tick prediction residual 主导，raw confidence 不得单独决定 winner；`both implausible → conflict_no_measurement` 不产出 fused sample）。
- `multiview-global-player-state`：新增 innovation guard 需求（D2，`MeasurementUpdateResult` 语义：reject 不刷新任何真实测量状态）与污染标记生命周期（recent event + TTL/clear condition，非永久 boolean）。
- `multiview-player-association`：新增 trusted historical-identity reanchor 需求（D3，决策与执行分离；普通/continuity/historical gate 语义不变）。

## Impact

- `backend/app/vision/multiview/association_global.py`：`fuse_assignments()` 由 static 改 instance method 并接收 pre-tick predictions（D1）；显式 r1/r2 仲裁；reanchor 决策（D3）；`last_tick_fusion_decisions` 结构化明细（D4）。
- `backend/app/vision/multiview/global_state.py`：`absorb_measurement()` 返回 `MeasurementUpdateResult`；innovation guard；污染标记生命周期（D2）。
- `backend/app/vision/multiview/multiview_joint_run.py`：`fuse_assignments()` 调用处传 pre-tick prediction；reanchor update 的 reseed 执行（D3）。
- `backend/app/vision/multiview/quality.py`：不改（`pair_consistency` 仅保留 inter-view/conflict 检测职责；per-view residual 由 D1 显式计算）。
- 相关 spec delta：`multiview-player-trajectory-fusion`、`multiview-global-player-state`、`multiview-player-association`。
- 回归防护：5 个最小单测（conflict poison / innovation guard / reanchor / ambiguous reanchor / D1 regression）+ 真实 60s acceptance（重点窗口 24–30s，验收指标见 tasks 5.4/5.5）。
