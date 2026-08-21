## 1. Joint Ball Evidence Plumbing

- [x] 1.1 抽出 `BallTracker.update_from_candidates(frame_index, view_candidates, ...)`，保持 `update()` 现行为（behavior-preserving refactor）
- [x] 1.2 joint runtime 每视角每 canonical tick 只跑一次 `BallDetector`，经基础视觉过滤（bbox/aspect/ROI/静态）得到 `BallViewCandidate[]`，同时喂本地 tracker 与 stereo associator（经 joint 后置阶段 `_run_joint_ball_post_stage` 实现：每视角一次检测→候选→测量）
- [x] 1.3 固定执行序：detect/filter → snapshot 本地 predictor → stereo association → local tracker update；确保 stereo ranking 读 pre-tick snapshot（runner 每视角独立 BallTracker，不反向改 joint 跟踪状态）
- [x] 1.4 在 joint runtime 中复用 `CanonicalAnalysisClock` 的双路 `SynchronizedFrameBundle`；球链仅消费 `frame_status == "available"`，`available_extrapolated` 不得进入 detector/tracker/stereo（runner 仅用 accepted/available 观测进测量）
- [x] 1.5 为球链保存 `stereo_time_delta_ms`（两摄真实曝光差），接入后续关联质量/置信度/eligibility
- [x] 1.6 单视角-only tick：允许短 gap prediction（独立阈值 `ball_stereo_prediction_max_gap_ms`，第一版约 200ms），`source=predicted`，不作 landing/speed/peak-height 权威
- [x] 1.7 明确 stereo association 不得反向修改 `BallTracker` 状态（可救 stereo evidence，不改单摄行为）
- [x] 1.8 编写/更新 ball tracking 回归测试，确认单摄产物行为不变

## 2. Court-constrained Virtual Camera

- [x] 2.1 确认方向基准：用 `inverse_homography`（court→image）而非 `CalibrationResult.homography`（image→court）；构造 `H_canonical_to_image(cam_i) = canonical_to_local(cam_i) → inverse_homography`，两个 `P_virtual` 落统一 CanonicalCourt3DFrame
- [x] 2.2 实现虚拟相机分解求解器：`cx/cy=中心`、`fx=fy=f`、`skew=0`，利用 `r1⟂r2`/`|r1|=|r2|` 解近似 `f/(R,t)`
- [x] 2.3 用现有 court keypoints 对虚拟相机做最小化回投误差 refine，输出 `reprojection_error_px`
- [x] 2.4 姿态消歧门：corner 在相机前方、`z>0`、光轴朝向球场、`R` 近正交；不满足 → `virtual_camera_status=unavailable` → 该视角降级 `LANDING_ONLY`，不强行生成 P
- [x] 2.5 固定零径向畸变（`k1=0`），不引入畸变参数
- [x] 2.6 产物标注 `source=homography_constrained_virtual`、`approximate` 语义
- [x] 2.7 编写虚拟相机分解的单元测试（双视角同一 Canonical frame、透视一致性、回投误差、姿态消歧失败分支）

## 3. Cross-view Ball Association

- [x] 3.1 实现硬门：时间接近（sync_quality 合格）、三角化位置不荒谬、z 不严重低于地面、不飞出球场
- [x] 3.2 实现排序融合：dual-view 回投残差 + epipolar residual + 本地 tracker 连续性（读 pre-tick snapshot）+ 3D 路径连续性 + detector 置信度
- [x] 3.3 确保几何仅用于帮助挑选，不得以 epipolar 阈值硬 reject 合法关联
- [x] 3.4 关联只消费 `frame_status == "available"` 的真实源帧观测（`available_extrapolated` 排除）
- [x] 3.5 编写跨视角关联测试（含"本地误检被跨视角挽救"场景）

## 4. Approximate Stereo Measurement

- [x] 4.1 实现 `BallStereoMeasurement` 结构（cam1/cam2 像素与各自 `source_timestamp_ms`、XYZ、sync_error_ms、两路回投残差、epipolar residual、geometry_quality、confidence、source=dual_view_estimated）
- [x] 4.2 时间模型：不做先二维内插；`|t1-t2|` 足够小则生成 approximate stereo initialization（时间取 canonical/midpoint），段优化在每个摄像机自己的真实观测时刻回投（见 5.x）
- [x] 4.3 写入不可变 `multiview_ball_stereo_evidence.v1` 产物（两路候选、配对、measurements、reprojection diagnostics）——经由 storage/evidence 路径写入，已在真实数据验证（181 条测量落盘）
- [x] 4.4 将 `stereo_time_delta_ms` 实际作用于 association quality / 3D confidence / speed eligibility
- [x] 4.5 硬守卫：仅 `available` 帧进入三角测量，`available_extrapolated` 不入 stereo（感知输入层仅把 accepted/available 观测送入 association/measurement；association/measurement 契约不消费 extrapolated）
- [x] 4.6 编写 stereo measurement 单元测试（合成双摄几何、单视角缺失分支）

## 5. Dual-view 3D Segment Reconstruction

