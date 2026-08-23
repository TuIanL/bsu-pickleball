## ADDED Requirements

### Requirement: 球路页面展示 v3 双摄三维结果
任务级球路页面 SHALL 识别 `reconstructed_ball_trajectory.v3`，并在标准球场视图中展示可用的三维轨迹、落点、击球/弹地事件、整体状态和关键质量指标。页面 SHALL 区分估算三维结果与旧版二维/2.5D 结果。

#### Scenario: 展示完整三维结果
- **WHEN** 页面读取到 `FULL_ESTIMATED_3D` v3
- **THEN** 页面 SHALL 展示三维轨迹、落点、覆盖率、重投影误差与速度
- **AND** SHALL 标明该轨迹为双摄估算结果而非单摄真值

#### Scenario: 展示部分三维结果
- **WHEN** 页面读取到 `PARTIAL_3D`
- **THEN** 页面 SHALL 只连线有效三维段
- **AND** SHALL 展示缺口/无效段状态与可用范围

#### Scenario: 仅落点可用
- **WHEN** 页面读取到 `LANDING_ONLY`
- **THEN** 页面 SHALL 展示落点及置信度
- **AND** SHALL 明确提示三维球路不可用

### Requirement: 页面展示球分析运行状态与失败原因
页面 SHALL 从 Parent artifacts 的 status/detail 渲染 `queued`、`running`、`succeeded`、`degraded`、`failed` 或 `UNAVAILABLE` 等状态，不得把缺少 URL 直接显示为“没有数据”。球分析失败时，页面 SHALL 保留并显示球员分析入口。

#### Scenario: 球分析仍在运行
- **WHEN** Parent 已可查询但球分析 status 为 running
- **THEN** 页面 SHALL 显示分析进行中状态
- **AND** SHALL 不显示空的“暂无球路”结论

#### Scenario: 球分析失败
- **WHEN** status 为 failed 或 unavailable 且 detail 可用
- **THEN** 页面 SHALL 显示简短失败原因与可选诊断入口
- **AND** SHALL 允许用户返回球员轨迹、指标或报告页面

### Requirement: 页面兼容旧版球路产物
旧任务仅包含 legacy `ball_trajectory_url`、`cleaned_ball_trajectory_url` 或 v2 轨迹时，页面 SHALL 继续按既有兼容规则渲染；新任务若同时包含 v3 与 legacy 产物，默认 SHALL 选择 v3，并保留旧数据的明确标识。

#### Scenario: 旧任务读取
- **WHEN** Parent 没有 v3 但有 legacy 轨迹
- **THEN** 页面 SHALL 使用兼容读取路径
- **AND** SHALL 不因新增 v3 字段而报错

#### Scenario: 新任务双版本并存
- **WHEN** Parent 同时发布 v3 与旧版轨迹
- **THEN** 页面默认 SHALL 展示 v3
- **AND** SHALL 标注旧版数据不可与双摄三维质量指标等价

### Requirement: Vision 页面提供双摄球分析入口但不伪造像素叠加
Vision 页面 SHALL 展示双摄球分析状态、三维球路页面入口和质量摘要；在未完成 v3 到视频像素投影前，MUST NOT 把世界坐标轨迹直接叠加到单路视频像素坐标上。

#### Scenario: Vision 页面存在 v3
- **WHEN** Parent 有可用或降级 v3 artifact
- **THEN** Vision 页面 SHALL 展示球分析状态与进入球路页面的入口
- **AND** SHALL 可展示覆盖率、重投影误差等摘要

#### Scenario: 无像素投影标定
- **WHEN** 当前任务没有经过验证的 world-to-pixel 投影
- **THEN** Vision 页面 SHALL 不绘制伪造的 v3 视频叠加轨迹
- **AND** SHALL 将 v3 轨迹引导至标准球场三维/俯视视图
