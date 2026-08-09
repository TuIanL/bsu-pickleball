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
