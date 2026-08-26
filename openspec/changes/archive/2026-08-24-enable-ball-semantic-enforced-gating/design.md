## Context

第一阶段已经建立 `MatchSemanticSnapshot`、`BallSearchPolicy`、语义时间线 provider、单摄/双摄接入和 `ball_semantic_timeline.v1`。默认 Shadow Mode 下，策略会记录“应抑制”和“应重新捕获”的建议，但正式 `BallTracker`、轨迹发布和 v3/v4 分段仍按旧逻辑运行。

第二阶段的核心不是再增加 detector 规则，而是把已验证的比赛边界变成正式球链的生命周期边界。当前需要同时满足四个约束：权威 `non_play` 必须能阻止正式候选污染下一分；上一回合的预测和 tracker 历史不能跨回合泄漏；发球准备阶段必须能渐进恢复搜索；语义 provider 失败或只提供算法推断时，旧球链仍可用。

本阶段只对 manual/corrected 时间线提供硬门。球员静止、站位、ServeStartDetector 和其他 algorithm evidence 继续产生软策略或 Shadow 诊断，不直接关闭正式球链。

## Goals / Non-Goals

**Goals:**

- 提供按 take/运行配置控制的 Enforced rollout，默认仍为 Shadow，能够不改代码回滚。
- 将权威 `non_play`、`rally_end` 转换为一次性的正式球段封存和 tracker 边界动作。
- 使被抑制的 raw candidate、formal candidate、tracker 状态变化和边界原因可追溯。
- 在 `PRE_SERVE`/`SERVE_ARMED` 阶段建立渐进式重新捕获路径，过滤手持静止球，保留真实发球开始的恢复能力。
- 保证单摄和双摄使用同一 canonical semantic snapshot；双摄每个 tick 的 gate 和 boundary action 只执行一次。
- 在 7 月 20 日真实双摄素材上用同一批检测结果完成 Shadow-vs-Enforced 回放对照。

**Non-Goals:**

- 不修改 `models/ball/tennis-ball.pt` 或任何 detector 权重、类别和推理模型。
- 不把 algorithm authority 的非比赛判断升级为硬门。
- 不在本阶段确认击球者、出界、碰网、回合胜负或比分。
- 不因为一次候选丢失、一次球员静止或一次 bounce/contact 候选就结束回合。
- 不删除 raw detector 候选，不把 semantic suppression 写入静止误检黑名单。

## Decisions

### 1. 以 authority 和 explicit rollout 共同决定硬门

Enforced 不作为全局默认值，而是由 job/take 级配置显式打开；即使打开，也只有 `authority ∈ {manual, corrected}` 且 phase 为 `NON_PLAY_CONFIRMED`、`POST_RALLY` 或命中的权威 `rally_end` 边界时，才允许禁止正式发布。`algorithm`、`none` 和 provider 失败统一走兼容/软策略。

采用“来源 + 配置”双门，是为了避免部署配置误开后把视觉推断误当成事实。替代方案是只要 `mode=enforced` 就对所有 `NON_PLAY_CONFIRMED` 硬门，但这会让算法状态机的误判直接造成漏球，因此不采用。

### 2. 边界动作采用边沿触发，不在每帧重复 reset

语义策略在 phase 发生以下边沿时生成结构化 boundary action：

```text
active/pre-serve → NON_PLAY_CONFIRMED/POST_RALLY
    → seal_formal_segment + reset_tracker_for_next_rally
NON_PLAY_CONFIRMED/POST_RALLY → PRE_SERVE
    → warm_reacquire
PRE_SERVE → SERVE_ARMED
    → serve_reacquire
权威 rally_start → RALLY_ACTIVE
    → open_formal_segment
```

`seal_formal_segment` 只封存当前已经确认的正式轨迹和诊断，不把边界后的候选追加到旧段；`reset_tracker_for_next_rally` 清理预测位置、连续性计数、暂态候选和本回合状态，但保留 job 级诊断和原始候选。边沿 ID 或 canonical timestamp 用于幂等，避免双摄/重试重复封存。

替代方案是每个非比赛 tick 都调用 `BallTracker.reset()`，实现简单但会重复创建段、丢失边界原因并放大双摄时序问题，因此不采用。

### 3. 发球恢复分成 warm-up 与 formal publish 两层

`PRE_SERVE` 和 `SERVE_ARMED` 不直接把所有候选发布为正式球点。策略先允许 detector 候选进入 warm/reacquire 路径，并要求候选满足发球区域、运动变化、连续性或权威 `rally_start` 中的至少一类有效条件；单帧静止手持球只能保留为 raw/diagnostic。满足正式条件后才进入 `RALLY_ACTIVE` 的 formal publish。

