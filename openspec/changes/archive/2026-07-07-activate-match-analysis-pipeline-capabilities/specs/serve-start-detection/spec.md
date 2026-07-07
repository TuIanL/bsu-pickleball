## ADDED Requirements

### Requirement: 发球检测可消费球分析辅助信号
系统 SHALL 允许发球开始候选检测在球轨迹或弹跳候选 artifact 可用时把它们作为辅助信号，但不得要求这些信号存在才能保持现有发球候选能力。

#### Scenario: 球轨迹辅助信号可用
- **WHEN** 发球检测运行且同一任务存在可用球轨迹、清洗球轨迹或弹跳候选 artifact
- **THEN** 发球检测 MAY 使用这些信号辅助定位候选时间点
- **AND** artifact 中 SHALL 记录使用了哪些球分析信号

#### Scenario: 球分析辅助信号不可用
- **WHEN** 发球检测运行但球分析配置关闭、缺少依赖或没有生成候选 artifact
- **THEN** 发球检测 SHALL 保持现有基于 tracking、player trajectory、pose、ROI motion 或其他支持信号的降级路径
- **AND** MUST NOT 因缺少球轨迹而把发球检测整体标记为失败

#### Scenario: 发球候选仍不是完整回合
- **WHEN** 发球检测使用了球轨迹或弹跳候选辅助信号
- **THEN** 系统 SHALL 继续只声明发球开始候选点
- **AND** MUST NOT 从辅助信号推断完整 rally segmentation、回合结束、比分或战术结论
