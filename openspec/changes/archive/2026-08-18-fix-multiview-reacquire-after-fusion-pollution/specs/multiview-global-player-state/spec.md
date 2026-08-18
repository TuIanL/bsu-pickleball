# multiview-global-player-state

## ADDED Requirements

### Requirement: 测量更新结构化结果（MeasurementUpdateResult）

`GlobalPlayerRegistry.absorb_measurement()` MUST 返回结构化 `MeasurementUpdateResult(accepted, x_ft, y_ft, innovation_ft, gate_ft, reason)`。**accepted=False（measurement 被 innovation guard 拒绝）时 MUST NOT 刷新任何真实测量状态**：SHALL NOT 更新 position/velocity/uncertainty，SHALL NOT 刷新 `last_seen_s`，SHALL NOT 增加 `roster_confirm_ticks`。拒绝的语义是"这一帧没有真实看见该 player"，而非"看见但未采用"。

#### Scenario: 拒绝不刷新可见性

- **WHEN** 某 measurement 被 innovation guard 拒绝
- **THEN** 系统 SHALL 保持 `last_seen_s` 不变（stale eligibility 正常推进）
- **AND** SHALL NOT 增加 `roster_confirm_ticks`
- **AND** SHALL 返回 `accepted=False` 与 reason

### Requirement: 测量创新守卫（measurement innovation guard）

`GlobalPlayerRegistry.absorb_measurement()` 在调用 estimator update 前 MUST 计算 innovation residual（`r = dist(measurement, predicted_position)`），并与独立配置的 guard 门比较：`gate = max(innovation_floor_ft, innovation_uncertainty_k × prediction_uncertainty_ft)`（`innovation_floor_ft` 独立于 association 的 `max_reacquire_gate_ft`，首版均默认 8.0，但架构上不绑定）。当 `r > gate` 时 MUST 拒绝该 measurement（见 `MeasurementUpdateResult` 语义）。`GlobalMotionEstimator` 本身 SHALL 保持单纯（predict→Kalman update→写 state），guard 策略 SHALL 位于 Registry 层。

#### Scenario: 灾难性跳变被拒

- **WHEN** 某 measurement 距预测位置 15ft 且预测 uncertainty 仅 ~1ft（远超 floor 与缩放门）
- **THEN** 系统 SHALL 拒绝该 measurement
- **AND** estimator 位置/速度 SHALL 保持不变
- **AND** SHALL 记录 `measurement_innovation_rejected`

#### Scenario: 合法大机动不被误拒

- **WHEN** measurement 距预测 5ft 且预测 uncertainty 已随缺观测增长（`innovation_uncertainty_k × uncertainty` 覆盖该距离）
- **THEN** 系统 SHALL 正常吸收该 measurement
- **AND** SHALL NOT 误报 innovation rejection

### Requirement: 污染风险标记生命周期

global 的污染风险标记 MUST 为**有时效的事件状态**而非永久 boolean：`last_state_risk_tick: int | None` + `state_risk_reason: innovation_rejected | conflict_no_measurement | None`。MUST 支持以下清除条件（任一）：连续 M 帧（M=5）clean accepted measurement（无 reject / 无 conflict 未选中）；`reanchor_succeeded`；`last_state_risk_tick` 距今超过 `reanchor_risk_window_ticks`（默认 90）。

#### Scenario: 风险标记驱动 reanchor

- **WHEN** `global_player_4` 近期发生 innovation rejection 或 conflict 未选中（`last_state_risk_tick` 在窗口内）
- **THEN** 其风险标记 SHALL 对 reanchor 评估可见
- **AND** 窗口外或已清除的 global SHALL NOT 进入 reanchor 路径（防误锚）
