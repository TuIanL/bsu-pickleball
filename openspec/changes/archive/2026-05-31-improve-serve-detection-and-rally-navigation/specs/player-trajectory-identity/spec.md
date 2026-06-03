## ADDED Requirements

### Requirement: Player trajectory 覆盖诊断

后端 SHALL 在 player trajectory identity 输出或分析阶段 counters 中提供轨迹覆盖诊断，使下游发球检测能够识别目标球员轨迹提前中断、身份失联或目标球场过滤过严。

#### Scenario: Player trajectory 覆盖完整视频
- **WHEN** 真实视频分析完成且稳定 player trajectory 覆盖接近完整源视频时长
- **THEN** trajectory artifact 或 diagnostics SHALL 暴露每个 `player_id` 的样本数量、最早时间、最晚时间、detected/interpolated 分布和源 track 历史摘要

#### Scenario: Player trajectory 提前中断
- **WHEN** tracking overlay 仍覆盖后续视频但所有或主要 player trajectory 的最后样本时间明显早于源视频结束时间
- **THEN** trajectory diagnostics SHALL 记录覆盖缺口、最后活跃时间、可能原因和被过滤或未匹配 track 的摘要

#### Scenario: 目标球场过滤导致无样本
- **WHEN** 后半段存在人体检测框但 primary-player selection 或 target-court eligibility 没有为 identity layer 提供合格 track
- **THEN** diagnostics SHALL 记录该时间段的过滤原因，以便发球检测和 UI 能报告输入链路不足

#### Scenario: 下游能力读取覆盖诊断
- **WHEN** 发球检测消费 player trajectory artifact
- **THEN** 它 SHALL 能读取或推导 trajectory 覆盖信息，并在覆盖不足时输出降级或诊断结果
