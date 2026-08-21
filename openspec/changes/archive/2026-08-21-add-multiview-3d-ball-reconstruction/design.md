## Context

- 当前球链仅存在于单摄 `AnalysisPipeline`；`reconstructed_ball_trajectory.v2` 是 `event_anchored_2_5d`，`metric_validity = visualization_only`，高度来自事件边界 + 弧线先验（`ReconstructionMode` 的 `LOCAL_VISUAL_ARC` / `DUAL_ANCHOR_WARP` 等）。
- `BallTracker` 是彻底单摄模型：一次 `detector.detect()` → `BallCandidate[]` → 框尺寸/ROI/静态/运动/物理门过滤 → 本视角内选唯一球（`update()` 内部自调 detector）。
- P1 已就绪：`CanonicalAnalysisClock` 每个 canonical tick 为 Cam1/Cam2 解析真实源帧（`source_frame_index` / `source_timestamp_ms` / `selection_error_ms` / `sync_quality` / 细分 status，如 `no_new_frame`、`available_extrapolated`），且 joint runtime 建在其上。球员侧已有一套 `JointViewRuntime → per-view tracking → pre_association → fusion → reprojection consistency → FSM` 的可复用模式。
- 球场约束充分：`compute_homography` 提供 image↔court 四角单应，`CalibrationResult` 保存 court keypoints；已知球场 20×44 ft、平行/垂直边线、球网 y=22。
- 无真实相机内参，未来也大概率不引入。因此本项目目标是"大致正确的空间球路 + 可靠落点 + 条件性球速"，非 metric 3D。

## Goals / Non-Goals

**Goals:**
- 两视角同一 canonical tick 共享同一份 detection evidence，detector 每帧只跑一次。
- 由球场 Homography 解近似虚拟相机，不做内置标定、不做径向畸变。
- 跨视角关联用几何帮助挑选，不因不完美虚拟相机 hard-reject 真实球。
- 逐 tick triangulation 仅产 `dual_view_estimated` measurement 证据；最终 3D 来自飞行段级双视角重投影约束曲线优化。
- bounce `z=0` 双路地面 Homography 融合成最高可信落点权威。
- 指标按可信度分级输出；产物区分不可变 evidence（v1）与用户轨迹（v3，沿用统一 `reconstructed-ball-trajectory` 概念）。
- 新的双摄任务分层降级，不再默认回退假 2.5D 弧线；v1/v2 保留兼容旧任务/单摄。

**Non-Goals:**
- 真实相机内参标定、非 pixel 假设的物理度量学精度。
- 径向畸变 k1（单独后续 Change）。
- 瞬时/出拍瞬时球速。
- 逐帧 metric truth 声称；`z` 仍为 `estimated_multiview_height_ft`，但来源变为双摄真实约束。

## Decisions

### D1. 球候选接进 joint runtime：候选证据三级模型
将 `BallTracker.update(frame)` 保持现有行为，抽出 `update_from_candidates(frame_index, view_candidates, ...)`。每视角每 tick 的候选形成固定三级流水线：
```
BallDetector
    ↓ raw_candidates
basic candidate filter
    bbox / aspect / ROI / 明显静态误检
    ↓ BallViewCandidate[]
        ├─────────────→ Stereo Associator
        └─────────────→ Local BallTracker selection
```
Stereo 消费的是**经过基础视觉过滤、但未被 tracker 唯一选择**的候选集合。固定执行序（避免读到被本次修改后的状态）：
```
detect/filter → snapshot 本地 predictor → stereo association → local tracker update
```
Stereo ranking 若读取"本地 tracker continuity"，必须读取 **pre-tick snapshot**。P2 V1 明确：**stereo association 不得反向修改 `BallTracker` 状态**——它可挽救 stereo evidence，但不改变现有单摄 tracker 行为，这才使 `update_from_candidates` 真正 behavior-preserving。
- **备选**：直接对两个 `BallTracker` 的最终球做立体——被否，误检会在每视角内部被冻结成唯一球，跨视角无法挽救。
- **备选**：让 stereo 层再独立跑一次 detector——被否，违背每帧一次、浪费且易与 tracker 状态不同步。

