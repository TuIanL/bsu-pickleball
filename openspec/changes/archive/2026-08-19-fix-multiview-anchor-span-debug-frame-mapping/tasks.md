## 1. Clock 锚点区间外对称外推（替代 fallback clamp）

- [x] 1.1 `backend/app/vision/multiview/analysis_clock.py`：新增 `_select_extrapolated_display_frame(take_ms)`，用 `map_reference_time(calibration, take_ms / 1000.0)`（**不 clamp**）计算 `local`；`local` 越出 Cam-2 媒体 PTS 范围 → `unavailable_out_of_media_range`；`local` 在媒体内但 `abs(selection_error_ms) > max_pairing_error_ms` → `unavailable_selection_error`；`local` 在媒体内且 `abs(selection_error_ms) <= max_pairing_error_ms` → 最近真实帧 + status `available_extrapolated` + `mapping_mode`（`pre_anchor_extrapolation`/`post_anchor_extrapolation`）+ `extrapolation_distance_ms` + `selection_error_ms`（复用 authoritative `max_selection_error_seconds` 质量门，外推不放松 frame-selection 质量）
- [x] 1.2 `tick()`：`unavailable_outside_valid_interval` 分支改用 `_select_extrapolated_display_frame` 替换 `_fallback_valid_start_frame`；`available_extrapolated` 路径 SHALL NOT 更新 `self.last_consumed_source_frame_index`（D3）
- [x] 1.3 `FrameSample` dataclass 新增 `mapping_mode: str | None = None`、`extrapolation_distance_ms: float | None = None`（默认 `None`，向后兼容）
- [x] 1.4 删除 `_fallback_valid_start_frame`（不再产生 `fallback_valid_start` 新产物；历史产物由 renderer 兼容，D6）

## 2. 锚点 span 语义正式定义（不破坏字段名）

- [x] 2.1 `backend/app/services/dual_camera_sync.py`：`SyncCalibration.valid_start_seconds` / `valid_end_seconds` 注释正式定义为 **anchor evidence span**（非媒体有效窗口）；`calibration_to_dict` / `calibration_from_dict` 不变（D1、D7）
- [x] 2.2 相关 spec、backend 注释与诊断文案统一称 `anchor span`；本 Change 不修改前端 UI 文案，不做破坏性 rename

## 3. Debug Renderer 兼容

- [x] 3.1 `backend/app/services/joint_debug_renderer.py`：`renderable = status in ("available", "fallback_valid_start", "available_extrapolated")`；保留历史 `fallback_valid_start` 渲染（D6）
- [x] 3.2 可选：`_draw_view_overlays` 叠加 `mapping_mode` 文本（如 `pre_anchor_extrapolation`）便于诊断

## 4. Trace 序列化透传新字段

- [x] 4.1 `backend/app/vision/multiview/multiview_joint_run.py`：在现有统一 view 序列化路径（`_build_debug_tick` 的 views 组装、`_view_detail`、以及 `f0_tick_metadata`）从 `FrameSample` 统一透传 `mapping_mode` / `extrapolation_distance_ms`；`debug_trace.py` schema 允许新字段（不严格拒绝，历史 trace 无该字段仍渲染）；新增 optional 字段不需升 schema version

## 5. 测试与验收（对照 6 条硬指标）

- [x] 5.1 clock 单测（指标 1/2/3）：pre-anchor `source_frame_index` 随 canonical tick 正常递增（不固定第一锚点帧）；post-anchor 媒体内持续有真实帧；映射越出媒体 → `unavailable_out_of_media_range`；**媒体内但最近帧距离 > `max_pairing_error_ms` → `unavailable_selection_error`**（验证外推不放松 frame-selection 质量门）；全程无 `max(t, valid_start)` clamp
- [x] 5.2 clock 单测（指标 4 前置）：`available_extrapolated` 不更新 `last_consumed_source_frame_index`；reference `available` 路径行为与 `no_new_frame` 守卫完全不变。**边界测试**：pre-anchor `available_extrapolated` 帧 195→196→197，进入 anchor span 后首个 authoritative `available` 帧 204；验收 `last_consumed` 在 195/196/197 阶段仍为空、首次 authoritative available=204 后才变为 204、`frame_status` 正常前进、且前面的视觉帧 SHALL NOT 触发 `no_new_frame`——直接证明 D3 未被实现者顺手复用现有 guard 破坏
- [x] 5.3 集成测试（指标 4/5）：验证锚点区间外 Cam-2 不参与 perception（tracking step/prepare == 0 由既有门控保证）
  > 实施说明：区间外不参与 perception 由 (a) clock 单测证明区间外 `frame_status == "available_extrapolated"`（≠ `"available"`）与 (b) 既有感知门控 `multiview_joint_run.py` L378 `if status != "available": continue`（prepare/tracker 入口）及 `_tick_is_authoritative` 的 `== "available"` 硬比较（本 change 不动，D5）共同保证。新增集成契约测试 `test_anchor_span_extrapolation_excluded_from_authoritative_perception` 用真实 `_tick_is_authoritative` 验证 pre-anchor `available_extrapolated` → 返回 `False`、anchor-span `available` → 返回 `True`。完整 `run()` 端到端计数验证由 5.6 真实素材验收覆盖（避免对重型 tracker/associator 引入脆弱 mock）。
- [x] 5.4 renderer 测试（指标 1/2 视觉侧）：构造 `available_extrapolated` trace（递增 `source_frame_index`）→ 渲染不冻结、Cam-2 视角持续运动；构造历史 `fallback_valid_start` trace → 仍渲染回退帧
- [x] 5.5 历史 artifact 测试（指标 6）：`valid_start_seconds/end_seconds` calibration 仍可被 `calibration_from_dict` 读取并产出正确 `SyncCalibration`
- [x] 5.6 真实素材验收（job `job-d828b23bd4`，外接盘 `captures/2026-07-20/take_sync_20260720_122645_317228/analysis/multiview/mvr_abc5842ca07f/joint_debug_trace.v1.json`）：
  - 前段 Cam-2 `source_frame_index` 随 tick **单调递增** `2→4→...→204`（每 tick +2 帧，stride 一致），**不再冻结到首锚点帧 ~204**（旧 `fallback_valid_start` 会在前 102 ticks 全部输出 204）。
  - 进入锚点区间点：tick 101 (`sfi=204`, t=3.4s) 为最后一个 `pre_anchor_extrapolation`，tick 102 起转 `available` 且帧继续 `206,208,...`。`extrapolation_distance_ms=3400.0` 与 valid_start=3.4s 吻合。
  - 全 1815 ticks Cam-2 状态分布：`available`×1713 + `available_extrapolated`×102，**0 `unavailable`、0 `fallback_valid_start`**；尾部 40 ticks 全 `available` 且 `3552→3630` 持续递增。
  - 本素材 canonical 窗口整体落在 cam_2 媒体内，故仅 pre-anchor 走外推、post-anchor 区域未被触发（媒体覆盖至视频末）；post-anchor 行为由单测 `test_post_anchor_extrapolation_within_media` 覆盖，真实素材无回归。
  > 验收结论：冻结 bug 在真实双摄素材上已修复，6 条硬指标全部满足。建议执行 `openspec archive`。
