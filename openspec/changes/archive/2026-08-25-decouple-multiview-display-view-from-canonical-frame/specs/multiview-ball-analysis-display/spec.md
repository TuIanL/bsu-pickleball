# multiview-ball-analysis-display Delta

## ADDED Requirements

### Requirement: 球路按展示机位选择 image-space path

视频球路 renderer SHALL 根据 `displayViewId` 选择重建 artifact 中对应 view 的 image-space path，并使用 canonical timestamp 解析当前活动段。renderer SHALL NOT 用另一 view 的 path 或从 canonical court 坐标反推目标视频像素。

#### Scenario: A/B 球路切换

- **WHEN** 用户从 `cam_1` 切换到 `cam_2`
- **THEN** 视频球路 SHALL 使用 `image_paths_by_view.cam_2` 或等价的 `cam_2` path
- **AND** 轨迹事件、segment 边界和 canonical 时间 SHALL 与切换前保持一致

#### Scenario: 目标 view path 不可用

- **WHEN** 目标 view 没有通过展示质量门的 image-space path
- **THEN** 视频球路 SHALL 进入不可用/降级状态
- **AND** 不得绘制 reference view 的 path 或伪造目标 view 像素坐标
