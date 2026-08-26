## MODIFIED Requirements

### Requirement: Semantic state transitions

系统 SHALL 支持 `UNKNOWN`、`NON_PLAY_CONFIRMED`、`PRE_SERVE`、`SERVE_ARMED`、`RALLY_ACTIVE`、`RALLY_END_CANDIDATE` 和 `POST_RALLY` 状态，并以结构化证据驱动转换；当权威语义状态发生边沿变化时，系统 SHALL 生成幂等的 boundary action，供正式球链封存、重置或重新捕获使用。

#### Scenario: 权威非比赛进入正式边界

- **WHEN** 当前处于 `RALLY_ACTIVE`、`PRE_SERVE` 或 `SERVE_ARMED`
- **AND** 当前 canonical 时间命中 manual/corrected 的 `non_play` 或 `rally_end` 边界
- **THEN** 系统 SHALL 转入 `NON_PLAY_CONFIRMED` 或 `POST_RALLY`
- **AND** SHALL 生成一次 `seal_formal_segment` 与 `reset_tracker_for_next_rally` boundary action
- **AND** 同一 canonical boundary 不得重复生成或重复执行 reset

#### Scenario: 非比赛进入准备发球

- **WHEN** 当前处于 `NON_PLAY_CONFIRMED` 或 `POST_RALLY`
- **AND** 球员站位、静止基线和准备活动形成发球候选
- **THEN** 系统 SHALL 转入 `PRE_SERVE` 或记录等价的准备发球候选
- **AND** SHALL 生成 `warm_reacquire` boundary action
- **AND** SHALL NOT 直接将手持静止球确认成正式球观察

#### Scenario: 发球捕获已就绪

- **WHEN** 当前处于 `PRE_SERVE`
- **AND** server/receiver 位置与 ServeStartDetector 证据满足配置的 arm 条件
- **THEN** 系统 SHALL 转入 `SERVE_ARMED`
- **AND** SHALL 生成 `serve_reacquire` action，允许发球相关区域进入渐进式捕获

#### Scenario: 权威回合开始打开正式球段

- **WHEN** 当前 canonical 时间命中 manual/corrected 的 `rally_start`
- **OR** 当前处于 `SERVE_ARMED` 且出现满足配置门槛的发球运动证据
- **THEN** 系统 SHALL 转入 `RALLY_ACTIVE`
- **AND** SHALL 生成一次 `open_formal_segment` action
- **AND** SHALL 记录触发该转换的 evidence

#### Scenario: 仅凭单一弱证据不能结束回合

- **WHEN** 出现一次球丢失、一次弹地候选、一次碰网候选或一次球员停止移动
- **THEN** 系统 SHALL 最多进入 `RALLY_END_CANDIDATE`
- **AND** SHALL NOT 自动生成正式回合封存 action、确认回合结束或写入比分结果

### Requirement: Authority and inference layering

系统 SHALL 区分 authority 与 evidence：人工或 corrected 时间线在显式 Enforced rollout 开启时可以产生正式球链硬约束，algorithm 或视觉推断只能产生软策略；语义策略不确定或 provider 失败时 SHALL 使用 `UNKNOWN` 回退。

#### Scenario: 权威非比赛窗口抑制正式搜索

- **WHEN** 当前时间位于人工或 corrected 的 `non_play`、`rally_end` 或等价非比赛窗口
- **AND** 当前 take/job 显式启用 Enforced rollout
- **AND** policy mode 为 `enforced`
- **THEN** 策略 SHALL 禁止新球候选进入正式 tracker 输出
- **AND** SHALL 生成一次边界封存/重置 action
- **AND** SHALL 保留原始 detector 候选及抑制原因供诊断

#### Scenario: Enforced rollout 未启用

- **WHEN** 当前时间具有 manual/corrected 语义证据
- **AND** 当前 take/job 未启用 Enforced rollout或 policy mode 为 `shadow`
- **THEN** 系统 SHALL 记录建议的 suppression 和 boundary action
- **AND** 正式球轨迹 SHALL 保持第一阶段兼容行为

#### Scenario: 算法推断非比赛状态

- **WHEN** 当前非比赛判断仅来自球员静止、站位或活动变化
- **THEN** 策略 SHALL 将其记录为 algorithm evidence
- **AND** 在没有足够稳定证据时 MUST NOT 以硬门完全关闭正式球链或重置 tracker

#### Scenario: 语义 provider 失败

