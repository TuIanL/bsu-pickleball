## ADDED Requirements

### Requirement: Vidat 修正的比赛状态重放
系统 MUST 使用 CaptureTake 已保存的 `scoring_ruleset_version` 重放已确认 Vidat 导入得到的回合结果和比分锚点，生成一致的比分、胜局和比赛胜者投影。

#### Scenario: 导入回合结果后重放
- **WHEN** 确认的 Vidat 导入包含有效的 rally 结果变更
- **THEN** 系统 SHALL 从该 CaptureTake 的语义动作序列重放计分状态
- **AND** LiveCodingState、TimelineEvent 与报告可见的最终比赛结果 SHALL 与重放结果一致
