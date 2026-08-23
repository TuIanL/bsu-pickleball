## MODIFIED Requirements

### Requirement: 整段双视角重投影约束的 3D 曲线优化
系统 SHALL 对每个独立飞行段（`FlightSegment`，由 hit/bounce/loss/serve reset 边界切分）分别求解低维参数化曲线；系统 MUST NOT 把完整分析窗口或多个飞行段合并为一条 3D 曲线。只有满足双摄资格的段才执行 3D 优化，其余段 SHALL 进入显式混合降级。

#### Scenario: 低维参数化
- **WHEN** 系统对合格飞行段参数化 3D 曲线
- **THEN** 曲线 SHALL 为 Cubic B-spline 3D 轨迹 `(X(t),Y(t),Z(t))`、`t∈[0,1]`、由少量 control points 决定
- **AND** control points 数量 SHALL 按 segment duration 决定且存在上限
- **AND** 禁止使用逐 tick 三个自由变量等高维参数化

#### Scenario: 目标函数
- **WHEN** 系统优化某个合格飞行段
- **THEN** 目标 SHALL 最小化两个视角在各自真实观测时刻的 Huber 回投损失
- **AND** 附加 2 阶光滑、bounce 端 `z=0` hard anchor、落点 XY 锚、`z≥0` bound、max-height/max-speed soft plausibility
- **AND** 该优化的最终 3D 球路 SHALL 取代逐帧 triangulation 作为该段最终 3D 输出

#### Scenario: 逐帧三角测量是输入证据
- **WHEN** 系统生成某段最终 3D 球路
- **THEN** `BallStereoMeasurement` SHALL 作为测量证据输入段级优化
- **AND** SHALL NOT 被直接当作最终球路

#### Scenario: 双摄资格不足
- **WHEN** 某段 stereo coverage、几何质量或回投残差不满足 3D 阈值但存在合格单摄连续观测
- **THEN** 系统 SHALL 将该段交给 2.5D 重建
- **AND** MUST NOT 因该段不合格而阻止其他段或整场估算球路发布

### Requirement: 高度由双摄约束或显式视觉估算产生
系统 SHALL 区分双摄约束高度和仅用于可视化的先验弧线；双摄合格段的 `estimated_z(t)` SHALL 由两个视角约束，双摄不合格段可以输出显式标记的 2.5D 估算高度，但 MUST NOT 冒充三维测量。

#### Scenario: 双摄合格段
- **WHEN** 段级重建满足 `stereo_estimated_3d` 资格
- **THEN** `z(t)` SHALL 来自两视角回投约束
- **AND** SHALL 标记为 approximate multiview height

#### Scenario: 双摄不合格但单摄段可显示
- **WHEN** 段具有连续单摄证据与事件端点但不足以重建 3D
- **THEN** 系统 SHALL 允许使用事件边界感知的二次弧生成估算高度
- **AND** SHALL 标记 `metric_validity = visualization_only` 与具体 reconstruction mode
- **AND** MUST NOT 输出真实最高点或三维球速

### Requirement: 分层可用状态
系统 SHALL 分别输出真实双摄三维状态与展示球路状态，而非用单一 pass/fail 同时控制指标和可视化。

#### Scenario: 三维状态枚举
- **WHEN** 系统评估双摄三维能力
- **THEN** 3D 状态 SHALL 为 `FULL_ESTIMATED_3D`、`PARTIAL_3D`、`LANDING_ONLY` 或 `UNAVAILABLE` 之一
- **AND** 状态 SHALL 与三维轨迹、权威落点和速度资格一致

#### Scenario: 三维不可用但估算段可用
- **WHEN** 3D 状态为 `UNAVAILABLE` 且至少一个 2.5D 段通过可视化质量门
- **THEN** `display_trajectory_status` SHALL 为 `available` 或 `degraded`
- **AND** 前端 SHALL 能显示这些明确标注的估算段

