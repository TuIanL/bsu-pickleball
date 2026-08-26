## ADDED Requirements

### Requirement: 比赛语义状态快照

系统 SHALL 在 canonical take time 上生成可序列化的 `MatchSemanticSnapshot`，至少包含当前 phase、phase confidence、authority、结构化 evidence、policy mode、policy decision 和 decision reason。

#### Scenario: 有权威非比赛时间线

- **WHEN** 当前 canonical 时间落在人工或 corrected 来源的 `non_play` 时间窗口内
- **THEN** 快照 SHALL 将 `authority` 标记为 `manual` 或 `corrected`
- **AND** `phase` SHALL 为 `NON_PLAY_CONFIRMED` 或等价的权威非比赛状态
- **AND** evidence SHALL 保留命中的时间线事件标识和窗口来源

#### Scenario: 没有可用语义上下文

- **WHEN** 当前 take 没有关联时间线、时间线读取失败或视觉证据不足以确定比赛阶段
- **THEN** 系统 SHALL 生成 `authority=none` 或等价快照
- **AND** `phase` SHALL 为 `UNKNOWN`
- **AND** 策略 SHALL 回退现有球搜索行为

#### Scenario: 双摄使用统一时间

- **WHEN** 两个视角在同一 canonical tick 提供球员和球候选
- **THEN** 两个视角 SHALL 共享同一个 `take_timestamp_ms` 和语义 phase
- **AND** 系统 MUST NOT 为每个视角独立推断互相冲突的比赛阶段

### Requirement: 语义状态转换

系统 SHALL 支持 `UNKNOWN`、`NON_PLAY_CONFIRMED`、`PRE_SERVE`、`SERVE_ARMED`、`RALLY_ACTIVE`、`RALLY_END_CANDIDATE` 和 `POST_RALLY` 状态，并以结构化证据驱动转换。

#### Scenario: 非比赛进入准备发球

- **WHEN** 当前处于 `NON_PLAY_CONFIRMED`
- **AND** 球员站位、静止基线和准备活动形成发球候选
- **THEN** 系统 SHALL 转入 `PRE_SERVE` 或记录等价的准备发球候选
- **AND** SHALL NOT 直接将手持静止球确认成正式球观察

#### Scenario: 发球捕获已就绪

- **WHEN** 当前处于 `PRE_SERVE`
- **AND** server/receiver 位置与 ServeStartDetector 证据满足配置的 arm 条件
- **THEN** 系统 SHALL 转入 `SERVE_ARMED`
- **AND** 球搜索策略 SHALL 允许在发球相关区域重新捕获球

#### Scenario: 发球后进入正式回合

- **WHEN** 当前处于 `SERVE_ARMED`
- **AND** 出现满足策略门槛的球运动或发球活动证据
- **THEN** 系统 SHALL 转入 `RALLY_ACTIVE`
- **AND** SHALL 记录触发该转换的 evidence

#### Scenario: 仅凭单一弱证据不能结束回合

- **WHEN** 出现一次球丢失、一次弹地候选、一次碰网候选或一次球员停止移动
- **THEN** 系统 SHALL 最多进入 `RALLY_END_CANDIDATE`
- **AND** SHALL NOT 自动确认回合结束或比分结果

### Requirement: 权威与推断策略分层

系统 SHALL 区分 authority 与 evidence：人工或 corrected 时间线可以产生硬搜索约束，algorithm 或视觉推断只能产生软策略；语义策略不确定时 SHALL 使用 `UNKNOWN` 回退。

#### Scenario: 权威非比赛窗口抑制正式搜索

- **WHEN** 当前时间位于人工或 corrected 的 `non_play` 窗口
- **AND** policy mode 为 `enforced`
- **THEN** 策略 SHALL 禁止新球候选进入正式 tracker 输出
- **AND** SHALL 保留原始 detector 候选及抑制原因供诊断

#### Scenario: 算法推断非比赛状态

- **WHEN** 当前非比赛判断仅来自球员静止、站位或活动变化
- **THEN** 策略 SHALL 将其记录为 algorithm evidence
- **AND** 在没有足够稳定证据时 MUST NOT 以硬门完全关闭正式球链

#### Scenario: 语义 provider 失败

