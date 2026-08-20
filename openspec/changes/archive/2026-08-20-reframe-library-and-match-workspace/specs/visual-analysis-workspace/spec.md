## ADDED Requirements

### Requirement: 视觉分析作为 Workspace view
视觉分析工作区（video-first、真实数据、不阻塞 overlay、状态 rail 等行为契约）SHALL 保留，作为 LibraryItemWorkspace 的「数据分析」view，而非独立一级结果页。

#### Scenario: 数据分析 view
- **WHEN** 用户在工作区选择「数据分析」
- **THEN** 系统 SHALL 渲染保留原行为契约的视觉分析内容（视频 + overlay + 状态 rail）
- **AND** 页面边界从独立结果页收敛为该 view

#### Scenario: 从报告/球路返回数据分析
- **WHEN** 用户从其他 view 回到「数据分析」
- **THEN** 系统 SHALL 保持同一素材上下文与历史 replace 语义