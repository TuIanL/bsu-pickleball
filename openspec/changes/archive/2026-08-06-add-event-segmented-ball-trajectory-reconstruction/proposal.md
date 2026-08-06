# add-event-segmented-ball-trajectory-reconstruction

## Why

当前球路可视化把"逐帧检测点 → 地面单应投影到球场坐标 → 前端 Catmull-Rom 样条平滑"直接当作展示轨迹,叠加了三个独立问题:

1. 检测点本身有误检、抖动和跳点;
2. 击球、弹地、丢球后的轨迹被错误连接成一条线;
3. 空中球被当作地面点套单应矩阵,投影天然产生位置偏差。

此外,前端对每一段统一生成 `z = 4 × peak × progress × (1-progress)` 的高度弧线,把**所有段端点强制落到地面高度 z=0**——无论该段实际是击球开始、丢失结束还是平面跳变切断,都会人为制造"假弹地"和不合理拱形。后端虽有 `ball_trajectory.json`、`cleaned_ball_trajectory.json`、`bounce_events.json`,但弹跳事件没有参与段结构,击球事件完全不存在,重建环节也没有独立产物。

根因是**分段、拟合、空间重建与高度生成全部发生在错误的位置**:前端渲染端在已被单应投影过的球场点上做样条平滑,样条不尊重事件边界,只会把错误轨迹变得更圆滑。

## What Changes

- **新增后端事件切段重建链**:在现有 `BallTracker`（候选关联/物理门控/跟踪状态机,保持不变）之后,新增"图像空间鲁棒拟合 → 击球候选检测 + 弹跳事件 → 事件仲裁 → 飞行段切分 → 事件锚定的 2.5D 重建 → 质量评估"处理链,输出第三套独立产物。
- **新增击球候选检测与事件仲裁**:纯启发式 `BallContactEventDetector`（突变前/后连续有效观测、速度方向突变、低残差、非长丢失后首次重锁、避开已确认弹地抑制窗口、refractory period）;`BallEventResolver` 仲裁击球与弹地候选的时空冲突,不武断分类。
- **新增飞行段结构**:以 `confirmed_hit`、`confirmed_bounce`、`long_tracking_loss`、高可信 `serve_reset`、`end_of_stream` 为切段边界（优先级依次）。语义上硬切段,几何上击球/弹地共享同一锚点保持视觉连续。
- **新增事件锚定的 2.5D 重建**:图像空间做带置信度权重的 Huber 拟合（必要时 RANSAC 初始化）,拟合点经 homography 生成 pseudo-ground path,再以事件锚点做"单调约束的锚点校正"生成球场坐标;高度模型按段类型设置边界,不再统一两端归零。
- **新增重建产物 `reconstructed_ball_trajectory.json`**:包含 `reconstruction_mode`、`coordinate_semantics`（`metric_validity: visualization_only`）、事件列表、分段（每段含 fit_space、model、anchors、quality、samples）;`source` 区分 `detected / interpolated / model_predicted / anchor`。
- **前端退化为哑渲染器**:球路页不再自行分段、估算高度或生成轨迹模型,改为加载第三套产物,按 `flight_segment` 创建独立 geometry;移除跨事件边界的 Catmull-Rom（最好完全移除,直接以重建采样点构造 line strip）。
- **明确不在本 Change 范围**:重新实现候选关联/物理门控/跟踪状态机、完整相机内外参标定、真实三维速度与真实最高点、RTMPose 手腕辅助击球检测、权威 Rally 状态与 `rally_id` 填充、双摄三角测量。

## Capabilities

### New Capabilities

- `ball-contact-event-detector`: 覆盖启发式击球候选检测、候选事件输出（`hit_candidate / confirmed_hit / rejected_hit`）、与弹跳事件仲裁的 `BallEventResolver`、最小事件间隔与抑制窗口。
- `ball-flight-segmenter`: 覆盖事件驱动的飞行段切分（击球/弹地/长时间丢失/serve 重置/流结束）、`segment_id` 确定性生成、段间共享锚点与语义/几何分离规则。
- `event-anchored-trajectory-reconstruction`: 覆盖图像空间鲁棒拟合、pseudo-ground path、单调约束锚点校正、锚点数量降级策略、按段类型的高度边界模型、重建采样输出。
- `trajectory-quality-evaluator`: 覆盖多维质量评分（观测覆盖率、图像拟合残差、锚点置信度、推算比例、事件置信度、物理合理性）、展示阈值、过网状态软诊断。
- `reconstructed-trajectory-artifact`: 覆盖重建产物 JSON 契约、`source` 分类、`coordinate_semantics` 与 `metric_validity` 语义、存储路径/API slug/前端类型接线。

### Modified Capabilities

- `ball-trajectory-visualization`: 现有球路页自行分段、估高、以单一 Catmull-Rom 绘制整条轨迹的需求,改为从重建产物加载分段数据、按段创建独立 geometry、移除前端高度生成与 Catmull-Rom 跨事件平滑。

## Impact

- **后端 vision 模块**:新增 `ball_contact_event_detector.py`、`ball_event_resolver.py`、`ball_flight_segmenter.py`、`image_space_trajectory_fitter.py`、`event_anchored_trajectory_reconstructor.py`、`trajectory_quality_evaluator.py`;在 `analysis_pipeline.py` 弹跳检测之后接入重建链;复用现有 `BallTracker`、`TrajectoryCleaner`、`BounceDetector`,不修改其跟踪/门控/状态机逻辑。
- **存储与 API**:`StorageService.reconstructed_ball_trajectory_json_path()`;`routes_analysis.py` 的 `Literal` 白名单新增 `reconstructed-ball-trajectory` 及路径映射;`AnalysisArtifacts` 新增字段;mock/unavailable/skipped 产物。
- **前端**:`report.ts` 新增 `ReconstructedBallTrajectoryArtifact`;`analysisClient` 新增 getter;球路页改读第三套产物;`ballTrajectoryVisualization.ts` 不再负责正式分段与估高;`BallTrajectoryScene` 按 `segment.samples` 渲染独立 geometry。
- **测试与夹具**:后端图像拟合/切段/重建/仲裁/质量评分单元测试;重建产物序列化与确定性测试;前端产物解析与分段渲染回归测试。
- **依赖**:本 Change 不引入新第三方运行时依赖;确定性要求 RANSAC 固定随机种子。