- **WHEN** 时间线 provider 或语义证据构建发生可恢复异常
- **THEN** 策略 SHALL 进入 `UNKNOWN`
- **AND** 现有球检测、球跟踪和球员分析 SHALL 继续运行

### Requirement: Shadow Mode 不改变正式球路结果

系统 SHALL 支持 Shadow Mode，在该模式下计算完整语义策略但不改变现有正式球轨迹、球事件、v3/v4 分段或球员分析结果。

#### Scenario: Shadow 策略建议抑制候选

- **WHEN** Shadow Mode 判断一个候选在当前 phase 下应被抑制
- **THEN** 现有正式 pipeline SHALL 按兼容逻辑继续处理该候选
- **AND** 语义诊断 SHALL 记录 shadow decision、reason、candidate id 和对应时间

#### Scenario: Shadow 策略建议重新捕获

- **WHEN** Shadow Mode 判断当前进入 `SERVE_ARMED` 且应扩大或改变球搜索范围
- **THEN** 系统 SHALL 记录建议的 search scope 和 policy parameters
- **AND** SHALL NOT 重复运行 detector 或产生第二份正式球轨迹

### Requirement: 原始候选与正式候选分离

系统 SHALL 将 raw detector candidate、tracker-consumable candidate、formal published candidate 和 policy-suppressed candidate 作为可区分的结果层级。

#### Scenario: 非比赛时刻出现手持球候选

- **WHEN** detector 在 `NON_PLAY_CONFIRMED` 期间输出静止球候选
- **THEN** 原始候选 SHALL 保留在语义诊断中
- **AND** enforced 策略 SHALL 可禁止其进入正式球 tracker 输出
- **AND** 该候选 MUST NOT 仅因被策略抑制而写入静止误检黑名单

#### Scenario: 未知状态出现候选

- **WHEN** phase 为 `UNKNOWN`
- **THEN** 系统 SHALL 使用既有 BallTracker 候选过滤和状态机行为
- **AND** 诊断 SHALL 标记本帧使用了兼容回退

### Requirement: 双摄球处理遵守 prepare/commit 时序

系统 SHALL 为双摄 canonical 球处理提供 prepare/commit 语义：prepare 阶段每视角每 tick 至多调用一次 detector 并缓存候选，语义评估可以消费当 tick 的球员上下文，commit 阶段每视角 tracker 至多更新一次。

#### Scenario: 当 tick 球员上下文参与策略

- **WHEN** canonical tick 的两路球候选已经 prepare 完成
- **AND** 当 tick 的球员感知、身份或位置上下文已经完成 barrier
- **THEN** `MatchSemanticSnapshot` SHALL 可以使用这些上下文
- **AND** tracker SHALL 只在 policy evaluation 之后消费候选

#### Scenario: detector 单次调用

- **WHEN** 一个视角在一个 canonical tick 同时需要本地 tracker、双摄关联和语义 Shadow 诊断
- **THEN** detector SHALL 只调用一次
- **AND** 所有消费者 SHALL 共享同一份基础候选集合

#### Scenario: 单摄兼容路径

- **WHEN** 单摄 pipeline 没有 prepare/commit 运行时或没有语义快照
- **THEN** 系统 SHALL 保留现有 `BallTracker.update(frame)` 或等价兼容行为
- **AND** 语义策略不可用不得阻断单摄球员分析

### Requirement: 语义策略诊断可回放

系统 SHALL 为每个 canonical tick 记录可审计的语义策略诊断，至少包含时间、phase、authority、evidence 摘要、policy decision、candidate counts、suppressed counts 和 fallback 标识。

#### Scenario: 生成 Shadow 诊断

- **WHEN** Shadow Mode 完成一个分析任务
- **THEN** 系统 SHALL 生成 `ball_semantic_timeline.v1` 或等价结构化 artifact
- **AND** artifact SHALL 能够按时间顺序重放 phase 和 policy decision
- **AND** artifact SHALL 不替代现有球轨迹 artifact

#### Scenario: 语义阶段异常

- **WHEN** 状态转换或 policy evaluation 发生异常
- **THEN** 诊断 SHALL 记录异常类型和 fallback 状态
- **AND** 任务 SHALL 保留现有球检测、球路和球员分析结果（若其自身仍可用）
