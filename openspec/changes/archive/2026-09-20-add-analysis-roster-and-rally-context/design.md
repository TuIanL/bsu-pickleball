## Context

当前 `start_next_rally` 可以从可重放计分状态得知发球队和比分，但录制期尚未发生 P1–P4 确认；`initial_side` 也只代表画面/物理半场。把 roster 放进现场 snapshot 会形成“引用未来对象”的时序矛盾，把端位放进 ScoringState 则会把空间投影与纯计分 reducer 耦合。正式 `AnalysisWindowPlan` 目前主要含自动分段边界，不能仅凭时间容差安全对应人工计分事件。

## Goals / Non-Goals

**Goals:**

- 将录制事实、分析身份和场地端位分层保存，并在 Job 创建时组成可复现回合上下文。
- 让更正、撤销、换边和名册改动都有明确影响范围与 provenance。
- 让 formal Rally、canonical artifact 和下游指标能只读取不可变输入。

**Non-Goals:**

- 不以 CV 自动判定发球队、真实姓名或 Team A/B。
- 不实现厨房线到位率、视频回跳或其他下游战术指标。
- 不把单摄/双摄作为 context calculator 的固有限制；产品入口可另行设置准入策略。

## Decisions

### 1. 录制期只保存 `RallyScoringSnapshot`

在 `rally_start` 同一事务中写入 `{rally_id, server_team, score_a_before, score_b_before, scoring_ruleset_version, action_id, event_id, action_revision}`。它是 action ledger 重放的派生事实；重放或修正产生新的版本和 supersede 链。选择此分层而非现场引用 roster，因为 roster 尚不存在且之后可重新确认。

### 2. 名册是分析期的 identity contract

bootstrap 仅给用户提供 P1–P4 候选与锚点，用户确认后创建不可变 `AnalysisRosterSnapshot`。每条确认记录 `canonical_player_id`、display name、team、`source_view_id`、`anchor_timestamp_ms`、`anchor_bbox`、`anchor_court_xy`、`bootstrap_run_id`、`bootstrap_model_version`、confidence。正式 tracking 必须输出 `bootstrap_binding_audit`，将锚点绑定到正式 canonical player；绑定失败即令依赖正式身份的能力 unavailable，禁止静默编号替换。

### 3. 用独立 `CourtEndProjection` 重放换边

projection 以用户确认的初始端位为种子，读取有效 `side_change` action 切换 A/B near/far。它不进入 `ScoringState`，因此计分 reducer 继续只负责比分、发球权、计分阶段和发球站位。选择独立投影可供所有空间指标复用，也避免将非计分语义纳入 score correction。

### 4. Job 创建时合成 `AnalysisRallyContextSnapshot`

context composer 为每个可用 scoring snapshot 找到 Job 的 roster snapshot 和该回合开始时的 court-end projection，写入 `server_team`、比分、A/B 球员、端位、来源 ids、`scoring_hash`、`roster_hash`、`court_end_hash` 与 `context_hash`。AnalysisJob 绑定 context-set hash。已创建 Job 永远读取自己的 context；新名册或有效计分修正只能创建新的上下文/Job 版本，不回写旧 Job。

### 5. Formal window 按证据强度绑定

绑定优先级严格为：`direct_segment_link`（formal window 的 CaptureSegment id 到 segment 的 start_event_id）> `direct_start_event_link` > `unique_temporal_match`（合法顺序、唯一性和配置容差）> unavailable。保存所采用的 binding method、候选数和诊断。选择分级而非纯时间匹配，以抵抗剪辑、修正和相邻 Rally。

## Risks / Trade-offs

- [bootstrap 与正式 tracking 身份断裂] → 输出 audit 并降级 unavailable，不猜测替换。
- [历史 take 没有 score/action 或初始端位] → 保持既有分析可读，context 明确 unavailable。
- [修正后的 context 与既有 job 冲突] → 新 context/hash 触发新 Job 版本；旧 job 的结果保持可追溯。
- [自动 window 无直接关联] → 只允许唯一时间降级，歧义不发布给队伍指标。

## Migration Plan

1. 增加 snapshot、projection、binding audit 与 job context schema，历史字段可选读取。
2. 发布 scoring snapshot 与 side-change projection 的 action-ledger replay，先产出诊断但不启用任何下游指标。
3. 发布 bootstrap/roster 确认与 Job composer，覆盖新 Job 签名和缓存隔离。
4. 接入 formal window、canonical artifact；在真实样本验证修正、换边和 identity 断裂降级后，供下游 change 使用。
5. 如发生问题，停用 composer consumer；既有普通分析、计分与窗口计划继续运行。

## Open Questions

> 两个 Open Question 已在实施期关闭，结论如下（2026-09-20）。

- CaptureSegment 与 timeline event 的现有持久化关系是否可完整提供 `start_event_id`；若缺失，需先补直接关联再允许时间降级。
  - **已定：在窗口计划内挂源引用，且引用不参与 `plan_hash`。** 现状核查：人工 rally 区间（`coding_actions_service` 创建）**确实**写入 `start_event_id`；而 formal algorithm 区间（`formal_segmentation_service` 发布）的 `start_event_id` 为空。因此选择在 `AnalysisWindowPlan` 的每个 window 上新增 `source_rally_segment_id` / `source_start_event_id` / `context_rally_id` / `context_hash` / `binding_method` / `binding_diagnostics`，在切分发布时由唯一时间匹配写入，**并把它们排除在 plan_hash 的哈希材料之外**——这样挂引用不会让既有任务的 `windowPlanHash` 失配（有单测锁定：同一窗口挂引用前后 plan_hash 相等）。
- 初始 A/B 端位是否每个 game 都必须重新确认，或可由 game transition 明确继承；实现前需锁定产品交互。
  - **已定：Job 级确认一次 + 结构化诊断。** 端位确认在创建 Job 时落盘为该 CaptureTake 的有效种子（重新确认产生新 revision，旧行转 non-effective）。其后的换边完全由有效 `change_side` action 回放。局边界若没有显式换边，投影**继续继承**上一局端位，同时写 `game_boundary_without_explicit_side_change` 诊断（含局序号与时间戳），不静默假装用户确认过。
- **实施期新增的显式解释**：`correct_score` 的 retroactive 语义。一个 `correct_score` 在某个回合**尚未产生结果**期间发生时，视为对该回合 before-facts 的重新陈述，因此覆盖该回合的计分快照（旧版本转 `superseded`，新 revision 保留 `supersedes_snapshot_id` 链）；一旦该回合已记录结果或已结束，后续改分不再回溯影响它。该解释写在 `rally_scoring_service._replay_scoring_state` 的 docstring 中并有专门测试。
- **发布状态**：context consumer 默认开启；任务创建页以 `useRallyContext` 固化本次选择，默认 `true`，用户可显式选择 `false` 回到 legacy 流程。部署仍可用 `PICKLEBALL_RALLY_CONTEXT_ENABLED=false` 做全局回滚；关闭时创建任务不冻结名册/上下文，formal window 也不做绑定，普通分析行为逐字不变。
