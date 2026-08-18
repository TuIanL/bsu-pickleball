# multiview-global-player-state Specification

## Purpose
`GlobalPlayerState` + `GlobalMotionEstimator`(4-state constant-velocity Kalman):`predict(t) → position + covariance`,支撑跨视角 guidance。**不修改 P0 `GlobalTrackFilter`。**
## Requirements
### Requirement: GlobalPlayerState 契约

系统 SHALL 提供 `GlobalPlayerState`,包含 `global_player_id`、位置 `(x_ft, y_ft)`、速度 `(vx_ft_s, vy_ft_s)`、`position_uncertainty_ft`、lifecycle(`tentative | confirmed | lost`)、`cross_view_anchored`(bool)与 `view_bindings`(`cam_1`/`cam_2`: `view_player_id` / `track_id` / `last_seen` / `quality`)。

#### Scenario: 状态完整

- **WHEN** 一个 global player 被建立
- **THEN** 其状态 SHALL 包含位置、速度、uncertainty、lifecycle、cross_view_anchored 与各 view binding
- **AND** 状态 SHALL 可被 guidance 生成器与关联器消费

#### Scenario: 缺 view binding

- **WHEN** 某 global player 在 cam_2 当前不可见
- **THEN** 其 cam_2 binding SHALL 标记为已过期/缺失
- **AND** 该 player SHALL 仍以 cam_1 binding 维持全局状态

### Requirement: GlobalMotionEstimator 提供预测与协方差

系统 SHALL 提供 `GlobalMotionEstimator`(**新类,不修改 P0 `GlobalTrackFilter`**),采用 **4-state constant-velocity Kalman `[x, y, vx, vy]` + covariance**。`predict(t)` SHALL 返回 `(predicted_position, prediction_covariance)`;guidance ROI 尺寸 SHALL 由 covariance 自然推导的 uncertainty 决定。

#### Scenario: 预测位置与协方差

- **WHEN** 对某 global player 调用 `predict(t)`(t 在未来)
- **THEN** 返回基于 last position + velocity 的预测位置
- **AND** 返回随预测时长增长的 covariance(uncertainty)

#### Scenario: 吸收融合测量

- **WHEN** 一次融合产生真实测量
- **THEN** estimator SHALL 更新位置/速度并收紧 covariance
- **AND** `predicted` 样本 SHALL NOT 回灌滤波器(避免预测自我喂养,见 invariant 4)

### Requirement: lifecycle 与 cross_view_anchored 分离

`lifecycle = confirmed` SHALL 可仅由单视角稳定达成(不阻止 local identity 稳定)。`cross_view_anchored = true` SHALL 仅当历史上存在 ≥N 次稳定双视角 canonical 一致观测。**强 cross-view guidance 仅对 `confirmed AND cross_view_anchored` 的 global player 生成。**

#### Scenario: 单摄稳定可 confirmed

- **WHEN** 某 global player 单视角非常稳定
- **THEN** 其 `lifecycle` SHALL 可为 `confirmed`
- **AND** `cross_view_anchored` SHALL 仍为 false(无足够双视角一致历史)

#### Scenario: 双视角一致才 anchored

- **WHEN** 某 global player 历史上存在 ≥N 次稳定双视角 canonical 一致观测
- **THEN** 其 `cross_view_anchored` SHALL 置 true
- **AND** 此后才允许为其生成强 guidance

#### Scenario: tentative 不产生强 guidance

- **WHEN** global player 处于 `tentative` 或 `cross_view_anchored=false`
- **THEN** 系统 SHALL NOT 为其生成强 guided ROI
- **AND** 仅允许其接受 base detection 继续积累证据

### Requirement: Binding 逐 tick aging 与最后 view evidence

registry SHALL 在每个 canonical tick、perception 前以 take timestamp age 全部 bindings。`ViewBinding` SHALL 保存最后 local player identity、`local_identity_epoch`、track、source frame、quality、visibility、lock/tracking state、observation origin 与可用 guidance reference。availability 不得被伪装为视觉 observation。

#### Scenario: 消失后 aging
- **WHEN** 一个 view 的当前可用 source frame 未形成该 player observation
- **THEN** binding SHALL 随配置阈值从 observed 转为 weak/lost
- **AND** 另一 view 的 binding 仍可维持 global state

#### Scenario: local identity epoch 变更
- **WHEN** 同一 view 的 `player_id` 经 identity reset 产生新的 `identity_epoch`
- **THEN** 系统 SHALL 不将新 epoch 继承为旧 epoch 的 continuity binding

