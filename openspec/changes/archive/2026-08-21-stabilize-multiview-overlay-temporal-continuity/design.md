## Context

`joint_tracking_v2` 已能把真实检测、guided recovery、跨视角投影与预测融合成稳定球员身份，并产出两类正交展示语义：`evidence_type`（真实证据来源）与 `display_state`（展示几何形态）。后端 `OverlayDisplayStateMachine` 已定义毫秒级迟滞参数（`hysteresis_grace_ms = 100`、`projected_box_hold_ms = 400`、`predicted_ttl_ms = 500`），并在每个 Overlay entity 序列化了 `display_state`。

但存在三层断裂：

1. **状态机"死参数"**：[overlay_display_state.py](file:///Users/tuian/Documents/大学/竞赛/大创/匹克球/前期展示web/pre-pickleball/backend/app/vision/multiview/overlay_display_state.py) 的 `step()` 全程未读 `hysteresis_grace_ms` / `projected_box_hold_ms`，BOX↔POINT 完全由 `has_synthetic_bbox` 每 tick 二值决定，渐进降级未发生。
2. **renderer 不消费 `display_state`**：`FusedPlayerBox` 只键在 `entity.evidence_type` → `FUSED_EVIDENCE_STYLE`，从未读 `display_state`。
3. **颜色被 evidence 驱动**：`FUSED_EVIDENCE_STYLE` 为 base/guided=绿、refined=蓝、cross_view=黄、predicted=灰、bootstrap=粉，直接违反 `video-overlay-hud` "球员颜色仅表示身份"契约。

现状链路：

```
后端 evidence_type ──→ FUSED_EVIDENCE_STYLE ──→ 颜色/线型/透明度
后端 display_state ──→ (被序列化但无人消费)
```

## Goals / Non-Goals

**Goals:**

- 建立 `player_id → identity hue` / `display_state → geometry topology` / `evidence_type → provenance style` 三层的正式职责划分，并让 renderer 真正消费 `display_state`。
- 完成 `OverlayDisplayStateMachine` 的毫秒级迟滞语义，使 `hysteresis_grace_ms` / `projected_box_hold_ms` 真正参与渐进降级。
- 保持真实 observation 零延迟恢复、hard stop（TTL/geometry invalid/identity reset）优先于任何 hold。
- 用真实素材（既有 P1 job 重建，不重跑 detector/tracker）量化验收 `identity_color_switch_count = 0` 及 metric diff = 0。
- 本 Change 范围只到 Stage 0–2（契约修正 + FSM 闭环 + 真实素材验收），插值/几何平滑留到 Future Work。

**Non-Goals:**

- 不修改 P1 tracking / association / GlobalPlayerState、F0/F1 fusion、evidence_type 判定、detector/source confidence、metric_eligible、fused_player_trajectory、移动/热力图/区域指标。
- 不新增 ReID、不新增 presentation trajectory artifact。
- 不做 short-gap 双向插值、不做 One Euro / Kalman bbox smoothing（Future Work）。

## Decisions

### D1 三层职责冻结（而非 `display_state` 绝对化）

不采用"display_state 决定实/虚、evidence_type 只管 badge"的二元绝对划分，避免削弱"synthetic evidence 不得伪装真实检测"契约。冻结为：

| 输入 | 负责 | 是否可被时间迟滞改变 |
|---|---|---|
| `player_id` | identity hue（主色恒定跨 evidence） | 否 |
| `display_state` | geometry topology：BOX/POINT/HIDDEN 与 time hold / 渐进降级 | 是（本层核心） |
| `evidence_type` | provenance style：实线/虚线/透明度/badge（MUST NOT 改主色） | 否（保持诚实降级） |

→ 例：`P1 + base_observed` = P1 主色 + BOX + 实线；`P1 + cross_view_projected` = 同一 P1 主色 + BOX + 虚线；`P1 + predicted_only` = 同一 P1 主色 + POINT/HALO + 淡化。

**三件事完全正交**：`evidence_type` 回答"现在凭什么认为人在这里"，`display_state` 回答"现在怎么展示"，`bbox_source` 回答"这个框的几何从哪里来"，三者职责不重叠。特别是 **`REAL_BOX` / `ASSISTED_BOX` SHALL 仅在当前 tick 存在对应真实 target-view bbox 时才合法**；真实 bbox 丢失后迟滞 SHALL 立即把 `display_state` 降为 `PROJECTED_BOX`（复用最后可靠 presentation box geometry），**MUST NOT 继续输出 `REAL_BOX`**——grace 保护的是"BOX topology 不塌成 POINT"，不是"REAL_BOX 状态继续存在"。

**备选考虑**：直接由 `display_state` 单一权威决定全部视觉。否决理由：会令 synthetic 框与真实框在证据层面难以区分，削弱 honesty 契约；也与既有 spec 的"evidence 诚实降级"相冲突。

### D2 唯一决定 hue 的键是 `player_id`

移除以 evidence → 颜色的映射，改为 `Player_N → identity color palette`（跨 evidence 恒定）。`refined_observed` / `bootstrap_backfill` 不再拥有独立主色，改由次级通道表达 provenance：
- refined：保留出身 badge（label），不暗示"更高可信"；
- bootstrap：用透明度/短时标签表达"启动回填"，不整框换色。

**Legacy ID 兼容**：`Player_N → 固定 palette`；可解析的历史 ID（`P1`、`player_1`、`global_player_1` 等）先 normalise 到 `Player_N` 再取 palette；unknown ID 用 `deterministic hash` 分配 palette 槽位。三者均满足"同一 ID 跨 evidence hue 恒定"，且 unknown 不得全部落到默认绿（避免撞色）。

**备选考虑**：为 refined 保留独立 accent 色。否决理由：会重新引入"颜色随 evidence 变"的路径，且与 spec（颜色=身份）冲突。

### D2b 展示决断收敛为纯函数 resolver

为可测性与 legacy fallback，把展示决断收敛为无副作用的纯函数，替代散落 JSX 的条件：
- `resolvePlayerIdentityHue(playerId)`：identity hue（跨 evidence 恒定）
- `resolveEvidencePresentation(evidenceType, displayState?)`：provenance（实/虚/透明度/badge）
- `resolveDisplayGeometry(displayState)`：topology（BOX/POINT/HIDDEN）
- `resolveEffectiveDisplayState(entity)`：新产物 `display_state` 为 direct authority；旧产物缺失时从 `evidence_type + bbox + footpoint` 推导 legacy display_state

这样"身份色恒定"与 backward compatibility 都可做纯单元测试，renderer 只消费 resolver 结果。

### D3 迟滞语义冻结：作用域 + 计时权威

`projected_box_hold_ms` = "模板瞬失宽限"，非"合成框总生命周期"——仅在**已存在可信 projected/display bbox 后、bbox template 短时间内瞬时不可用**时短暂保持上一份 presentation box geometry。position evidence TTL 与 geometry template hold 是两套概念；donor/global evidence 失效由更高层 hard TTL 强制收敛。

**作用域**：`hysteresis_grace_ms` 只在仍存在当前跨视角位置证据（`observed → cross_view_projected`）的降级上生效；`observed → predicted_only` 直接 `PREDICTED_POINT`，不得用旧 bbox 画人体框。两条独立的降级链：

```
REAL_BOX / ASSISTED_BOX
  │  target miss + donor/global projected evidence valid
  ▼  立即降级为 PROJECTED_BOX（复用最后可靠 presentation geometry，MUST NOT 保留 REAL_BOX）
PROJECTED_BOX
  │  template 瞬失 ≤ projected_box_hold_ms
  ▼  保持上一份 presentation box geometry（不塌 POINT）
PROJECTED_BOX (held)
  │  template 仍不可用 / hold 用尽
  ▼
PROJECTED_POINT
  │  donor 消失但 global prediction 有效
  ▼
PREDICTED_POINT
  │  prediction hard TTL 超限
  ▼
HIDDEN

REAL_BOX / ASSISTED_BOX
  │  target miss + 无 projected 位置证据，仅 prediction
  ▼  直接 PREDICTED_POINT（不用旧 bbox 画人体框）
PREDICTED_POINT → HIDDEN
```

**计时权威**（不再用一个泛化的 `last_box_ts` 承担三语义）：
- `hysteresis_grace_ms` 从 **`last_real_bbox_ts`**（真实观测）起算；
- `projected_box_hold_ms` 从 **`last_valid_box_geometry_ts`**（最后成功 presentation bbox）起算——MUST NOT 从 `last_real_bbox_ts` 起算，否则 real 后经 200ms 的 projected 复用会让 hold 提前过期而失去保护；
- `last_state_transition_ts` 仅作诊断。

Hard stop 恒定优先于一切 hold：`geometry invalid`、`identity reset`、无有效 projected/predicted position、prediction TTL expired、job/roster reset。

### D4 真实 observation 零延迟恢复

当前 target view 出现真实 bbox（base/guided/accepted refined）时立即升回 BOX，`hysteresis timer / synthetic confirm counter / projected hold` 均不延迟。沿用现有逐帧逻辑与既有单测。

**备选考虑**：真实恢复也走短暂确认。否决理由：与既有 spec 及"真实重检测立即显示"不变量冲突。

### D5 验收：frontend 契约测试 + backend 真实素材验收（含反向 safety）

用既有 P1 job / `joint_debug_trace` 反复构建 Overlay（后端 display builder 是 post-fusion、只读消费 F0/F1 evidence），不重跑 detector/tracker。验收分两侧：

**前端 contract test（身份色）**：颜色是 React renderer 职责，不放 Python 里复制第二套映射。基于 D2b 的纯函数 resolver 做单测：`resolvePlayerIdentityHue(player_id)` 跨 evidence 恒定 → `identity_color_switch_count == 0`。

**backend real-material acceptance（状态机与 hold）**：扩展 `accept_overlay_stability.py`，采集：
- `display_state_transitions_per_minute` / `box_point_transition_count` / `hidden_transition_count` / `short_hidden_gap_count`
- `real_observation_display_latency_ms ≈ 0`
- `synthetic_box_hold_duration_ms`（验证 D3 计时权威）

**反向 safety（防赖屏作弊）**——"最容易消灭 flicker 的办法是让框永不消失"，必须加：
- `hard_ttl_violation_count == 0`：evidence 已超 TTL / geometry invalid / reset 后仍继续显示 BOX/POINT 的次数
- `max_hold_overrun_ms ≤ 一个 canonical tick tolerance`：`projected_box_hold_ms=400` 实际不得 hold 到 700ms
- （可选）`false_persistence_count`：对人工标注"球员确实消失/离场"窗口，确认旧框不赖屏

验收 = flicker ↓ **AND** false persistence 不 ↑。

**权威数据不变量（hash 化）**：metric diff 不靠重跑 metric pipeline 比较数值，而用 artifact 前后 hash / canonical JSON deep-equality——rebuild overlay 前对 `fused_player_trajectory`、movement/heatmap inputs 等权威产物取 SHA256，rebuild 后再取，断言逐一相等。避免浮点/序列化差异与扩大测试面。

**备选考虑**：直接盲上插值/平滑后凭观感验收。否决理由：无法分辨收益来自"状态不乱跳"还是"框更平滑"，且无法证明不污染指标。

### D6 OpenSpec 管理

- 新建（不修改）归档的 `2026-08-15-stabilize-multiview-overlay-display`。
- Delta Spec 修改三个 live spec：`stabilize-multiview-overlay-display`、`video-overlay-hud`、`multiview-fused-player-overlay`（均在 `openspec/specs/`）。
- 第一轮不新增 presentation artifact；仅当 Stage 0–2 收尾且仍有明显的 `100–500ms` 空洞，才进入 Future Work（短空洞恢复 → 几何平滑）。

## Risks / Trade-offs

- **`projected_box_hold_ms` 过度延长导致合成框赖屏** → 由更高层 hard TTL（prediction TTL / identity reset / job reset）兜底，hold 仅保护"template 瞬时不可用"。
- **renderer 改键到 `display_state` 后出现"实/虚"新冲突**（如迟滞 hold 期间 `REAL_BOX` 但 evidence 为 cross_view）→ 用 D1 三层职责 + 一条显式优先级规则（display_state 定 topology，evidence_type 定线型）写进 delta spec，避免 Phase 1 引入歧义。
- **身份色归并掩盖 provenance** → refined/bootstrap 以次级通道（badge/透明度/短标签）保留可辨识度，并加"identity 颜色跨 evidence 不变"的前端测试。
- **迟滞 ms 跨 `frameStride` 稳定性**：canonical tick 间距随 frameStride 变化，故全部用 ms 而非 tick → 参数已是 ms，`step()` 需以 `now_ms` 驱动。
- **验收依赖真实素材质量** → 复用既有 P1 job + `joint_debug_trace` 与已有 stability acceptance script，量化而非观感验收。

## Open Questions

- `refined_observed` / `bootstrap_backfill` 的次级 provenance 视觉通道具体形态（badge 文案 / 透明度档位 / 短时标签）——实施时按可视化一致性定稿，不影响 architecture。
- （已定）在 delta spec 增加一条 Requirement："展示几何状态与证据来源正交"——`display_state` 定 topology、`evidence_type` 定 provenance、`player_id` 为 identity hue 唯一 authority，3 者 MUST NOT 相互重写。