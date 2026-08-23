## ADDED Requirements

### Requirement: 双摄球路分析使用统一时间轴与共享观测
joint 模式的球路分析 SHALL 从 `CanonicalAnalysisClock` 产生的 `SynchronizedFrameBundle` 读取双摄帧，并在同一 canonical tick 上完成候选生成、跨视角关联、三角测量与轨迹更新。生产链路 MUST 复用每个视角每个 tick 的候选结果，MUST NOT 为 stereo 分析再次独立运行 detector。

#### Scenario: 两路帧在同一 canonical tick 可用
- **WHEN** 两路视频在 tick `t_k` 均有可用帧
- **THEN** 球候选 SHALL 由这两帧各检测一次后供 association、tracker 和 stereo 共同消费
- **AND** evidence 中 SHALL 记录 `tick_id`、两路真实帧索引与各自时间戳

#### Scenario: 一路帧不可用
- **WHEN** tick `t_k` 只有一个视角有可用帧
- **THEN** 该 tick SHALL NOT 生成权威双摄三角测量
- **AND** 单视角观测可作为带状态标记的 tracker 输入，但不得伪造另一视角观测

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
系统 SHALL 根据三维重建覆盖率、重投影误差、三角测量几何质量与落点信息生成 `FULL_ESTIMATED_3D`、`PARTIAL_3D`、`LANDING_ONLY` 或 `UNAVAILABLE`。状态计算 SHALL 与原始 evidence 分离，且每个核心指标 SHALL 带有 validity 或质量分级。

#### Scenario: 三维覆盖与几何质量达标
- **WHEN** 轨迹具有足够双摄覆盖且质量阈值达标
- **THEN** v3 SHALL 标记为 `FULL_ESTIMATED_3D`
- **AND** SHALL 发布三维轨迹、落点、速度与质量指标

#### Scenario: 仅部分片段满足三角测量
- **WHEN** 只有部分飞行片段具备足够双摄观测
- **THEN** v3 SHALL 标记为 `PARTIAL_3D`
- **AND** 无效区间 SHALL 断开或显式标记，不得连续连线制造完整轨迹

#### Scenario: 三维不足但落点可用
- **WHEN** 可靠三维段不足但落点判定满足落点条件
- **THEN** v3 SHALL 标记为 `LANDING_ONLY`
- **AND** 页面 SHALL 只展示落点及其置信度，不得回退为默认 2.5D 球路

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