### Requirement: Registry roster 化
`GlobalPlayerRegistry` SHALL 在创建时接收 `expected_player_count`。registry SHALL 通过 `allocate_roster_slot()` 分配正式 global 身份，roster 满后返回 None；公开的 `new_global_id()` SHALL 不再作为普通 unmatched 观测的可用路径（仅在 roster reset / 重建等明确事件中由内部使用）。`predict_all()` SHALL 仅返回 roster 内且具备普通关联资格的 global 的预测；候选池（`candidate_N`）SHALL NOT 参与预测与关联匹配。

#### Scenario: 双打 roster 上限 4

- **WHEN** `expected_player_count=4` 且已分配 4 个 slot
- **THEN** 再次 `allocate_roster_slot()` SHALL 返回 None
- **AND** 候选池候选 SHALL 不进入 `predict_all()`

#### Scenario: 单打 roster 上限 2

- **WHEN** `expected_player_count=2`
- **THEN** roster 最多 2 个正式 global
- **AND** 多余观测 SHALL 停留在候选池或 unresolved

### Requirement: 三级生命周期状态机与确认
registry SHALL 维护 `candidate → provisional roster occupant → roster confirmed` 生命周期：candidate 晋升后成为 provisional occupant（占 slot），仅当全部 slot 均有 occupant 且每个 occupant 额外稳定 K 个 canonical tick 或至少一次可靠 cross-view anchoring 后，roster 才进入 `ROSTER_ACTIVE`。**slot 占满 SHALL NOT 使 roster 可信**；确认窗口内错误 occupant SHALL 可被推翻。

#### Scenario: 候选晋升为 occupant

- **WHEN** candidate 满足晋升规则
- **THEN** 其 SHALL 成为 provisional roster occupant（占 slot，参与融合与指标）
- **AND** registry SHALL 仍处于 BOOTSTRAPPING（未确认）

#### Scenario: 确认后进入 ACTIVE

- **WHEN** 全部 slot 占用且每 occupant 满足稳定 K tick 或 cross-view anchoring
- **THEN** registry SHALL 进入 `ROSTER_ACTIVE`
- **AND** 此后不创建新 global

#### Scenario: 占满未确认仍可推翻

- **WHEN** 4 个 occupant 均未满足确认条件
- **THEN** registry SHALL 保持 BOOTSTRAPPING
- **AND** 错误 occupant SHALL 可被弱绑定 / geometry 证据替换

### Requirement: 存在与普通关联资格分离
`GlobalPlayerState` 的"存在于 registry"与"有资格参与普通 association"SHALL 分离：当 `position_uncertainty_ft > threshold` 或 `last_seen_age > threshold`（配置）时，该玩家 SHALL 标记为 stale，退出普通紧门匹配（其预测不作为普通候选吸附观测），仅允许经 historical local continuity、guided recovery、strong reacquire 路径回归；恢复成功后重新获得普通资格。candidate 与从未 confirmed 的 tentative SHALL 可过期淘汰；已进入 roster 的 confirmed global 出画 SHALL 仅降级 weak → lost，等待 recovery，SHALL NOT 删除。仅 roster reset 才销毁。

#### Scenario: 候选过期

- **WHEN** candidate 长时间未达晋升条件
- **THEN** registry SHALL 将其过期清理
- **AND** 清理 SHALL 不影响 roster 内 global

#### Scenario: roster 内 P3 出画不删

- **WHEN** roster 内 Global P3 出画（binding 降级 lost）
- **THEN** GlobalPlayerState P3 SHALL 继续存在于 registry
- **AND** 恢复时 SHALL 复用原 global，不得创建新 global

#### Scenario: stale 不吸附

- **WHEN** Global P3 失踪超阈值
- **THEN** P3 的预测 SHALL 退出普通关联
- **AND** 其他观测 SHALL NOT 因 P3 的 stale 预测被误吸附

#### Scenario: 明确换场才重建

- **WHEN** 系统识别到 new_match / roster_reset / participant-change
- **THEN** registry SHALL 销毁现有 roster 并重新进入 `BOOTSTRAPPING`
- **AND** 普通遮挡 / epoch reset / 局盘切换 / 换边 SHALL 不触发重建

### Requirement: base-only cross-view anchor

`cross_view_anchored` SHALL 只由同一 tick 中 distinct views 的 base+base 一致 observation 累积；guided/base 组合可融合但不得建立或增加 anchor。

#### Scenario: guided 恢复不自证
- **WHEN** 某 tick 包含 Cam1 base 与 Cam2 guided_roi observation
- **THEN** 系统 SHALL 可将其作为真实 measurement 融合
- **AND** SHALL NOT 因该组合使尚未 anchored 的 global 成为 anchored

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

