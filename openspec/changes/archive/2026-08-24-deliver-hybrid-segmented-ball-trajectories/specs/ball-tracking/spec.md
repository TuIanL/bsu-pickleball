## ADDED Requirements

### Requirement: 高速小球多帧候选一致性
系统 SHALL 在不重复运行 detector 的前提下，以连续多帧候选、预测位置、尺度变化、场地 ROI、静态位置历史和运动物理约束筛选球候选，并保存每个候选的接受或拒绝原因。

#### Scenario: 单帧高置信静态误检
- **WHEN** 高置信候选长期停留在广告牌、边线标记或固定灯光位置且不符合球运动
- **THEN** tracker SHALL 将其标记为静态误检并加入有期限的黑名单
- **AND** MUST NOT 仅因单帧置信度最高而锁定该候选

#### Scenario: 高速球短时模糊或漏检
- **WHEN** 真球在短时间内出现尺度变化、运动模糊或少量缺帧但仍与预测轨迹一致
- **THEN** tracker SHALL 保持同一轨迹身份
- **AND** 缺失帧 SHALL 标记为 predicted，不得冒充 detector 观测

### Requirement: 球跟踪连续性使用有效时间步长
球 tracker 的速度、预测门、静止窗口和丢失阈值 SHALL 使用 effective FPS、frame stride 与真实 timestamp 计算，MUST NOT 假设相邻处理样本的 source frame index 差恒为 1。

#### Scenario: stride 为 2
- **WHEN** 源视频 60 FPS 且分析 stride 为 2
- **THEN** frame index 从 `n` 变为 `n+2` SHALL 被视为一个正常处理时间步
- **AND** tracker SHALL NOT 因帧索引差为 2 自动进入 lost 或重新搜索状态

