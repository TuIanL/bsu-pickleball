# analysis-task-management Specification

## Purpose

TBD - created by archiving change rework-video-analysis-task-flow. Update Purpose after archive.

本 Change 为该能力新增：任务列表默认只返回 `visibility=public` 的 Parent 任务（internal child 默认隐藏）、`include_internal=true` 仅用于诊断、录制卡片按 session 查询同样只返回 Parent、双摄任务卡片的 A/B/融合子状态与数据来源展示、级联删除语义。

## ADDED Requirements

### Requirement: 级联删除语义

`AnalysisDeleteResult` / 批量删除路径 MUST 支持 multiview Parent 的级联删除（Parent + owned child 分析产物 + fusion run 产物 + parent artifacts/report），且 MUST NOT 删除 CaptureTake、源视频或 CaptureTrack。child 的删除仅能由 Parent cascade 触发。

#### Scenario: 删除 Parent 级联

- **WHEN** 用户删除 terminal 的 multiview Parent
- **THEN** 删除结果 SHALL 覆盖 Parent 及其 owned child 的分析产物与 fusion run 产物
- **AND** 录制资产（CaptureTake / 源视频 / CaptureTrack）SHALL 保留

#### Scenario: 删除 child 被阻断

- **WHEN** 外部 API 尝试直接删除 internal child
- **THEN** 系统 SHALL 返回 `blocked`
- **AND** 删除 SHALL 仅经 Parent cascade 发生

## MODIFIED Requirements

### Requirement: Analysis task list retrieval

`GET /api/analysis/jobs` MUST 默认只返回 `visibility=public` 的任务。`include_internal=true` 查询参数才返回 `visibility=internal` 的 child，且该参数仅用于开发/诊断界面。

#### Scenario: 默认隐藏 internal child

- **WHEN** 前端请求任务列表（不带 `include_internal=true`）
- **THEN** 返回结果 SHALL 只含 `visibility=public` 的任务
- **AND** multiview child（`visibility=internal`）SHALL 被过滤

#### Scenario: 诊断模式查看 internal

- **WHEN** 前端以 `?include_internal=true` 请求
- **THEN** 返回结果 SHALL 额外包含 internal child
- **AND** 该模式 SHALL 仅用于开发/诊断界面

### Requirement: Analysis task management page

任务管理页 MUST 对每个双摄分析只展示一张 Parent 卡片，卡片标注「双摄协同分析」与 A/B/融合子状态，不再出现两张无关联的机位任务卡片。双摄任务卡片的 CTA 按 Parent 状态区分：完成 → 查看报告；失败/取消 → 提供「重新双摄分析」入口；运行中 → 展示进度。

#### Scenario: 双摄任务单卡片

- **WHEN** 任务列表包含 multiview Parent
- **THEN** 该 Parent SHALL 以单张卡片展示，含「双摄协同分析」标题、A 机位/B 机位/多视角融合子状态与数据来源
- **AND** 其 internal child SHALL 不单独出现在列表中

#### Scenario: 失败/取消的 Parent 可重新分析

- **WHEN** multiview Parent 状态为 `failed` 或 `canceled`
- **THEN** 录制卡片 SHALL 提供「重新双摄分析」入口（导航到 `MultiViewAnalysisSetupPage`）
- **AND** SHALL NOT 误显示为「分析中」

### Requirement: Analysis task list filters by recording session

按录制 session 过滤的任务查询 MUST 同样默认只返回 `visibility=public` 的 Parent，保证录制卡片查询该 session 的分析任务时不会出现三条（Parent + 两个 child）。

#### Scenario: 录制卡片查询 Parent

- **WHEN** 录制卡片请求 `GET /api/analysis/jobs?recording_session_id=<sid>`
- **THEN** 返回结果 SHALL 只含该 session 的 public Parent 任务
- **AND** internal child SHALL NOT 混入

### Requirement: Analysis task recording origin display

双摄录制卡片的 CTA MUST 将主操作改为「双摄协同分析」，次级的「分析 A/B 机位」MUST 降级为工程调试入口，分析状态展示 MUST 基于 Parent。

#### Scenario: 录制卡片主 CTA

- **WHEN** 双摄录制卡片渲染且存在对应 CaptureTake
- **THEN** 主操作 SHALL 为「双摄协同分析」
- **AND** A/B 单摄入口 SHALL 置于次级操作
