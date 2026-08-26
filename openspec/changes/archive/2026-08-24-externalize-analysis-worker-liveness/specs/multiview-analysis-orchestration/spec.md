## MODIFIED Requirements

### Requirement: AnalysisJob 编排字段

系统 MUST 为 `AnalysisJobSummary` 保留现有编排字段，并允许 `canonicalStatus` 使用 `queued / running / succeeded / failed / canceled / interrupted`。`interrupted` 表示 Parent 或 child 的 Worker 执行失联；等待 child 的 Parent 在 child 尚未完成时仍保持 `canonicalStatus=queued` 和 `orchestrationStatus=waiting_sources`。任务摘要的 `stages` MUST 根据 `executionMode` 使用规范化阶段图；`viewRuns` 只有在存在真实 dedicated child 或内部 `ViewRun` 时才返回非空内容。

#### Scenario: 历史任务读取兼容

- **WHEN** 读取不含新字段的历史 `AnalysisJobSummary`
- **THEN** 系统 SHALL 按 `analysisKind=single_view`、`visibility=public`、`orchestrationStatus=none` 缺省解析
- **AND** 不得因缺字段而解析失败或改变既有渲染

#### Scenario: 双摄任务创建

- **WHEN** 用户发起一次双摄协同分析
- **THEN** 系统 SHALL 创建一个 `analysisKind=multiview` 的 public Parent，初始 `canonicalStatus=queued, orchestrationStatus=waiting_sources`
- **AND** Parent SHALL 根据其 `executionMode` 选择对应的顶层阶段图，而不是复用单摄阶段后追加双摄阶段

#### Scenario: interrupted child is represented

- **WHEN** 一个 multiview child 因 Worker heartbeat 超时进入 `canonicalStatus=interrupted`
- **THEN** Parent 的 `viewRuns` SHALL 暴露该机位的 interrupted/lost 状态和最后已知进度
- **AND** Parent SHALL NOT 继续把该 child 当作普通 running child

### Requirement: MultiViewAnalysisCoordinator 事件驱动编排

系统 MUST 提供 `MultiViewAnalysisCoordinator` 负责 Parent ↔ Source Job A/B ↔ `MultiViewFusionRun` 的编排：创建 Parent + 两个 child、监听 child completion/interruption、推进 Parent 编排状态。Parent MUST NOT 持有“被 claim 后 while 等待 child”的逻辑。

#### Scenario: 双路完成推进 fusion_ready

- **WHEN** cam_1 与 cam_2 两个 child 均已 completed
- **THEN** Coordinator SHALL 把 Parent 推进到 `orchestrationStatus=fusion_ready`
- **AND** Parent SHALL 随后可被 `claim_next` 领取

#### Scenario: 单路失败或失联推进 fallback_ready

- **WHEN** 一个 child completed、另一个 child failed、canceled 或 interrupted
- **THEN** Coordinator SHALL 把 Parent 推进到 `orchestrationStatus=fallback_ready`
- **AND** Parent SHALL 仍可被 claim，并按确定性单视角降级规则执行

#### Scenario: 双路失败或失联 Parent 终止

- **WHEN** cam_1 与 cam_2 两个 child 均 failed、canceled 或 interrupted
- **THEN** Parent SHALL 被置为明确的 failed/interrupted terminal 状态
- **AND** Parent SHALL 不得继续停留在 `waiting_sources`

### Requirement: 应用启动 reconciliation

应用启动后，Coordinator MUST 对账扫描 `analysisKind=multiview AND canonicalStatus not terminal`，并在 Worker liveness recovery 后按 child 终态推进 Parent。至少一路 child 仍有新鲜 lease 时保持等待；child 已 interrupted 时按失败型终态参与 fallback/failed 判定；`fusion_ready / fallback_ready` 且无 Worker 所有者的 Parent 保持 queued 等待 claim。

#### Scenario: 重启后 Parent 恢复

- **WHEN** 进程重启，Parent 处于 `waiting_sources` 且两个 child 已完成
- **THEN** reconciliation SHALL 把 Parent 推进到 `fusion_ready`
- **AND** 该 Parent SHALL 可被正常 claim 执行

#### Scenario: child heartbeat expired during restart

- **WHEN** 重启时 child heartbeat 已过期
- **THEN** Worker recovery SHALL 先将 child 标记为 interrupted
- **AND** Coordinator SHALL 随后把 Parent 推进到 fallback_ready、failed 或 interrupted 的稳定状态
- **AND** Parent SHALL 不得无限显示等待 child
