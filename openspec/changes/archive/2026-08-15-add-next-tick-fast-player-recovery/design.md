## Context

joint 模式 recovery 的触发延迟来自 `ViewBinding.update_visibility`（`global_state.py:123-133`）：

```text
gap = now_take_ms - last_seen_take_timestamp_ms
gap <= weak_after_ms (300ms)   → visibility = "observed"
gap <= lost_after_ms (1000ms)  → visibility = "weak"
否则                            → visibility = "lost"
```

而 `GuidanceGenerator.generate()`（`guidance.py:96-99`）只在 `visibility in {"weak","missing","lost"}` 时生成 guidance。因此某球员在 target view 首次漏检后，至少 300ms（≈9 ticks @30fps）内无法触发 guidance，即使 donor view 当前帧看得非常清楚。

Phase 0 诊断（mvr_35ac365aec96 @ 00:07，recovery episode re_000002，5.07-8.27s）证实：丢失期内仅 1 次 guidance 尝试，最终靠 base 自恢复。而 `add-player-display-diagnostics` 已落地 `GuidanceDecision` 与显示漏斗。

本 Change 在此基础上把"触发延迟"作为优化目标：**上一 canonical tick 的 available miss 使下一 tick 提前有资格触发 guidance**（one-canonical-tick fast recovery，非 same-tick）。

## Goals / Non-Goals

**Goals:**

- 将"首次漏检 → guidance 可触发"的等待从 `binding_weak_after_ms=300ms` 缩短到**下一 canonical tick**（30fps stride=1 约 33ms）。
- 在不修改 `visibility` recency 语义、不修改 pre-tick snapshot 时序、不修改 cooldown 实现、不修改任何安全门的前提下实现。
- **attempt authority 正确**：miss 只对真正被 perception 尝试过的 view 记账，availability/decode skip 不计 miss。
- **observability 闭环**：fast path 触发的 guidance 与 recovery opportunity/episode 建立同步；`GuidanceDecision` 拆 trigger/reason；漏斗行展示 `available_miss_streak`。

**Non-Goals:**

- 不做 same-tick bidirectional recovery（属 `strengthen-multiview-cooperative-player-perception`）。
- 不修改 `multiview_joint_run.py` 的 guidance snapshot 时序（仍 pre-tick）。
- 不修改 association、不修改 tracker.update-once 不变式。
- **不重新定义 cooldown 语义**（当前以 reference frame index 为 tick，frameStride>1 时不严格等于 canonical tick；本 Change 原样保持）。
- 不在 spec 承诺固定毫秒延迟。

## Decisions

### D1: miss 记账 = association 后 + attempt authority = `view_results`

**attempt authority SHALL 是 `view_results`（dict of `view_id → ViewFrameResult`），`bundle.frame_status` 只是 source availability authority。**

joint loop 中存在"frame_status == available 但系统未成功处理该 view"的情况：
- `view_id in self.view_degraded`（`multiview_joint_run.py:338`）→ 跳过 step；
- `runtime.step()` decode 返回 None（`:358`）→ `continue`；
- 其他导致 `view_results` 无该 view 的路径。

因此记账逻辑冻结为：

```text
process_tick 之后
view_id ∈ view_results
且 frame_status[view_id] == "available"
    ↓ 这才叫 attempted available tick
有 AssociationUpdate(global_id, view_id)
    → observed：miss=0，last_observed_tick=tick
无 AssociationUpdate(global_id, view_id)
    → available global-view miss：miss += 1
frame_status == available 但 view_id ∉ view_results
    → availability/decode/runtime skip：不递增（不记账）
frame_status != available
    → availability skip：不递增
```

**miss 定义精确化**：`available global-view miss` = target view 本 canonical tick 被成功处理（attempted available tick），但该 global 在该 view 未得到 `AssociationUpdate`。它可能来自 projection/formal observation failure 或 association failure（`formal JointObservation` 存在但 association 拒绝也计 miss——从 global-view binding 视角确实是一次 miss，且 guided expected-global 强约束在下一 tick 可能有帮助）。文档 MUST NOT 描述为"无 formal observation"。

### D2: `consecutive_available_misses` 独立于 `visibility`（正交维度）

`ViewBinding` 新增四个字段（不触碰现有字段）：

```python
consecutive_available_misses: int = 0
last_attempted_take_timestamp_ms: float | None = None
last_attempted_tick: int | None = None
last_observed_tick: int | None = None
```

语义：
- `consecutive_available_misses`：该 global 在该 view 连续几个 attempted available tick 没有 `AssociationUpdate`（有观测则清零）；
- `last_attempted_take_timestamp_ms`：最近一次 attempted available tick 的 take timestamp（诊断用）；
- `last_attempted_tick`：最近一次 attempted available tick 的 canonical tick（**幂等键**）；
- `last_observed_tick`：最近一次观测到的 canonical tick（诊断用）。

`visibility` 保持纯 recency 语义，fast path 不修改它。**关键**：fast path 触发后 `visibility` 可能仍是 `observed`（last_seen 未过期），两者正交、不冲突。

**记账幂等**：`record_attempt(result: bool, take_ms: float, tick: int)` 若 `tick == self.last_attempted_tick` 则直接 return（相同 canonical tick 重复调用不重复记账）。正常主循环每 tick 至多一次，幂等设计让重构/测试更安全。

### D3: 共享 predicate `is_target_recovery_eligible(binding, fast_recovery_enabled)`

**必须消除"幽灵 guidance"**：当前 `MultiViewJointRun` 在 guidance 生成前先建立 recovery opportunity/episode（`:252` 只认 `weak/missing/lost`）。若 guidance 因 fast path 触发但 opportunity/episode 仍只认 visibility，则 recovery funnel denominator 不包含它、episode 为 None、后续 `guided_recovery_success` 无法正确归属。

