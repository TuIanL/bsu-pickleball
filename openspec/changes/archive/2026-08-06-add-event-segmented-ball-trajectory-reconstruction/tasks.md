# add-event-segmented-ball-trajectory-reconstruction — Tasks

## 1. 后端测量模型：图像空间鲁棒拟合

- [x] 1.1 新增 `backend/app/vision/pickleball_game_analysis/image_space_trajectory_fitter.py`：对单个飞行段做带检测置信度权重的 Huber 回归拟合 `u(t)`、`v(t)`；存在严重离群点时先 RANSAC 初始化，RANSAC 固定随机种子。
- [x] 1.2 拟合器输出：拟合曲线、异常观测标记、图像拟合残差（像素 RMSE）、观测覆盖率；损失基于图像坐标，不使用已失真的 `court_xy`。
- [x] 1.3 有效观测点低于配置下限时，不输出正式拟合曲线，段保留为原始检测模式。

## 2. 击球候选检测与事件仲裁

- [x] 2.1 新增 `ball_contact_event_detector.py`：纯启发式击球候选（突变前/后连续有效观测、速度方向变化或幅值突变达到阈值、前后拟合残差校验、非长缺失后首次重锁、弹地抑制窗口、refractory period），输出 `hit_candidate / confirmed_hit / rejected_hit` 及结构化拒绝原因。
- [x] 2.2 新增 `ball_event_resolver.py`：仲裁同一时间窗口内击球候选与弹地候选（高可信 bounce 抑制 hit、近球员且 bounce 弱则接受 hit、证据均不充分输出 `event_type = ambiguous`）；`player_motion_pixels` 仅作弱证据。
- [x] 2.3 击球事件携带 `event_source = heuristic`，为 `pose_assisted / manual_corrected` 预留扩展位；复用现有 `BounceDetector` 弹跳事件作为仲裁输入，不修改其检测逻辑。
- [x] 2.4 确定性命中检测：相同输入重复运行，候选、仲裁结果与事件 ID 序列完全一致。

## 3. 飞行段切分

- [x] 3.1 新增 `ball_flight_segmenter.py`：按优先级 `confirmed_hit → confirmed_bounce → long_tracking_loss → high_confidence_serve_reset → end_of_stream` 切分，每个边界生成新的 `segment_id`。
- [x] 3.2 段间共享锚点：弹地/击球前后两段的 `end_anchor_id == start_anchor_id`，两段独立拟合与渲染；明确"语义断开必须、几何断裂不需要"。
- [x] 3.3 长时间丢失与无法解释的数据空洞处视觉上真正断开；短缺失以 `model_predicted` 虚线连接；serve 事件作为可选 `boundary_reason = "serve_reset"` 重置锚点，不构建权威 `rally_id`。
- [x] 3.4 每段输出 `start_event_id / end_event_id / start_event_type / end_event_type / boundary_reason`；缺少权威 `rally_id` 时置 `null`。

## 4. 事件锚定 2.5D 重建

- [x] 4.1 新增 `event_anchored_trajectory_reconstructor.py`：将图像拟合曲线经 homography 生成 `pseudo_court(t)`（中间量，不直接作为最终球场坐标）。
- [x] 4.2 单调约束锚点校正：以锚点建立主轴，`longitudinal_progress` 满足 `s(t0)=0、s(t1)=1、ds/dt>=0`（isotonic regression 或 monotonic cubic fitting），横向残差鲁棒平滑、限制幅度与横向加速度、端点归零；输出 `court_xy(t) = A0 + s(t)*(A1-A0) + bounded_lateral_residual(t)`。
- [x] 4.3 空间锚点分级：bounce 硬锚点（z=0，单应可信）、contact 软锚点（保存空间不确定度）、raw endpoint 弱约束、loss boundary 非锚点。
- [x] 4.4 锚点数量降级：双锚点 `dual_anchor_warp`、单锚点 `single_anchor_warp`（质量上限受限、未知端渐隐）、无锚点 `image_only`（不出现在默认球场视图）、锚点距离过小 `local_visual_arc` 或不输出。
- [x] 4.5 事件边界感知的高度模型：按段类型设置 `hit→bounce`、`bounce→hit`、`hit→hit`、`bounce→loss`、`unknown→unknown` 的高度边界，不把段端统一置零。
- [x] 4.6 可配置接触高度先验（`default_contact_height_m=1.10`、裁剪 `0.45–2.40m`、`uncertainty_m=0.60`），来源 `global_contact_prior` / `serve_prior`，低置信度，不按球场区域自动修改。

