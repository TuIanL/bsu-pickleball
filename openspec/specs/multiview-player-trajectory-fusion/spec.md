# multiview-player-trajectory-fusion Specification

## Purpose
TBD - created by archiving change add-multiview-player-trajectory-fusion. Update Purpose after archive.
## Requirements
### Requirement: 观测质量拆分为 Intrinsic + Pair

系统 MUST 将观测质量拆为两个正交概念：**ViewIntrinsicQuality**（某一路自身的质量：`detector confidence / normalized bbox height / projection confidence / footpoint method / tracking state / calibration quality / sync selection error`）与 **PairConsistency**（两路之间的成对关系：`inter-view distance / residual to predicted global position / association cost`）。决策输入 MUST 为 `ViewIntrinsicQuality + PairConsistency + Global prediction`，MUST NOT 将 pairwise relation 混入单视角 intrinsic 质量评分。

#### Scenario: intrinsic 不混 pairwise

- **WHEN** 系统计算某一路单视角质量
- **THEN** 该评分 SHALL 只基于该路 intrinsic 特征
- **AND** 两路 disagreement 等 pairwise relation SHALL 只在 PairConsistency 中参与决策

#### Scenario: bbox 归一化

- **WHEN** 系统使用 bbox 作为质量特征
- **THEN** bbox 尺寸 SHALL 使用归一化形式（如 `bbox_height / frame_height` 或归一化面积）
- **AND** 系统 SHALL NOT 直接使用原始像素面积（不同分辨率/zoom/裁切下不可比）

#### Scenario: 插值点区分

- **WHEN** 某观测来自插值而非真实检测
- **THEN** 系统 SHALL 区分其来源并降低其质量权重
- **AND** 插值观测 SHALL NOT 作为独立证据参与融合

### Requirement: 位置融合状态机

`PlayerPositionFusion` 在同一 canonical timestamp、同一 global player 下融合有效观测，状态 MUST 只包括 `dual_observed / single_view_fallback / conflict / unavailable`。**`predicted` MUST NOT 属于 Fusion 状态**；是否在无观测时刻输出预测点 MUST 由 `GlobalTrackFilter` 决定。Fusion MUST NOT 采用固定 50/50 平均，而应按观测质量加权。

#### Scenario: 双观测

- **WHEN** 同一 global player 在同一时刻有两路有效观测
- **THEN** 系统 SHALL 按观测质量加权融合
- **AND** 融合状态 SHALL 为 `dual_observed`

#### Scenario: 单视角回退

- **WHEN** 仅一路存在有效观测
- **THEN** 系统 SHALL 使用该路观测
- **AND** 融合状态 SHALL 为 `single_view_fallback`

#### Scenario: 无观测无预测状态

- **WHEN** 两路均无有效观测
- **THEN** `PlayerPositionFusion` SHALL 标记 `unavailable`
- **AND** 是否输出预测点 SHALL 交由 `GlobalTrackFilter` 决定，而非 Fusion 产生 `predicted` 状态

### Requirement: 冲突检测

当两路观测在 canonical 空间出现无法合理解释的大幅不一致时，系统 MUST 将状态置为 `conflict`，MUST NOT 平均出不存在的中间位置，并按全局预测或高质量单视角选择输出。

#### Scenario: 冲突不平均

- **WHEN** 两路观测距离超过阈值且无法由运动预测合理解释
- **THEN** 系统 SHALL 置 `fusion_status = conflict`
- **AND** 系统 SHALL NOT 输出两路坐标的算术平均作为真实位置

#### Scenario: 冲突选择

- **WHEN** 冲突已判定
- **THEN** 系统 SHALL 按全局预测或高质量单视角选择输出
- **AND** 冲突信息 SHALL 记入 diagnostics

### Requirement: GlobalTrackFilter predict/update 时序

`GlobalTrackFilter` MUST 前置提供 `predict(t)`，输出 predicted global positions，供关联与融合引用；MUST 在融合后提供 `update(measurement)` 吸收新观测。系统 MUST NOT 让 `PlayerPositionFusion` 与 `GlobalTrackFilter` 各自独立产生预测（避免双重状态估计）。

#### Scenario: predict 先行

- **WHEN** 融合开始处理时刻 `t`
- **THEN** `GlobalTrackFilter.predict(t)` SHALL 先产生 predicted global positions
- **AND** 关联与融合 SHALL 使用该预测作为唯一全局预测来源

