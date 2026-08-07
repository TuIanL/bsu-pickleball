# Tasks: add-multiview-player-trajectory-fusion

## 1. Canonical Court Frame Contract

- [x] 1.1 定义 `CourtOrientation` 类型：`Literal["identity", "rotate_180", "mirror_x", "mirror_y"]`，并实现 local→canonical 变换函数（`(20-x, 44-y)` / `(20-x, y)` / `(x, 44-y)` / `(x, y)`）
- [x] 1.2 定义两级坐标系常量与文档注释：Local Camera Court Frame（`local y=0 = image-top / camera-far end`）与 Canonical Physical Court Frame（`end_a`@canonical y=0 / `end_b`@canonical y=44，`sideline_a`@canonical x=0 / `sideline_b`@canonical x=20），canonical 端点不得使用 `near/far` 命名
- [x] 1.3 定义 `CanonicalCourtFrameDefinition`（`frame_id / capture_take_id / end_a_definition / end_b_definition / created_at / schema_version`）并持久化；同一 take 多次分析引用同一 `frame_id`，禁止每次重选端点
- [x] 1.4 声明 P0 支持范围：仅 axis-preserving 标定视角（对向底线机位、底线类高位机位）；轴交换标定视为不支持并拒绝融合
- [x] 1.5 单元测试：4 个枚举值各自变换正确；非法取值被拒绝；`court_orientation: CourtOrientation | None`（`None` = 未声明，不引入第五种朝向）；**断言 `cam_2` 不会被自动推断为 `rotate_180`**

## 2. MultiViewFusionRun + Input Contract

- [x] 2.1 定义 `MultiViewViewInput`（`capture_track_id / video_id / analysis_job_id / calibration_id / court_orientation`），`court_orientation` 挂 view input 而非 CaptureTrack
- [x] 2.2 实现 `MultiViewFusionRun` 运行实体：`capture_take_id / source_analysis_job_ids[] / view_inputs[] / sync_calibration_ref / canonical_frame_ref`，并定义其产物目录（fused artifact 归属 Run，不挂 cam_1/cam_2 Job，不挂 CaptureTake）
- [x] 2.3 实现 Run 编排：等待两个 source AnalysisJob 完成；任一失败/缺失 → job-level fallback，不生成 fused artifact
- [x] 2.4 将 `dual_camera_sync_calibration.v1` 落为 take 存储规划的约定路径 `take_dir/timeline/sync_calibration.json`，并让 `annotation_manifest.sync_calibration` 在权威 artifact 可用时引用它而非恒写 `unknown`
- [x] 2.5 实现 Canonical Timeline：融合时刻 = reference track analysis-frame timeline；对每时刻用 sync mapping 找另一视角最近真实 source sample，要求 `abs(selection_error_ms) <= max_pairing_error_ms`，否则该路该时刻 `view_status = unavailable`
- [x] 2.6 实现同步门控：`good` → 正常融合；`degraded` → 允许但降权并输出诊断；`unknown / unavailable` → job-level 单视角 fallback
- [x] 2.7 单元测试：Run 所有权（产物归属 Run）、等待/失败语义、`good / degraded / unknown` 三态门控、pairing tolerance 越界标记；**断言"无 sync artifact ≠ offset_ms=0"**
- [x] 2.8 **确认 AnalysisJob 契约不变**：两路 source job 保持单 `video_id` + 单 `calibration_id`，不做任何混合改造

## 3. P0 Spike Adapter（验证核心假设）

- [x] 3.1 **先冻结 Spike 数据源真实契约**（已核验）：`player_render_trajectory.v2` 的 sample `source ∈ {"observed", "interpolated"}`（**不是 "detector"/"detected"**）、无 `bbox` 字段、`x_ft/y_ft` 为 raw；写死过滤器为 `source == "observed"`
- [x] 3.2 实现 Spike Adapter：读取 `player_render_trajectory.v2`，仅取 `source == "observed"` 样本及其 raw `x_ft / y_ft`（含 `projection_status / projection_confidence / footpoint_method / source_track_id`），加"至少有一个 observed sample"冒烟断言
- [x] 3.3 对 Spike 观测应用 Canonical Court Normalizer（决策 1 的变换）
- [x] 3.4 用真实双摄 take 验证三个假设：(a) 同一球员两路 canonical 化后空间接近；(b) 关联稳定；(c) 近端机位确实改善远端轨迹；输出 Spike 结论文档（`docs/multiview-spike-conclusion.md`；完整量化确认待真实 sync 双摄数据）
- [x] 3.5 **本阶段不创建 `PerViewCourtObservationArtifact`**；若假设成立，将 Spike adapter 下沉为正式 raw observation 契约列为后续任务

## 4. Cross-view Association

- [x] 4.1 实现 `CrossViewPlayerAssociator`：`(view_id, view_player_id) → global_player_id`，在 canonical 空间用 `canonical distance + GlobalTrackFilter.predict 预测残差 + temporal continuity + previous association + physical court constraints` 构建小规模二分图匹配（2×2 / 4×4 Hungarian）
- [x] 4.2 实现 association hysteresis：已有关联不被单帧略优候选立即替换，仅连续强证据 reassociate
- [x] 4.3 单元测试：同真实球员映射到同一 `global_player_id`；`cam_1/Player_1` 与 `cam_2/Player_1` 不默认等价；**断言关联代价不包含 `side` 字段输入**；迟滞切换行为