## 5. 轨迹质量评估

- [x] 5.1 新增 `trajectory_quality_evaluator.py`：多维质量评分（观测覆盖率、图像拟合残差 RMSE、锚点置信度、推算比例、事件置信度、物理合理性），汇总 `overall`。
- [x] 5.2 高度可信度独立评估（因全局低可信先验而受限）；`single_anchor_warp` 段质量上限受限。
- [x] 5.3 过网软诊断：`net_crossing_status`（not_expected / expected / estimated / implausible / unknown）进入 `physical_plausibility_score` 与 diagnostics，不过网硬门控，不输出真实过网高度/擦网结论。
- [x] 5.4 展示阈值（`≥0.80 实线 / 0.60–0.80 部分虚线 / 0.40–0.60 仅调试 / <0.40 不生成`）与确定性评分。

## 6. 重建产物与后端接线

- [x] 6.1 新增 `reconstructed_ball_trajectory.json` 序列化：`schema_version`、`reconstruction_mode = event_anchored_2_5d`、`coordinate_semantics`（`metric_validity = visualization_only`）、`events`、`segments`（含 `fit_space`、`model = weighted_huber_anchor_constrained`、`anchors`、`quality`、`samples`）。
- [x] 6.2 重建样本携带 `source`（detected / interpolated / model_predicted / anchor）、`estimated_height_ft`、`height_source`、`height_confidence`、可选 `height_uncertainty_ft`、`gap_length_frames`、`reprojection_error_px`；弹地边界高度严格为 0、击球边界非 0。
- [x] 6.3 新增 `StorageService.reconstructed_ball_trajectory_json_path()`（`reconstructed_ball_trajectory.json`）。
- [x] 6.4 `routes_analysis.py` artifact `Literal` 白名单新增 `reconstructed-ball-trajectory` 及路径映射；`AnalysisArtifacts` 新增字段。
- [x] 6.5 `analysis_pipeline.py` 在弹跳检测之后接入重建链并写入产物；mock/unavailable/skipped 状态与现有 artifact 状态机一致；保留 raw/cleaned 两套数据不覆盖。
- [x] 6.6 配置入口：`ball_reconstruction` 接触高度先验参数接入现有配置体系。

## 7. 前端哑渲染器改造

- [x] 7.1 `src/types/report.ts` 新增 `ReconstructedBallTrajectoryArtifact`（events / segments / samples / source / quality / coordinate_semantics）。
- [x] 7.2 `src/services/analysisClient.ts` 新增重建产物 getter。
- [x] 7.3 `src/pages/BallTrajectoryPage.tsx` 改读重建产物；无重建产物时降级到原始轨迹模式或明确"重建不可用"，不静默失败。
- [x] 7.4 `src/services/ballTrajectoryVisualization.ts` 移除前端正式分段、方向生成、平均置信度与高度生成（不再以统一 `4×peak×p×(1-p)` 强制段端置零）。
- [x] 7.5 `src/components/platform/BallTrajectoryScene.tsx` 按 `segment.samples` 构造独立 line strip geometry；移除跨击球/弹地事件边界的 Catmull-Rom 单一样条；弹地橙色圆环、击球菱形、推算点虚线、丢失边界断开。

## 8. 测试与回归

- [x] 8.1 后端单元测试：图像拟合、击球候选、事件仲裁、飞行段切分、2.5D 重建（含锚点降级与高度边界）、质量评估、产物序列化。
- [x] 8.2 确定性测试：相同输入重复运行，事件 ID、`segment_id` 与重建样本序列完全一致。
- [x] 8.3 验收不变量测试：弹地/击球/长缺失一定产生新 `segment_id`；弹地前后共享锚点且分别拟合；`model_predicted` 与 `detected` 在 artifact 上可区分；无锚点段不伪装高可信球场空间。
- [x] 8.4 前端测试：重建产物解析、按段渲染、事件锚点视觉语义、重建产物不可用降级。
- [x] 8.5 回归：现有 player / pose / tracking / serve / court-view 行为不变；已归档任务旧产物（raw/cleaned/bounce）展示不受影响。