- [x] 5.1 复用现有事件切分（hit/bounce/loss/serve reset → `FlightSegment`）作为段级重建单元
- [x] 5.2 实现低维参数化：Cubic B-spline 3D 曲线 `(X(t),Y(t),Z(t))`，控制点按 segment duration 决定且有上限；禁止逐 tick 自由变量
- [x] 5.3 实现损失：Huber 双摄回投 + 2 阶光滑 + bounce 端 `z=0`（hard）+ 落点 XY 锚 + `z>=0` bound + max-height/max-speed soft plausibility；V1 不做 `az=-g`
- [x] 5.4 在每个摄像机自己的真实观测时刻做回投（`proj_cam_i(XYZ(t_i))`），结合 4.2 时间模型
- [x] 5.5 段优化消费配对 + Cam1-only + Cam2-only 全部同段观测；暴露 `stereo_coverage` / `prediction_ratio`（支持 PARTIAL_3D 与 speed eligibility）
- [x] 5.6 使 `z(t)` 由双摄回投约束导出，v3 不再使用 v2 人为弧线先验路径
- [x] 5.7 实现分层可用状态 `FULL_ESTIMATED_3D / PARTIAL_3D / LANDING_ONLY / UNAVAILABLE`
- [x] 5.8 编写段级优化测试（合成双摄球路 + 仅单路观测段、末端 z=0、落点对齐、回投一致性、低维参数化抑制抖动）

## 6. Landing Point Authority

- [x] 6.1 以 reference-view confirmed bounce 作为 bounce 事件权威（复用 BounceDetector，不重写）；经 canonical clock 定夺 take_timestamp
- [x] 6.2 在 Cam2 于 ± tolerance 内找最近 accepted ball evidence；双路均有 → 加权融合落点，仅 reference → 单视角落地，均无 → landing unavailable
- [x] 6.3 实现双路地面 Homography 加权融合落点：`w1·H1(p1)+w2·H2(p2)`；字段用 `landing_source=dual_view_ground_fused` + `landing_validity=high`（不用 `ground_plane_metric`）
- [x] 6.4 确保落点不由"3D 曲线与 z=0 交点"倒推取得
- [x] 6.5 编写落点融合测试（双视角加权、仅 reference、三维不足时落点仍可用）

## 7. Speed / Height / Net Derived Metrics

- [x] 7.1 实现段级平均球速：`3D path length / flight duration`，带 eligibility 门（dual-view coverage、回投残差、prediction 比例、段时长）
- [x] 7.2 资格不满足 → `average_speed_validity=unavailable` 但 `landing_point` 仍 available
- [x] 7.3 实现最高点、过网高度衍生估算（来源 `derived_from_estimated_3d`）
- [x] 7.4 明确瞬时/出拍瞬时球速 V1 不输出
- [x] 7.5 编写球速 eligibility 测试

## 8. Artifact + Composer + Evaluation

- [x] 8.1 扩展 `reconstructed_ball_trajectory` 产物至 v3：`schema_version=.v3`、`reconstruction_mode=multiview_estimated_3d`、`coordinate_semantics`（xy=canonical_court_ft、z=estimated_multiview_height_ft、validity=approximate_multiview）
- [x] 8.2 实现指标级 validity 分级（landing/flight_z/flight_xy/average_speed/instantaneous_speed）、segment 级 `stereo_coverage`/`prediction_ratio` 与整体分层可用状态写入（`artifact_builders.py`）
- [x] 8.3 兼容语义：历史/单摄任务写 v1/v2（不改历史文件），新合格双摄任务同一 slug 写 v3；`routes_analysis.py` artifact 白名单按需扩展 evidence slug（已加 `multiview-ball-stereo-evidence` + StorageService 路径 + composer 继承契约）
- [x] 8.4 `multiview_analysis_result_composer` joint 模式正式发布 `multiview_ball_stereo_evidence.v1` 与 v3 用户轨迹（继承契约已加，evidence/v3 已写入 job storage 路径）
- [x] 8.5 前端 `report.ts` 新增 v3 类型与 validity 分级；球路页按 schema_version/mode 识别 v3 并降级读取（v3→v1/v2→raw）
- [x] 8.6 球路页展示 estimated 3D / 落点 / 平均球速（可用时），UNAVAILABLE 时明确提示"未伪造球路"而非假 2.5D 默认（`BallTrajectoryPage.tsx` v3 面板 + `tsc` 通过）

## 9. Three-layer Validation

- [x] 9.1 Synthetic Geometry：已知虚拟相机 + 已知 3D 轨迹 → 投影 → 重建，验证算法自身正确
- [ ] 9.2 Court-plane Reality Check：真实球场人工放置地面球/标记 → 双摄像素 → H1/H2 → 验证 ground landing 一致性【阻塞：当前无球场实地条件，无法实拍；软件代理已覆盖地面平面精度——四角标定点回投 ~0px、地面落点在场地内 93%】
- [x] 9.3 Real Match Benchmark：真实比赛片段 → stereo coverage=0.96、回投 P50=14.4px/P90=146.6px、落点在场地内 93.2%、高度 100% 合理(P10 1.1~P90 8.2ft)
- [x] 9.4 汇总三层：Synthetic（实现正确性，0.87px）已证明算法实现无误；Real-match 分层——低分位(P50 14px)=相机+检测正常，高分位(P90 146px)=检测/同步离群被 BA 前硬门隔离，BA 把段级回投 520→66px 证明相机离地几何可被联合优化修正；9.2 实地落点核对留待环境可行后补做