## Context

`CanonicalAnalysisClock.tick()` 当前对 secondary view 的解析顺序是：

```text
build_frame_map()  → authoritative 路径
    ↓ 区间外报 unavailable_outside_valid_interval
_fallback_valid_start_frame(take_ms)
    ↓ seed_target = max(take_ms/1000.0, valid_start_seconds)   ← 低侧钳制
    ↓ map_reference_time(calibration, seed_target)
    ↓ 媒体内 → 同一帧 ; 媒体外 → None
    ↓ status = fallback_valid_start
```

`fallback_valid_start` 由 `8e22ac0` 引入，目的是消灭窗口开头 Cam-2 黑屏，但代价是把前 `valid_start` 秒内的所有 tick 钳到第一锚点帧——Debug Replay 渲染时 `cached_frame.copy()` 把这些 tick 画成同一张静止画面（你肉眼看到的"Cam-2 定格"）。

`build_frame_map()` 对 `valid_start_seconds` / `valid_end_seconds` 是对称硬门，但 `_fallback_valid_start_frame` 只 clamp 低侧。pre-anchor 是确定性的 clamp freeze 回归；post-anchor 时 `seed_target = max(t, valid_start) = t` 仍随 canonical 推进，若 `map_reference_time(t)` 落在 Cam-2 PTS 内当前代码其实已返回推进帧（只是误标 `fallback_valid_start`），仅当 mapped local 真正越出媒体才返回 `None`。即 pre 是确定修 bug，post 更多是语义正规化。

本 Change 是 Scope A（visual-only）：修复 Debug Replay 的冻结/黑屏，**不触碰** joint perception 主链。Scope B（外推帧条件式进入感知并降权）明确不进本 Change。

## Goals / Non-Goals

**Goals:**

- 让锚点区间外（pre/post 对称）的 Cam-2 在 Debug Replay 中拿到真实、随时间递增的媒体帧，不再定格/黑屏。
- 引入 `available_extrapolated` + `mapping_mode` / `extrapolation_distance_ms` / `selection_error_ms` 诊断，与 authoritative `available` 显式区分。
- 外推帧**不进入** detector / tracker / association / fusion / recovery（perception 行为零变化）。
- `build_frame_map()` 的默认权威契约不变；历史 `valid_start/end` calibration artifact 仍能读取。

**Non-Goals (Scope A 明确不做):**

- 不改任何 `status != "available"` 门控（共约 22 处，分布在 `multiview_joint_run.py` / `fusion.py` / `quality.py` / `offline_refinement.py` / `player_display_diagnostics.py` 等）。
- 不引入 `participates_in_perception(...)` / `is_tracking_eligible(...)` 统一谓词（属 Scope B）。
- 不对 `available_extrapolated` 做 fusion 加权 / confidence gating（属 Scope B）。
- 不破坏性 rename `valid_start_seconds` / `valid_end_seconds`（仅重定义语义）。
- 不修改前端代码。

## Decisions

### D1：`valid_start_seconds/end` 重定义为 anchor evidence span，字段名不动

`SyncCalibration.valid_start_seconds` / `valid_end_seconds` 字段名与 `calibration_to_dict()` / `calibration_from_dict()` 读写**完全不变**——历史 sync calibration artifact 依赖这两个键。

本 Change 仅将其**语义**正式从"媒体有效窗口"改为"人工锚点覆盖的 reference 时间区间（anchor evidence span）"：它只表示"从这里开始我们有直接证据验证 affine mapping"，不表示"在此之前 Cam-2 没有对应画面"。spec、backend 注释与诊断文案统一称 "anchor span"；本 Change 不修改前端 UI 文案，不做破坏性 rename。如需新增 `anchor_span_start_seconds/end_seconds`，reader 必须新字段优先 + legacy `valid_*` 回退，writer 至少过渡期保留兼容。本 Change 采取最保守路径：保留 Python 字段名，仅改注释与文档语义。

### D2：pre/post 两端对称外推，删除 clamp

`CanonicalAnalysisClock` 新增 `_select_extrapolated_display_frame(take_ms)` 替换 `_fallback_valid_start_frame()`：

