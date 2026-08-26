# reconstructed-trajectory-artifact Specification Delta

## MODIFIED Requirements

### Requirement: 分层可用状态写入产物

系统 SHALL 同时记录 3D overall status、`display_trajectory_status`、段级 display level 与指标级 validity，供前端分别控制球路和测量指标。每个 segment SHALL 额外记录质量门摘要、观测覆盖、插值/预测比例、断点/provenance 和 `display_eligible`；这些字段 SHALL 能解释该段为什么可展示、仅调试可见或不可用。

#### Scenario: 状态组合

- **WHEN** 写入混合产物
- **THEN** 3D overall status SHALL 为 `FULL_ESTIMATED_3D`、`PARTIAL_3D`、`LANDING_ONLY` 或 `UNAVAILABLE`
- **AND** `display_trajectory_status` SHALL 为 `available`、`degraded` 或 `unavailable`
- **AND** 每个速度、高度和落点指标 SHALL 自带 validity/reason
- **AND** 每个 segment SHALL 保存 `display_level`、`display_eligible` 和质量门摘要

#### Scenario: 低质量段不具备默认展示资格

- **WHEN** segment 的观测覆盖不足、插值/预测比例超限、双摄 pair 歧义或存在未跨越的长缺口
- **THEN** segment SHALL 标记为 `display_eligible = false` 或仅调试级 `display_level`
- **AND** `display_trajectory_status` SHALL 不得因该段单独存在而被提升为可用
- **AND** artifact SHALL 保存对应的拒绝/降级 reason

#### Scenario: provenance 与断点可追溯

- **WHEN** segment 包含 detected、interpolated、model_predicted 或 stereo-anchor 样本
- **THEN** artifact SHALL 保留各样本来源、实际时间戳、缺口时长和断点原因
- **AND** 前端与诊断消费者 SHALL 能据此断开长缺口，不得把样本数量解释为时间长度
