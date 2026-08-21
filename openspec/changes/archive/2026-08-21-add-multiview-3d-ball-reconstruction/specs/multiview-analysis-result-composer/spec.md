## ADDED Requirements

### Requirement: joint 模式发布球立体产物
系统 SHALL 使 `multiview_analysis_result_composer` 在 joint 模式下正式发布球相关产物：不可变 `multiview_ball_stereo_evidence.v1` 与用户轨迹 `reconstructed_ball_trajectory.v3`。

#### Scenario: 发布 stereo evidence
- **WHEN** joint 任务已生成球立体证据
- **THEN** composer SHALL 发布 `multiview_ball_stereo_evidence.json`
- **AND** 该 evidence SHALL 为不可变原始证据，供审计与后续重建引用

#### Scenario: 发布 v3 用户轨迹
- **WHEN** joint 任务已生成多视角估算三维球路
- **THEN** composer SHALL 在同一语义 slug 发布 `reconstructed_ball_trajectory.json`（schema `.v3`）
- **AND** 输出整体可用状态 `FULL_ESTIMATED_3D / PARTIAL_3D / LANDING_ONLY / UNAVAILABLE` 与指标级 validity 分级

#### Scenario: 产物可用性降级
- **WHEN** 双摄 3D 证据不足但落点权威可用
- **THEN** composer SHALL 发布 `LANDING_ONLY` 状态与可用落点
- **AND** 不得回退为假 2.5D 默认产物