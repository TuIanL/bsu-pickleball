## Why

当前 `joint_tracking_v2` 已能通过真实检测、guided recovery、跨视角投影与预测持续维护稳定球员身份，但融合人物 Overlay 在视频回放中仍存在明显视觉频闪：同一球员在 `base_observed / guided_observed / refined_observed / cross_view_projected / predicted_only` 等 evidence source 间切换时，人物框颜色、线型与形态高频变化；synthetic bbox 短暂不可用时人物在 BOX 与 POINT 间逐 tick 切换；短时 evidence 波动还可能表现为人物瞬时消失后再度出现。现有实现已定义 `evidence_type` 与 `display_state` 两套正交语义并在后端 Overlay entity 携带 `display_state`，但当前前端仍以 `evidence_type` 直接决定颜色与样式、未将 `display_state` 作为几何展示的权威输入；后端 `OverlayDisplayStateMachine` 的 `hysteresis_grace_ms` / `projected_box_hold_ms` 等毫秒级迟滞参数也未真正参与状态转移。这与 `video-overlay-hud` 中"球员颜色仅表示身份、同一 Player 颜色不得随 evidence source 改变"及"漏检渐进降级、毫秒级迟滞"的既有契约不一致。本 Change 完成这些既有契约在实际 renderer 与状态转移路径中的闭环，优先级高于继续推进 P2。

## What Changes

### 1. 修复球员身份颜色契约

视频人物 Overlay 的主色由 `player_id / Player_N` 决定，不再由 `evidence_type` 决定。同一 `Player_1` 在 `base_observed / guided_observed / refined_observed / cross_view_projected / predicted_only / bootstrap_backfill` 等状态始终使用同一身份色。Evidence provenance 改由次级视觉通道表达：`line pattern / opacity / badge / text label / geometry form`，不改变 Player 主色。`refined_observed` 与 `bootstrap_backfill` SHALL 保留明确 provenance 但不得通过改变主色表达。特别地，`refined_observed` SHALL NOT 被预设为"比 base 更高可信"——它仅表示 observation provenance 不同。

### 2. 正式接入 `display_state → renderer`

`REAL_BOX / ASSISTED_BOX / PROJECTED_BOX / PROJECTED_POINT / PREDICTED_POINT / HIDDEN` 成为前端人物 Overlay 几何展示的**权威状态**。展示职责三层冻结：

- `player_id` → 决定 identity hue（主色恒定，跨 evidence 不变）；
- `display_state` → 决定 geometry topology（BOX / POINT / HIDDEN）与时间 hold / 渐进降级；
- `evidence_type` → 决定 provenance style（observed / assisted / projected / predicted，实线 / 虚线 / 透明度 / badge），**MUST NOT 改变 identity hue**。

`display_state` 通过时间迟滞保持几何连续性，但 MUST NOT 修改或伪造 `evidence_type`；`evidence_type` 继续保持当前 tick 的真实 evidence provenance，MUST NOT 被 display hysteresis 修改。

### 3. 完成 Temporal Display FSM 的毫秒级迟滞语义

让 `hysteresis_grace_ms / projected_box_hold_ms / confirm_max_gap_ms / prediction TTL` 真正参与状态转换。冻结语义：真实 bbox 消失后，`hysteresis_grace_ms` 内视觉上保持 BOX-class geometry 且 `evidence_type` 立即诚实降级；随后进入 `PROJECTED_BOX`；synthetic bbox/template 瞬时不可用时 `projected_box_hold_ms` 内短暂保持上一份 presentation box geometry；随后 `PROJECTED_POINT`；donor 不可用但 global prediction 有效 → `PREDICTED_POINT`；prediction hard TTL 超限 → `HIDDEN`。

`projected_box_hold_ms` SHALL 表示"已存在可信 projected/display bbox 后，bbox template 短时间内瞬时不可用时的 geometry hold grace"，**不是** synthetic box 的无限生命周期。以下 hard stop 优先级高于任何 hold：`geometry invalid / identity reset 边界 / 无有效 projected·predicted position / prediction TTL expired / job·roster reset`，不得通过迟滞让已失效或离场人物框长期留在画面。