- **WHEN** 时间线 provider 或语义证据构建发生可恢复异常
- **THEN** 策略 SHALL 进入 `UNKNOWN`
- **AND** SHALL 不生成硬 reset action
- **AND** 现有球检测、球跟踪和球员分析 SHALL 继续运行

### Requirement: Shadow mode preserves formal ball results

系统 SHALL 支持 Shadow Mode 和 Enforced Mode；Shadow Mode 计算完整语义策略但不改变现有正式球轨迹、球事件、v3/v4 分段或球员分析结果，Enforced Mode 仅在满足权威来源和 rollout 条件时改变正式候选生命周期。

#### Scenario: Shadow 策略建议抑制候选

- **WHEN** Shadow Mode 判断一个候选在当前 phase 下应被抑制
- **THEN** 现有正式 pipeline SHALL 按兼容逻辑继续处理该候选
- **AND** 语义诊断 SHALL 记录 shadow decision、reason、candidate id 和对应时间
- **AND** SHALL 记录模拟 Enforced 结果但不得写入正式轨迹

#### Scenario: Enforced 权威边界生效

- **WHEN** Enforced Mode 已启用
- **AND** 当前 snapshot 的 authority 为 `manual` 或 `corrected`
- **AND** 当前 phase/action 命中正式边界条件
- **THEN** 系统 SHALL 在正式候选发布前执行对应 gate 或 boundary action
- **AND** SHALL 保留 raw candidate、formal candidate before/after 和 tracker 状态差异

#### Scenario: 关闭 rollout 后回滚

- **WHEN** take/job 关闭 Enforced rollout 或 semantic policy 配置不可用
- **THEN** 系统 SHALL 回到 Shadow/兼容球链路
- **AND** SHALL 不要求删除已有 raw candidate、语义诊断或历史轨迹 artifact

### Requirement: Raw and formal candidate layers remain distinct

系统 SHALL 将 raw detector candidate、warm/reacquire candidate、tracker-consumable candidate、formal published candidate 和 policy-suppressed candidate 作为可区分的结果层级；边界 action 只能改变后续正式消费，不得删除原始证据。

#### Scenario: 非比赛时刻出现手持球候选

- **WHEN** detector 在 `NON_PLAY_CONFIRMED` 或 `POST_RALLY` 期间输出静止球候选
- **THEN** 原始候选 SHALL 保留在语义诊断中
- **AND** Enforced 策略 SHALL 可禁止其进入正式球 tracker 输出
- **AND** 该候选 MUST NOT 仅因被策略抑制而写入静止误检黑名单

#### Scenario: 回合边界后的候选不跨段发布

- **WHEN** 已执行 `seal_formal_segment` 和 `reset_tracker_for_next_rally`
- **AND** 边界后的候选仍被 detector 输出
- **THEN** 候选 SHALL 只能进入 raw、diagnostic 或 warm/reacquire 层
- **AND** MUST NOT 追加到已封存的正式球段

#### Scenario: 未知状态出现候选

- **WHEN** phase 为 `UNKNOWN`
- **THEN** 系统 SHALL 使用既有 BallTracker 候选过滤和状态机行为
- **AND** 诊断 SHALL 标记本帧使用了兼容回退

### Requirement: Semantic policy diagnostics are replayable

系统 SHALL 为每个 canonical tick 记录可审计的语义策略诊断，至少包含时间、phase、authority、evidence 摘要、policy decision、candidate counts、suppressed counts、boundary action、tracker 状态差异和 fallback 标识。

#### Scenario: 生成 Shadow/Enforced 对照诊断

- **WHEN** Shadow 或 Enforced Mode 完成一个分析任务
- **THEN** 系统 SHALL 生成 `ball_semantic_timeline.v1` 或等价结构化 artifact
- **AND** artifact SHALL 能够按时间顺序重放 phase、policy decision、boundary action 和正式发布前后差异
- **AND** artifact SHALL 不替代现有球轨迹 artifact

#### Scenario: 双摄边界 action 可审计且幂等

- **WHEN** 双摄两路在同一 canonical tick 消费语义策略
- **THEN** 两路 SHALL 共享同一个 `boundary_action_id`、phase 和 rollout decision
- **AND** diagnostics SHALL 能区分 action 被执行一次、重复请求被忽略或因 fallback 未执行

#### Scenario: 语义阶段异常

- **WHEN** 状态转换、boundary action 或 policy evaluation 发生异常
- **THEN** 诊断 SHALL 记录异常类型和 fallback 状态
- **AND** 任务 SHALL 保留现有球检测、球路和球员分析结果（若其自身仍可用）
