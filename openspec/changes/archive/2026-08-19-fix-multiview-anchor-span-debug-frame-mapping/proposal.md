## Why

双摄联同分析的 Debug Replay 四象限里，Cam-2 视角在视频开头通常"定格"数秒后才突然开始运动，而 Cam-1 / 球场 / 状态象限早已正常推进。根因已高置信度定位（并对照 `main` 与 `8e22ac0` 核实）：

- `CanonicalAnalysisClock._fallback_valid_start_frame()` 当前用 `seed_target = max(take_ms/1000.0, calibration.valid_start_seconds)` 把锚点区间外的所有 canonical tick 钳制到**第一锚点时间**（`dual_camera_sync.py` 中 `valid_start_seconds = min(reference_times)`）。
- 因此 `t < valid_start` 的连续几十个 tick 全选中 Cam-2 的同一张源帧，`joint_debug_renderer.py` 的 `if source_index == last_index: frame = cached_frame.copy()` 把这些 tick 渲染成同一张冻结画面。
- 该 `fallback_valid_start` 路径由 `8e22ac0`（2026-08-15，"修 Cam-2 开头黑屏"）引入——为消灭窗口开头 UNAVAILABLE 黑屏，代价是把"无权威帧"替换成了"静止帧"，是一次语义回归。

同一根因在 pre/post 两端表现不同：`build_frame_map()` 对 `valid_start_seconds` / `valid_end_seconds` 是对称硬门，但 `_fallback_valid_start_frame` 只 clamp 低侧。pre-anchor 是确定性的 clamp freeze 回归；post-anchor 时 `seed_target = max(t, valid_start) = t` 仍随 canonical 推进，若 `map_reference_time(t)` 落在 Cam-2 PTS 内，当前代码其实已返回推进帧（只是误标 `fallback_valid_start`），仅当 mapped local 真正越出媒体才返回 `None`。即 pre 是确定修 bug，post 更多是在做语义正规化（把误标的 `fallback_valid_start` 显式化为 `available_extrapolated`）。

本 Change 只做 **Scope A（visual-only 修复）**：让锚点区间外的 Cam-2 拿到真实递增的媒体帧，Debug Replay 不再冻结/黑屏；**不改变** detector / tracker / association / fusion / recovery 的任何感知行为。**Scope B（让外推帧条件式进入感知并降权）明确不进本 Change**，列为后续独立 Change `enable-confidence-gated-anchor-extrapolated-perception`。

## What Changes

- **pre/post 两端对称外推**：锚点区间外的 canonical tick 直接用原始时间 `map_reference_time(calibration, t)` 计算 Cam-2 目标时间（删除 `max(t, valid_start)` clamp）；目标落在 Cam-2 媒体 PTS 内 → 选最近真实帧并标记 `available_extrapolated`；越出媒体才标记 `unavailable_out_of_media_range`。低侧不再冻结，高侧只要真实媒体仍在就持续有画面。
- **新增诊断状态 `available_extrapolated`** 与字段 `mapping_mode`（`pre_anchor_extrapolation` | `post_anchor_extrapolation`）、`extrapolation_distance_ms`（距最近锚点边界的外推距离）、`selection_error_ms`，全部如实记录、不冒充 authoritative `available`。
- **Debug Replay 渲染 `available_extrapolated`**，并兼容历史 `fallback_valid_start` 产物（旧 trace 仍渲染回退帧）。
- **外推帧不进入感知主链**：`available_extrapolated` 携带真实 `source_frame_index` 进入 trace / renderer，但**不推进** `last_consumed_source_frame_index`；`MultiViewJointRun` 因 `status != "available"` 自动跳过，detector / tracker / association / fusion / recovery 行为完全不变。
- **`build_frame_map()` 默认权威契约不变**：它仍对锚点区间外返回 `unavailable_outside_valid_interval`；外推是 `CanonicalAnalysisClock` 在拿到该状态后**额外**做的显示层动作，不回写、不修改其既有权威 `available` 语义，避免把其他调用方一起改成"允许外推"。
- **历史 artifact 兼容**：`SyncCalibration.valid_start_seconds` / `valid_end_seconds` 字段名与 `calibration_to_dict` / `calibration_from_dict` 读写**保持不变**；本 Change 仅将其语义正式定义为 **anchor evidence span（人工锚点覆盖区间）**，不再表示"媒体有效窗口"。spec、backend 注释与诊断文案称 "anchor span"，不修改前端 UI 文案，不做破坏性 rename。

## Capabilities

### Modified Capabilities

- `multiview-synchronized-analysis-clock`：将既有的"窗口开头副摄帧选择回退"需求泛化为"锚点区间外对称外推真实媒体帧"（pre/post 同修、不 clamp、新增 `available_extrapolated`）；新增"外推帧不污染 tracker 消费游标"需求（视觉路径不推进感知游标）。
- `multiview-joint-observability`：将"Debug replay 帧选择与 clock 回退一致"需求扩展为兼容 `available_extrapolated` 渲染且保留历史 `fallback_valid_start` 兼容。

## Impact

- **后端**：`backend/app/vision/multiview/analysis_clock.py`（`_fallback_valid_start_frame` 替换为 `_select_extrapolated_display_frame`，删除 clamp；新增 `available_extrapolated` 路径且不更新 `last_consumed`；`FrameSample` 增加 `mapping_mode` / `extrapolation_distance_ms` 字段）、`backend/app/services/joint_debug_renderer.py`（`renderable` 集合加入 `available_extrapolated`，保留 `fallback_valid_start` 历史兼容）、`backend/app/vision/multiview/multiview_joint_run.py`（在统一 `_view_detail(...)` 路径从 `FrameSample` 透传 `mapping_mode` / `extrapolation_distance_ms` / `frame_status`；不在 secondary view trace dict 特例塞值；因 status 仍非 `available`，感知行为零变化）、`backend/app/services/dual_camera_sync.py`（`valid_start_seconds/end` 注释正式定义为 anchor evidence span，读写逻辑不变）。
- **契约**：trace view 增加可选 `mapping_mode` / `extrapolation_distance_ms`（向后兼容，旧 trace 无该字段仍正常渲染）；`FrameSample` 新增字段默认 `None`。
- **测试**：clock 单测（pre/post 外推递增、无 clamp、媒体外 `unavailable_out_of_media_range`、游标不推进）；renderer 测试（`available_extrapolated` 不冻结、历史 `fallback_valid_start` 仍渲染）；集成测试（锚点区间外 `tracking_session.step/prepare` 次数 == 0、锚点内行为不变）；历史 `valid_start/end` artifact 读取测试。
- **前端**：无代码改动（Debug Replay 为后端生成 MP4，前端仅播放；`available_extrapolated` 作为 status 字符串自然呈现）。如后续需在 UI 标注 `mapping_mode` 徽标，属展示增强，不纳入本 Change。
- **OpenSpec**：MODIFIED `multiview-synchronized-analysis-clock`、MODIFIED `multiview-joint-observability`；后续 `enable-confidence-gated-anchor-extrapolated-perception`（Scope B）将新增统一 `participates_in_perception(...)` 谓词并收敛 22 处字符串门控。