### D2. Court-constrained Virtual Camera：Homography 分解，不做视觉自标定、不做 k1
**方向基准确认**：仓库 `CalibrationResult.homography` 定义为 **image→court**，`inverse_homography` 才是 **court→image**。构建因子化 camera 必须用后者，且因 Cam1/Cam2 可能存在不同 local court orientation，真正构造的是：
```
H_canonical_to_image(cam_i):
  Canonical Court
    → canonical_to_local(cam_i)
    → inverse_homography(cam_i)
    → Image
```
**硬不变量**：Cam1/Cam2 的两个 `P_virtual` 必须落统一 **CanonicalCourt3DFrame**（否则一台把 y=0 当近端、另一台当远端，单独回投正确但联合 triangulation 错误）。

由 `H_canonical_to_image(cam_i)` 利用 `H ≈ K [r1 r2 t]` 与 `r1 ⟂ r2`、`|r1|=|r2|`，在固定 `cx/cy=中心`、`fx=fy=f`、`skew=0` 假设下解近似 `f`，得 `(R,t)`，再用 court keypoints 最小化回投误差 refine。**姿态消歧门**：所有 corners 在相机前方、相机 `z>0`、光轴朝向球场、`R` 近正交；不满足 → `virtual_camera_status = unavailable` → 该视角降级 `LANDING_ONLY`，禁止强行生成 `P`。
- **备选**：自行检测球场直线求两个消失点→估焦距→估姿态——被否，绕远且对畸变更敏感；本质利用同一批透视约束，现有 Homography 已含该信息。
- **备选**：真实内参标定——被否，无标定板/机型信息，目标也不需要。
- **明确冻结**：V1 `k1 = 0`。因 focal/pose/k1 相互补偿，会让"数学损失更低但空间模型更不稳"；先看真实双摄回投误差是否为系统桶形/枕形，再开 `refine-virtual-camera-radial-distortion`。

### D3. Cross-view Association：几何用于排名，硬门只卡物理合理性
同 tick 双路候选先验对齐。硬门仅：时间足够接近（`sync_quality` / `selection_error_ms` 门）、triangulation 不荒谬、`z` 不严重低于地面、位置不严重飞出球场环境。排序融合：dual-view 回投残差、epipolar residual、本地 tracker 连续性（读 pre-tick snapshot，见 D1）、上一 3D 路径连续性、检测置信度。关联只消费 `frame_status == "available"` 的真实源帧观测。
- **备选**：`epipolar residual > 3px → hard reject`——被否（项目核心设计）。近似相机下卡太死会过早杀死真实球；P1 曾因把 prediction/排序代价混入 feasibility hard gate 而误过滤合法 association，P2 从一开始就分离两者。

### D4. 逐 tick Approximate Stereo Measurement（证据，非最终球路）
仅在 two-view-observed tick 三角化，输出：
```
BallStereoMeasurement {
  take_timestamp_ms; cam1_timestamp_ms; cam2_timestamp_ms;
  cam1_image_xy; cam2_image_xy;
  estimated_x_ft; estimated_y_ft; estimated_z_ft;
  sync_error_ms;
  reprojection_error_cam1_px; reprojection_error_cam2_px; epipolar_residual_px;
  geometry_quality; confidence; source="dual_view_estimated";
}
```
逐帧 triangulate 的 `z` 抖动大，因此它只是 evidence，进入 segment 优化而非直接当作终点。
- 球运动比球员快：`stereo_time_delta_ms`（两摄真实曝光差）必须影响 association quality / 3D confidence / speed eligibility，不能只作 diagnostics。**时间处理不做先二维内插**——保留每个真实 observation 的 `source_timestamp_ms`；`|t1-t2|` 足够小则生成 approximate stereo initialization（时间取 canonical/midpoint），最终段优化在每个摄像机自己的真实观测时刻做回投（见 D5）。`stereo_time_delta_ms` 作为 confidence / speed-eligibility 因子。
- **硬规则**：P2 perception 只消费 `frame_status == "available"` 的帧；`available_extrapolated` 明确只是 Debug Replay 显示帧，不进入检测/跟踪/stereo。

