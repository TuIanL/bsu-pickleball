## Why

录制期间的 `rally_start` 发生在用户启动分析任务并确认 P1–P4 之前；因此现场计分事件不能引用未来才产生的分析名册。现有系统也未将发球、比分、换边和正式自动回合窗口组合为可审计的任务级事实链，后续基于队伍的分析容易被改分、撤销或名册编辑污染。

本变更先建立独立、可重放且任务绑定的分析回合上下文，作为厨房线到位率及后续接发、第三拍和协同分析的可靠前提。

## What Changes

- 录制时在有效 `rally_start` 同一事务中生成仅含比赛事实的 `RallyScoringSnapshot`：发球队、回合开始前比分、计分规则、来源 action/event 与 revision；不得保存或推断 P1–P4 名册。
- 在分析任务创建前以 bootstrap 辅助用户确认 P1–P4；冻结包含身份连续性证据的 `AnalysisRosterSnapshot`，并建立 bootstrap 到正式 canonical Player 的 binding audit。
- 新建与计分 FSM 分离、可由 `side_change` ledger 回放的 `CourtEndProjection`；它只描述 Team A/B 在每个时点的 near/far 端位。
- 在 AnalysisJob 创建时，由 scoring snapshot、roster snapshot 与 court-end projection 合成 job-bound `AnalysisRallyContextSnapshot`，记录来源 hash；后续名册编辑或计分修正不得静默改写已绑定 Job。
- 为正式自动窗口增加有优先级的绑定策略：直接 CaptureSegment 链路优先，其次直接 start-event 链路，再其次唯一时间匹配；歧义时明确 unavailable。
- canonical Rally/Shot 与 Job 签名只消费上述冻结上下文；`initial_side` 保持物理诊断语义，不再充当正式 Team A/B 身份。

## Capabilities

### New Capabilities

- `analysis-roster-confirmation`: 预检确认、不可变分析名册及 bootstrap-to-formal identity audit。
- `serving-rally-context`: 录制计分事实、独立端位投影及任务绑定的分析回合上下文。

### Modified Capabilities

- `rally-scoring-fsm`: 在 `rally_start` 原子封存计分事实，但不扩展计分状态承担空间端位。
- `formal-match-state-segmentation`: 正式窗口按可审计优先级绑定 job-bound 分析回合上下文。
- `analysis-job-orchestration`: Job 签名与执行记录绑定冻结的 roster/context 输入，并保持历史兼容。
- `shot-rally-event-metrics`: canonical Rally/Shot 传递正式 Team A/B 与分析回合上下文引用。

## Impact

- 后端：计分 action 投影、CaptureTake/AnalysisJob 数据模型与迁移、bootstrap、formal tracking identity audit、window binding 和 canonical artifact 组装。
- 前端：分析任务创建前的名册确认与端位确认，以及明确的预检失败/跳过状态。
- 依赖关系：`add-serving-team-kitchen-line-arrival` 必须消费本变更发布的 `AnalysisRallyContextSnapshot`，而不能直接读取当前 LiveCodingState 或可编辑名册。
