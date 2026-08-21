# report-detail-pages Specification

## Purpose
明确报告作为 Workspace 报告 view 的承载方式：Workspace 内 SHALL 挂载 `PbReportContent`（复用 PB 风格组件、不含独立抽屉），独立报告路由与 legacy 布局保留。

## MODIFIED Requirements

### Requirement: 报告作为 Workspace view

报告 SHALL 作为 LibraryItemWorkspace 的「报告」view 呈现，而非独立的一级页面对象；报告天然属于某一场比赛/训练。报告承载按四层职责划分：`ReportContent`（useJobReport 驱动的数据与业务状态：loading/failed/canceled/no report）→ `PbReportContent`（Pb 视觉内容，NO Drawer、NO navigation）→ `PbVisionReportLayout`（仅 standalone 的 chrome：PbPlayerDrawer / Drawer expander / 独立间距）。Workspace 报告 view SHALL 直接以 `ReportContent` + `PbReportContent` 承载；`PbVisionReportLayout` SHALL 只用于独立报告路由。

#### Scenario: 报告进入统一工作区
- **WHEN** 素材存在分析结果且有报告
- **THEN** 用户 SHALL 在工作区的「报告」view 查看该比赛/训练的报告
- **AND** 报告中心不作为用户一级页面展示

#### Scenario: PB 风格组件在报告 view 中复用
- **WHEN** 素材存在权威分析结果
- **THEN** 报告 view SHALL 复用 PB 风格视觉组件（Skill Card / Player Header / Court Coverage / Serves & Returns / Coach Insight / Filter）
- **AND** SHALL NOT 展示报告独立抽屉栏或专属导航体系
- **AND** Workspace 报告 view SHALL 渲染 `ReportContent` + `PbReportContent`，不经过会挂载 Drawer / 独立间距的 `PbVisionReportLayout` 整页

#### Scenario: 报告职责四层不混
- **WHEN** 报告 view 因任务数据缺失进入 loading/failed/no report
- **THEN** 该状态的判定与文案 SHALL 由 `ReportContent` 负责
- **AND** `PbReportContent` SHALL 只在拿到 report data 后渲染视觉内容
- **AND** `PbVisionReportLayout` 的 Drawer/expander 逻辑 SHALL NOT 出现在 workspace 报告 view 中

#### Scenario: 独立报告路由保留
- **WHEN** 用户访问独立报告路由（`/reports/:type` 或 `/analysis/:jobId/reports/:type`）
- **THEN** 系统 SHALL 继续以既有方式渲染报告（`PbVisionReportLayout` 新布局含 drawer 或 legacy），不因 Workspace 重构而破坏

#### Scenario: 真实任务不得伪造 mock 结论
- **WHEN** 报告 view 面向真实任务
- **THEN** 无权威数据支撑的分析结论 SHALL NOT 被伪造填充
- **AND** 相关数据必须服从 performance-insights 证据约束