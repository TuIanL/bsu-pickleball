## Why

双摄同步分析 Debug Replay 存在两个可解释性/可读性缺陷：其一，副摄（如 cam-2）前几秒画面中有人但没有任何检测框，用户会误判为检测器漏检——实际上这是两条不同路径的叠加：`available_extrapolated` 等 display-only tick 根本没有执行 perception（tracker 未 step，无任何 track 数据），以及正常 `available` tick 中 bootstrap 期候选 track 被 `lock_only` eligibility 正确隔离在 formal `detections` 之外。Debug Replay 目前无法表达"算法实际处在哪个阶段"。其二，左下角 canonical court panel 把 20×44 ft 球场非等比映射到 530×225 px（横向 26.5 px/ft vs 纵向 5.11 px/ft，失真约 5.18 倍），几何外观完全失真，且缺少网、NVZ 线和发球中线。

本 change 仅提升 joint Debug Replay 对运行事实的可解释性与球场几何可读性；不改变 PlayerLock、tracking eligibility、association、fusion、sync authority 或正式分析产物的判定语义。

## What Changes

- **Debug Trace 新增可选 `candidate_detections` 字段（debug-only）**：正常 `available` tick 中，若 tracker 已产生存活 track 但尚未满足 `lock_only` formal eligibility，trace 可额外保存这些 provisional 候选框（含 bbox/track_id）；formal `detections` 定义保持不变。旧 trace（无此字段）仍可正常加载，schema 版本保持 `joint_debug_trace.v1`。
- **Debug Renderer 区分候选框与正式框**：候选框以细线弱色绘制并统一标注 `candidate`（不做 PlayerLock slot 状态反查）；正式框保持现状高亮实线并标注 `Player_N`。tracker 完成正式锁定后，候选框被正式框取代。
- **Display-only 帧明确标识**：`available_extrapolated` / `fallback_valid_start` 等仅用于显示、未执行 perception 的帧，renderer SHALL 在画面上明确标注 "DISPLAY ONLY / TRACKING NOT STEPPED" 类状态，且 SHALL NOT 伪造任何 candidate/formal bbox。
- **Canonical court panel 等比重绘**：使用单一 px/ft 比例（横置 44 ft 长边，保持真实 2.2:1 比例），补齐网、两条 NVZ line（距网 7 ft）和两段 service centerline；canonical `(x_ft, y_ft)` 数据不变，仅显示层交换轴。
- **MP4 输出契约不变**：四联 1280×620 布局与既有输出尺寸测试保持不变。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `multiview-visual-acceptance`: Debug trace evidence 增加可选 candidate 层语义（formal `detections` 定义不变、旧 trace 兼容、candidate 不得进入正式产物）；debug MP4 renderer 增加 court panel 等比绘制与候选框/正式框双层可视化需求。
- `multiview-joint-observability`: Debug replay 帧显示语义扩展——display-only 帧（`available_extrapolated` / `fallback_valid_start`）须明确标注未执行 tracking，不得呈现为漏检或伪造检测框。

## Impact

- **后端代码**：
  - `backend/app/vision/player_tracking_engine/view_tracking_session.py` — `step()` 中在 lock 过滤前已有全量存活 `tracks`，新增 candidate detections 输出（不过滤或反向过滤），零算法改动。
  - `backend/app/vision/multiview/multiview_joint_run.py` — `_build_debug_tick()` 写入可选 `candidate_detections`（`view_results` 为空的 display-only tick 不写候选，也无从写）。
  - `backend/app/vision/multiview/debug_trace.py` — validator 将 `candidate_detections` 作为可选字段校验（存在时须为 list）。
  - `backend/app/services/joint_debug_renderer.py` — `_court_panel()` 重写为横置等比绘制；`_draw_view_overlays()` 增加 candidate 弱框绘制与 display-only 帧状态横幅。
- **测试**：
  - `backend/tests/test_view_tracking_session.py` — candidate 输出边界（lock 过滤不影响 formal，candidate 仅含未锁定存活 track）。
  - `backend/tests/test_joint_debug_trace.py` — 可选字段兼容（无字段旧 trace 可加载）、formal/candidate 隔离。
  - `backend/tests/test_joint_debug_renderer_extrapolation.py`（或同级 renderer 测试）— display-only 横幅、court 等比、1280×620 尺寸不变。
- **不受影响**：PlayerLock 判定、`eligibility_policy="lock_only"` 配置、association、fusion、sync authority、正式 `frame_detections` / `fused_player_trajectory.v2` / fused overlay、前端 `MultiviewObservabilityPage.tsx`（仅播放 MP4，无需改动）。
- **明确不做（Out of scope）**：不把 `lock_only` 改回 `legacy_union`；不降低 `bootstrap_min_seconds`；不为 candidate 框反查 PlayerLock slot 精细状态（`player_states` 是 slot 级而非 track 级）；不 bump trace schema 到 v2。
