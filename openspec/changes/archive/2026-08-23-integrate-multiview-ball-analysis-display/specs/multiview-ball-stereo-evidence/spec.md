## ADDED Requirements

### Requirement: 生产 joint 球链路消费 canonical evidence
生产 joint 球链路 SHALL 使用 canonical tick 的双摄 frame bundle 与共享候选生成 evidence。离线 `real_data_runner` 可作为调试或回归入口，但不得作为绕过主编排、独立解码或独立 detector 的正式发布路径。

#### Scenario: 正式 joint 运行
- **WHEN** 用户提交 joint 双摄任务
- **THEN** evidence 生成 SHALL 记录 canonical clock 与 source frame decision
- **AND** 正式路径 SHALL 不再通过两个独立 detector/读取循环生成可发布证据

#### Scenario: 离线回归运行
- **WHEN** 测试或调试直接调用离线 runner
- **THEN** runner 输出 SHALL 明确标记为 offline/debug context
- **AND** 不得被误当作已完成 Parent 的正式 artifact

### Requirement: evidence 的帧选择与时间配对严格一致
双摄 evidence SHALL 只使用实际可用帧；两路观测的配对 SHALL 使用统一时间单位和显式阈值，超出时间门的观测 SHALL 不得生成 stereo measurement。每个 measurement SHALL 保留两路真实 timestamp 与 frame index。

#### Scenario: 时间差在门限内
- **WHEN** 两路观测的真实时间差不超过配置门限
- **THEN** 系统 SHALL 允许生成该 tick 的 stereo measurement
- **AND** SHALL 记录时间差与门限结果

#### Scenario: 时间差超过门限
- **WHEN** 两路观测时间差超过球侧严格时间门
- **THEN** 系统 SHALL 拒绝该 stereo 配对
- **AND** SHALL 在统计中记录 unmatched / rejected 原因

### Requirement: evidence 记录三角测量几何质量
每个可用 stereo measurement SHALL 尽可能记录三角测量射线夹角、重投影误差、深度/空间范围检查与质量等级；缺少必要几何质量时，用户轨迹不得将该点标为高可信三维点。

#### Scenario: 几何质量达标
- **WHEN** 射线夹角、重投影误差与空间范围均满足阈值
- **THEN** measurement SHALL 标记为可用于高可信三维重建
- **AND** v3 SHALL 能引用该质量等级

#### Scenario: 几何质量不达标
- **WHEN** 射线夹角过小或重投影误差过大
- **THEN** measurement SHALL 保留在审计 evidence 中但标记为低质量/无效
- **AND** 不得无标记地进入权威三维轨迹

### Requirement: evidence 文件发布后不可变
正式发布的 `multiview_ball_stereo_evidence.v1` SHALL 在生成后保持内容不可变，后续轨迹重建或页面读取 SHALL 通过引用消费。重跑 SHALL 生成新的版本化任务 artifact，不得原地覆盖已完成任务的 evidence。

#### Scenario: 页面读取 evidence
- **WHEN** 前端或调试工具读取已完成任务的 evidence
- **THEN** 读取结果 SHALL 与 Composer 发布时一致
- **AND** 不得因页面加载改变 evidence 内容

#### Scenario: 任务重跑
- **WHEN** 用户对同一输入重新运行分析
- **THEN** 系统 SHALL 生成新任务作用域的 evidence
- **AND** 原任务 evidence SHALL 保持可复现
