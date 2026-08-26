## ADDED Requirements

### Requirement: Semantic evidence ledger preserves source and freshness

系统 SHALL 为每个 canonical tick 生成可序列化的 semantic evidence ledger；每条证据 SHALL 包含稳定 `evidence_id`、canonical timestamp、证据类型、来源 authority、confidence、freshness 或有效时间范围、摘要 payload 和 provenance。后续聚合或状态转换不得覆盖原始证据。

#### Scenario: Multi-source evidence is recorded on one tick

- **WHEN** 同一 canonical tick 同时获得时间线、球员运动、ServeStartDetector 和球候选证据
- **THEN** 系统 SHALL 为每类证据保留独立记录和来源
- **AND** `MatchSemanticSnapshot` SHALL 引用这些 evidence id 并保存聚合摘要

#### Scenario: Stale evidence is not treated as current

- **WHEN** 某条视觉或 ServeStartDetector 证据超过其 `fresh_until_ms`
- **THEN** 仲裁器 SHALL 将该证据标记为 stale 或降低其有效性
- **AND** stale evidence MUST NOT 单独确认新的 rally boundary

#### Scenario: Test-injected evidence remains identifiable

- **WHEN** 回放 fixture 注入 serve candidate 或人工边界证据
- **THEN** provenance SHALL 标记其为 fixture/manual input
- **AND** 诊断 MUST NOT 将其描述为 detector 或 ServeStartDetector 的真实输出

### Requirement: Boundary adjudication requires stable corroboration

系统 SHALL 基于多证据 corroboration、最小持续窗口、phase transition hysteresis 和 contradiction handling 产生 `pending_start`、`pending_end`、`confirmed_start` 或 `confirmed_end`；单一弱证据不得直接执行正式 boundary action。

#### Scenario: Single weak signal creates pending end only

- **WHEN** 仅出现一次球丢失、bounce 候选、碰网候选或球员停止移动
- **THEN** 系统 SHALL 最多进入 `RALLY_END_CANDIDATE` 或 `pending_end`
- **AND** SHALL NOT 封存 formal segment、reset tracker 或写入比分结果

#### Scenario: Corroborated end confirms after the configured window

- **WHEN** 非比赛时间线/活动变化、球路终止或其他配置证据在最小持续窗口内形成足够 corroboration
- **THEN** 系统 SHALL 生成 `confirmed_end`
- **AND** 仅在权威来源与 Enforced rollout 条件同时满足时执行 formal boundary action

#### Scenario: Contradictory evidence prevents premature confirmation

- **WHEN** pending end 窗口内重新出现有效球运动、连续轨迹或明确比赛活动
- **THEN** 系统 SHALL 保留或恢复 `RALLY_ACTIVE`
- **AND** SHALL 记录 contradiction evidence 与未确认原因

### Requirement: Active rally rescue is explicit and bounded

系统 SHALL 支持在 boundary 尚未确认时撤销 pending end 并生成 `rescued_active` 结果；rescue 必须满足配置的球运动、轨迹连续性和球员活动联合条件，并不得复用已经封存的 formal segment。

#### Scenario: Valid moving ball rescues a pending end

- **WHEN** 当前为 `pending_end`
- **AND** 候选在预测门内连续出现且球员活动满足 active-play 条件
- **THEN** 系统 SHALL 清除 pending end 计数并记录 `rescued_active`
- **AND** 当前 formal segment SHALL 保持可继续消费

#### Scenario: Rescue is unavailable after authoritative reset

- **WHEN** manual/corrected boundary 已确认且 Enforced rollout 已执行 `seal_formal_segment` 与 `reset_tracker_for_next_rally`
- **THEN** 后续球候选 MUST NOT 通过 rescue 追加到旧 segment
- **AND** 只能在新的 `rally_start`/`RALLY_ACTIVE` action 后创建新 segment

### Requirement: Boundary evaluation artifact is replayable

系统 SHALL 为启用语义分析的任务提供可选 `ball_semantic_boundary_eval.v1` artifact，记录 policy/rollout 版本、每 tick phase、evidence 摘要、pending/confirmed 状态、boundary action、formal candidate before/after、segment id、fallback 和异常信息。

#### Scenario: Replay produces deterministic adjudication

- **WHEN** 使用相同 canonical tick、evidence ledger、配置版本和 rollout 输入重复回放
- **THEN** 每个 tick 的 adjudication、boundary action id、segment id 和 candidate counts SHALL 一致

#### Scenario: Evaluation compares reference boundaries

- **WHEN** fixture 或人工标注提供回合开始/结束参考窗口
- **THEN** artifact SHALL 输出 boundary precision、recall、确认延迟、误封存率、跨段污染率和真实球路误抑制率
- **AND** 指标 SHALL 区分 Shadow 建议与 Enforced 实际结果

#### Scenario: Artifact remains optional and failure-safe

- **WHEN** 评估 artifact 写入失败或没有参考标签
- **THEN** 主球检测、球跟踪、球路和球员分析 SHALL 继续运行
- **AND** artifact status/detail SHALL 标记 unavailable、partial 或 failed 的具体原因

### Requirement: Calibration replay uses versioned cases and no online learning

系统 SHALL 提供包含 2026-07-20 双摄代表窗口和合成边界案例的版本化 replay fixture；校准结果 SHALL 通过配置/policy version 记录，不得在分析运行中自动学习或修改生产阈值。

#### Scenario: Real take coverage includes boundary failure modes

- **WHEN** 回放校准集
- **THEN** 案例 SHALL 覆盖捡球/准备、发球预热、正常回合、球短时丢失、碰网候选、回合结束和下一回合重捕获

#### Scenario: Model file remains unchanged

- **WHEN** 执行语义边界校准和回放
- **THEN** 系统 SHALL 继续使用现有 detector adapter
- **AND** SHALL NOT 修改或替换 `models/ball/tennis-ball.pt`
