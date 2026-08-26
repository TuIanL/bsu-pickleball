# multiview-ball-analysis-display Specification

## Purpose
TBD - created by archiving change integrate-multiview-ball-analysis-display. Update Purpose after archive.
## Requirements
### Requirement: 双摄球路分析使用统一时间轴与共享观测
joint 模式的球路分析 SHALL 从 `CanonicalAnalysisClock` 产生的 `SynchronizedFrameBundle` 读取双摄帧，并在同一 canonical tick 上完成候选生成、跨视角关联、三角测量与轨迹更新。生产链路 MUST 复用每个视角每个 tick 的候选结果，MUST NOT 为 stereo 分析再次独立运行 detector。跨视角关联 SHALL 经过时间、重投影、3D 球场范围、运动连续性和歧义 margin 质量门；未通过质量门的 pair 只能作为诊断，不能成为权威双摄观测。

#### Scenario: 两路帧在同一 canonical tick 可用
- **WHEN** 两路视频在 tick `t_k` 均有可用帧
- **THEN** 球候选 SHALL 由这两帧各检测一次后供 association、tracker 和 stereo 共同消费
- **AND** evidence 中 SHALL 记录 `tick_id`、两路真实帧索引与各自时间戳
- **AND** 只有通过跨视角质量门且达到歧义 margin 的 pair 才能生成权威双摄三角测量

#### Scenario: 一路帧不可用
- **WHEN** tick `t_k` 只有一个视角有可用帧
- **THEN** 该 tick SHALL NOT 生成权威双摄三角测量
- **AND** 单视角观测可作为带状态标记的 tracker 输入，但不得伪造另一视角观测

#### Scenario: 两路均有帧但 pair 不可信

- **WHEN** 两路均有候选，但最佳 pair 的重投影误差、3D 范围、运动连续性或歧义 margin 未通过质量门
- **THEN** tick SHALL 保留候选和拒绝诊断
- **AND** SHALL NOT 用该 pair 更新权威 anchor、权威落点或默认双摄球路

### Requirement: 双摄球分析的时间与单位语义可追溯
球路分析内部时间 SHALL 统一使用秒；跨模块传输的毫秒值 MUST 明确字段语义并在边界转换。`frame_stride` SHALL 同时控制实际视频读取与 frame index / timestamp 推进；输出速度 SHALL 由统一单位换算为 `km/h`，不得把 `ft/s` 直接标记为 `km/h`。

#### Scenario: stride 为 2 的视频读取
- **WHEN** 分析配置 `frame_stride=2`
- **THEN** 解码器 SHALL 实际读取相邻两帧中的一帧并丢弃另一帧
- **AND** emitted frame index 与 timestamp SHALL 与被读取的真实帧一致

#### Scenario: 轨迹跨模块传递时间
- **WHEN** observation、association、tracker 和 evidence 传递同一观测时间
- **THEN** 内部计算 SHALL 使用秒
- **AND** evidence/API 字段若使用毫秒 SHALL 通过字段命名或 schema 明确标注

#### Scenario: 速度单位输出
- **WHEN** v3 轨迹包含速度指标
- **THEN** JSON 中的 `speed_kmh` SHALL 是真实的 km/h 数值
- **AND** 页面 SHALL 不再把英尺每秒数值当作 km/h 展示

### Requirement: 双摄球分析产出分级可用状态

系统 SHALL 根据三维覆盖、重投影误差、几何质量、落点信息和高度物理约束生成 3D overall status，并根据所有合格 3D/2.5D segment 另行生成 `display_trajectory_status`。质量门 SHALL 按段和指标生效，MUST NOT 因 3D 不可用而隐藏合格的估算球路。对于存在可展示轨迹的 `available` 或 `degraded` 结果，普通数据分析页和球路报告 SHALL 通过视图导航和 3D 轨迹直接呈现结果，不得重复渲染状态提示卡、估算资格说明或诊断详情。状态、质量和诊断字段 SHALL 继续通过 artifact API 保持可查询。

#### Scenario: 三维覆盖与几何质量达标
- **WHEN** 轨迹具有足够双摄覆盖、回投质量达标且所有高度样本满足非负约束
- **THEN** 3D overall status SHALL 为 `FULL_ESTIMATED_3D`
- **AND** SHALL 发布三维轨迹、合格落点、速度与质量指标
- **AND** 普通球路视图 SHALL 直接展示轨迹，不额外显示双摄状态说明卡