```text
tick() 拿到 unavailable_outside_valid_interval (canonical 在 anchor span 外)
    ↓
_select_extrapolated_display_frame(take_ms)
    ↓
local = map_reference_time(calibration, take_ms / 1000.0)   # 不 clamp
    ↓
local 越出 [cam2_first_pts, cam2_last_pts] 媒体范围
    → unavailable_out_of_media_range
local 在媒体内，但 最近真实帧距离 |nearest.pts - local| > max_selection_error_seconds
    → unavailable_selection_error        # 复用 authoritative 质量门，外推不放松 frame-selection 质量
local 在媒体内 且 最近帧距离 <= max_selection_error_seconds
    → 选最近真实帧 → available_extrapolated
    → mapping_mode = pre_anchor_extrapolation | post_anchor_extrapolation
    → extrapolation_distance_ms = |canonical_t - nearest_anchor_boundary_t| * 1000
    → selection_error_ms = (nearest.pts - local) * 1000
```

低侧（`t < anchor_start`）：当前是确定性的 clamp freeze 回归，修复后不再固定第一锚点帧，`source_frame_index` 随 canonical 正常推进。高侧（`t > anchor_end`）：当前代码若 `map_reference_time(t)` 落在 Cam-2 媒体内已返回推进帧（误标 `fallback_valid_start`），本 Change 把它显式化为 `available_extrapolated`；仅当映射真正越出媒体才 `unavailable_out_of_media_range`。即 pre 修 bug、post 做语义正规化，实现上仍对称。

`max_selection_error_seconds` 与 `build_frame_map()` authoritative 路径同值（默认 `1/30` s ≈ 33 ms，即 `max_pairing_error_ms`）；外推改变的是 anchor-span authority gate，SHALL NOT 放松 frame-selection 质量门。

### D3：`available_extrapolated` 不污染 tracker 消费游标

`available` 路径（现 `analysis_clock.py:142`）会写 `self.last_consumed_source_frame_index[secondary_view]`——该游标语义是"已喂给有状态 tracker"，是 monotonic 不重复守卫的依据。

`_select_extrapolated_display_frame` 返回的 `FrameSample` 写入 `views[secondary_view]`、标记 `available_extrapolated`，但**SHALL NOT** 更新 `last_consumed_source_frame_index`。`MultiViewJointRun` 的 perception 主链（`multiview_joint_run.py:368` 等）与 recovery 的 `target_available` 判定都基于 `status == "available"`，因此 `available_extrapolated` 自动被跳过。

即使连续两个 canonical tick 映射到同一 Cam-2 源帧：外推路径也**不触发** `no_new_frame`（那是 `available` 路径的守卫）；renderer 的 `cached_frame.copy()` 同帧拷贝优化本就正确——真正的问题从来不是"偶尔两 tick 同帧"，而是"人为 clamp 让几十个 tick 同帧"。

### D4：诊断字段 `mapping_mode` / `extrapolation_distance_ms`

`FrameSample` dataclass 新增两个可选字段（默认 `None`，向后兼容）：

```python
mapping_mode: str | None = None          # "pre_anchor_extrapolation" | "post_anchor_extrapolation"
extrapolation_distance_ms: float | None = None
```

`selection_error_ms` 已存在，外推路径直接复用。这些字段 SHALL 在现有统一 view 序列化路径 `_view_detail(...)` 中从 `FrameSample` 透传，而非在 secondary view 的 trace dict 上做特例塞值。`joint_debug_trace.v1` 的 validator 仅要求若干必需字段存在、不拒绝额外字段，故新增 optional 字段不需升 schema version。`available_extrapolated` 的 `frame_status` 也由 `_view_detail` 统一写出（见 D8）。

### D5：`build_frame_map()` 契约不变

`build_frame_map()` 对锚点区间外返回 `unavailable_outside_valid_interval` 的权威行为**完全保留**。外推是 `CanonicalAnalysisClock` 在拿到该状态后**额外**做的显示层动作，不回写 `build_frame_map`、不修改其既有权威 `available` 语义。这样其他调用方（测试、单视角配对等）不会被动从"锚点内映射"改成"允许外推"——这是 Scope A "零 blast radius" 的保证。

