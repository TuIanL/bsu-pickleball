# hybrid-segmented-ball-trajectory-delivery Specification

## Purpose
TBD - created by archiving change deliver-hybrid-segmented-ball-trajectories. Update Purpose after archive.
## Requirements
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

### Requirement: 视频叠加固定渲染视角

球路 artifact 或其前端 adapter SHALL 为视频叠加明确 `render_view_id`，默认取任务 `reference_view_id`。segment 的 `primary_view_id` 只 SHALL 用于重建质量、来源和 diagnostics，不得直接决定视频的 image-space 渲染视角。视频叠加 SHALL 只消费 `image_paths_by_view[render_view_id]` 或后端生成的等价 target-view reprojected path。

#### Scenario: 主视角与渲染视角不同
- **WHEN** 某 segment 的 `primary_view_id=cam_2`，但当前视频的 `reference_view_id=cam_1`
- **THEN** 视频 renderer SHALL 使用该 segment 的 `cam_1` path 或 target-view reprojected path
- **AND** SHALL NOT 把 `cam_2` 的 image-space 点直接画到 `cam_1` 视频上

#### Scenario: 目标视角路径缺失
- **WHEN** segment 没有 `render_view_id` 对应的有效 image path，且没有可用的后端重投影 path
- **THEN** 该 segment SHALL 标记为 video-overlay unavailable 或 diagnostic-only
- **AND** SHALL 保留 court-space/报告侧 segment
- **AND** SHALL NOT 静默回退到另一摄像头的 image-space 坐标

#### Scenario: 视角契约可追溯
- **WHEN** artifact 发布可显示的 video trajectory
- **THEN** artifact SHALL 记录 `render_view_id`、reference view、path availability 和视角转换/缺失原因
- **AND** diagnostics SHALL 能定位每个 segment 是否使用原生 target-view path 或 reprojected path

### Requirement: 视频片段边界使用半开时间窗口

视频叠加的 segment display window SHALL 使用半开区间 `[start_ms, end_ms)`。相邻 segment 在共享边界时 SHALL 只由后一个 segment 拥有该边界 tick；segment 的重建样本、事件端点和渲染端点 SHALL 保持独立，不得因视频尾迹策略重新连接为单一曲线。

#### Scenario: 相邻片段共享边界
- **WHEN** segment A 的 `end_ms` 等于 segment B 的 `start_ms`
- **THEN** 在该边界时刻 renderer SHALL 只选择 segment B
- **AND** SHALL NOT 同时渲染 A 与 B 的完整 path

#### Scenario: 后继片段开始后停止旧尾迹
- **WHEN** 后继 segment 已进入其 display window
- **THEN** 前一 segment 的 retention tail SHALL 立即停止
- **AND** 最多 SHALL 保留一个与后继 segment 去重后的公共端点

#### Scenario: 不跨事件边界连接
- **WHEN** 两个 segment 由 hit、bounce、loss、reset 或质量断点分隔
- **THEN** 视频 renderer SHALL 保持两段 geometry 独立
- **AND** SHALL NOT 为了尾迹连续性跨边界插值或连线