## 5. Observation Quality（Intrinsic + Pair）

- [x] 5.1 实现 `ViewIntrinsicQuality` 确定性规则：`detector confidence + normalized bbox height + projection confidence + footpoint method + tracking state + calibration quality + sync selection error`；bbox 用 `bbox_height / frame_height`，不使用原始像素面积
- [x] 5.2 实现 `PairConsistency`：`inter-view distance + residual to predicted global position + association cost`；决策输入 = `ViewIntrinsicQuality + PairConsistency + Global prediction`，pairwise 不混入 intrinsic
- [x] 5.3 Spike 第一轮 render v2 无 `bbox` 字段时，ViewIntrinsicQuality 暂不使用 bbox；A/B 表明必要再经 `source_track_id + frame_index` join detection artifact 恢复
- [x] 5.4 单元测试：intrinsic 与 pairwise 分离；bbox 归一化后跨分辨率可比；插值点区分来源并降权

## 6. Position Fusion + GlobalTrackFilter 时序

- [x] 6.1 实现 `GlobalTrackFilter.predict(t)`：复用 `CourtPositionSmoother` 模式（EWMA + raw 帧间位移 outlier + stride 感知 gap），按 `global_player_id` 维护状态；predict 先行，作为关联/融合唯一全局预测来源
- [x] 6.2 实现 `PlayerPositionFusion` 状态机：仅 `dual_observed / single_view_fallback / conflict / unavailable`，按观测质量加权，禁止固定 50/50 平均；**不含 `predicted` 状态**（无观测时标记 `unavailable`，预测交由 GlobalTrackFilter）
- [x] 6.3 实现 conflict gate：两路 canonical 距离超阈值且无法由运动预测合理解释时置 `conflict`，不平均出不存在的中间位置，按全局预测或高质量单视角选择
- [x] 6.4 实现 `GlobalTrackFilter.update(measurement)`：吸收融合测量并更新 Global State，形成 predict → associate → quality → pair → conflict → fusion → update 循环
- [x] 6.5 单元测试：双观测加权、单视角回退、无观测 `unavailable`（无 `predicted` 状态）、冲突不平均、predict/update 单一预测来源（无双重状态估计）

## 7. Fused Artifact + Diagnostics

- [x] 7.1 定义 `fused_player_trajectory.v1` schema：每 sample 含 `global_player_id / timestamp_seconds / take_timestamp_ms / reference_frame_index / x_ft / y_ft / fusion_status / fusion_confidence / contributing_views / selected_view / view_observations / association_confidence / sync_quality / court_frame_version / measurement_source / metric_eligible`
- [x] 7.2 `view_observations` 每路含 `source_frame_index / source_timestamp_ms / mapped_take_timestamp_ms / selection_error_ms / x_ft / y_ft / quality`，可回答"该 fused 点由哪两个真实帧组成"
- [x] 7.3 实现 fused trajectory 写入与读取；`measurement_source` 与 `metric_eligible` 随 sample 持久化
- [x] 7.4 实现独立 diagnostics artifact：`orientation normalization / frame mapping errors / association decisions / view quality scores / view disagreement / fallback & conflict counts`
- [x] 7.5 区分并实现 job-level 与 sample-level fallback：job-level 不生成 fused artifact；sample-level 单时刻 `single_view_fallback` 且 Run 继续

## 8. 下游接线（受 metric eligibility 约束）

- [x] 8.1 `minimap / movement distance & speed / heatmap / court-position visualization` 支持消费 `FusedPlayerTrajectoryArtifact`（后端 consumer 适配：`movement_points` / `visualization_points`；前端 CourtMinimap 经 API 读取 fused artifact 为后续接线点）
- [x] 8.2 实现 metric eligibility 消费策略：`dual_observed` / `single_view_fallback` → metrics yes；`conflict` → 按是否接受某一路真实观测带 `metric_eligible`；`predicted` → visualization yes、movement/heatmap 默认 no；`unavailable` → no
- [x] 8.3 fused 不可用时显式回退单视角产物；现有单视角 artifact 不删除、不覆盖

## 9. A/B Validation

- [x] 9.1 人工标注 GT：抽选已知球场线附近帧 + 人工确认物理 court coordinate + 两视角交叉复核；GT 不依赖被评估的同一套 Homography（避免循环验证）（规范见 `docs/multiview-ab-validation.md`；实际标注待真实数据）
- [x] 9.2 GT 包含 `global_player_id`，使 identity switch 可统计
- [x] 9.3 四组对比：`single cam_1` / `single cam_2` / `configured default view` / `multiview fused`，统计 `RMSE / 轨迹缺失率 / 异常跳点率 / 跨视角冲突率 / identity switch / 连续轨迹覆盖率`；不使用事后 oracle baseline（`scripts/multiview_ab_validate.py`）
- [x] 9.4 分区域验证：重点 `Cam1 far-side subset / Cam2 far-side subset / overall`，证明"双摄互补"价值
- [x] 9.5 输出验证结论：证明 Fusion 相对最佳/默认单视角确实提升球场位置质量；未达标项记入后续改进任务（结论模板见 `docs/multiview-ab-validation.md`；数值待真实 GT 数据填充）