#### Scenario: 仅部分片段满足三维重建
- **WHEN** 只有部分飞行段具备足够双摄观测
- **THEN** 3D overall status SHALL 为 `PARTIAL_3D`
- **AND** 无效区间 SHALL 断开或由明确标注的 2.5D 段替代，MUST NOT 无标记地连接
- **AND** 可展示段 SHALL 通过统一 3D 视图呈现，质量资格 SHALL 由指标字段控制而不是通过整块说明卡表达

#### Scenario: 三维高度约束失败
- **WHEN** 某段出现负高度、非有限高度、bounce 端不为 0 或段内穿地
- **THEN** 该段 SHALL 从可用 3D 资格中移除
- **AND** 若存在合格单摄证据则 SHALL 降级为 visualization-only 2.5D
- **AND** 否则 SHALL 标记为不可用并保留诊断原因

#### Scenario: 三维不足但落点可用
- **WHEN** 可靠三维段不足但落点满足权威条件
- **THEN** 3D overall status SHALL 为 `LANDING_ONLY`
- **AND** 页面 SHALL 保留权威落点数据供轨迹和技术详情使用，并可同时显示独立通过可视化门的估算 2.5D 段
- **AND** 普通报告 SHALL 不重复显示落点资格、2.5D 说明或逐段诊断文案

#### Scenario: 三维和权威落点均不可用但估算段可用
- **WHEN** 3D overall status 为 `UNAVAILABLE` 且存在合格 visualization-only 段
- **THEN** `display_trajectory_status` SHALL 为 `degraded`
- **AND** 页面 SHALL 展示估算球路及其可视轨迹
- **AND** SHALL 隐藏无资格的速度、最高点和权威落点
- **AND** SHALL 不在普通球路卡片中显示“估算 2.5D”限制说明或环境离群诊断

### Requirement: 双摄球分析失败不得破坏球员分析
球分析 SHALL 作为 joint 流程中的独立阶段运行。球模型、输入视频、标定或重建失败时，系统 SHALL 保留已完成的球员 roster、track、metrics 与可视化产物，并以可解释状态完成任务。

#### Scenario: 球分析失败而球员结果已完成
- **WHEN** player pipeline 已成功但球分析抛出可捕获异常
- **THEN** Parent 结果 SHALL 保留球员相关 artifacts
- **AND** 球相关 artifacts SHALL 标记为 `UNAVAILABLE` 或 `FAILED` 并包含 detail
- **AND** 整体任务 SHALL 进入可查询的降级完成状态，不得静默丢弃失败原因

#### Scenario: 球分析超时
- **WHEN** 球分析超过任务允许的阶段超时
- **THEN** 系统 SHALL 停止或隔离球分析资源
- **AND** SHALL 发布阶段超时 detail，同时保留已经写入的球员结果

### Requirement: 双摄球分析提供可审计诊断
球分析 SHALL 输出与用户轨迹一一对应的诊断信息，包括输入帧范围、实际采样 stride、双摄可用帧数、候选/关联/三角测量计数、时间匹配统计、三角测量角度与重投影误差摘要。诊断 SHALL 能通过任务 artifact API 查询。

#### Scenario: 查询分析诊断
- **WHEN** 用户或测试读取 joint 任务的球分析详情
- **THEN** 响应 SHALL 包含 pipeline 状态、输入范围、采样参数与关键质量指标
- **AND** 诊断数值 SHALL 与 evidence / v3 的内容一致

#### Scenario: 发现时间匹配异常
- **WHEN** 双摄时间差、无配对 tick 或重投影误差超过阈值
- **THEN** 系统 SHALL 在 detail 与质量摘要中显式记录异常
- **AND** SHALL 使对应三维段降级或不可用，不得仅依靠最终总状态隐藏异常

### Requirement: 球路按展示机位选择 image-space path

视频球路 renderer SHALL 根据 `displayViewId` 选择重建 artifact 中对应 view 的 image-space path，并使用 canonical timestamp 解析当前活动段。renderer SHALL NOT 用另一 view 的 path 或从 canonical court 坐标反推目标视频像素。

#### Scenario: A/B 球路切换

- **WHEN** 用户从 `cam_1` 切换到 `cam_2`
- **THEN** 视频球路 SHALL 使用 `image_paths_by_view.cam_2` 或等价的 `cam_2` path
- **AND** 轨迹事件、segment 边界和 canonical 时间 SHALL 与切换前保持一致

#### Scenario: 目标 view path 不可用

- **WHEN** 目标 view 没有通过展示质量门的 image-space path
- **THEN** 视频球路 SHALL 进入不可用/降级状态
- **AND** 不得绘制 reference view 的 path 或伪造目标 view 像素坐标