#### Scenario: update 吸收观测

- **WHEN** `PlayerPositionFusion` 产出测量值
- **THEN** `GlobalTrackFilter.update(measurement)` SHALL 吸收该测量并更新 Global State

### Requirement: 不做双重平滑

融合 MUST 以真实观测点作为输入，MUST NOT 将两路已经插值和平滑后的轨迹互相作为独立证据重复平滑。

#### Scenario: 观测输入约束

- **WHEN** Fusion 层接收观测
- **THEN** 系统 SHALL 过滤非真实检测点（如 `source != observed`）
- **AND** 系统 SHALL NOT 将已插值点作为融合的独立证据

### Requirement: FusedPlayerTrajectoryArtifact

系统 MUST 生成版本化 `fused_player_trajectory.v1` artifact，每个 sample 至少记录 `global_player_id / timestamp_seconds / take_timestamp_ms / reference_frame_index / x_ft / y_ft / fusion_status / fusion_confidence / contributing_views / selected_view / view_observations / association_confidence / sync_quality / court_frame_version / measurement_source / metric_eligible`。`view_observations` 中每路 MUST 记录 `source_frame_index / source_timestamp_ms / mapped_take_timestamp_ms / selection_error_ms / x_ft / y_ft / quality`。

#### Scenario: artifact 字段

- **WHEN** 生成 fused trajectory artifact
- **THEN** 每个 sample SHALL 包含 `global_player_id / timestamp_seconds / take_timestamp_ms / reference_frame_index / x_ft / y_ft / fusion_status / fusion_confidence`
- **AND** SHALL 包含 `contributing_views / selected_view / view_observations / association_confidence / sync_quality / court_frame_version / measurement_source / metric_eligible`

#### Scenario: 组成可追溯

- **WHEN** 需要解释 fused 点由哪些真实帧组成
- **THEN** 每路 `view_observations` SHALL 含 `source_frame_index / source_timestamp_ms / mapped_take_timestamp_ms / selection_error_ms`
- **AND** 融合完成后 SHALL NOT 丢弃原始证据

### Requirement: 融合诊断 artifact

系统 MUST 生成独立 diagnostics artifact，记录 `orientation normalization / frame mapping errors / association decisions / view quality scores / view disagreement / fallback & conflict counts`。

#### Scenario: 诊断可追踪

- **WHEN** 融合完成后
- **THEN** diagnostics SHALL 记录各 canonical 归一化结果、帧映射错误、关联决策、各视角质量评分、视角分歧与 fallback/conflict 计数
- **AND** 诊断 SHALL 可供定位"该融合点为何落在该位置"

### Requirement: 下游消费受 metric eligibility 约束

下游消费 Fused Trajectory MUST 保持受 metric eligibility 约束：`dual_observed / single_view_fallback → metrics yes`；`conflict` 按 `metric_eligible` 标志；`predicted → visualization yes、metrics no`；`unavailable → no`。本 Change 的 Composer 接入 MUST NOT 放宽该消费契约。

#### Scenario: eligibility 契约不变

- **WHEN** Composer 消费 fused trajectory
- **THEN** `metric_eligibility_policy` 语义 SHALL 与 P0 冻结版本一致
- **AND** `predicted` / `unavailable` 样本 SHALL NOT 计入 movement / heatmap

### Requirement: 轨迹来源选择含 unavailable

`TrajectorySource` MUST 扩展为 `Literal["fused", "single_view", "unavailable"]`。`select_trajectory_source(fused_available, single_view_available)` MUST 按以下规则返回：fused 可用 → `"fused"`；仅单视角可用 → `"single_view"`；两者均不可用 → `"unavailable"`。MUST NOT 在双路失败时声称存在单视角轨迹。

#### Scenario: fused 可用

- **WHEN** `fused_available=True`
- **THEN** 返回 SHALL 为 `"fused"`

#### Scenario: 仅单视角可用

- **WHEN** `fused_available=False` 且 `single_view_available=True`
- **THEN** 返回 SHALL 为 `"single_view"`

#### Scenario: 双路失败

- **WHEN** `fused_available=False` 且 `single_view_available=False`
- **THEN** 返回 SHALL 为 `"unavailable"`
- **AND** 消费方 SHALL 按无可用轨迹处理（Parent 失败），不得虚构单视角轨迹

