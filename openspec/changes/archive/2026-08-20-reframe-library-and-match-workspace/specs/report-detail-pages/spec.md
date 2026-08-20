## ADDED Requirements

### Requirement: 报告作为 Workspace view
报告 SHALL 作为 LibraryItemWorkspace 的「报告」view 呈现，而非独立的一级页面对象；报告天然属于某一场比赛/训练。

#### Scenario: 报告进入统一工作区
- **WHEN** 素材存在分析结果且有报告
- **THEN** 用户 SHALL 在工作区的「报告」view 查看该比赛/训练的报告
- **AND** 报告中心不作为用户一级页面展示

#### Scenario: PB 风格组件在报告 view 中复用
- **WHEN** 素材存在权威分析结果
- **THEN** 报告 view SHALL 复用 PB 风格视觉组件（Skill Card / Player Header / Court Coverage / Serves & Returns / Coach Insight / Filter）
- **AND** SHALL NOT 展示报告独立抽屉栏或专属导航体系

#### Scenario: 真实任务不得伪造 mock 结论
- **WHEN** 报告 view 面向真实任务
- **THEN** 无权威数据支撑的分析结论 SHALL NOT 被伪造填充
- **AND** 相关数据必须服从 performance-insights 证据约束