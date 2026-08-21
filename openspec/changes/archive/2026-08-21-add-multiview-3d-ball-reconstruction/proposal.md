## Why

当前球路重建停留在 `event_anchored_2_5d`：`reconstructed_ball_trajectory.v2` 的 `metric_validity = visualization_only`，高度 `estimated_height_ft` 由事件边界与弧线先验生成，而非第二台摄像机的真实观测约束。P1 已建立 `CanonicalAnalysisClock`（每个 canonical tick 为 Cam1/Cam2 解析真实源帧，带 selection_error_ms / sync_quality）与 dual-view joint runtime，但没有一套把"两路球观测共同约束"变成球路拓扑的层。本项目不再追求科研级 metric 3D（无真实内参 K/R/t），改为在已知标准球场几何约束下做"双摄估算三维重建"，让球路能同时解释 Cam1/Cam2 两个真实视频，落点可靠，数据足够时给出估算球速。

## What Changes

- 将球链接入 dual-view joint runtime：每视角每 canonical tick 的 detector 只跑一次，先经基础视觉过滤得到 `BallViewCandidate[]`（bbox/aspect/ROI/明显静态误检），未经本地 `BallTracker` 唯一选择，再同时供给 Stereo Associator 与本地 tracker——避免"各自先挑唯一球再拿两个最终答案做立体"导致误检传播。固定执行序：detect/filter → snapshot 本地 predictor → stereo association → tracker update；P2 V1 中 stereo association **不得反向修改 `BallTracker` 状态**。
- 新增 **Court-constrained Virtual Camera**：不做视觉自标定，直接由现有球场平面 Homography 的正交约束解近似 pinhole 相机（`cx/cy = 中心`、`fx = fy`、`skew = 0`）→ 估 `f / R / t` → 用 court keypoints 最小化回投误差 refine。第一版 `k1 = 0`（径向畸变单独后续 Change）。Cam1/Cam2 的两个 `P_virtual` 必须解析到**同一 CanonicalCourt3DFrame**（链：Canonical Court → canonical_to_local(cam_i) → inverse_homography(cam_i) → image），并做姿态消歧（所有 corners 在相机前方、`z>0`、光轴朝向球场、`R` 近正交）；解算不满足时置 `virtual_camera_status = unavailable` 并降级 `LANDING_ONLY`，禁止强行生成 `P`。
- 新增 **Cross-view Ball Association**：几何用于帮助挑选而非 hard reject；硬门只保留时间接近、三角化位置合理、z 不低出地面、不飞出球场；排序融合回投残差、epipolar residual、本地跟踪连续性、3D 路径连续性、检测置信度。
- 新增 **Approximate Stereo Measurement**：每个 canonical tick 仅在双视角均观测到球时产生一次 `dual_view_estimated` 空间测量，作为"证据"而非最终球路；记录 sync_error_ms、两路回投残差、epipolar residual、geometry_quality。观测时间各自用真实 `source_timestamp_ms`（不做先二维内插），最终段级优化在每个摄像机自己的真实观测时刻做重投影。P2 perception 只能消费 `frame_status == "available"` 的帧，`available_extrapolated` 仅用于 Debug Replay，不得进入 stereo。
- 新增 **Dual-view 3D Segment Reconstruction**（本 Change 核心设计）：逐帧 triangulation 只是 measurement，最终 3D 来自整段 flight-segment 的重投影约束曲线优化——用低维参数化（Cubic B-spline，`(X(t),Y(t),Z(t))`，控制点有上限），同时贴近 Cam1/Cam2 真实球像素（Huber loss）加 2 阶光滑、bounce `z=0`、落点 XY 锚、`z>=0` 与 max-height/max-speed 软约束。段优化消费**配对观测 + Cam1-only + Cam2-only** 全部同段像素证据，使 `PARTIAL_3D` 有意义；V1 不做 `az=-g` 支配曲线。v3 双摄路径不再使用 v2 的人为高度弧线，v1/v2 legacy 行为保持不变。
- 新增 **Landing Point Authority**：bounce 事件权威在第一版固定为 **reference-view confirmed bounce**（复用现有 BounceDetector，不重写），经 canonical clock 定夺 take_timestamp 后，在 Cam2 于 ± tolerance 内找最近 accepted ball evidence；两路均有则双路地面 Homography 加权融合出 `(x,y)`，仅 reference 则单视角落地，均无则 landing unavailable。不从 3D 曲线交点倒推。落点字段语义用 `landing_source = dual_view_ground_fused` + `landing_validity = high`（/ `court_plane_metric_estimate`），避免"精确测量"暗示。
- 指标按可信度分级：落点 XY=高可信正式指标，飞行 XY=中高、飞行 Z=中、最高点/过网高度=衍生估算、平均球速=条件满足时输出、瞬时速度=第一版不输出。
- **BREAKING（仅产物语义，不破坏原路径）**：新增原始 stereo evidence 产物（`multiview_ball_stereo_evidence.v1`，不可变）与正式用户轨迹 `reconstructed_ball_trajectory.v3`；历史/单摄任务保留 v1/v2，新合格双摄任务在同一语义 slug 输出 v3（不回写历史文件）。前端沿用统一 `reconstructed-ball-trajectory` 概念。新的双摄任务不再把"假 2.5D 弧线"当默认 fallback，改为分层降级：`FULL_ESTIMATED_3D / PARTIAL_3D / LANDING_ONLY / UNAVAILABLE`。
- 说明：球短 gap prediction 使用独立阈值 `ball_stereo_prediction_max_gap_ms`（第一版约 200ms，不复用球员 short-gap 的 300-500ms）；`source = predicted` 绝不冒充 detection，也不作为 landing / speed / peak-height 权威。

