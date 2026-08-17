## Why

`multiview-fused-player-overlay` 已落地"分支决策链"（F0 strong → refined → F0 weak → cross_view → predicted → hidden），但每个 canonical tick 都**根据瞬时证据立即决定展示形态**。真实素材（mvr_35ac365aec96 @ 00:07）已实证：P1/P2/P3 在相邻 tick 间在 `base_observed / cross_view_projected / predicted_only / hidden` 之间来回切换（用户截图：远端点/框跳动、近端 P1 短暂消失）。算法上每帧可能都有理由，但视觉上极不稳定，产品语义上让用户误以为"系统不稳定"。

另一个缺陷：`cross_view_projected` 的 bbox 依赖 `TargetViewBBoxMemory` 的 `last_good_bbox`，当某球员在目标 view **从无历史真实 bbox**（如远端球员从未被该 view 清晰捕获）时，只能降级为 footpoint 光圈——即使该 view 本身对"这个深度的人"有稳定的透视尺度规律，也不利用。用户截图里 P3 的"只有点没有框"正是这类。

## What Changes

- **Overlay Display Hysteresis（迟滞稳定 geometry，不伪造 evidence，A2）**：对每个 `(Player_N, displayed_view)` 维护跨 tick 展示状态机，**迟滞稳定的是"box → point → hidden"的几何形态，绝不伪造证据来源**。`evidence_type` SHALL 永远反映当前 tick 的真实证据来源；`DisplayState` 与 `evidence_type` **彻底正交**，映射冻结为：`base_observed → REAL_BOX`、`guided/refined_observed → ASSISTED_BOX`、`cross_view_projected + bbox → PROJECTED_BOX`、`cross_view_projected 无 bbox → PROJECTED_POINT`、`predicted_only → PREDICTED_POINT`、`none → HIDDEN`。
- **真实 bbox 恢复立即升级**：当前 target-view 真实 bbox（base / guided / accepted refined）出现时 SHALL **立即**升级到 `REAL_BOX`/`ASSISTED_BOX` 并清空 recovery confirmation counter；`confirm_ticks` 只控制 synthetic upgrade（如 `PROJECTED_POINT → PROJECTED_BOX`），MUST NOT 延迟真实观测的展示。
- **迟滞时间单位用 ms（非 tick）**：因 `frameStride` 使 canonical tick 间距不固定，迟滞参数改为 `hysteresis_grace_ms` / `projected_box_hold_ms`；恢复确认仍要求连续 N 次有效 evidence，但**同时有 gap 约束**（防止隔半秒的三次观测被当作"三连"）。删除 `projected_box_stale_ticks`，统一由 bbox source 报告 freshness/age，状态机只消费该信息（消除两套过期权威打架）。
- **ViewPersonScaleProfile（A3，整场两遍式静态 profile）**：Pass 1 整场收集该 view 的可靠真实 bbox → 冻结静态尺度模型；Pass 2 逐 tick 查询。**硬约束**：只收 `base/guided/accepted refined` 的真实 target-view bbox；`last_good_bbox_reanchored`、`view_scale_profiled` 等 synthetic bbox **绝不能回喂** profile 或 BBoxMemory（防自我强化）；clipped / 极端长宽比 / 尺寸异常的 bbox 不作为 scale sample（仅过 `is_qualifying_bbox` 不够）。profile 查询用**邻桶 linear interpolation**（非 nearest bucket）+ `min_total_samples` / `min_samples_per_bin` + width/height physical bounds，防止"footpoint 移 2px 虚线框长高 22px"的新抖动。
- **bbox fallback 顺序调整**（freshness 优先于 stale personal memory）：`当前真实 bbox → fresh personal bbox memory（age ≤ normal TTL）→ view scale profile（当前 projected footpoint 深度估计尺寸）→ stale personal memory grace（仅 profile 不可用时兜底）→ footpoint 光圈`。`bbox_memory_grace_ms` 是真正的 grace（不压过更合适的当前尺度估计）。
- **契约扩展**：`bbox_source` 新增 `view_scale_profiled`；overlay player 可选新增 `display_state`（状态机当前状态）、`bbox_stale: bool`、`bbox_age_ms: float | null`（后端知道 stale/age，前端据此淡化，不做无依据猜测）。
- **状态机硬 stop / reset 不变量**：target geometry invalid → 不允许 synthetic projected box；无有效 fused/projected point 且 prediction 超 TTL → 必须 HIDDEN；bbox memory > ttl+grace 且 profile 不可用 → 不得因上一状态是 PROJECTED_BOX 继续画框；**new build / new job / roster reset → 状态机必须 reset**（不得把上一场 P1 状态带进下一场）。
- **验收语义独立**：本 Change 只保证"同一 evidence 序列输入，几何形态不再逐帧抖动且不伪造证据来源"；不承担"把 P1 救出来"（那是感知层 change 的职责）。
- **scope 边界（明确不做）**：不修改 `_decide_entity` 的证据来源与分支优先级（F0/F1/donor/fused 判定逻辑不动）；不修改 guidance/association/perception；不新增检测阶段；不改变 `evidence_type` 语义（只新增正交的展示层状态）。

