## 1. Candidate detections 生产链（tracking session → joint run → trace）

- [x] 1.1 `view_tracking_session.py`：`ViewFrameResult` 新增 `candidate_detections` 字段；`step()` 中先显式计算集合差 `candidate_track_ids = live_track_ids - eligible_track_ids`，再仅对该集合生成候选列表（复用 `_tracks_to_frame_detections()` 构造语义）；formal 路径与 `eligible_track_ids` 语义保持不变
- [x] 1.2 `multiview_joint_run.py`：`_build_debug_tick()` 将 `result.candidate_detections` 写入 view 的可选 `candidate_detections`（dict 行含 bbox/track_id/confidence，不含 player_id；`view_results` 缺失的 display-only tick 不写）
- [x] 1.3 `debug_trace.py`：validator 将 view 级 `candidate_detections` 作为可选字段做 **list 级校验**——缺失时通过、存在但非 list 时失败；SHALL NOT 加强 formal `detections` 的历史逐元素校验（保证历史 trace 全量兼容）；schema 版本保持 `joint_debug_trace.v1`
- [x] 1.4 测试 `test_view_tracking_session.py`：构造"track A 已锁定 / track B 存活未锁定"，断言 formal `frame_detections` 仅含 A、`candidate_detections` 仅含 B、B 不带 player_id，且 `formal_track_ids ∩ candidate_track_ids == ∅`（同 tick 硬不变量）
- [x] 1.5 测试 `test_joint_debug_trace.py`：旧 trace（无字段）加载通过；带字段 trace 校验通过；字段存在但非 list 时校验失败

## 2. Renderer 双层框与 display-only 标注

- [x] 2.1 `joint_debug_renderer.py`：`_draw_view_overlays()` 绘制 `view.get("candidate_detections", [])`——细线（thickness 1）弱色框，标签统一 `track_<id> · tracker candidate`，不显示 Player_N；formal 框样式与标注保持现状
- [x] 2.2 `joint_debug_renderer.py`：view 状态为 `available_extrapolated` / `fallback_valid_start` 时，在画面固定位置叠加 `DISPLAY ONLY · TRACKING NOT STEPPED` 标识，并**主动跳过全部 overlay 绘制**（formal/candidate bbox、footpoint、guidance ROI）——不依赖生产端恰好为空，即使 trace 中这些 tick 带有 detections 数据也不画
- [x] 2.3 测试：构造 formal 空 / candidate 非空的 bootstrap tick trace，渲染断言出现候选框且无 Player_N 标注；构造同一 track 后续 tick 进入 formal 的 trace，断言候选框被正式框取代、同 tick 内不同时出现
- [x] 2.4 测试：构造 `available_extrapolated` tick trace，渲染断言横幅存在、无任何 bbox 绘制、后续 `available` tick 横幅消失；**对抗样本**——构造 `available_extrapolated` 但 trace 带有非空 detections 的异常数据，断言 renderer 仍不画任何框（active skip 生效）（扩展 `test_joint_debug_renderer_extrapolation.py`）

## 3. Court panel 等比重绘

- [x] 3.1 `joint_debug_renderer.py`：重写 `_court_panel()`——几何提取为纯函数 `_court_layout()`（返回 origin_x/origin_y/scale/court_width_px/court_height_px）与 `_court_to_panel(x_ft, y_ft, layout)`；横置（44 ft 横轴 / 20 ft 纵轴），`scale = min(可用宽/44, 可用高/20)` 单一比例；绘制外边界、网（y_ft=22）、两条 NVZ line（y_ft=15/29）、两段 service centerline（x_ft=10, y_ft∈[0,15]∪[29,44]）
- [x] 3.2 球员点映射改为显示层轴交换（screen_x ← y_ft、screen_y ← x_ft），保留既有 canonical 坐标 `[0,20] × [0,44]` clamp（越界点显示行为不变）；canonical `(x_ft, y_ft)` 与 trajectory 数据不动；`global_player_id` 文本标注沿用
- [x] 3.3 测试：直接对纯函数断言——`_court_layout()` 的 scale 横纵一致（同一 px/ft）、`court_width_px/court_height_px ≈ 44/20`、网/NVZ/centerline 映射坐标正确、`_court_to_panel` clamp 行为保留；MP4 级测试仅守 `1280×620` 输出尺寸（既有尺寸测试保留通过）
- [x] 4.1 运行受影响测试面全量：`test_view_tracking_session.py`、`test_joint_debug_trace.py`、`test_joint_debug_renderer_extrapolation.py` 及既有 renderer 尺寸/布局测试；更新因 court 坐标变化而失效的旧像素断言
- [x] 4.2 用真实双摄素材跑一次 `debug_trace_enabled=true` 的 joint run + replay 渲染，人工核对验收分界：display-only tick 有横幅无框 → available bootstrap tick 有 candidate 弱框 → 锁定后被 Player_N 正式框取代；court panel 无拉伸且球场线齐全（真实 take 1920×1080@60，120 tick：extrapolated 0-44 / candidate 45-119 / formal 60-119，含对抗样本与 court 线像素核对；产物 `backend/data/tmp/dbg_replay_e2e_out/debug.mp4` 供肉眼复核）
- [x] 4.3 确认正式产物零变化：同输入下 `frame_detections`/`fused_player_trajectory.v2`/fused overlay 与改动前一致（`eligibility_policy` 仍为 `lock_only`）（注：工作区含其它 change 的未提交修改，git A/B 不纯；采用 differential test 等价证明 + 单元 formal-only-eligible 断言 + E2E 120 tick per-track 互斥三层证据收口）
