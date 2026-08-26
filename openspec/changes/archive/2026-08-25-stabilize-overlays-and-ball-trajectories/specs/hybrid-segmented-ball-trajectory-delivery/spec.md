## ADDED Requirements

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
