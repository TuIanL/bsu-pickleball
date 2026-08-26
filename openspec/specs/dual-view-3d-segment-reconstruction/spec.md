# dual-view-3d-segment-reconstruction Specification

## Purpose
TBD - created by archiving change add-multiview-3d-ball-reconstruction. Update Purpose after archive.
## Requirements
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

### Requirement: 段优化消费全部同段观测
系统 SHALL 使段级优化消费同一 flight segment 内的配对双摄观测、Cam1-only 与 Cam2-only 观测，只要时间与身份属于该段即可作为回投约束。

#### Scenario: 单路观测参与优化
- **WHEN** 段内某时刻仅 Cam1（或仅 Cam2）观测到球
- **THEN** 该观测 SHALL 作为 `proj_cam_i(XYZ(t_i)) ≈ observation_i` 的约束参与优化
- **AND** SHALL NOT 因缺少配对双摄证据被丢弃（由此 `PARTIAL_3D` 才有意义）

#### Scenario: 暴露覆盖率诊断
- **WHEN** 系统输出段级结果
- **THEN** 每段 SHALL 暴露 `stereo_coverage` 与 `prediction_ratio`
- **AND** 二者 SHALL 用于 speed eligibility 与前端渲染判断

### Requirement: 段级空间不变量

系统 SHALL 对优化所得 3D 曲线施加空间与物理不变量。

#### Scenario: 弹地端高度为零
- **WHEN** 飞行段以 bounce 为端点
- **THEN** 端点 `Z` SHALL 为 0（`z=0` 硬锚点）
- **AND** 地面 XY SHALL 对齐双摄 Homography 融合得到的落点权威

#### Scenario: 段内连续且无异常值
- **WHEN** 飞行段内存在测量
- **THEN** 3D 曲线 SHALL 在段内连续
- **AND** 不得产生明显不合理的速度或高度跳变
- **AND** 短缺口允许预测，但 `source = predicted`，不冒充 detection

#### Scenario: 高度不得低于地面
- **WHEN** 3D 段完成优化或准备发布
- **THEN** 所有有效控制点和密集采样点的 `estimated_height_ft` SHALL 为有限值且不小于 0
- **AND** 允许不超过数值容差的浮点误差，但不得出现可见的负高度

#### Scenario: 3D 高度约束失败时降级
- **WHEN** 优化结果出现负高度、非有限高度、bounce 端不为 0 或段内穿过地面
- **THEN** 该段 MUST NOT 以 `stereo_estimated_3d` 或其他可用 3D 状态发布
- **AND** 系统 SHALL 优先交给同段合格的 2.5D 重建，否则标记为 `unavailable`
- **AND** artifact SHALL 保存高度约束失败原因供诊断

### Requirement: 高度由双摄约束而非先验弧线

系统 SHALL 区分双摄约束高度和仅用于可视化的先验弧线；双摄合格段的 `estimated_z(t)` SHALL 由两个视角约束，双摄不合格段可以输出显式标记的 2.5D 估算高度，但 MUST NOT 冒充三维测量。

#### Scenario: 双摄合格段
- **WHEN** 段级重建满足 `stereo_estimated_3d` 资格
- **THEN** `z(t)` SHALL 来自两视角回投约束
- **AND** SHALL 标记为 approximate multiview height
- **AND** SHALL 同时满足高度非负和端点物理不变量

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

### Requirement: 平均球速条件性输出
系统 SHALL 在满足资格条件时输出段级平均球速估算，否则标记 unavailable 而保留落点与球路。

#### Scenario: 平均球速资格
- **WHEN** 计算段级平均球速
- **THEN** 系统 SHALL 以 `3D segment path length / flight duration` 计算
- **AND** 仅当 dual-view 覆盖充分、回投残差足够低、prediction 比例不过高且段时长足够时输出估算值
- **AND** 输出口径 SHALL 为近似估算（如"约 42 km/h"），不得输出高精度假读数

#### Scenario: 资格不足时降级
- **WHEN** 资格条件不满足
- **THEN** `average_speed` SHALL 标记 `unavailable`
- **AND** 落点 `landing_point` SHALL 仍为 available
- **AND** 瞬时/出拍瞬时球速 SHALL 在第一版不输出

### Requirement: 场景标定质量决定双摄高度资格

系统 SHALL 区分由 scene-calibrated 双摄约束得到的 metric/近似高度和仅用于可视化的先验弧线。双摄合格段的 `estimated_z(t)` SHALL 由两个视角回投约束；其 metric 资格还 SHALL 依赖所引用 scene calibration revision 的状态和质量。双摄不合格段可以输出显式标记的 approximate 或 2.5D 高度，但 MUST NOT 冒充 metric 三维测量。

#### Scenario: ready scene 的双摄段
- **WHEN** 段级重建使用 `ready` scene revision、双视角回投约束和合格 stereo coverage
- **THEN** `z(t)` SHALL 来自两视角回投约束
- **AND** SHALL 标记 `metric_validity = metric_multiview` 或明确的近似 metric 状态
- **AND** sample SHALL 保存 scene revision 与 height uncertainty

#### Scenario: approximate scene 的双摄段
- **WHEN** 段具有双摄观测但只使用 `homography_constrained_virtual` 相机
- **THEN** 系统 SHALL 允许输出 approximate multiview height
- **AND** SHALL 标记 `metric_validity = approximate_multiview`
- **AND** SHALL 禁止将 peak height、speed 或其他高度指标表达为精确 metric 结果

#### Scenario: 双摄不合格但单摄段可显示
- **WHEN** 段具有连续单摄证据与事件端点但不足以重建可靠 3D
- **THEN** 系统 SHALL 允许使用事件边界感知的二次弧生成估算高度
- **AND** SHALL 标记 `metric_validity = visualization_only` 与具体 reconstruction mode
- **AND** MUST NOT 输出真实最高点或三维球速

### Requirement: 场景标定失败时分层降级

系统 SHALL 将 scene calibration unavailable、degraded、invalidated 与动态 stereo 质量失败分别记录，不得因为单个失败原因覆盖其他诊断。场景标定失败时 SHALL 优先保留球场 XY、落点和可解释的 2.5D 展示结果。

#### Scenario: 场景 revision 被 invalidated
- **WHEN** 当前任务引用的 scene revision 与输入 video/image-size provenance 不匹配
- **THEN** 该任务 SHALL NOT 发布 metric 3D height
- **AND** SHALL 记录 mismatch reason
- **AND** 在满足现有质量门时允许显式 approximate fallback

