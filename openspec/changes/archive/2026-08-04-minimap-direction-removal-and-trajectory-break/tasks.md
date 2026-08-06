## 1. 移除球员方向指示（数据层）

- [x] 1.1 `src/services/videoOverlayHud.ts`：删除 `HudPlayer.direction` 字段；将 `resolveMotion` 更名 `resolveSpeed`，返回值去掉 `direction` 只保留 `speedMetersPerSecond`；更新 `buildVideoOverlayHud` 中的 `...resolveSpeed(segments, config.courtUnit)` 调用
- [x] 1.2 `src/components/platform/CourtMinimap.tsx`：删除方向箭头 `<line markerEnd="url(#court-hud-arrow)" ...>` 渲染，并删除 `<marker id="court-hud-arrow">` 定义；停滞状态样式（透明度/虚线/摘要丢失标记）保持不变
- [x] 1.3 更新测试：`videoOverlayHud.test.ts` "does not present a numeric speed when the coordinate unit is unknown" 用例移除 `direction` 断言，只断言 `speedMetersPerSecond === null`；确认 `CourtMinimap.test.tsx` 无 `direction`/`court-hud-arrow` 引用

## 2. 球员尾迹位移断线

- [x] 2.1 `src/services/videoOverlayHud.ts`：`VideoOverlayHudOptions` 与 `DEFAULT_OPTIONS` 新增 `maxTrailJumpFt?: number`，默认 `6.0`
- [x] 2.2 扩展 `splitAtGaps(points, maxGapSeconds, maxPoints, maxDisplacementFt = Infinity)`：相邻两点位移超过 `maxDisplacementFt` 时开新 segment（与时间缺口断线并列）；球员轨迹调用传 `config.maxTrailJumpFt`，球轨迹调用保持默认（不按位移断线）
- [x] 2.3 新增测试：`videoOverlayHud.test.ts` 增加"两簇点位移超阈值被拆成独立 segments（不连线）"与"球轨迹不受位移断线影响"用例

## 3. 验证

- [x] 3.1 运行 `npm test`：videoOverlayHud 与 CourtMinimap 相关测试全量通过
- [x] 3.2 运行 `npm run build`（tsc + vite）通过
- [x] 3.3 `openspec validate --changes` 通过
- [x] 3.4 用 job-6c0cc96f86 数据在视觉分析页核对：22 秒附近 P1 尾迹不再出现跨半场的 V 形连线，方向箭头已消失（已用真实 `result.tracks` 复算新逻辑：P1 由 1 条连续线拆为 5 个 segment，4 处跳变对全部 >6ft 断线；浏览器目视确认待用户复核）
