# minimap-direction-removal-and-trajectory-break

## Why

视频分析小地图的球员方向指示基于相邻两帧的单帧位移计算，60fps 下方向抖动严重、可信度低；且在身份锁跳变（job-6c0cc96f86 22 秒附近 P1 被误接到他人 track）时方向会指向错误球员，误导观感。同时，当身份层把多个不同 source track 的样本缝进同一球员时，会产生 13-14 英尺的大位移跳变，前端 HUD 目前只按"时间缺口"断线，无法断开，导致小地图画出"来回抽搐"的 V 形扫线。

## What Changes

- **移除**小地图球员方向指示（方向字段、箭头 marker、方向渲染），只保留速度摘要。
- **新增**前端 HUD 球员轨迹的"位移断线"：相邻两点位移超过阈值时拆成独立轨迹片段，不画跨越跳变的直线。
- 速度摘要逻辑保持不变（速度基于窗口内位移/时间，仍然有用且不误导）。
- 不涉及后端身份锁定逻辑（根因修复留作后续独立 change）。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `video-overlay-hud`: 移除"显示球员方向"需求（方向箭头从 HUD 中删除），保留速度摘要；将"同步显示球员移动轨迹"扩展为同时按时间缺口**和**大位移跳变断线；同步更新"停滞球员"需求中关于方向箭头的描述。

## Impact

- `src/services/videoOverlayHud.ts` — 移除 `direction` 字段与 `resolveMotion` 中的方向计算；在轨迹分段逻辑中新增位移断线阈值。
- `src/components/platform/CourtMinimap.tsx` — 删除方向箭头 `<line>` 与 `court-hud-arrow` marker。
- `src/components/platform/CourtMinimap.test.tsx`、`src/services/videoOverlayHud.test.ts` — 更新/新增对应用例。
- 纯前端改动，不涉及后端 pipeline、schema 或存储。
