## Context

`FusedPlayerOverlayBuilder._decide_entity`（`fused_overlay_builder.py:293-383`）当前逐 tick 按瞬时证据决定展示形态：

```text
F0 strong → base/guided（实线框）
F1 recovered → refined_observed（实线框）
F0 weak → base/guided（实线框）
donor 可用 + fused 可用 + geometry 有效 → cross_view_projected（虚线框/脚点）
predicted + TTL 未过 → predicted_only（光圈）
否则 → 不渲染
```

每个 tick 独立决策，导致真实素材上同一球员在相邻 tick 间于 `实线框 / 虚线框 / 光圈 / 消失` 之间随机跳变。同时 `TargetViewBBoxMemory.reanchor()`（`:162-189`）在 `bbox_memory_ttl_ms=2000ms` 过期后直接返回 None（降级光圈），TTL 边界处也会抖动；且从无历史 bbox 的球员（远端）永远只能显示 footpoint。

本 Change 不改变证据来源与分支优先级（那是 fused overlay 已固化的语义），只在其上增加两层稳定性：**跨 tick 展示状态机（迟滞稳定 geometry，不伪造 evidence）** 与 **整场两遍式 view scale profile bbox fallback**。

## Goals / Non-Goals

**Goals:**

- 消除"同一 evidence 序列下展示形态逐帧抖动"：`REAL_BOX → HIDDEN` 必须渐进降级，synthetic upgrade（`PROJECTED_POINT → PROJECTED_BOX`）必须稳定确认。
- **真实 bbox 恢复立即展示**：当前 tick 出现真实 target-view bbox（base/guided/accepted refined）→ 立即 `REAL_BOX`/`ASSISTED_BOX`，不等 confirm。
- 无历史 bbox 的球员在目标 view 可获得 projected bbox（虚线），而非永远 footpoint 光圈。
- 保持分支决策链的证据来源与优先级完全不变（`_decide_entity` 的判定逻辑不动）；**`evidence_type` 永远反映真实证据来源，`display_state` 正交独立**。

**Non-Goals:**

- 不修改 F0/F1/donor/fused 证据判定语义（`_is_strong / _is_weak / _donor_candidate / _fused_is_usable` 不动）。
- 不修改 guidance / association / perception / tracker。
- 不"拯救"丢失的球员（那是感知层 change 的职责）。
- 不做跨 view 的 bbox 直接拷贝（view scale profile 是每 view 自学习）。
- **不伪造 evidence**：任何 synthetic bbox（reanchor / scale profile）不得在 `evidence_type` 上伪装为真实检测。

## Decisions

### D1: 迟滞稳定 geometry，`evidence_type` 与 `display_state` 彻底正交

新增 `OverlayDisplayStateMachine`（`(player_id, view_id) → DisplayState`），包装在 `_decide_entity` 外层。**核心语义**：

- `evidence_type`（`base_observed / guided_observed / refined_observed / cross_view_projected / predicted_only`）SHALL 永远反映当前 tick 的真实证据来源，由 `_decide_entity` 权威决定，状态机 MUST NOT 修改它；
- `display_state`（`REAL_BOX | ASSISTED_BOX | PROJECTED_BOX | PROJECTED_POINT | PREDICTED_POINT | HIDDEN`）是正交的展示层状态，决定"几何形态"（框/点/隐藏 + 线型），由状态机决定。

冻结映射：

```text
base_observed                 → REAL_BOX
guided_observed / refined_observed → ASSISTED_BOX
cross_view_projected + bbox   → PROJECTED_BOX
cross_view_projected 无 bbox  → PROJECTED_POINT
predicted_only                → PREDICTED_POINT
none                          → HIDDEN
```

**迟滞只稳定几何形态**：t=100 真实 `base_observed`（REAL_BOX 实线）→ t=101 本视角 miss 但 donor 可靠 → `evidence_type=cross_view_projected`（虚线 PROJECTED_BOX），**不是**"保持 REAL_BOX"。形态从实线变虚线是诚实降级，但不会从框直接跳成点。

### D2: 真实 bbox 恢复立即升级；confirm 只控制 synthetic upgrade

- 当前 target-view 真实 bbox（`base / guided_roi / accepted refined`）出现 → **立即** `REAL_BOX`/`ASSISTED_BOX`，并清空 recovery confirmation counter。MUST NOT 等待 `confirm_ticks`。
- `confirm_ticks`（改名为 `synthetic_upgrade_confirm_ticks`）只控制 synthetic upgrade：`PROJECTED_POINT → PROJECTED_BOX` 需连续 ≥ N 次有效 synthetic evidence（donor 恢复 + 可靠 bbox 模板）才升级；单帧 synthetic 恢复不立即跳框。

### D3: 迟滞时间单位用 ms（非 tick）+ 统一 freshness 权威

joint 的 canonical tick 间距随 `frameStride` 变化（30fps stride=1 → 3 tick ≈ 100ms；stride=3 → ≈ 300ms；60fps → ≈ 50ms）。展示层 SHALL 使用**实际 canonical timestamp**：

```text
hysteresis_grace_ms    # 真实框短暂漏检的保持窗口（默认 ~100ms）
projected_box_hold_ms  # synthetic projected box 的保持窗口
```

恢复确认仍要求连续 N 次有效 evidence，但**同时有 gap 约束**（`confirm_max_gap_ms`，防止隔半秒的三次观测被当作"三连"）。

