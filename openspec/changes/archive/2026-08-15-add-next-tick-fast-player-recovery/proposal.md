## Why

当前 guidance 只在 target binding 进入 `weak / missing / lost` 后才触发，而 `ViewBinding.update_visibility` 以 `binding_weak_after_ms=300ms` 判定 weak（`global_state.py:123-133`）。因此某 global 球员在 target view 首次漏检后，即使 donor view 当前帧看得非常清楚，也要等约 300ms（30fps 下约 9 个 canonical tick）才可能触发 guidance 补检。视觉表现就是"框消失 → 空白 300ms → 恢复"。Phase 0 诊断（mvr_35ac365aec96 @ 00:07）已实证 recovery episode re_000002 在 5.07-8.27s 丢失期内仅 1 次 guidance 尝试，且 fused_diagnostics 显示大量 `recovery_skip_uncertainty`——recovery 的触发延迟与门槛是"框消失"体感的重要来源之一。

同时，`add-player-display-diagnostics` 已为 `GuidanceGenerator` 增加 side-effect-free `GuidanceDecision`（`guidance.py`），现在"为什么没触发 guidance"已经可观测，本 Change 把触发延迟本身作为优化目标具备了闭环证据基础。

## What Changes

- **Available-Miss Fast Path（next-tick fast recovery）**：在 `ViewBinding` 增加**独立于 `visibility` 的可用性维度字段**（`consecutive_available_misses` / `last_attempted_take_timestamp_ms` / `last_attempted_tick` / `last_observed_tick`），不修改现有 `visibility = observed | weak | missing | lost` 的 recency 语义。
- **attempt authority = `view_results`（不是 `frame_status`）**：miss 记账 SHALL 仅对**本 tick 真正被 perception 成功尝试过的 view**（`view_id ∈ view_results`）进行。`bundle.frame_status == "available"` 只是 source availability authority；`view_degraded` 跳过、`runtime.step` decode 返回 None 等导致无 `ViewFrameResult` 的情况 SHALL 记为 availability/decode/runtime skip，MUST NOT 递增 miss（否则把"没被尝试"误记为"尝试了但 P1 没出现"）。
- **miss 定义精确化**：`available global-view miss` = target view 本 canonical tick 被成功处理（attempted available tick），但该 global 在该 view 未得到 `AssociationUpdate`。它可能来自 projection/formal observation failure 或 association failure（`formal JointObservation` 存在但 association 拒绝也计 miss——从 global-view binding 视角确实是一次 miss，且 guided expected-global 强约束在下一 tick 可能有帮助）。
- **recovery opportunity / episode 与 fast path 同步（消灭幽灵 guidance）**：recovery opportunity 判定与 guidance 触发使用**同一 predicate**（抽共享纯函数 `is_target_recovery_eligible(binding, fast_recovery_enabled)`）：`visibility in {weak,missing,lost} OR (fast_recovery_enabled AND consecutive_available_misses >= 1)`。fast path 触发的 guidance 必须同步建立 `recovery_episode_id`、计入 `recovery_opportunity_count`，后续 `guided_recovery_success` 才能正确归属。
- **`GuidanceDecision` 拆 trigger/reason**：`GuidanceDecision` 增加 `trigger_source`（`visibility_age | available_miss | None`）表示"为什么有资格"，原 `reason` 字段保持表示"最终为什么生成/拒绝"（`target_not_missing / donor_unavailable / donor_low_quality / prediction_uncertain / cooldown / geometry_unavailable / generated` 等）。MUST NOT 把 `available_miss_fast_path` 塞进 `reason`（否则 `miss_streak=1 但 donor_quality=0.31` 这类场景会丢失真正的失败原因）。
- **记账顺序冻结**：`association → available-miss ledger → display diagnostics → fusion/debug serialization`。当前 tick 的 miss 状态必须先于该 tick 的 display diagnostics 构建完成（否则首次 miss 时漏斗仍显示 0，诊断晚一拍）。
- **记账幂等**：`record_attempt()` SHALL 按 canonical tick 幂等——相同 tick 重复调用直接 return（存 `last_attempted_tick`）。
- **cooldown 原样保持**：现有 `guidance_cooldown_ticks` 的计数 key、单位解释（当前实现以 reference frame index 为 tick，frameStride>1 时不严格等于 canonical tick 数）、`commit()` 消费行为 SHALL 原样保持，本 Change 不重新定义其语义（避免 scope 扩大）。
- **配置真源锁定**：`fast_recovery_enabled` 的唯一配置真源为 `P1OnlineRecoveryConfig`（默认 True）；`MultiViewJointRun.__init__` SHALL 将该布尔同步进 `CrossViewGuidancePolicy`（沿用现有 `policy.min_donor_quality = recovery_config.min_donor_quality` 的同步模式），两个地方不得各自持有独立默认值。
- **one-canonical-tick 语义（非 same-tick）**：明确本 Change 不是 same-tick bidirectional recovery——guidance 仍在 pre-tick snapshot 生成（不动 `multiview_joint_run.py` 的时序），只是上一 tick 的 miss 记录使下一 tick 提前有资格。实际延迟取决于 reference FPS / frameStride / canonical tick spacing（30fps stride=1 约一个 33ms tick），**不在 spec 承诺固定毫秒数**。
- **安全门全部保留**：现有 guidance 门限（confirmed + cross_view_anchored、target geometry、prediction uncertainty、donor quality/recency/origin、max_regions_per_view_per_tick）一律不动；fast path 只放宽"binding age"这一个准入条件。
- **`add-player-display-diagnostics` 联动**：display diagnostics 漏斗行在 `add-player-display-diagnostics` 中已记录 `binding_visibility`；本 Change 补充记录 `available_miss_streak`（沿用该 Change 的 flat 行契约与 API）。
- **scope 边界（明确不做）**：不做 same-tick 双向 recovery、不修改 tracker.update-once 不变式、不修改 association、不修改 guidance 门限/cooldown 单位/cooldown 语义、不重新校准 cooldown 为严格 canonical-tick；raw detector / lock rejection 归因仍不属于本 Change（属后续 `strengthen-multiview-cooperative-player-perception`）。**预期管理**：本 Change 只解决"已有可用 donor、却被 300ms target-age gate 白白拖延"的场景；若某 tick 连续两台相机都无可用 donor binding，fast path 仍会被 donor gate 拦住（交由第 4 个 change）。

