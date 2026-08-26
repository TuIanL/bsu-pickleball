## 1. 双摄媒体生命周期同步

- [x] 1.1 调整 `VideoAnalysisCard` 的媒体事件、逐帧回调与清理逻辑，使其绑定到实际 `activeVideoSrc` 对应的 video 元素。
- [x] 1.2 实现一次性跨机位切换状态，保存 canonical seek 位置与切换前播放状态，并防止过期媒体事件影响当前机位。
- [x] 1.3 在目标机位 metadata/seek 完成后恢复正确位置；仅在原视频播放且用户未中断时自动续播，并处理 `play()` 失败。
- [x] 1.4 保持单摄、手动进度条、发球 marker seek、暂停切换与 `requestVideoFrameCallback` 不可用时的 RAF 回退行为。

## 2. 小地图展示方向

- [x] 2.1 将当前展示机位的 `courtOrientation` 从 `VisionPage` 接线至 `VideoAnalysisCard` 和 `CourtMinimap`。
- [x] 2.2 在 `CourtMinimap` 的 SVG mapper 中实现 `identity`、`rotate_180`、`mirror_x`、`mirror_y` 的显示变换及无效值回退。
- [x] 2.3 确保场地、厨房线、NET、球员轨迹/当前位置、球路、球点和弹跳 marker 共享同一方向 mapper，且不修改 canonical 数据或 P1–P4 身份。

## 3. 回归验证

- [ ] 3.1 为 A→B（及返回 A）切换增加组件测试，验证新 video 获得事件/帧回调、overlay 持续更新、canonical 时间正确映射，且播放状态按切换前状态恢复。
- [ ] 3.2 为暂停状态切换、加载期用户暂停、目标 `play()` 被拒绝与 RAF fallback 增加边界测试。
- [x] 3.3 为 CourtMinimap 增加 identity、rotate_180、mirror_x、mirror_y 的坐标测试，并验证方向切换不会改写球员标签、颜色、轨迹或球路数据。
- [x] 3.4 运行相关前端测试与类型检查，人工验证真实双摄任务在播放中切换 A/B 时的 overlay 连续性及小地图近远端方向。
