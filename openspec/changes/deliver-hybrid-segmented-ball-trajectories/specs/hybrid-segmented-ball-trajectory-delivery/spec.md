## ADDED Requirements

### Requirement: 飞行段优先的球路编排
系统 SHALL 在重建前按 confirmed hit、confirmed bounce、serve reset、长时间跟踪丢失与流结束边界切分独立 `FlightSegment`，并 SHALL NOT 跨事件边界或跨回合拟合单条球路。

#### Scenario: 多拍分析窗口
- **WHEN** 一个分析窗口包含多次击球与弹地
- **THEN** 系统 SHALL 为每次连续飞行生成独立 segment
- **AND** 任何输出曲线 MUST NOT 跨越 confirmed hit 或 confirmed bounce 边界

#### Scenario: 事件证据不足
- **WHEN** 某段没有可信 hit 或 bounce 但出现超过配置阈值的跟踪丢失
- **THEN** 系统 SHALL 在丢失处断开 segment
- **AND** SHALL NOT 用长插值把丢失前后的候选连接为同一拍

### Requirement: 段级动态主视角
系统 SHALL 为每个飞行段分别计算各视角的观测覆盖、连续性、检测置信度、拟合残差、预测比例、静态误检比例与可见性，并选择单一主视角；另一视角 SHALL 仅作为验证、缺口补充或 stereo anchor 来源。

#### Scenario: 球飞向某摄像头半场
- **WHEN** 该摄像头对当前段具有更高连续覆盖且球框尺度/可见性更好
- **THEN** 系统 SHALL 优先将该视角选为本段主视角
- **AND** 主视角选择理由及评分 SHALL 写入 diagnostics

#### Scenario: 两视角质量接近
- **WHEN** 两视角均有足够连续观测且差值未超过滞回阈值
- **THEN** 系统 SHALL 保持确定性的主视角选择
- **AND** SHALL 尝试以另一视角产生稀疏 stereo anchor，而非在段内频繁切换主视角

### Requirement: 混合分级重建
系统 SHALL 按段选择 `stereo_estimated_3d`、`stereo_anchored_2_5d`、`single_view_event_anchored_2_5d`、`single_view_visual_arc` 或 `unavailable`，并为每段声明 `metric_validity` 与可显示级别。

#### Scenario: 双摄证据稀疏但主视角连续
- **WHEN** 同段只有少量可信 stereo anchor 且主视角有连续观测
- **THEN** 系统 SHALL 输出 `stereo_anchored_2_5d` 或 `single_view_event_anchored_2_5d`
- **AND** SHALL 标记 `metric_validity = visualization_only`
- **AND** MUST NOT 因无法逐帧双摄配对而隐藏整段球路

#### Scenario: 只有不连续或物理不合理候选
- **WHEN** 同段未达到最小观测数、时间跨度或物理连续性阈值
- **THEN** 系统 SHALL 将该段标记为 `unavailable`
- **AND** MUST NOT 生成连接误检点的估算弧线

### Requirement: 同一轨迹事实驱动视频与报告
视频分析页、任务级球路页和球路报告 SHALL 消费同一任务版本的 segment、event 与 provenance；前端 MUST NOT 各自重新切段或估算不同端点。

#### Scenario: 视频播放进入某飞行段
- **WHEN** 播放时间位于 segment 时间范围内
- **THEN** 视频 SHALL 在对应机位图像坐标中显示当前球路尾迹
- **AND** 段结束后 SHALL 按配置短暂保留完整轨迹及端点标记

#### Scenario: 打开对应球路报告
- **WHEN** 用户从同一分析版本打开球路页或报告页
- **THEN** 页面 SHALL 显示与视频相同的 segment 数量、事件时间和端点语义
- **AND** SHALL 在标准球场视图中显示可用的估算弧线

