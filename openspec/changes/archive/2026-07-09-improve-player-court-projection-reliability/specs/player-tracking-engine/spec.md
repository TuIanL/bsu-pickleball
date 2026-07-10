## MODIFIED Requirements

### Requirement: Footpoint estimation

后端 SHALL 提供 `FootpointEstimator`，从每帧跟踪球员框和可选姿态关键点估计图像空间地面接触点。估计 SHALL 采用 hybrid 策略：优先双踝中点、其次单踝、再膝外推，最后 fallback 到 bbox 底边中点；当 bbox 底边接近画面底部时 SHALL 降低基于 bbox 的估计置信度。

#### Scenario: Bbox bottom center is estimated

- **WHEN** 估计器接收 bbox `[x1, y1, x2, y2]` 且无姿态关键点可用
- **AND** bbox y2 不接近画面底部（y2 <= frame_height * 0.94 或无 frame_shape）
- **THEN** 返回 `image_footpoint` 等于 `[(x1 + x2) / 2, y2]`，method 为 `bbox_bottom_center`，confidence 为 0.7

#### Scenario: 双踝关键点可用

- **WHEN** 姿态关键点中左右踝（COCO 15/16）置信度均 >= 0.35
- **THEN** 返回 method 为 `pose_ankle_midpoint`，confidence 为 min(左右踝置信度)
- **AND** image_footpoint 为左右踝坐标均值

#### Scenario: 单踝关键点可用

- **WHEN** 仅一侧踝关键点置信度 >= 0.35
- **THEN** 返回 method 为 `pose_ankle_single`，confidence 为该踝置信度
- **AND** image_footpoint 为该踝坐标

#### Scenario: 膝外推

- **WHEN** 双膝关键点（COCO 13/14）置信度均 >= 0.4 且双踝均不可用
- **THEN** 返回 method 为 `knee_extrapolated`，confidence 为 min(膝置信度) * 0.8
- **AND** image_footpoint 基于膝中点向下外推计算

#### Scenario: near-clip fallback

- **WHEN** 无姿态关键点可用，且 bbox y2 > frame_height * 0.94
- **THEN** 返回 method 为 `bbox_bottom_clipped`，confidence <= 0.35
- **AND** image_footpoint 仍为 `[(x1 + x2) / 2, y2]`

#### Scenario: 正常 bbox fallback

- **WHEN** 无姿态关键点可用，且 bbox y2 <= frame_height * 0.94（或 frame_shape 为 None）
- **THEN** 返回 method 为 `bbox_bottom_center`，confidence 为 0.7
- **AND** image_footpoint 为 `[(x1 + x2) / 2, y2]`

#### Scenario: Future footpoint strategy is selected

- **WHEN** 未来 pose 或 segmentation 策略被引入
- **THEN** 估计器接口可以报告新的 method 值，而无需改变下游投影输出形状