## Capabilities

### New Capabilities

- `next-tick-fast-player-recovery`: available-miss fast path——`ViewBinding` 可用性维度记账（`consecutive_available_misses` 等，独立于 `visibility`）+ guidance 触发条件扩展为"上一 canonical tick available miss 即可提前触发"，不改变 cooldown 单位与 pre-tick 时序。

### Modified Capabilities

- `cross-view-player-guidance`: 触发条件从 `binding.visibility in {weak, missing, lost}` 扩展为含 `consecutive_available_misses >= 1` 的 fast path（MODIFIED），安全门与 cooldown 语义保持。
- `multiview-online-player-recovery`: recovery opportunity 的判定补充 available-miss 触发语义（weak/lost 之外的下一 tick 快速机会），episode 语义与 success 定义不变。
- `player-display-diagnostics`: 漏斗行补充 `available_miss_streak` 字段（ADDED），沿用既有 flat 行契约与查询 API。

## Impact

- **后端**：`backend/app/vision/multiview/global_state.py`（`ViewBinding` 新增 `consecutive_available_misses / last_attempted_take_timestamp_ms / last_attempted_tick / last_observed_tick` 字段 + 幂等记账方法）、`backend/app/vision/multiview/guidance.py`（`generate()` 触发条件扩展 fast path；`GuidanceDecision` 增加 `trigger_source`，reason 语义不变）、`backend/app/vision/multiview/multiview_joint_run.py`（`is_target_recovery_eligible` 共享 predicate：recovery opportunity/episode 建立与 guidance 同步；association 后按 `view_results` 记账 miss，先记账再构建 display diagnostics）、`backend/app/vision/multiview/recovery_config.py`（`fast_recovery_enabled` 默认 True + `MultiViewJointRun.__init__` 同步进 policy）、`backend/app/vision/multiview/player_display_diagnostics.py`（漏斗行增加 `available_miss_streak`）。
- **契约**：`player-display-diagnostics.v1` 行结构增加 `available_miss_streak`（向后兼容：缺失按 0 处理）；`cross-view-player-guidance` 触发条件以 MODIFIED delta 表达。
- **测试**：guidance 触发条件扩展（available miss 下一 tick 触发、cooldown 仍生效、donor/uncertainty 门限仍生效）、binding 记账（有观测清零 / available miss 递增 / frame 不可用不计）、display diagnostics 新字段；核心回归保护（fast path 关闭时行为与现状一致）。
- **前端**：`src/types/report.ts` 漏斗行类型增加 `available_miss_streak`（可选），诊断面板展示该字段；无其他前端改动。
- **OpenSpec**：新增 capability `next-tick-fast-player-recovery`；MODIFIED `cross-view-player-guidance`、`multiview-online-player-recovery`；ADDED `player-display-diagnostics`（沿用上轮已落地 capability）。
