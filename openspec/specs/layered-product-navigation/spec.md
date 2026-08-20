# layered-product-navigation Specification

## Purpose
TBD - created by archiving change build-layered-visual-analysis-platform. Update Purpose after archive.
## Requirements
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
- **THEN** 系统导航到 `/analysis/tasks`，展示所有分析任务列表

### Requirement: Report entry flow
The system SHALL allow completed analysis results to route users into supported lower-level result pages while directing general task details to the analysis details page.

#### Scenario: User opens analysis details from a completed task
- **WHEN** the user clicks a completed task's analysis details action from task management or a completed job context
- **THEN** the system opens the job-specific analysis details page for that task

#### Scenario: User opens a supported report from visual analysis
- **WHEN** the user clicks a supported movement or diagnosis report action from a completed result context
- **THEN** the system opens the matching job-specific report detail page for that report type

#### Scenario: User opens an unsupported or removed report type
- **WHEN** the current route or selected report type does not match a supported current report definition such as removed landing analysis
- **THEN** the system provides a stable fallback to the analysis details page, task management, or an available report page instead of rendering a broken state

### Requirement: Independent product identity
The system SHALL use original product naming, icons, copy, mock visuals, and interaction labels.

#### Scenario: User views brand and visual assets
- **WHEN** the application renders navigation, hero content, video mockups, cards, icons, and CTAs
- **THEN** the system does not display PB Vision or SwingVision logos, brand names, original imagery, original icons, or original marketing copy

### Requirement: Presentation-ready responsive layout
The system SHALL keep the layered product pages polished and legible across common desktop and mobile viewports.

#### Scenario: User captures a desktop screenshot
- **WHEN** the application is viewed on a desktop viewport
- **THEN** the page presents a premium AI sports analytics layout with clear hierarchy, stable spacing, no incoherent overlap, and a strong first-screen visual signal

#### Scenario: User views the product on mobile
- **WHEN** the application is viewed on a mobile viewport
- **THEN** page sections stack or condense into stable layouts while preserving readable text, accessible controls, and constrained visualization dimensions

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
- **THEN** 系统打开任务历史页面 `/analysis/tasks`，展示所有分析任务

### Requirement: Job-specific route support
The system SHALL support route states for analysis jobs, job-specific result pages, and job-specific analysis details.

#### Scenario: User opens job status route
- **WHEN** the user navigates to a route representing an analysis job identifier
- **THEN** the app shell preserves navigation context and renders the analysis job status page

#### Scenario: User opens job-specific visual route
- **WHEN** the user navigates to a route representing visual analysis for a specific job identifier
- **THEN** the app shell renders the visual analysis workspace with that job context

#### Scenario: User opens job-specific details route
- **WHEN** the user navigates to `/analysis/:jobId/details`
- **THEN** the app shell renders the analysis details page with that job context

#### Scenario: User opens job-specific report route
- **WHEN** the user navigates to a route representing a currently supported report type for a specific job identifier
- **THEN** the app shell renders the matching report detail page with that job context

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

### Requirement: 一级导航 Library-first
系统 SHALL 以「比赛库 / 现场采集 / 设备与设置」作为一级主导航；「分析任务」「报告中心」SHALL 退出一级导航，作为比赛库的生命周期与比赛详情的视图存在。

#### Scenario: 主导航展示
- **WHEN** 用户在标准模式查看主导航
- **THEN** 主导航 SHALL 只包含比赛库（→`/library`）、现场采集（→`/capture`）、设备与设置入口
- **AND** 主导航 SHALL NOT 将「分析任务」「报告中心」作为一级项暴露

#### Scenario: 工程层入口
- **WHEN** 需要查看工程任务（Parent/child、Pipeline Stage、错误码）
- **THEN** 用户 SHALL 从「设备与设置 → 工程模式/开发者模式 → 分析任务」进入 Engineering Task Console
- **AND** 普通用户默认不可达工程入口

### Requirement: 训练页不占一级导航
系统 SHALL 保留训练页路由（`/training`）但不作为一级导航项，且不从首页主入口直接引导。

#### Scenario: 训练页不再导航
- **WHEN** 用户查看任意页面主导航
- **THEN** 主导航 SHALL 不包含训练入口

#### Scenario: 训练页直接访问
- **WHEN** 用户直接访问 `/training`
- **THEN** 系统 SHALL 正常渲染训练页内容

### Requirement: 首页工作流入口调整
首页 SHALL 提供面向 Library-first 的主 workflow 入口：进入比赛库与开始现场采集，而非仅一条限制性的单一入口。

#### Scenario: 首页进入比赛库
- **WHEN** 用户加载根路径 `/`
- **THEN** 首页 SHALL 提供进入比赛库的主入口
- **AND** 首页 SHALL 提供开始现场采集的主入口

