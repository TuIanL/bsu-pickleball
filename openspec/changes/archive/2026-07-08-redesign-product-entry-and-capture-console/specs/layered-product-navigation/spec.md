## MODIFIED Requirements

### Requirement: Top navigation for core workflows

系统 SHALL 在页面顶部提供极简导航，仅包含产品标识和辅助入口，不展示页面跳转标签。

#### Scenario: User views desktop navigation
- **WHEN** 应用在桌面视口展示
- **THEN** 导航左侧显示「拍动视析 Logo + 产品名」
- **AND** 导航右侧显示「任务历史」辅助入口（帮助入口预留但本次不实现）
- **AND** 导航中不显示「总览 / 视频分析 / 球场采集 / 训练」等一级 tab
- **AND** 点击 Logo 或产品名 SHALL 导航到首页 `/`

#### Scenario: User views narrow navigation
- **WHEN** 应用在窄视口展示
- **THEN** 导航保持 Logo + 辅助入口的极简布局
- **AND** 导航内容不换行或溢出，辅助入口可折叠为汉堡菜单

### Requirement: Layered page architecture

系统 SHALL 提供以两个产品工作流为入口的页面架构：首页（Landing）→ 上传模式 → 分析工作流；首页 → 录制模式 → 采集工作流。

#### Scenario: User opens the landing page
- **WHEN** 用户加载应用根路径 `/`
- **THEN** 系统展示产品首页，包含 Hero 区、两个主工作流入口按钮（上传已有视频 / 进入现场录制）和三个能力介绍卡片

#### Scenario: User enters upload mode
- **WHEN** 用户点击首页「上传已有视频」按钮
- **THEN** 系统导航到 `/upload`，展示视频上传、标定和分析任务创建流程

#### Scenario: User enters recording mode
- **WHEN** 用户点击首页「进入现场录制」按钮
- **THEN** 系统导航到 `/capture`，展示现场采集首页

#### Scenario: User accesses task history
- **WHEN** 用户点击导航栏右上角「任务历史」
- **THEN** 系统导航到 `/tasks`，展示所有分析任务列表

### Requirement: Analysis workflow navigation

系统 SHALL 通过首页和上传模式入口暴露真实分析工作流。

#### Scenario: User starts upload analysis from landing page
- **WHEN** 用户从首页点击「上传已有视频」按钮
- **THEN** 系统导航到 `/upload` 上传模式页面

#### Scenario: User starts analysis from upload mode
- **WHEN** 用户在 `/upload` 页面完成视频上传、标定和元数据填写
- **THEN** 系统创建分析任务并导航到任务状态页面 `/analysis/:jobId`

#### Scenario: User opens task history
- **WHEN** 用户点击导航栏右上角「任务历史」或从完成面板进入
- **THEN** 系统打开任务历史页面 `/tasks`，展示所有分析任务

## ADDED Requirements

### Requirement: 录制模式路由

系统 SHALL 支持 `/capture`、`/capture/new` 和 `/capture/:id` 路由，分别对应采集任务首页、创建向导和采集控制台。

#### Scenario: 访问采集任务首页
- **WHEN** 用户导航到 `/capture`
- **THEN** 系统展示采集任务列表和新建入口

#### Scenario: 访问新建采集向导
- **WHEN** 用户导航到 `/capture/new`
- **THEN** 系统展示三步创建向导

#### Scenario: 访问采集控制台
- **WHEN** 用户导航到 `/capture/:id`
- **THEN** 系统加载对应 Field Session 的采集控制台

### Requirement: 上传模式路由

系统 SHALL 支持 `/upload` 路由，对应上传已有视频分析工作流入口。

#### Scenario: 用户访问上传模式
- **WHEN** 用户导航到 `/upload`
- **THEN** 系统展示视频上传、四角标定和元数据表单页面

### Requirement: 训练页软隐藏

系统 SHALL 从所有一级导航和首页入口中移除训练页，但保留其路由和代码。

#### Scenario: 训练页不在导航中
- **WHEN** 用户在任意页面查看主导航
- **THEN** 导航中不包含训练入口

#### Scenario: 训练页保留直接访问
- **WHEN** 用户直接访问 `/training` 路由
- **THEN** 系统正常渲染训练页内容
