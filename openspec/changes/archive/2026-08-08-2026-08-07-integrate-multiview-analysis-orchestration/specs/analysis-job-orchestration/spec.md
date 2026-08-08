# analysis-job-orchestration Specification

## Purpose

TBD - created by archiving change add-analysis-job-orchestration-foundation. Update Purpose after archive.

本 Change 为该能力新增：编排字段兼容、`is_runnable()` 统一 claim 判定、Worker 经 Executor registry 分发、编排状态独立维度（`orchestrationStatus`）。`canonicalStatus` 五态生命周期与阶段遥测不变。

## ADDED Requirements

### Requirement: 可执行判定统一为 is_runnable

`JobStore.claim_next()` / `claim` 的可执行判定 MUST 收口为 `is_runnable(job)`：`canonicalStatus != "queued"` → False；`analysisKind=single_view` → True；`analysisKind=multiview` → `orchestrationStatus ∈ {fusion_ready, fallback_ready}`。MUST NOT 再直接按 `canonicalStatus == "queued"` 领取。

#### Scenario: waiting_sources 不被领取

- **WHEN** `claim_next()` 遇到 `orchestrationStatus=waiting_sources` 的 Parent
- **THEN** 该 Parent SHALL 被跳过，不占用 Worker（杜绝 Parent 占锁等待 child 的死锁）

#### Scenario: fusion_ready 正常领取

- **WHEN** Parent `orchestrationStatus=fusion_ready`
- **THEN** `claim_next()` SHALL 按既有优先级/排队规则领取

### Requirement: Worker 经 Executor registry 分发

`AnalysisWorkerRuntime._execute` MUST 通过 `executor_registry.resolve(job.analysisKind)` 解析执行体并调用 `execute(job, token, progress_callback)`，MUST NOT 在 Worker 主循环内按 `analysisKind` 硬编码分支。第一版 registry 仅含 SingleView / MultiView 两个执行体（不做插件框架）。取消/重试/超时兜底逻辑归属与行为保持不变。

#### Scenario: 单摄执行不变

- **WHEN** 执行 `analysisKind=single_view` 任务
- **THEN** 行为 SHALL 与改造前一致（SingleViewAnalysisExecutor 封装现有 Pipeline）
- **AND** 现有单摄回归测试 SHALL 通过

#### Scenario: 双摄执行链路

- **WHEN** 执行 `analysisKind=multiview` 的 Parent
- **THEN** MultiViewAnalysisExecutor SHALL 读 child 产物 → 执行 Fusion → Composer → 返回 Parent 结果

### Requirement: 新增编排字段兼容读取

`AnalysisJobSummary` MUST 支持新增字段（`analysisKind` / `visibility` / `parentJobId` / `analysisScope` / `orchestrationStatus` / `fusionRunId` / `sourceJobs` / `viewRuns` / `referenceViewId` / `clipStartMs` / `clipEndMs`）的历史兼容读取：缺省按 `single_view` / `public` / `none` 解析，不破坏既有任务。

#### Scenario: 历史任务读取

- **WHEN** 读取不含新字段的历史 job
- **THEN** 系统 SHALL 按缺省值解析并正常渲染

## MODIFIED Requirements

### Requirement: Durable analysis job lifecycle

`canonicalStatus` 五态生命周期（`queued / running / succeeded / failed / canceled`）保持为唯一业务状态维度；系统 MUST 使用独立维度 `orchestrationStatus`（`none / waiting_sources / fallback_ready / fusion_ready / fusing / composing / completed`）表达多视角 Parent 的编排，MUST NOT 将 `waiting_sources` 等编排状态塞入 `canonicalStatus`。创建任务时 MUST 持久化分析窗口（`clipStartMs` / `clipEndMs`）与 `analysisKind`，使子任务执行时能拿到窗口。

#### Scenario: multiview Parent 等待 child

- **WHEN** 一个 `analysisKind=multiview` 的 Parent 已创建且两个 child 未全部完成
- **THEN** 该 Parent SHALL 保持 `canonicalStatus=queued`、`orchestrationStatus=waiting_sources`
- **AND** 该状态 SHALL 在 `queued` 兼容语义下可被取消

#### Scenario: 取消等待中的 Parent

- **WHEN** 用户取消 `waiting_sources` 的 Parent
- **THEN** 该 Parent SHALL 置 `canonicalStatus=canceled`
- **AND** 编排层 SHALL 级联取消其 owned 非终态 children

#### Scenario: 分析窗口落盘

- **WHEN** 创建分析任务携带 `clipStartMs/clipEndMs`
- **THEN** 任务摘要 SHALL 持久化该窗口
- **AND** 子任务执行时 SHALL 按其窗口限定的帧范围分析，而非整场视频

### Requirement: Stage telemetry

阶段遥测保持既有 `AnalysisStage` 结构。`MultiViewAnalysisExecutor` 返回的 `AnalysisPipelineResult.stages` MUST 表达聚合阶段（素材与同步检查 / A 机位视觉分析 / B 机位视觉分析 / 多视角融合 / 指标重算 / 报告），子级细粒度进度 MUST 经 Parent `viewRuns` 暴露（运行中惰性刷新为 child 实时进度），MUST NOT 铺 24 行单摄阶段。

#### Scenario: Parent 聚合阶段

- **WHEN** 前端轮询 multiview Parent 摘要
- **THEN** Parent `stages` SHALL 展示聚合阶段
- **AND** `viewRuns`（`cam_1 / cam_2` 各自的 `status / stage / progress`）SHALL 提供两路子进度，运行中也反映 child 实时进度
