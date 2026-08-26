## Context

当前单摄和双摄球链路已经具备 detector、候选过滤、BallTracker、轨迹点、弹地候选和球侧击球候选，但这些组件默认持续运行，不知道当前是否处于比分结束、捡球、准备发球或正式回合。

双摄 canonical 运行时目前在当 tick 的球员感知前调用球 detector/tracker；球员感知本身已经具备 prepare、same-tick barrier、complete 和 global association 的阶段划分。与此同时，时间线已经能够表达 `non_play`、`rally_start`、`rally_end` 等比赛语义，但这些信息尚未成为球搜索策略的输入。

本变更的约束是：不修改球体识别模型文件，不在第一阶段确认击球者、不确认回合结束、不自动判分，并且在语义数据不可用时保持现有球链路可用。

## Goals / Non-Goals

**Goals:**

- 建立统一的 `MatchSemanticSnapshot`，在 canonical take time 上表达比赛阶段、权威来源、视觉证据和置信度。
- 建立独立于 `BallTracker` 的 `BallSearchPolicy`，决定当前是否搜索、是否允许 tracker 更新、是否允许候选进入正式球链，以及是否只保留诊断证据。
- 支持 `UNKNOWN` 回退、权威时间线硬约束、视觉推断软约束和 Shadow Mode。
- 覆盖 `NON_PLAY`、发球准备、发球捕获、正式回合和回合结束候选等阶段。
- 为双摄建立 `prepare_tick` → 球员上下文/语义评估 → `commit_tick` 的时序契约，保证 detector 每视角每 tick 一次、tracker 每视角每 tick 至多一次。
- 输出可回放、可比较的语义策略诊断，用于衡量非比赛误检减少和真实发球捕获是否受损。

**Non-Goals:**

- 不修改 detector 模型权重、类别定义或模型文件。
- 不在本变更中实现正式的球员击球归因、击球序列校验、网球事件、出界判定、回合结束确认或比分 FSM。
- 不用单个“球员开始移动”证据直接确认发球或回合结束。
- 不删除被语义策略抑制的原始 detector 候选。
- 不要求第一阶段立刻关闭非比赛时刻的 detector；Shadow Mode 下 detector 可以继续运行以获得对照证据。

## Decisions

### 1. 语义层独立于 BallTracker

新增策略层放在 detector/candidate filter 与 tracker 正式更新之间。`BallTracker` 继续负责局部视觉连续性、预测、物理门和自身状态；`BallSearchPolicy` 负责比赛阶段、搜索开关、候选发布级别和语义原因。

这样可以避免把“比赛是否进行中”“是否应该接受手持球”“是否已经进入下一分”等全局规则塞入局部 tracker，也保留单摄旧调用 `BallTracker.update(frame)` 的兼容路径。

备选方案是直接扩展 `BallTracker` 的内部状态机，但这会使 tracker 同时承担视觉状态和比赛状态，难以在单摄、双摄、人工时间线和缺失时间线之间复用，因此不采用。

### 2. Authority 与 Evidence 分离

`MatchSemanticSnapshot` 至少包含：

- `take_timestamp_ms`、`phase`、`phase_confidence`；
- `authority`: `manual`、`corrected`、`algorithm`、`none`；
- `evidence`: 时间线窗口、球员静止/移动、站位、发球候选、最近球事件等结构化证据；
- `policy_mode`: `shadow` 或 `enforced`；
- `policy_decision` 与 `decision_reason`。

人工或修正时间线是硬约束来源；算法推断只产生软策略。没有可用权威或证据不足时进入 `UNKNOWN`，并回退现有行为，防止语义层误判造成系统性漏球。

### 3. 状态机采用保守转换和 UNKNOWN 回退

状态采用：

```text
UNKNOWN
NON_PLAY_CONFIRMED
PRE_SERVE
SERVE_ARMED
RALLY_ACTIVE
RALLY_END_CANDIDATE
POST_RALLY
```

`NON_PLAY_CONFIRMED` 只能由权威非比赛时间线或足够稳定的多证据组合进入；算法性的静止、捡球、球员离场等只能作为候选或软证据。`PRE_SERVE` 和 `SERVE_ARMED` 允许以球员站位、发球准备和 ServeStartDetector 证据逐级增强搜索，但不把手持静止球直接发布为正式球观察。

`RALLY_END_CANDIDATE` 只表示需要观察后续证据，第一阶段不得自动关闭回合或写入比分结果。

### 4. 正式输出与原始证据分离

每个 tick 的策略结果分为：