### D5.（核心）Dual-view 3D Segment Reconstruction：整段重投影约束优化
复用现有事件切分（`hit / bounce / loss / serve reset → FlightSegment`）。对每个飞行段解一条 **低维参数化** 的 3D 曲线，禁止用"每 tick 三个自由变量"等高维参数化（否则虚拟相机误差被曲线吸收成"回投好但空间乱抖"）。
```
Cubic B-spline 3D trajectory
    t ∈ [0,1]
    (X(t), Y(t), Z(t)) 由少量 control points 决定
    控制点数按 segment duration 决定，但必须有上限
```
损失项（V1）：
```
min  Σ_i Huber( proj_cam1(XYZ(t1)) − obs_cam1(t1) )
   + Σ_j Huber( proj_cam2(XYZ(t2)) − obs_cam2(t2) )
   + λ1 2nd-derivative smoothness
   + λ2 bounce hard anchor (端 z=0)
   + λ3 landing XY hard/strong anchor (对齐落点权威)
   + z >= 0 bound
   + max-height / max-speed soft plausibility
```
**"weak physics" 第一版不做 `az = -g`**，避免用理想抛物线支配视觉证据（回到旧 2.5D 老路）。**段优化输入不限于配对 stereo measurements**：只要时间与身份属于同一 flight segment，`Cam1+Cam2 配对观测 + Cam1-only + Cam2-only` 都能作为 `proj_cam_i(XYZ(t_i)) ≈ observation_i` 的约束，这样 `PARTIAL_3D` 才真正有意义（否则双摄重叠率低时会扔掉大量单路真实像素证据）。每个摄像机只在**自己的真实观测时刻**做回投（对应 D4 的时间模型）。
- **备选**：单帧 triangulation + Kalman/平滑——被否，虚拟相机系统误差未在段级消化，收敛差且易抖。
- **备选**：仅在既有 2.5D 上微调——被否，高度仍非双摄证据约束。
- 描述口径：v3 双摄路径不再使用 v2 的人为高度弧线；v1/v2 legacy 行为保持不变（不是修改历史 v2）。

### D6. Landing Point Authority：reference-view bounce 权威 + z=0 双路 ground-plane fusion
**bounce 事件权威**（P2 V1 不重写 BounceDetector）：以 **reference-view confirmed bounce** 作为 canonical bounce event authority → 经 canonical clock 定夺 `take_timestamp` → 在 Cam2 于 ± tolerance 内找最近 accepted ball evidence。
```
Cam1 + Cam2 均有 → dual ground-plane fusion (按 geometry_quality 加权)
仅 reference      → single-view ground landing
均无               → landing unavailable
```
不从 3D 曲线与 `z=0` 交点倒推。字段命名避免"精确测量"暗示：`landing_source = dual_view_ground_fused`（或 `single_view_ground`）+ `landing_validity = high`（文档可注解 `court_plane_metric_estimate`），不再用 `ground_plane_metric` 作字段名。
- 产品不变量：**落点是最高可信正式指标，即使 3D 不足也不影响落点**。
- 后续（数据成熟后）再以 `3D z≈0 + vz sign change` 升级 bounce event authority，不在本 Change 范围内。

### D7. 分级可信度与分层降级
```
Landing XY         landing_source=dual_view_ground_fused  HIGH
Flight XY          dual_view_estimated     MEDIUM-HIGH
Flight Z           dual_view_estimated     MEDIUM
Peak Height        derived_from_estimated_3d MEDIUM/LOW
Average Speed      derived_from_estimated_3d conditional
Instantaneous Speed  V1 不输出
```
可用状态机：`FULL_ESTIMATED_3D / PARTIAL_3D / LANDING_ONLY / UNAVAILABLE`，非 PASS/FAIL。

### D8. Speed：仅段级平均估算，带 eligibility 门
`3D segment path length / flight duration`。eligibility：dual_view coverage 足够、回投残差足够低、prediction ratio 不过高、segment duration 足够。不满足 → `speed=unavailable` 但 `landing=available`。输出形如"约 42 km/h"，不输出高精度假读数。