抽共享纯函数（放 `recovery_config.py` 或 guidance 附近，两边 import）：

```python
def is_target_recovery_eligible(binding, fast_recovery_enabled: bool) -> bool:
    if binding is None:
        return False
    if binding.visibility in {"weak", "missing", "lost"}:
        return True
    if fast_recovery_enabled and binding.consecutive_available_misses >= 1:
        return True
    return False
```

**同一 predicate 用于三处**：
1. `MultiViewJointRun` 的 recovery opportunity/episode 建立（`:252` 处替换）；
2. `GuidanceGenerator.generate()` 的 target eligibility（`:96-99` 处替换）；
3. 诊断漏斗的 `guidance_status` 解释（可选）。

这样 run 与 guidance 不会再次漂移。

### D4: `GuidanceDecision` 拆 trigger/reason

`GuidanceDecision` 增加 `trigger_source` 字段：

```python
trigger_source: str | None = None  # "visibility_age" | "available_miss" | None
```

- `trigger_source` 表示"为什么有资格"：由 visibility age 触发 → `visibility_age`；由 fast path 触发 → `available_miss`；两者同时满足时优先 `visibility_age`（语义更成熟）。
- 原 `reason` 字段**保持表示最终 decision reason**：`target_not_missing / donor_unavailable / donor_low_quality / prediction_uncertain / cooldown / geometry_unavailable / not_confirmed_anchored / generated` 等。

MUST NOT 把 `available_miss_fast_path` 塞进 `reason`。诊断展示效果：

```text
binding_visibility: observed
available_miss_streak: 1
trigger_source: available_miss
guidance: not generated
reason: donor_low_quality
```

### D5: 记账与 display diagnostics 顺序冻结

```text
process_tick (association)
    ↓
available-miss ledger（record_attempt）
    ↓
build player display diagnostics（读最新 miss state）
    ↓
fusion / debug serialization
```

当前 tick 的 miss 状态必须先于该 tick 的 display diagnostics 构建完成——否则首次 miss 时漏斗仍显示 `available_miss_streak=0`，下一 tick 才显示 1，诊断整体晚一拍。下一 tick 的 pre-tick guidance 自然读取上一 tick 已完成的 miss state（时序不变）。

### D6: cooldown 原样保持

`guidance_cooldown_ticks` 的现有计数 key（`(global, view) → last_tick`）、单位解释（当前实现以 reference frame index 为 tick，frameStride>1 时不严格等于 canonical tick 数）、`commit()` 消费语义（仅真正调用 target ROI detection 后消费）SHALL **原样保持**，本 Change 不重新定义。不引入 time-based cooldown。fast path 只影响"是否有资格尝试"，不影响"尝试后何时能再试"。

### D7: 配置真源锁定

`fast_recovery_enabled: bool = True` 的唯一配置真源为 `P1OnlineRecoveryConfig`（`recovery_config.py`）；`MultiViewJointRun.__init__` SHALL 在注入 recovery_config 时同步进 `CrossViewGuidancePolicy`（沿用现有 `policy.min_donor_quality = recovery_config.min_donor_quality` 的同步模式，`multiview_joint_run.py:104-110`），两个地方不得各自持有独立默认值。

### D8: 诊断联动——漏斗行加 `available_miss_streak`

`player-display-diagnostics.v1` 行结构增加 `available_miss_streak`（int，缺省 0），由 builder 从 `ViewBinding` 读取；查询 API 直接透传（无 schema 破坏，前端可选展示）。与 `binding_visibility` 并列展示。本 Change 对既有漏斗语义只做字段追加，不改变 `expected_region_status` / 分层断裂状态 / association / guidance decision 的任何既有语义。

## Risks / Trade-offs

- [fast path 触发频率升高 → ROI 重检变多] → cooldown 仍限制重复尝试；`max_regions_per_view_per_tick=4` 不变；仅对 confirmed + anchored 球员生效。
- [attempt authority 判断出错 → miss 误记账] → D1 冻结"view_results 为准"；`last_attempted_tick` 幂等防重复；availability/decode skip 路径不递增。
- [recovery opportunity 与 guidance 漂移 → 幽灵 guidance] → D3 共享 predicate 三处复用；测试断言 opportunity/episode 与 guidance 同步。
- [trigger/reason 混淆 → 诊断丢失失败原因] → D4 拆字段；测试覆盖"fast path 有资格但 donor 拒绝"场景断言 `trigger_source=available_miss, reason=donor_low_quality`。
- [fast path 关闭时行为回归] → 配置开关默认开启；测试覆盖关闭路径（行为与现状一致）。
- [预期管理：donor 双双缺失时 fast path 无效] → 明确本 Change 只解决"已有可用 donor 但被 target-age gate 拖延"；双 donor 缺失场景属第 4 个 change。

## Migration Plan

- 后端字段为 dataclass 新增默认值，无破坏性变更；旧产物（无 `available_miss_streak`）前端按 0 显示。
- `player-display-diagnostics.v1` 行结构向后兼容（新增可选字段）。
- 无 API 路由变更（沿用既有 display-diagnostics 查询 API）。
- `GuidanceDecision` 新增 `trigger_source`（默认 None），旧诊断消费者不受影响。

## Open Questions

- `is_target_recovery_eligible` 放置位置：`recovery_config.py`（与配置同模块）还是 `guidance.py`（与触发同模块）？→ 建议 `recovery_config.py`（无循环依赖风险），guidance 与 joint run 共同 import。
- fast path 是否需要单独的最小触发间隔（如至少间隔 1 tick 防连续 miss 每 tick 触发）？→ 默认不需要（cooldown 已覆盖）；真实数据验证后再定。