- 原始候选：模型输出及基础过滤结果，始终可进入诊断；
- 跟踪候选：允许 tracker 消费的候选；
- 正式发布候选：允许进入现有球轨迹/overlay 的候选；
- 策略抑制记录：候选本身不删除，只记录阶段、策略、原因和时间。

Shadow Mode 下正式发布候选仍完全采用旧逻辑，新策略只生成旁路决策和对照统计。未来切换 enforced 时，权威非比赛区间才允许先启用硬抑制；算法状态先以提高门槛、限制搜索区域或暂停新锁定等软方式介入。

### 5. 双摄采用 prepare/commit，而不是重复 detector

双摄每个 canonical tick 按以下顺序执行：

```text
clock.tick
→ ball.prepare_tick（解码、detect、过滤、缓存，不更新 tracker）
→ player prepare/complete 与 global association
→ MatchSemanticPolicy.evaluate
→ ball.commit_tick（按策略消费候选，tracker 每视角更新一次）
→ stereo association / trajectory evidence
```

第一阶段可以保留旧处理结果作为 shadow baseline，但接口和计数器必须能区分 prepare、policy、commit。单摄仍允许旧的 `update(frame)` 行为；当没有语义快照时，策略必须选择兼容路径。

### 6. 诊断产物优先于正式行为改变

新增 `ball_semantic_timeline.v1` 诊断产物或等价 job artifact，按 canonical tick 保存 phase、authority、证据摘要、策略决策、候选数量、抑制数量、旧逻辑与新策略的差异。它只用于审计和回放，不替代现有 `ball_trajectory`、`reconstructed_ball_trajectory.v4` 或 rally 结果。

关键验收指标包括：非比赛时间每分钟误检候选数、发球后首次可靠球观察延迟、正式回合内候选召回率、Shadow 抑制比例、未知状态比例，以及新旧策略产生的轨迹点差异。

## Risks / Trade-offs

- **[语义误判导致漏球]** → 默认 `UNKNOWN` 回退；第一阶段 Shadow Mode；enforced 只允许人工/修正时间线硬抑制。
- **[停止 detector 后无法发现发球开始]** → `NON_PLAY_CONFIRMED` 仍由球员运动/站位感知驱动，进入 `PRE_SERVE` 或 `SERVE_ARMED` 后恢复球搜索；第一阶段不真正关闭 detector。
- **[语义规则与 BallTracker 状态相互污染]** → policy 不直接改写 tracker 内部历史，只通过明确的候选消费和生命周期命令影响 tracker。
- **[双摄与单摄行为不一致]** → 统一使用 canonical take time 和同一 `MatchSemanticSnapshot` 契约；没有语义上下文时分别保留原有兼容路径。
- **[Shadow Mode 增加计算和存储开销]** → 复用已有 detector 结果，不重复运行模型；诊断只保存结构化摘要和有限候选引用，并提供配置开关。
- **[时间线缺失或 capture take 无法关联]** → provider 返回 `authority=none`，策略进入 `UNKNOWN`，不得阻塞球员分析或现有球链。
- **[只记录状态但无法证明效果]** → 使用固定回放片段和标注区间比较新旧决策，至少覆盖非比赛、手持球、发球准备、正式回合、长丢失和回合结束候选。

## Migration Plan

1. 增加策略配置、快照模型、provider、Shadow Mode 诊断和单元测试；默认关闭 enforced。
2. 在单摄和双摄输出中并行生成语义时间线，与现有球轨迹和 v4 结果对照，不修改正式结果。
3. 先启用人工/修正 `non_play` 窗口的硬策略，验证不会影响有效回合；算法推断继续 Shadow。
4. 在确认指标稳定后，再逐步启用 `PRE_SERVE`/`SERVE_ARMED` 的软搜索策略。
5. 如需回滚，关闭策略配置即可恢复现有 BallTracker 和 canonical ball processor 路径；Shadow 诊断文件可以保留用于分析。

## Open Questions

- `effective_time_windows` 是否直接作为权威窗口 provider，还是新增一个统一的 `SemanticTimelineProvider` 包装手工、修正和算法事件？
- 正式启用时，权威 `non_play` 区间是停止 tracker 更新、清空 tracker，还是保留预测状态但禁止发布？
- `SERVE_ARMED` 的搜索 ROI 应优先使用球员 bbox、手腕/上肢位置，还是已有 court ROI 与 server side 的组合？
- `ball_semantic_timeline.v1` 应作为独立 artifact 持久化，还是先写入现有球路 diagnostics 后再独立化？
- 单摄离线 pipeline 是否在第一阶段只支持权威时间线 gating，算法语义 gating 等双遍重构后再启用？