**删除 `projected_box_stale_ticks`**：统一由 bbox source 报告 freshness/age（`bbox_age_ms`），状态机只消费该信息，消除两套过期权威打架。`TargetViewBBoxMemory` 的 `last_real_observed_ms` 是唯一 freshness 源。

### D4: bbox fallback 顺序（freshness 优先）+ stale 契约

fallback 顺序冻结为：

```text
1. 当前 tick 真实 bbox（base/guided/refined）
2. fresh personal bbox memory（age ≤ bbox_memory_ttl_ms）
3. view scale profile（用当前 projected footpoint 深度估计尺寸）
4. stale personal memory grace（age ≤ ttl + bbox_memory_grace_ms，仅 profile 不可用时兜底）
5. footpoint 光圈
```

**理由**：2.3s 前的个人 bbox（可能已从后场跑到网前）不应压过"当前 footpoint 深度估计的 scale profile"；`bbox_memory_grace_ms` 是真正的 grace 而非优先级压制。契约新增 `bbox_stale: bool`（该 bbox 是否来自 stale memory）与 `bbox_age_ms: float | null`（last real observed 距今，供前端淡化），后端不得只内部知道 stale 而不暴露。

### D5: ViewPersonScaleProfile 整场两遍式静态 profile

fused overlay 是离线产物，SHALL 用两遍式：

```text
Pass 1：整场收集该 view 的可靠真实 bbox → 冻结静态 scale 模型
Pass 2：逐 tick 生成 overlay → 查询已冻结 profile
```

**硬约束**：
- 只收 `base / guided_roi / accepted refined` 的**真实 target-view bbox**；
- `last_good_bbox_reanchored`、`view_scale_profiled` 等 synthetic bbox **绝不能回喂** profile 或 BBoxMemory（防自我强化）；
- clipped / 极端长宽比 / 尺寸异常的 bbox 不作为 scale sample（`is_qualifying_bbox` 之外需额外过滤）。

模型：按 `footpoint_y` 分桶（32 桶）做 robust median 拟合 `scale(y) → (width, height)`；查询用**邻桶 linear interpolation**（非 nearest bucket，防"footpoint 移 2px 框长高 22px"）；`min_total_samples` / `min_samples_per_bin` 门限；width/height physical bounds；无样本 → None。

### D6: 状态机硬 stop / reset 不变量

- target geometry invalid → 不允许 synthetic projected box（不生成 PROJECTED_BOX）；
- 当前无有效 fused/projected point 且 prediction 已超 TTL → 状态机 MUST `HIDDEN`（即使上一状态是 PROJECTED_BOX）；
- bbox memory > ttl + grace 且 profile 不可用 → 不得继续画框（降级 PROJECTED_POINT → HIDDEN）；
- **new build / new job / roster reset → 状态机必须 reset**（`OverlayDisplayStateMachine` 是有状态类，实例被复用/测试时不得把上一场 P1 状态带进下一场）。

### D7: 状态机输入 = raw evidence + display context，输出 = DisplayPlan

`_decide_entity()` 返回 `None` 时 wrapper 无法仅凭返回值执行 `REAL_BOX → PROJECTED_BOX`（还需要 projected footpoint / prediction / geometry / bbox memory / scale profile / timestamp）。因此：

```text
raw evidence decision（_decide_entity，权威不变）
+
current display context（projected_footpoint / prediction / geometry_valid /
    bbox_memory_freshness / scale_profile_result / timestamp）
        ↓
OverlayDisplayStateMachine.step(...)
        ↓
DisplayPlan(state, preferred_bbox_source, bbox_stale, bbox_age_ms)
        ↓
builder materialize entity（用 DisplayPlan 决定几何形态与 bbox 来源）
```

状态机本身保持无 I/O、好测；geometry/bbox 逻辑不进 transition engine。

## Risks / Trade-offs

- [迟滞掩盖真实丢失] → grace/confirm 用 ms + gap 约束；HIDDEN 仍由 predicted TTL / bbox 失效 / geometry 失效驱动，不无限拖长；硬 stop 不变量保证不越安全边界。
- [scale profile 制造不可靠 bbox] → 样本不足返回 None；synthetic 不回喂；只做虚线 projected；`bbox_source=view_scale_profiled` 显式标注来源。
- [状态机引入跨 tick 状态导致测试复杂] → 状态机独立成类（无 I/O），单测直接驱动 tick 序列验证；DisplayPlan 输出可断言。
- [真实观测被 confirm 延迟] → D2 明确真实 bbox 立即升级，confirm 只控 synthetic。
- [前端样式需新增] → `video-overlay-hud` 增量：`view_scale_profiled` 复用虚线样式族；`bbox_stale` 可淡化。

## Migration Plan

- 后端契约枚举扩展（旧值不变）；overlay 产物向后兼容（新字段缺省）。
- 前端类型扩展可选字段；旧产物解析不破坏。
- 无 API 路由变更。

## Open Questions

- `ViewPersonScaleProfile` 的样本量阈值（`min_total_samples` / `min_samples_per_bin`）默认值：建议 `min_total_samples=50`、`min_samples_per_bin=5`，真实素材标定后调整。
- 二维 `(x,y)` profile 是否 V1 需要？→ 默认不需要（一维 y 足够），真实机位发现同 y 左右尺度差异大再升级。
- 迟滞是否需要对 `cross_view_projected` 与 `predicted_only` 分别配置 grace？→ V1 统一参数，视觉验收后按 evidence 类型细分。
