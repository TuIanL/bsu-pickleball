# pose-estimation-engine Specification

## Purpose

定义姿态估计引擎：RTMPose 模型配置、逐帧姿态推理与结果序列化，以及骨架叠加层的语义。

约定模型输入、帧级姿态结果和骨架可视化的衔接，保证模型配置与序列化产物能够供后续分析和页面显示使用。

## Requirements
### Requirement: RTMPose model configuration
后端 SHALL 为真实上传视频任务提供可加载已配置 RTMPose runtime、model config、checkpoint 或导出模型的姿态引擎；启用姿态且资源可用时 SHALL 为符合条件的真实任务运行。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

#### Scenario: RTMPose assets are configured
- **WHEN** 姿态已启用且配置的 RTMPose runtime、model config、checkpoint 或导出模型可用
- **THEN** 后端 SHALL 懒初始化姿态引擎供 Pipeline 使用，并保留 demo 任务行为

#### Scenario: RTMPose assets are missing
- **WHEN** 姿态已启用但无法找到或加载已配置的 RTMPose 资源
- **THEN** 姿态阶段 SHALL 明确报告 skipped 或 failed，不宣称骨架叠加可用

#### Scenario: Pose modules are imported in lightweight mode
- **WHEN** 禁用姿态时导入后端模块
- **THEN** 导入 SHALL 成功，且不要求模型文件、GPU 或重型姿态 runtime 初始化

#### Scenario: Pose inference is intentionally disabled
- **WHEN** 真实视频任务完成且配置禁用了姿态
- **THEN** 后端 SHALL 报告 RTMPose 已禁用，不将缺少骨架解释成检测或过滤失败

### Requirement: Frame-level pose estimation
后端 SHALL 对已处理帧中与球场相关的跟踪球员框运行 RTMPose，并输出规范化帧级姿态。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

#### Scenario: Tracked player boxes are available
- **WHEN** 已处理帧含一个或多个经过球场相关性过滤仍符合条件的跟踪人框
- **THEN** 姿态引擎 SHALL 为各合格跟踪主体估计关键点，并关联 frame_index、timestamp_seconds 和 track_id

#### Scenario: Tracked person is outside match bounds
- **WHEN** 已处理帧中某跟踪主体的投影脚点超出已配置比赛相关边界
- **THEN** 姿态引擎 SHALL 不为该主体推理或持久化可渲染姿态

#### Scenario: No player boxes are available
- **WHEN** 已处理帧没有可用且与球场相关的人框
- **THEN** 姿态引擎 SHALL 跳过该帧，不伪造骨架关键点

#### Scenario: Low-confidence keypoints are returned
- **WHEN** RTMPose 返回接近配置阈值的关键点置信度
- **THEN** 关键点可见性 SHALL 使用 hysteresis：置信度 >= enter_threshold（默认 0.30）时由不可见转为可见；低于 exit_threshold（默认 0.20）时才由可见转为不可见
- **AND** 已可见点 SHALL 在置信度短暂落于 exit_threshold 与 enter_threshold 之间时保持可见，以减少闪烁
- **AND** 低于 exit_threshold 的点 SHALL 立即不可见，不依赖之前状态
- **AND** enter_threshold 与 exit_threshold SHALL 可通过环境变量独立配置

#### Scenario: Distant players produce stable skeletons
- **WHEN** 远处球员框的 PersonDetector 置信度低至 0.15
- **THEN** 检测 SHALL 传给姿态引擎，保留既有 PersonDetector.conf_threshold 从 0.25 调至 0.15 的约定
- **AND** 姿态引擎 SHALL 对该球员关键点使用 hysteresis，减少远距离低置信度导致的骨架闪烁
- **AND** 低置信度检测 SHALL 仍遵循下游球场相关性与 ROI 过滤

#### Scenario: 模块姿态按观测人框推理
- **WHEN** modular_v1 请求 pose.sequence 且已绑定有效人框/RGB
- **THEN** 姿态 SHALL 可在没有球场标定或 tracking 的情况下执行
- **AND** SHALL 使用 observation-scoped 主体，关闭或隔离依赖稳定 track_id 的历史状态
- **AND** SHALL 不制造跨帧稳定球员身份

### Requirement: Pose result serialization
后端 SHALL 将姿态持久化为可在源视频上渲染骨架的 JSON；可渲染主体 SHALL 与检测叠加使用的球场相关主体集合一致。

本条既有行为与场景 SHALL 适用于 analysisEngine=legacy_v1（含未声明 engine 的历史任务）。modular_v1 SHALL 遵循独立的冻结计划与运行清单合同。

#### Scenario: Pose results are persisted
- **WHEN** 真实分析任务的姿态估计完成
- **THEN** 后端 SHALL 写出姿态产物，包含 job/video 标识、源帧尺寸、处理帧元数据、规范化关键点、主体标识、关键点 schema 和球场相关主体的骨架连接元数据

#### Scenario: Frontend requests pose overlay data
- **WHEN** 已完成任务具有持久化姿态产物
- **THEN** 产物 SHALL 可通过原始 Pipeline 结果引用的后端 API 或 URL 读取

#### Scenario: Pose artifact is unavailable
- **WHEN** 姿态被跳过、失败或未产生结果
- **THEN** 系统 SHALL 显式表达 unavailable，不返回看似成功的空对象

#### Scenario: 模块姿态不可变序列化
- **WHEN** modular_v1 姿态推理完成
- **THEN** 系统 SHALL 发布带 schema、帧时间、坐标单位、主体作用域和来源引用的不可变产物
- **AND** Job SHALL 通过 ArtifactRef 使用它，无候选 SHALL 使用有效空集合与 no_candidates 质量
- **AND** SHALL 不把 job_id 作为内容身份或覆盖共享产物的生产者字段

### Requirement: Skeleton overlay semantics
The backend SHALL describe enough pose metadata for clients to render human skeletons consistently.

#### Scenario: Skeleton metadata is returned
- **WHEN** a pose artifact is returned to the frontend
- **THEN** it includes a stable keypoint schema name and the ordered skeleton edges needed to connect joints

#### Scenario: Unsupported keypoint schema is configured
- **WHEN** the configured pose model emits a keypoint schema the application does not recognize
- **THEN** the backend reports the pose stage as failed or skipped with a clear unsupported-schema detail

### Requirement: 模块姿态只在所需节点执行
modular_v1 SHALL 仅在计划中需要且缓存未满足 pose.sequence 时初始化所选姿态实现。模型缺失 SHALL 返回 model_environment 执行诊断，不套用 legacy 的可选 overlay 跳过逻辑。

#### Scenario: 球检测不触发姿态
- **WHEN** 模块请求仅为 ball.detect
- **THEN** 系统 SHALL 不初始化 RTMPose
- **AND** SHALL 不因全局姿态配置开启而追加姿态节点