这种分层可以在不停止 detector 的情况下尽早准备捕获，同时避免把球员手中的球当作新回合第一点。替代方案是等到第一颗球完全通过 tracker 后再开始搜索，容易增加发球后首球延迟；另一方案是进入 `SERVE_ARMED` 就全量发布，容易放行手持球，均不采用。

### 4. 双摄由 joint runtime 统一应用边界

`CanonicalBallStereoProcessor` 在 commit 阶段消费 joint runtime 生成的单一 `MatchSemanticSnapshot` 和 `BallSearchDecision`。边界 action 在 joint 层生成唯一 action id，再传给两路 tracker；两路保留各自 raw candidates 和 tracker diagnostics，但不得各自独立推进 phase、重复 reset 或重复封存同一正式段。

单摄继续使用相同的 policy contract；没有 prepare/commit 或没有 snapshot 时保留 `BallTracker.update(frame)` 的兼容路径。

### 5. 诊断记录 gate 前后差异，而不是只记录最终结果

每个 canonical tick 的语义诊断新增或稳定化以下信息：`rollout_mode`、`boundary_action`、`boundary_action_id`、`formal_candidate_count_before`、`formal_candidate_count_after`、`tracker_state_before`、`tracker_state_after`、`segment_id_before`、`segment_id_after`、`suppression_reason` 和 `fallback`。Shadow 回放时 effective formal result 仍是旧结果，但可以计算 Enforced 模拟结果，避免为了比较而重复运行 detector。

采用结构化差异诊断而不是另写一条“正式轨迹”是为了确保 detector 每 tick 只运行一次，并使回滚后仍能用同一批 raw evidence 复盘。

### 6. 真实素材验收采用固定边界样本和全链路回归

固定使用 2026-07-20 双摄 take 的同一 timeline、同一模型和同一采样参数，至少复核：回合外抑制、捡球、发球准备、发球 armed、正式回合、单视角丢失、权威 rally_end 后不跨段、provider unknown/failure。验收同时运行现有 ball tracker、reconstruction、dual-view、player 和 artifact API 回归测试。

## Risks / Trade-offs

- **[权威时间线标注边界略晚导致漏掉回合尾部或首球]** → 保留 raw candidates；边界前已确认样本封存，发球阶段通过 warm/reacquire 缓冲恢复；用固定片段统计首球延迟。
- **[reset tracker 后真实球仍在场内但 timeline 过早进入 non-play]** → 硬门只接受 manual/corrected；默认 Shadow；支持按 take 关闭 rollout 并保留旧结果。
- **[双摄两路重复执行边界动作]** → joint 层生成唯一 action id，processor/trackers 做幂等检查并增加重复调用测试。
- **[预热候选污染正式轨迹]** → 明确 warm-up 与 formal publish 分层，只有通过运动/连续性/权威回合条件才发布。
- **[旧任务没有 timeline]** → provider 返回 `UNKNOWN`，保持 fail-open；不要求历史任务补标后才能分析。
- **[diagnostics schema 增长造成旧消费者解析失败]** → 新字段采用可选向后兼容方式，保留现有 `ball_semantic_timeline.v1` 核心字段和旧 artifact 路径。

## Migration Plan

1. 增加 rollout、boundary action、幂等 reset 和 warm-up 的类型/配置/诊断字段，默认不改变正式结果。
2. 在单摄和双摄中先运行 Enforced simulation，与 Shadow 结果在同一 job 内对照，不写入正式轨迹。
3. 仅针对选定 7 月 20 日 take 或显式配置的 take 开启 manual/corrected `non_play`/`rally_end` 正式门，观察边界泄漏、首球延迟和回合内漏球。
4. 验收通过后保留按 take 灰度开关；算法 authority 继续 Shadow，后续另行提案扩大范围。

回滚方式：关闭 take/job 的 semantic enforced 配置，正式球链回到第一阶段 Shadow/旧兼容行为；诊断和 raw evidence 不删除。

## Open Questions

- 权威 `rally_end` 到达时，正式轨迹段的终点是否直接使用最后一个 accepted sample，还是允许一个很短的 boundary grace window 保存延迟到达的球点？本阶段默认使用最后 accepted sample，除非真实素材对照证明需要 grace window。
- `reset_tracker_for_next_rally` 是否需要保留球的最后空间位置作为下一分的 diagnostic reference？本阶段默认不作为 formal prediction，只保留在 diagnostics。
- 7 月 20 日素材验证通过后，Enforced rollout 的默认粒度是 CaptureTake、analysis job 还是用户手动选择的 timeline 版本？本阶段先实现 take/job 级配置，不改变全局默认。
