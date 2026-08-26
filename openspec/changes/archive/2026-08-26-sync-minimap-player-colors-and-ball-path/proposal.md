## Why

视频分析页面中，人物框已按 canonical `player_id` 使用稳定身份颜色，但小地图按当前数组顺序分配另一套颜色，导致同一球员在两处显示不同颜色。同时，视频已能优先显示重建球路，而小地图仅消费旧版二维球轨迹；使用重建球路的任务因此会在小地图中缺少球路，破坏视频与场地平面回放的一致性。

## What Changes

- 让小地图球员点和尾迹以 canonical `player_id` 解析与视频人物框相同的 identity hue，不再依赖渲染顺序。
- 为小地图接入 `reconstructed_ball_trajectory` 的 canonical court-space 球路，并与视频共享同一 canonical 播放 tick。
- 在重建球路不可用或不具备可展示 court-space 数据时，保留现有 `ballTrajectory` 的兼容回退。
- 让小地图遵守视频球路开关、段级展示资格、时间窗口和轨迹断段语义；不把 image-space 坐标当作场地坐标使用。
- 增加覆盖颜色同步、重建球路显示及旧产物回退的前端测试。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `video-overlay-hud`: 要求小地图与视频人物框采用同一 canonical 身份颜色，并在使用重建球路时渲染同 tick、同质量门下的 court-space 球路。

## Impact

- 前端：`CourtMinimap`、`VideoAnalysisCard` 及其球路/身份颜色适配逻辑和测试。
- 数据消费：读取现有 `reconstructed_ball_trajectory` 的场地坐标、展示资格与时间信息；不新增后端 API 或 artifact。
- 兼容性：保留单摄和旧 `cleaned_ball_trajectory` 的小地图球路回退路径。
