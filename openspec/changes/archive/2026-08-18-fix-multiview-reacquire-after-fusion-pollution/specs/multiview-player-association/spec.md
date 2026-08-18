# multiview-player-association

## ADDED Requirements

### Requirement: 可信历史 identity reanchor（决策与执行分离）

当普通匹配、continuity、weak historical binding 均因 geometry hard gate 拒绝（如被污染的 prediction 距恢复观测过远），且同时满足以下**全部**条件时，associator MUST 产生 reanchor 关联决策（`AssociationUpdate(..., reanchor=True)`）：

1. 观测 `(view_id, view_player_id)` 存在弱历史绑定（`historical_bindings`）指向原 global G；
2. G 当前处于 risk 状态（`last_state_risk_tick` 在 `reanchor_risk_window_ticks` 内，reason ∈ {innovation_rejected, conflict_no_measurement}，见 `multiview-global-player-state`）；
3. local identity 当前稳定（同 `view_player_id` 连续出现，无 epoch 抖动）；
4. 观测连续 N 帧（N=3，可配置）在自身运动连续邻域内（帧间位移 < 阈值，默认 3ft）；
5. 无歧义竞争：该观测对 G 的 residual 显著小于对次优 global 的 residual（margin），或次优 global 不在候选/已被绑定其它观测。

**associator 产生 reanchor 决策时 MUST NOT 直接调用 `absorb_measurement`/`reseed` 更新 GlobalState**（state update owner 唯一：由 `MultiViewJointRun` 在 fusion 后执行）。JointRun 对 reanchor update MUST 执行 `registry.reseed(...)`（position=观测位置、velocity=0、covariance=初始值、timestamp=当前），而非普通 `absorb_measurement`。

reanchor MUST NOT 通过整体放宽 `max_reacquire_gate_ft` 实现（普通/continuity/historical 三条路径的 gate 语义保持不变）；reanchor 决策 MUST 记录 `reanchor_pending / reanchor_succeeded / reanchor_rejected_ambiguous` 诊断事件与归因明细。

#### Scenario: 污染后正确观测恢复原 global

- **WHEN** `cam_1/Player_2` 曾稳定绑定 `global_player_4`；G 预测被污染偏离 14ft 且处于 risk 状态；恢复后观测连续 3 帧在 [19,-4] 邻域；无其他 global 与之竞争
- **THEN** associator SHALL 产生 `reanchor=True` 决策
- **AND** JointRun SHALL 以观测位置 reseed 其 estimator（velocity=0），清除污染位置与速度
- **AND** SHALL 记录 `reanchor_succeeded`

#### Scenario: 歧义时不 reanchor

- **WHEN** 恢复观测对两个 global 的 residual 都接近（如双打中相邻 P1/P2 站位模糊）
- **THEN** 系统 SHALL NOT 产生 reanchor 决策
- **AND** SHALL 记录 `reanchor_rejected_ambiguous`
- **AND** SHALL 按现有 unresolved 路径处理（roster 满时不新建）

#### Scenario: 无风险标记不 reanchor

- **WHEN** global 不在 risk 状态（无 innovation rejection / conflict 未选中记录，或已清除）
- **THEN** 系统 SHALL NOT 进入 reanchor 路径
- **AND** 仅按普通 association gate 评估

### Requirement: reanchor 不破坏既有 gate 语义

reanchor 路径 MUST 独立于 `_pair_gate_ft` 的普通匹配/continuity/historical 分支实现，MUST NOT 改变以下既有行为：稳定连续匹配用 `base_gate_ft` 紧门；历史 local 重连 / 跨 epoch reacquire 随 uncertainty 扩展至 `max_reacquire_gate_ft`；换人尝试用更严格门与 `PendingReassociation` 迟滞。`multiview-player-association` 既有 requirement（geometry-gated identity continuity prior / uncertainty-aware association gate）的语义 SHALL 保持不变。

#### Scenario: 普通 reacquire 语义不变

- **WHEN** 未被污染的 global 因短暂缺观测后恢复
- **THEN** 系统 SHALL 仍按 `uncertainty-aware association gate` 评估（gate 随 uncertainty 扩展）
- **AND** SHALL NOT 因 reanchor 路径存在而改变该评估