## Capabilities

### New Capabilities

- `stabilize-multiview-overlay-display`: fused overlay 展示稳定性——跨 tick 展示状态机（迟滞稳定 geometry、`evidence_type` 正交、ms 时间单位、硬 stop/reset）、整场两遍式 `ViewPersonScaleProfile` 透视尺度模型、bbox fallback 层级（freshness 优先）、`bbox_stale/bbox_age_ms` 展示 freshness 契约。

### Modified Capabilities

- `multiview-fused-player-overlay`: 展示决策从"逐 tick 瞬时证据"升级为"跨 tick 迟滞状态机"（MODIFIED：Evidence 分支决策链 requirement 补充正交语义——`evidence_type` 永远反映真实证据，`display_state` 独立于它）；`bbox_source` 新增 `view_scale_profiled`；cross_view projected bbox fallback 顺序调整。
- `video-overlay-hud`: 前端叠加样式新增 `view_scale_profiled` 虚线样式、`bbox_stale` 淡化语义（synthetic projected box 虚线；stale 可淡化）。

## Impact

- **后端**：`backend/app/vision/multiview/fused_overlay_builder.py`（新增 `OverlayDisplayStateMachine` 状态机 + `DisplayPlan` 输出、`ViewPersonScaleProfile` 两遍式构建与查询、bbox fallback 顺序调整、`bbox_memory_grace_ms` 配置、`_decide_display_entity` 包装器——接收 raw evidence + current display context）、`fused_overlay_types.py`（`BBoxSource` 新增 `view_scale_profiled`；overlay player 新增 `display_state / bbox_stale / bbox_age_ms` 可选字段）、`fused_overlay_bundle.py`（Pass 1 收集 scale 样本的只读数据源）。
- **前端**：`src/components/platform/VideoAnalysisCard.tsx`（`view_scale_profiled` 虚线样式、`bbox_stale` 淡化）、`src/types/report.ts`（`bbox_source` 枚举扩展、`display_state / bbox_stale / bbox_age_ms` 可选字段）。
- **契约**：`multiview-fused-player-overlay.v1` 的 `bbox_source` 枚举扩展（向后兼容：旧值不变）；overlay player 可选新增 `display_state / bbox_stale / bbox_age_ms`（缺省兼容）。
- **测试**：状态机（真实 bbox 恢复立即升级 / synthetic upgrade 需 confirm / geometry 无效 hard stop / reset / 逐帧抖动消除断言）；scale profile（两遍式 / 只收真实 bbox / synthetic 不回喂 / 邻桶插值 / 样本不足 fallback）；bbox fallback 顺序（fresh 优先于 stale / profile 优先于 stale memory）；验收不变量（真实 observation 当前 tick 显示真实框 / 无证据超 hard TTL 不显示 / synthetic 不进 memory/profile / 状态切换 ≤ baseline）。
- **OpenSpec**：新增 capability `stabilize-multiview-overlay-display`；MODIFIED `multiview-fused-player-overlay`、`video-overlay-hud`。