### D9. Artifact 形态：不可变 evidence（v1）+ 用户轨迹升级（v3）
- 新增 `multiview_ball_stereo_evidence.v1`：不可变原始证据（两路 candidates、pairing、stereo measurements、reprojection diagnostics）。`multiview_analysis_result_composer` 在 joint 模式正式发布该 evidence 与 v3 用户轨迹。
- 用户轨迹沿用统一产品概念 `reconstructed_ball_trajectory` 升到 `.v3`：
```
reconstruction_mode = multiview_estimated_3d
coordinate_semantics:
  xy = canonical_court_ft
  z = estimated_multiview_height_ft
validity: approximate_multiview
```
- **兼容语义（锁死）**：`reconstructed_ball_trajectory.json` 是单一语义 slug，无法同时是 v2 与 v3。明确——历史/单摄任务 → v1/v2 不变；新合格双摄任务 → v3（同一 slug），**不回写历史 v1/v2 文件**。不新增 `legacy_2_5d_baseline` 旁路（产品已不再默认回退假 2.5D）；旧 2.5D 基准如需并存以留给后续比较，另行评估，不在本 Change 默认。
- v1/v2 保留（兼容旧任务/单摄），前端按统一 slug 读取、按版本降级。避免前端维护两条平行"正式球路 artifact"。

### D10. Timing gate 更严格（球速快 + available_extrapolated 排除）
复用 `CanonicalAnalysisClock`，但球侧加 `stereo_time_delta_ms` 影响 association quality / 3D confidence / speed eligibility（而非仅 diagnostics）。单路-only tick 允许短 gap prediction，但**不复用球员 short-gap 语义**：专设 `ball_stereo_prediction_max_gap_ms`，第一版约 **200ms**（球员 500ms 对 40 km/h 球 ≈ 5.5m 位移，不适用），后续实验调参。`source=predicted` 不作为 landing/speed/peak-height 权威。**硬守卫**：P2 perception 只消费 `frame_status == "available"`，`available_extrapolated` 不进入 detector/tracker/stereo。

## Risks / Trade-offs

- **[Risk] 虚拟相机深度方向系统性误差**（f 假设不准）→ 段级重投影优化可消化小系统误差；若误差过大，输出降级为 `PARTIAL_3D / LANDING_ONLY`，落点权威不受影响。
- **[Risk] 两视角曝光时间差引入视差伪影** → `stereo_time_delta_ms` 进入质量与 eligibility；段优化在每个摄像机自己的真实观测时刻回投，不做先内插（D4/D5）。
- **[Risk] 高速球/遮挡导致某 tick 仅单路观测** → 分层降级 + 短 gap prediction（predicted，不作权威），绝不伪造 detection。
- **[Risk] detector 每帧一次 refactor 影响单摄行为** → 采用 behavior-preserving `update_from_candidates`，并跑既有 ball tracking 回归测试。
- **[Risk] epipolar hard-gate 误杀真实球** → 明确几何只用于排名（D3），hard gate 仅卡物理合理性，与 P1 教训一致。
- **[Trade-off] `z`/速度是估算口径而非 metric** → 文档与产物语义显式声明 `approximate_multiview` / conditional，避免误导。

## Migration Plan

- 后端按 D1→D9 顺序逐个落地；每次保持现有单摄/2.5D 产物不变（写新 evidence artifact 与 v3，不覆盖 v1/v2）。
- 前端球路页支持按 schema_version 降级读取（v3 → v1/v2 → raw）。
- 双摄任务接入 v3；旧任务/单摄任务继续走 2.5D 路径，无回滚破坏。
- 若 segment 优化结果回投误差异常高，安全门降至 `LANDING_ONLY`，落点仍可用。

## Open Questions

- 经真实双摄回投误差观测后，是否/何时开 `refine-virtual-camera-radial-distortion` 后续 Change（P2 V1 明确不做，保持未决）。
- （已定）v3 在 segment 级暴露 `stereo_coverage` / `prediction_ratio`：**采纳**，供前端渲染与 speed eligibility 展示，已纳入 `dual-view-3d-segment-reconstruction` 与 v3 spec。