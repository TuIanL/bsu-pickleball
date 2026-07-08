## MODIFIED Requirements

### Requirement: Dedicated training recommendations page

系统 SHALL 保留 `/training` 路由和训练页代码，但从所有一级导航和首页入口中隐藏训练入口。

#### Scenario: 训练页从导航中隐藏
- **WHEN** 用户在任意页面查看主导航或首页
- **THEN** 主导航和首页卡片中不包含训练入口

#### Scenario: 训练页保留直接路由访问
- **WHEN** 用户直接访问 `/training` 路由
- **THEN** 系统正常渲染训练页面，包含推荐训练项目、训练目标、难度/时长上下文和分析数据证据

#### Scenario: User follows training link from report
- **WHEN** 用户在报告详情页选择训练建议
- **THEN** 系统可导航到 `/training` 页面展示对应训练内容
