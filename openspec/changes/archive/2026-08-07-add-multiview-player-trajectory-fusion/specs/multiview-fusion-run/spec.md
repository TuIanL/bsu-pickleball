# multiview-fusion-run Specification

## Purpose

定义 `MultiViewFusionRun` 这一运行实体：它负责等待两路 source AnalysisJob 完成、持有 view inputs、执行融合管线、并把 `fused_player_trajectory.v1` 等融合产物挂在自己的产物目录下。该实体解决"谁等待、谁执行、产物存在哪"的所有权问题。

## ADDED Requirements

### Requirement: 运行实体所有权

系统 MUST 提供 `MultiViewFusionRun` 作为多视角分析的所有者。`MultiViewFusionRun` MUST 记录 `capture_take_id / source_analysis_job_ids[] / view_inputs[] / sync_calibration_ref / canonical_frame_ref`，并 MUST 将融合产物（如 `fused_player_trajectory.v1`）挂在其自身产物目录，MUST NOT 挂到任一 cam_1/cam_2 AnalysisJob 或 CaptureTake 上。

#### Scenario: 产物归属

- **WHEN** `MultiViewFusionRun` 完成融合
- **THEN** `fused_player_trajectory.v1` SHALL 写入该 Run 的产物目录
- **AND** 产物 SHALL 归属于 Run 自身，而非 cam_1/cam_2 Job 或 CaptureTake

#### Scenario: Run 标识

- **WHEN** 系统需要引用一次多视角分析
- **THEN** 系统 SHALL 使用 `MultiViewFusionRun` 标识
- **AND** 该标识 SHALL 可追溯 `capture_take_id` 与 `source_analysis_job_ids`

### Requirement: 等待 source job 完成

`MultiViewFusionRun` MUST 在启动融合前等待全部 `source_analysis_job_ids` 对应 AnalysisJob 完成。任一路 source job 失败或不存在时，Run MUST 按 job-level fallback 处理，不生成融合产物。

#### Scenario: 双路就绪

- **WHEN** cam_1 与 cam_2 两个 AnalysisJob 均已 completed
- **THEN** `MultiViewFusionRun` SHALL 进入融合执行
- **AND** 输入 SHALL 基于两路真实单视角分析产物

#### Scenario: 单路未完成

- **WHEN** 任一 source job 未完成、失败或不存在
- **THEN** `MultiViewFusionRun` SHALL NOT 生成 fused artifact
- **AND** 下游 SHALL 继续消费原单视角 artifact

### Requirement: 融合执行管线

`MultiViewFusionRun` MUST 按固定顺序执行融合管线：Canonical Timeline → `GlobalTrackFilter.predict(t)` → `CrossViewPlayerAssociator` → `ViewIntrinsicQuality` → `PairConsistency` → `PlayerPositionFusion`（conflict gate）→ `GlobalTrackFilter.update()`。管线的全局预测 MUST 统一来自 `GlobalTrackFilter.predict(t)`。

#### Scenario: 管线顺序

- **WHEN** Run 执行一次融合
- **THEN** 各阶段 SHALL 按上述固定顺序执行
- **AND** 关联/融合所引用的 global prediction SHALL 来自 `GlobalTrackFilter.predict(t)`

#### Scenario: 单一预测来源

- **WHEN** 某时刻两路无有效观测
- **THEN** 是否输出预测点 SHALL 由 `GlobalTrackFilter` 决定
- **AND** `PlayerPositionFusion` SHALL NOT 独立产生预测状态

### Requirement: Job-level 与 Sample-level Fallback 分离

`MultiViewFusionRun` MUST 区分两种 fallback：**job-level**（Run 无法合法启动：任一 view `court_orientation=None` 或 sync authority `unavailable` → 不生成 fused artifact，下游继续消费单摄 artifact）；**sample-level**（Run 合法但某时刻某路 `unavailable` → 该 fused sample `fusion_status = single_view_fallback`，Run 继续）。两种语义 MUST NOT 混用。

#### Scenario: job-level 不生成产物

- **WHEN** 任一 view `court_orientation = None` 或 sync authority `unavailable`
- **THEN** Run SHALL 判定为 job-level fallback
- **AND** Run SHALL NOT 生成 fused artifact

#### Scenario: sample-level 继续运行

- **WHEN** Run 合法，但某时刻某路观测 `unavailable`
- **THEN** 该 fused sample SHALL 置 `fusion_status = single_view_fallback`
- **AND** Run SHALL 继续处理其余时刻

### Requirement: 可诊断与可回滚

`MultiViewFusionRun` 的执行 MUST 可诊断（产出含 orientation normalization / frame mapping errors / association decisions / view quality scores / view disagreement / fallback & conflict counts 的 diagnostics），且删除 Run MUST 不改变任何现有单视角 artifact（可回滚）。

#### Scenario: 诊断产出

- **WHEN** Run 执行结束
- **THEN** Run SHALL 产出 diagnostics artifact
- **AND** diagnostics SHALL 记录归一化、映射、关联、质量、分歧与 fallback/conflict 计数

#### Scenario: 回滚不损单摄

- **WHEN** 删除某 `MultiViewFusionRun`
- **THEN** cam_1/cam_2 的现有单视角 AnalysisJob 与 artifact SHALL 保持不变
