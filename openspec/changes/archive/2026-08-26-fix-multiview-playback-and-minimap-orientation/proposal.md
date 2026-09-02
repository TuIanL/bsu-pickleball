## Why

双摄分析结果在从 A 机位切换到 B 机位后，新的 `<video>` 元素未稳定继承逐帧时间同步，导致视频可继续播放而人物框、球员轨迹点和球路叠加层停在切换或最近一次拖动进度条的时间。切换机位也不会恢复原先的播放状态，破坏连续回放体验。

同时，小地图始终采用固定的球场观看方向，未随展示机位反转；用户从球场另一端的 B 机位观看时，视频中的近端/远端与小地图中的我方/对方底线不一致，降低了空间判断的直观性。

## What Changes

- 修复双摄展示视频源切换后逐帧时间监听与 overlay 渲染时间脱节的问题，确保播放、暂停、拖动与 seek 都以当前实际挂载的视频元素驱动 canonical 时间。
- 在 A/B 机位切换时保存当前 canonical 时间和播放状态；目标视频完成 metadata 加载并完成时间映射 seek 后，若切换前正在播放则自动继续播放。
- 让小地图接收当前展示机位的球场方向，并仅在 SVG 展示映射阶段应用该方向；球员身份、canonical 球场坐标、球路和弹跳数据均保持不变。
- 对 B 机位按照已配置的 `courtOrientation` 反转小地图视角；典型对置相机使用 `rotate_180`，从而将视频近端对应为小地图我方底线。无有效方向元数据时保持既有固定方向。
- 补充覆盖跨机位连续播放、实时 overlay 更新、canonical 时间映射和小地图方向变换的回归测试。

## Capabilities

### New Capabilities

- 无。

### Modified Capabilities

- `visual-analysis-workspace`: 双摄视觉分析工作区的实时叠加层播放同步与当前机位导向的小地图展示要求变更。

## Impact

- 前端：`src/components/platform/VideoAnalysisCard.tsx` 的媒体生命周期、机位切换和回放恢复；`src/components/platform/CourtMinimap.tsx` 的坐标显示映射。
- 前端路由/数据接线：`src/pages/VisionPage.tsx` 需要把当前机位方向传入视频卡片与小地图。
- 测试：VideoAnalysisCard、CourtMinimap、multiview display utility 的单元/组件测试。
- 不改变分析后端输出、球员 canonical ID、轨迹 artifact 格式或既有单摄行为。
