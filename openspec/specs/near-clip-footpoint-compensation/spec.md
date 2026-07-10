# near-clip-footpoint-compensation Specification

## Purpose
TBD - created by syncing change improve-player-court-projection-reliability.

## Requirements
### Requirement: 近端 bbox 裁切检测

FootpointEstimator SHALL 在 bbox 底边接近画面底部时检测可能裁切状态，标记 `near_frame_bottom: true` + `bbox_clip_suspected: true`，并降低基于 bbox_bottom_center 的脚点置信度。系统不绝对断言裁切发生，仅标记可疑状态。

#### Scenario: bbox 底边接近画面底部

- **WHEN** `bbox.y2 > frame_height * near_clip_threshold`（默认 threshold=0.94）
- **AND** footpoint_method 为 `bbox_bottom_center` 或 hybrid fallback 到此方法
- **THEN** 返回的 FootpointEstimate.method SHALL 为 `"bbox_bottom_center"`（不改变 method 名称）
- **AND** FootpointEstimate 的 metadata SHALL 包含 `near_frame_bottom: true` 和 `bbox_clip_suspected: true`
- **AND** FootpointEstimate.confidence SHALL <= 0.35

#### Scenario: bbox 底边在安全区域

- **WHEN** `bbox.y2 <= frame_height * near_clip_threshold`
- **THEN** bbox_bottom_center 返回的 FootpointEstimate.confidence SHALL 维持默认值（0.7）
- **AND** metadata SHALL NOT 包含 `near_frame_bottom` 标记

#### Scenario: 无 frame_shape 时关闭裁切检测

- **WHEN** estimate() 调用时 `frame_shape` 参数为 None
- **THEN** 系统 SHALL NOT 执行裁切检测
- **AND** bbox_bottom_center 行为 SHALL 与现有完全一致（向后兼容）

#### Scenario: 非 bbox 方法不受裁切检测影响

- **WHEN** footpoint_method 为 `pose_ankle_midpoint` 或 `pose_ankle_single` 或 `knee_extrapolated`
- **THEN** 系统 SHALL NOT 因 bbox 位置而降低 FootpointEstimate.confidence
- **AND** 系统 SHALL NOT 设置 `near_frame_bottom` 或 `bbox_clip_suspected` 标记

### Requirement: 近端裁切阈值可配置

系统 SHALL 允许通过配置项 `near_clip_threshold` 调整裁切检测的画面比例阈值。

#### Scenario: 使用默认阈值

- **WHEN** `near_clip_threshold` 未配置
- **THEN** 系统 SHALL 使用默认值 0.94

#### Scenario: 自定义阈值

- **WHEN** `near_clip_threshold` 配置为 0.90
- **THEN** 系统 SHALL 在 `bbox.y2 > frame_height * 0.90` 时触发裁切检测

### Requirement: 裁切脚点的坐标不丢弃但仍标记低置信度

系统 SHALL 在近端裁切被标记时保留脚点坐标（不丢弃），但降低其 projection_confidence，使下游能区分可靠投影与低置信度投影。

#### Scenario: 裁切可疑脚点进入 minimap

- **WHEN** bbox 被标记 `near_frame_bottom: true`，脚点仍通过 homography 投影为有效 court_position
- **THEN** 该点 SHALL 进入 minimap 渲染（使用 tracking_bounds）
- **AND** 该点 SHALL NOT 进入热力图统计
- **AND** projection_status SHALL 标记为 `"inside_court"` 或 `"outside_court_visible"`（取决于实际坐标）
- **AND** projection_confidence SHALL <= 0.35

#### Scenario: 裁切可疑脚点用于轨迹显示

- **WHEN** bbox 被标记 `bbox_clip_suspected: true`，投影坐标在 minimap 上显示
- **THEN** 系统 SHALL 使用半透明样式绘制该点
- **AND** 轨迹连线 SHALL 在通过裁切可疑段时使用虚线样式

#### Scenario: pose_ankle 可用时不降级

- **WHEN** 姿态 ankle 关键点可用（即使 bbox 接近画面底部）
- **THEN** 系统 SHALL 优先使用 `pose_ankle_midpoint` 或 `pose_ankle_single`
- **AND** projection_confidence SHALL 基于 ankle 置信度设定，不受 near_frame_bottom 降级
- **AND** near_frame_bottom / bbox_clip_suspected SHALL NOT 被标记（因此场景未使用 bbox 方法）
