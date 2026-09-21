## ADDED Requirements

### Requirement: 录制时封存不依赖名册的计分事实
系统 MUST 在有效 `rally_start` 的同一事务中创建 `RallyScoringSnapshot`，记录 `rally_id`、server_team、回合开始前比分、scoring_ruleset_version、来源 action/event id 与 revision。snapshot MUST NOT 引用 `AnalysisRosterSnapshot`、P1–P4 或分析期端位。

#### Scenario: 下一回合继承发球权
- **WHEN** 有效 rally result 已经更新 reducer 的 server_team 和比分
- **AND** 用户执行 `start_next_rally`
- **THEN** 新 scoring snapshot SHALL 固化更新后的 server_team 与比分
- **AND** 后续分析 SHALL 不得读取当前 LiveCodingState 倒推该回合

### Requirement: 端位使用独立可回放 projection
系统 SHALL 以确认的初始 A/B court end 和有效 `side_change` action 建立 `CourtEndProjection`。projection MUST 与 ScoringState 分离，且可以按 action ledger 重放。

#### Scenario: 有效换边发生
- **WHEN** 两个回合之间发生有效 `side_change`
- **THEN** projection SHALL 为其后的回合交换 Team A/B near/far
- **AND** 计分 reducer SHALL 不承担或写入端位字段

### Requirement: Job-bound 分析回合上下文
系统 SHALL 在 Job 创建时由 `RallyScoringSnapshot`、该 Job 的 `AnalysisRosterSnapshot` 与 `CourtEndProjection` 合成 `AnalysisRallyContextSnapshot`。它 MUST 保存 scoring、roster、court-end 与 context hashes，并成为该 Job 的权威来源。

#### Scenario: 后续名册编辑
- **WHEN** 用户为同一视频确认新的名册或修改可编辑来源名册
- **THEN** 已有 Job 的 context SHALL 保持不变
- **AND** 新 Job SHALL 使用新 roster/context hash，且不得重用旧 Job 的队伍结果

#### Scenario: 计分修正影响历史回合
- **WHEN** undo 或 score correction 改变某个 scoring snapshot 的有效事实
- **THEN** 系统 SHALL 重放并 supersede 受影响的 scoring/context 版本
- **AND** 已绑定 Job SHALL 保留其原 context，新分析版本才可消费修正后的 context
