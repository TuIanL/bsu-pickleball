## MODIFIED Requirements

### Requirement: 球路页面展示 v3 双摄三维结果
任务级球路页面 SHALL 展示统一重建 artifact 中可用的三维与估算 2.5D segment、落点、击球/弹地/未知端点、整体状态和质量指标，并 SHALL 使用清晰视觉编码区分双摄估算三维、单摄估算弧线与预测区间。

#### Scenario: 展示完整三维结果
- **WHEN** 页面读取到 `FULL_ESTIMATED_3D` 段
- **THEN** 页面 SHALL 展示三维轨迹、落点、覆盖率、重投影误差与有资格的速度
- **AND** SHALL 标明该轨迹为双摄估算结果而非真值

#### Scenario: 展示混合结果
- **WHEN** 同一任务同时包含 3D 段和 visualization-only 2.5D 段
- **THEN** 页面 SHALL 逐段展示 reconstruction mode、来源与质量
- **AND** 预测区间 SHALL 使用虚线或降低透明度

#### Scenario: 仅估算 2.5D 可用
- **WHEN** 3D overall status 为 `UNAVAILABLE` 但 `display_trajectory_status` 可用
- **THEN** 页面 SHALL 展示估算弧线
- **AND** SHALL 隐藏无资格的真实高度、三维球速和权威落点指标

### Requirement: Vision 页面提供双摄球分析入口但不伪造像素叠加
Vision 页面 SHALL 展示双摄球分析状态、球路入口和质量摘要；视频叠加 SHALL 使用当前机位自身的 image-space 观测/拟合或经过验证的 world-to-pixel 投影，MUST NOT 把球场世界坐标直接当作视频像素坐标。

#### Scenario: 播放当前飞行段
- **WHEN** 播放时间进入具有当前机位 image-space 轨迹的 segment
- **THEN** Vision 页面 SHALL 绘制该段截至当前时间的球路尾迹
- **AND** detected、interpolated 与 predicted 区间 SHALL 使用不同视觉编码

#### Scenario: 段结束
- **WHEN** 播放越过 hit、bounce 或 loss 端点
- **THEN** 页面 SHALL 显示正确端点标记并按配置短暂保留该段
- **AND** MUST NOT 将未知 loss 端点绘制为落地点

#### Scenario: 无有效像素映射
- **WHEN** 当前 segment 既没有当前机位 image-space 轨迹，也没有经过验证的 world-to-pixel 投影
- **THEN** Vision 页面 SHALL 不绘制伪造叠加
- **AND** SHALL 引导用户进入标准球场球路视图

## ADDED Requirements

### Requirement: 球路报告展示端点与场外语义
球路报告 SHALL 使用统一 segment artifact 绘制类似简化运动弧线的可读球路，并显示击球、弹地、可能真实界外和未知终点。

#### Scenario: 真实界外候选点
- **WHEN** segment 结束于 `legal_out_candidate` bounce
- **THEN** 报告 SHALL 在标准球场边线外的实际估算位置显示端点
- **AND** SHALL 标记“可能界外落点，非自动判罚”，不得把该点隐藏或吸附回边线内

#### Scenario: 环境离群点
- **WHEN** endpoint 被分类为 `environment_outlier`
- **THEN** 正式报告 SHALL 不把该点作为球路端点
- **AND** 调试详情 SHALL 提供其拒绝理由和原始证据