### D6：Debug Renderer 兼容

`joint_debug_renderer.py:183` 的渲染集合从 `("available", "fallback_valid_start")` 扩展为 `("available", "fallback_valid_start", "available_extrapolated")`。历史 `fallback_valid_start` 产物（旧 trace）仍正常渲染回退帧；新 trace 输出 `available_extrapolated` 且 `source_frame_index` 正常递增 → renderer 解码对应真实帧，Cam-2 视角持续运动。可选：在 `_draw_view_overlays` 叠加 `mapping_mode` 文本便于诊断（不影响渲染正确性）。

### D7：历史 artifact 读取兼容

`calibration_to_dict` / `calibration_from_dict` 不变；`valid_start_seconds/end` 键照常读写。验收指标 6（历史 artifact 仍能读）由该不变性直接保证。

### D8：诊断分层 — authoritative selection 与 display availability 分离

`tick()` 当前先写 `diag["secondary_selection_status"] = selection.status`（authoritative `build_frame_map` 结果），再进入 fallback。新方案 SHALL NOT 用外推结果覆盖该值——它保留为 `unavailable_outside_valid_interval`，如实记录 authoritative 语义，D5 保护的 authoritative 契约不在 diagnostics 里混掉。

新增/区分三层诊断概念（为 Scope B 的感知资格判断预留干净接口）：

- `secondary_selection_status` = `build_frame_map()` 的 authoritative 结果（如 `unavailable_outside_valid_interval`）；
- `frame_status` = 当前 tick 交付给 Debug Replay 的显示可用状态（`available_extrapolated`）；
- `display_selection_status`（可选，显式别名）= `frame_status`；
- `mapping_mode` / `extrapolation_distance_ms` / `selection_error_ms` 作为外推诊断附在 `frame_status` 上。

即 authoritative selection、display availability、perception eligibility 是三层不同概念，互不覆盖。

## Risks / Trade-offs

- [外推帧 selection error 可能较大] → 外推统一标 `available_extrapolated`（非 `available`），误差如实记录；本 Change 不进 tracker，不引入加权；大误差风险留待 Scope B 用 `extrapolation_distance_ms` 阈值门控。
- [连续 tick 同帧被误判为 bug] → 仅"真实同帧"才触发 renderer `cached_frame.copy()`，符合预期；不再有人为 clamp 几十 tick。
- [误改 tracker 行为] → D3 保证不碰 `last_consumed`；perception 主链只认 `available`；验收指标 4（`tracking_session.step/prepare` 次数 == 0）证明 Scope A 没碰感知。
- [历史 `fallback_valid_start` trace 无法渲染] → D6 保留兼容，渲染集合显式包含该状态。
- [其他调用方因 `build_frame_map` 改动回归] → D5 不改其默认契约，外推仅在 clock 层追加。
- [高侧外推把本不该出现的帧塞进 replay] → 仅当 affine 映射真实落在 Cam-2 媒体内才 `available_extrapolated`；越界即 `unavailable_out_of_media_range`，不会出现越界静止帧。

## Migration Plan

- 纯后端字段新增（默认值），无破坏性 schema 变更；旧 trace（`fallback_valid_start`）与旧 calibration（`valid_start/end`）artifact 均向后兼容。
- `FrameSample` 新字段默认 `None`；旧消费者不受影响。
- 无 API 路由变更；Debug Replay 仍由 `debugTraceEnabled` 控制。
- `available_extrapolated` 为新增状态字符串，旧诊断/渲染消费者 unknown-status 分支照常处理。

## Open Questions

- `available_extrapolated` 是否应在 Sync section 展示外推比例/覆盖？→ 本 Change 只修渲染，不新增加权统计；展示增强随 Scope B。
- `extrapolation_distance_ms` 的降级门控阈值（Scope B 用于"外推 X 秒内才参与感知"）如何标定？→ 本 Change 只记录不消费；Scope B 再定阈值与 `sync_quality` 联合门控。