## Capabilities

### New Capabilities
- `court-constrained-virtual-camera`: 由标准球场平面 Homography 解算近似虚拟相机（pinhole、像素居中等假设、不做真实内参标定、无径向畸变），供跨视角关联与三角测量使用。
- `multiview-ball-stereo-evidence`: 双视角候选证据（detector 每帧一次、候选集合共享）+ 跨视角关联 + 逐 tick 近似三角测量证据产物（`multiview_ball_stereo_evidence.v1`）。
- `dual-view-3d-segment-reconstruction`: 飞行段级双视角重投影约束的整段 3D 曲线优化，生成估算三维球路（z = estimated_multiview_height_ft）。
- `landing-point-authority`: bounce `z=0` 约束下双路地面 Homography 加权融合，产出高可信落点权威。

### Modified Capabilities
- `ball-tracking`: 抽出 `update_from_candidates(...)`，detector 每帧一次、候选集可被多消费者共享，保持单摄行为不变，且 P2 的 stereo 关联不得反向修改 tracker 状态。
- `multiview-analysis-orchestration`: joint 执行在既有 fused player 输出之外，新增球 stereo（evidence + v3 ball artifact）兄弟路径并纳入联合产物链。
- `multiview-analysis-result-composer`: joint 模式正式发布 `multiview_ball_stereo_evidence.v1` 与 `reconstructed_ball_trajectory.v3` 球路产物。
- `analysis-artifacts`: 为球 stereo evidence 提供稳定的 url / path / status 契约。
- `reconstructed-trajectory-artifact`: 在现有 v1/v2 之上新增 v3（`reconstruction_mode = multiview_estimated_3d`），引入指标级 validity 分级与分层可用状态，前端沿用统一 `reconstructed-ball-trajectory` 概念读取。

## Impact

- **Backend 视觉链**：
  - `analysis_clock` / `multiview_joint_run`：供给 stereo layer 双路帧（可复用现有 bundle）；球链仅消费 `frame_status == "available"`。
  - `ball_tracker`：抽出 `update_from_candidates(...)`，detector 候选集合可被多消费者共享（behavior-preserving refactor）；stereo 关联不反向改 tracker 状态。
  - `multiview_analysis_result_composer`：joint 模式发布 stereo evidence 与 v3 ball artifact。
  - `reconstruction_engine` / `reconstruction_schemas`：新增 v3 重建与 segment 级 B-spline 曲线优化。
  - `calibration` / `homography`：复用现有球场 Homography 与 court keypoints；注意 `CalibrationResult.homography` 为 image→court，需以 `inverse_homography`（court→image）+ canonical_to_local 构造 `H_canonical_to_image(cam_i)`。
- **产物/存储**：`multiview_ball_stereo_evidence.json`（新）、`reconstructed_ball_trajectory.v3`（新合格双摄任务同一 slug，不回写历史）；`routes_analysis.py` artifact 白名单可能扩展 evidence slug。
- **前端**：`report.ts` 新增 v3 类型与 validity 分级；球路页读取 v3，历史/单摄任务走 v1/v2 降级。
- **测试（三层）**：
  - Synthetic Geometry：已知虚拟相机 + 已知 3D 轨迹 → 投影 → 重建，验证算法自身；
  - Court-plane Reality Check：真实球场人工放地面球/标记 → 双摄像素 → H1/H2 → 验证 ground landing 一致性；
  - Real Match Benchmark：真实比赛片段 → stereo coverage、回投 P50/P90、落点分歧、3D 段连续性、speed eligibility ratio。区分"数学实现错误 / 虚拟相机误差 / 真实检测与同步误差"。
- **不做**：真实相机内参标定、径向畸变 k1、瞬时球速、metric precision 声明。