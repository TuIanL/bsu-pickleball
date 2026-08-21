# dual-view-3d-segment-reconstruction Specification

## Purpose
TBD - created by archiving change add-multiview-3d-ball-reconstruction. Update Purpose after archive.
## Requirements
### Requirement: 整段双视角重投影约束的 3D 曲线优化
系统 SHALL 对每个飞行段（`FlightSegment`，由 hit/bounce/loss/serve reset 边界切分）求解一条**低维参数化**的 3D 曲线，使其同时贴近 Cam1 与 Cam2 的真实球像素观测，而非仅用逐帧 triangulation 或平滑。优化在每个摄像机自己的真实观测时刻做回投。

#### Scenario: 低维参数化
- **WHEN** 系统对某飞行段参数化 3D 曲线
- **THEN** 曲线 SHALL 为 Cubic B-spline 3D 轨迹 `(X(t),Y(t),Z(t))`、`t∈[0,1]`、由少量 control points 决定
- **AND** control points 数量 SHALL 按 segment duration 决定且存在上限
- **AND** 禁止使用逐 tick 三个自由变量等高维参数化以避免"回投好但空间乱抖"

#### Scenario: 目标函数
- **WHEN** 系统优化某飞行段
- **THEN** 目标 SHALL 最小化 `Σ Huber(project_cam1(XYZ(t1)) − observed_cam1(t1))` 与 `Σ Huber(project_cam2(XYZ(t2)) − observed_cam2(t2))`
- **AND** 附加 2 阶光滑、bounce 端 `z=0` hard anchor、落点 XY 锚、`z≥0` bound、max-height/max-speed soft plausibility
- **AND** V1 SHALL NOT 使用 `az = -g` 支配曲线（避免理想抛物线压制视觉证据）
- **AND** 该优化的最终 3D 球路 SHALL 取代逐帧 triangulation 作为最终输出

#### Scenario: 逐帧三角测量是输入证据
- **WHEN** 系统生成最终 3D 球路
- **THEN** 逐帧 `BallStereoMeasurement` SHALL 作为测量证据输入段级优化
- **AND** SHALL NOT 被直接当作最终球路

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

### Requirement: 高度由双摄约束而非先验弧线
系统 SHALL 使 `estimated_z(t)` 由两个视角的真实像素观测共同约束得出，不得再以人为生成的视觉弧线先验冒充。

#### Scenario: 取代 v2 弧线先验
- **WHEN** 双摄任务段级重建得到 `z(t)`
- **THEN** `z(t)` SHALL 来自两视角回投约束
- **AND** 新双摄分析 SHALL 不再默认绘制人为抛物线高度

### Requirement: 分层可用状态
系统 SHALL 按证据质量输出球路的分层可用状态，而非仅 pass/fail。

#### Scenario: 可用状态枚举
- **WHEN** 系统评估一次双摄球路
- **THEN** 可用状态 SHALL 为 `FULL_ESTIMATED_3D`、`PARTIAL_3D`、`LANDING_ONLY` 或 `UNAVAILABLE` 之一
- **AND** 证据不足以支撑 3D 但落点权威可用时 SHALL 输出 `LANDING_ONLY`
- **AND** 三项均不足时 SHALL 输出 `UNAVAILABLE`

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

