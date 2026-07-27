## ADDED Requirements

### Requirement: Vidat 比分锚点映射
系统 MUST 将 Vidat 中有效的比分修正标注转换为 `correct_score` 语义动作，并按既有修正锚点规则参与状态重放。

#### Scenario: 导入比分修正
- **WHEN** 确认的 Vidat 标注包含 score correction 及合法的 A/B 分数和发球方
- **THEN** 系统 SHALL 创建可审计的 `correct_score` 语义动作
- **AND** 后续回合 SHALL 从该锚点重放