### 4. 保持真实 observation 的零延迟恢复

当前 target view 出现真实 `base_observed / guided_observed / accepted refined_observed` bbox 时，当前 tick SHALL 立即恢复对应 BOX display，不得因 `hysteresis timer / synthetic confirmation counter / projected hold` 延迟真实观测显示。现有状态机已有此单元测试基础，本 Change 继续保持该不变量。

### 5. 新增 Temporal Continuity 验收指标

使用已有 P1 真实 job / `joint_debug_trace` 重建 Overlay（不重新运行 detector、tracker 或 fusion）。固定指标：`identity_color_switch_count`、`display_state_transitions_per_minute`、`box_point_transition_count`、`hidden_transition_count`、`short_hidden_gap_count`、`real_observation_display_latency_ms`、`synthetic_box_hold_duration_ms`。硬约束：`identity_color_switch_count = 0`（同一 Player 的 identity hue 不得随 evidence source 切换）、`real_observation_display_latency ≈ 0`、`metric trajectory diff = 0`、`movement metrics diff = 0`、`heatmap inputs diff = 0`。本 Change 只改变 presentation，不得污染任何权威位置数据。可在现有 Overlay stability acceptance script 基础上扩展评估。

## Capabilities

### New Capabilities

（无新增 capability。）

### Modified Capabilities

- `stabilize-multiview-overlay-display`: 扩展现有时间迟滞要求——`hysteresis_grace_ms` SHALL 真正参与 display geometry downgrade；`projected_box_hold_ms` SHALL 真正控制 synthetic geometry 短时 hold；`display_state` SHALL 成为最终 renderer 的 geometry/display authority；evidence provenance 与 display continuity 保持正交。
- `video-overlay-hud`: 修改/强化——Player identity hue SHALL 跨 evidence source 恒定；`evidence_type` 不再决定人物主色；evidence source 使用 line pattern / opacity / badge 等次级视觉语言表达；renderer SHALL 消费 `display_state`。
- `multiview-fused-player-overlay`: 修改/强化——已存在的 `display_state` 成为正式展示契约（而非仅被序列化但未消费的可选 metadata）；`evidence_type` 继续保持 raw provenance；旧 artifact 缺失 `display_state` 时保持兼容 fallback。

## Impact

主要影响：

```
backend/app/vision/multiview/overlay_display_state.py
backend/app/vision/multiview/fused_overlay_builder.py

src/components/platform/VideoAnalysisCard.tsx
src/types/report.ts

backend/tests/test_overlay_display_stability.py
frontend fused-overlay / playback 相关测试
backend/scripts/accept_overlay_stability.py

openspec/specs/stabilize-multiview-overlay-display/
openspec/specs/video-overlay-hud/
openspec/specs/multiview-fused-player-overlay/
```

**Non-Goals**（本 Change 不做）：修改 P1 tracking / association / GlobalPlayerState；修改 F0 / F1 fusion；修改 evidence_type 判定；修改 detector/source confidence；修改 metric_eligible；修改 fused_player_trajectory；修改移动距离/速度/热力图/区域统计；新增 ReID；新增新的 presentation trajectory artifact；实施 short-gap 双向插值；实施 One Euro / Kalman bbox smoothing。

**Future Work**（仅当完成并用真实素材验收后仍存在明显 `100–500ms` 空洞再考虑）：
- `add-multiview-overlay-short-gap-restoration`：对 `A 有 / B·C 缺失 / D 再有` 且满足 `same Player_N · same identity epoch/segment · gap ≤ threshold · 无 reset/conflict/long jump` 的空洞，在纯 presentation 层对 `(cx, cy, w, h)` 双向插值，插值结果 `presentation only / metric_eligible = false`。
- `smooth-multiview-overlay-bbox-geometry`：对连续有框但仍轻微几何 jitter 的情况，采用 `cx/cy → One Euro`、`w/h → slow EMA/adaptive filter`，而非直接平滑 `[x1,y1,x2,y2]`。