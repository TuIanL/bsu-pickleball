# multiview-ball-analysis-display Specification Delta

## MODIFIED Requirements

### Requirement: 双摄球路分析使用统一时间轴与共享观测

joint 模式的球路分析 SHALL 从 `CanonicalAnalysisClock` 产生的 `SynchronizedFrameBundle` 读取双摄帧，并在同一 canonical tick 上完成候选生成、跨视角关联、三角测量与轨迹更新。生产链路 MUST 复用每个视角每个 tick 的候选结果，MUST NOT 为 stereo 分析再次独立运行 detector。跨视角关联 SHALL 经过时间、重投影、3D 球场范围、运动连续性和歧义 margin 质量门；未通过质量门的 pair 只能作为诊断，不能成为权威双摄观测。

#### Scenario: 两路帧在同一 canonical tick 可用

- **WHEN** 两路视频在 tick `t_k` 均有可用帧
- **THEN** 球候选 SHALL 由这两帧各检测一次后供 association、tracker 和 stereo 共同消费
- **AND** evidence 中 SHALL 记录 `tick_id`、两路真实帧索引与各自时间戳
- **AND** 只有通过跨视角质量门且达到歧义 margin 的 pair 才能生成权威双摄三角测量

#### Scenario: 一路帧不可用

- **WHEN** tick `t_k` 只有一个视角有可用帧
- **THEN** 该 tick SHALL NOT 生成权威双摄三角测量
- **AND** 单视角观测可作为带状态标记的 tracker 输入，但不得伪造另一视角观测

#### Scenario: 两路均有帧但 pair 不可信

- **WHEN** 两路均有候选，但最佳 pair 的重投影误差、3D 范围、运动连续性或歧义 margin 未通过质量门
- **THEN** tick SHALL 保留候选和拒绝诊断
- **AND** SHALL NOT 用该 pair 更新权威 anchor、权威落点或默认双摄球路
