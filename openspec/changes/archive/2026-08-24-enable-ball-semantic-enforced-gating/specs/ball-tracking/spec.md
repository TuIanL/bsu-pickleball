## ADDED Requirements

### Requirement: Authoritative semantic gating controls formal tracker lifecycle

当 take/job 显式启用 Enforced rollout，且 canonical semantic snapshot 来自 manual/corrected 权威时间线时，球跟踪 SHALL 在正式候选发布边界执行语义 gate 和 lifecycle action；Shadow、UNKNOWN、algorithm authority 或 provider 失败 SHALL 保持 fail-open 兼容行为。

#### Scenario: 权威非比赛封存当前正式球段

- **WHEN** 当前时间命中 manual/corrected 的 `non_play` 或 `rally_end`
- **AND** Enforced rollout 已启用
- **THEN** tracker SHALL 在该边界封存当前 formal trajectory segment
- **AND** SHALL 禁止边界后的新候选进入已封存段或正式 overlay
- **AND** SHALL 保留 raw candidate、suppression reason 和 boundary metadata

#### Scenario: Tracker reset 只在边界边沿执行一次

- **WHEN** semantic phase 从 active/pre-serve 进入 `NON_PLAY_CONFIRMED` 或 `POST_RALLY`
- **THEN** tracker SHALL 清理预测位置、暂态候选、连续性计数和本回合 formal state
- **AND** 同一 `boundary_action_id` 的后续 tick MUST NOT 重复 reset 或重复封存
- **AND** job 级语义诊断和 raw candidate history SHALL 保留

#### Scenario: Semantic suppression does not pollute stationary blacklist

- **WHEN** 候选仅因 authoritative semantic gate 被抑制
- **THEN** tracker SHALL NOT 增加该候选的 stationary false-positive blacklist 计数
- **AND** 该候选 SHALL 可在 diagnostics 中标记为 `policy_suppressed`

#### Scenario: Unknown or algorithm context fails open

- **WHEN** snapshot phase 为 `UNKNOWN`、authority 为 `algorithm/none` 或 semantic provider 失败
- **THEN** tracker SHALL 继续使用既有连续性、物理门、预测和黑名单逻辑
- **AND** SHALL NOT 因语义上下文缺失而 reset 或禁止正式输出

### Requirement: Serve reacquisition is separated from formal publication

球跟踪 SHALL 在 `PRE_SERVE` 和 `SERVE_ARMED` 阶段支持 warm/reacquire 路径；手持静止球或单帧弱候选不得直接成为正式球点，只有满足运动、连续性、发球区域或权威回合开始条件的候选才可进入正式发布。

#### Scenario: Prepare serve ignores stationary handheld candidate

- **WHEN** semantic phase 为 `PRE_SERVE`
- **AND** detector 输出位于球员手部/身体附近且在连续 tick 中基本静止的候选
- **THEN** tracker SHALL 将候选保留为 raw 或 warm diagnostic
- **AND** SHALL NOT 将其直接发布为 formal trajectory sample

#### Scenario: Armed serve permits progressive reacquisition

- **WHEN** semantic phase 为 `SERVE_ARMED`
- **AND** 候选满足配置的发球区域、运动变化或连续性门槛
- **THEN** tracker SHALL 允许候选进入 reacquire/tracker path
- **AND** formal publish SHALL 仅在候选满足正式发布条件或命中权威 `rally_start` 后生效

#### Scenario: Rally start opens a new formal segment

- **WHEN** canonical semantic context 进入 `RALLY_ACTIVE`
- **AND** 已执行 `open_formal_segment`
- **THEN** 后续通过 tracker 质量门的候选 SHALL 进入新的 formal segment
- **AND** 新 segment MUST NOT 复用上一回合的 segment id 或预测历史

### Requirement: Dual-view semantic boundary application is consistent

双摄球处理 SHALL 在同一个 canonical tick 使用一个 `MatchSemanticSnapshot`、一个 `BallSearchDecision` 和一个 boundary action；两路 tracker 各自消费候选，但不得独立重算 phase、重复封存或重复 reset。

#### Scenario: Both views share one boundary action

- **WHEN** 双摄 canonical tick 命中权威 semantic boundary
- **THEN** 两个视角 SHALL 使用同一 `boundary_action_id` 和 `take_timestamp_ms`
- **AND** formal publish gate SHALL 在两路 commit 前生效
- **AND** 两路 SHALL 各自保留 raw/formal before-after diagnostics

#### Scenario: One view is missing at the boundary

- **WHEN** 一个视角在 semantic boundary tick 缺帧或为 `available_extrapolated`
- **THEN** 缺失视角 SHALL 不运行新的 detector/tracker 输入
- **AND** joint semantic boundary SHALL 仍只执行一次
- **AND** 另一可用视角不得因此创建第二个 phase 或第二个 segment
