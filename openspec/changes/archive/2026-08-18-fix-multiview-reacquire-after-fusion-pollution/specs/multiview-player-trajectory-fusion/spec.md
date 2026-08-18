# multiview-player-trajectory-fusion

## MODIFIED Requirements

### Requirement: 冲突检测

当两路观测在 canonical 空间出现无法合理解释的大幅不一致时，系统 MUST 将状态置为 `conflict`，MUST NOT 平均出不存在的中间位置，并按全局预测或高质量单视角选择输出。

冲突选择 MUST 以 **per-view pre-tick global prediction residual** 为第一仲裁依据：`r_cam1 = dist(cam1, pre_tick_pred)`、`r_cam2 = dist(cam2, pre_tick_pred)`。仲裁决策 MUST 为：仅一路 plausible 选该路；两路 plausible 且 residual 差超 margin 选 residual 更小者；两路 plausible 且 residual 接近时以 intrinsic quality 仲裁；两路都不 plausible 时不产出 measurement（`conflict_no_measurement`）。raw observation confidence MUST NOT 单独决定 conflict winner，仅作为多路 plausible 且 residual 接近时的排序证据之一。

#### Scenario: 冲突不平均

- **WHEN** 两路观测距离超过阈值且无法由运动预测合理解释
- **THEN** 系统 SHALL 置 `fusion_status = conflict`
- **AND** 系统 SHALL NOT 输出两路坐标的算术平均作为真实位置

#### Scenario: 冲突选择

- **WHEN** 冲突已判定
- **THEN** 系统 SHALL 按 pre-tick per-view residual 与 intrinsic quality 选择输出
- **AND** 冲突信息 SHALL 记入 diagnostics（含 selected_source 与两路 residual）

#### Scenario: 冲突无可信测量

- **WHEN** 两路观测均偏离 pre-tick prediction 超过门限
- **THEN** 系统 SHALL NOT 以任一路 measurement 更新 estimator
- **AND** SHALL 本 tick 不产出 fused metric sample（`conflict_no_measurement`；prediction 仅保留 runtime state/debug）

## ADDED Requirements

### Requirement: 冲突仲裁输入透传

joint 运行实体在调用 `fuse_assignments()` 时 MUST 传入 tick barrier 之前冻结的 pre-tick prediction（含 position 与 uncertainty），供 conflict 仲裁使用。仲裁计算 MUST 显式求 `r_cam1`/`r_cam2`，MUST NOT 依赖 `pair_consistency()` 的单一 `residual_to_prediction_ft`（该字段语义为两路最小 residual，非 per-view）。

#### Scenario: 单视图不触发 conflict

- **WHEN** 某 global 仅单视角观测（另一视角缺失/未分配）
- **THEN** 系统 SHALL 正常产出 measurement（`single_view_fallback`）
- **AND** SHALL NOT 因单视图进入 conflict 仲裁路径
