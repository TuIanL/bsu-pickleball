# training-feedback-loop Specification

## Purpose
TBD - created by archiving change build-digital-interaction-platform. Update Purpose after archive.
## Requirements
### Requirement: Personalized diagnosis

The system SHALL translate analysis outputs into personalized pickleball improvement diagnoses that users can understand.

#### Scenario: User views diagnosis panel

- **WHEN** the report includes diagnosis data
- **THEN** the system displays specific issues such as delayed backswing, center-of-gravity drift, recovery delay, or unstable backhand placement with severity and evidence

### Requirement: Actionable improvement suggestions

The system SHALL provide concrete improvement suggestions linked to each diagnosis.

#### Scenario: User reads an improvement suggestion

- **WHEN** a diagnosis is displayed
- **THEN** the system shows a specific training suggestion, expected outcome, and priority level for that diagnosis

### Requirement: Learning-practice-evaluation loop

The system SHALL present a closed loop from report finding to learning content, practice task, and future evaluation target in a dedicated training page and linked report contexts.

#### Scenario: User follows the training loop

- **WHEN** the user views a recommended training item from the training page or from a linked report finding
- **THEN** the system shows the related report issue, learning content placeholder, practice task, and measurable next-session target

### Requirement: Teaching content placeholders

The system SHALL include credible placeholders for teaching videos and motion comparison without implying that real video or 3D assets are already connected.

#### Scenario: Teaching module is rendered

- **WHEN** the teaching section or training page is displayed
- **THEN** the system presents video and motion comparison modules as product-ready placeholders tied to report diagnoses

### Requirement: Progress narrative

The system SHALL show how repeated reports can track improvement over time on the training page and any progress-oriented dashboard modules.

#### Scenario: User views progress context

- **WHEN** the training feedback page or progress module is visible
- **THEN** the system displays at least one previous-current-next comparison, trend chart, or goal indicator that explains how the platform supports continuous improvement

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
