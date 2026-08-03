## Why

`redesign-video-analysis-overlay` 交付后，真实视频分析页出现四个用户可感知的问题：小地图过长遮挡播放控件；视频中段检测框身份标签从 `P1-P4` 退化为 `person`；小地图与视频拍摄方向相反（我方底线显示为对方底线）；小地图点位与视频位置不一致、明显滞后。这些问题破坏复盘体验，需要一次聚焦修复。

## What Changes

- 小地图改为**默认收起**，仅在用户点击地图按钮时展开，展开后不遮挡底部播放控件（含全屏按钮）。
- 后端身份层为"合格但未匹配"的 track 增加**位置连续性软接管**：在无 lock hint、无既有映射时，按最近已知球场位置就近归入某个已有球员槽位，标记为低置信度的 `tentative` 身份并产出样本，使检测框标签在中段仍保持 `P1-P4`、小地图持续获得新点位。
- 修正小地图的球场 y 轴渲染方向，使其与视频拍摄方向一致（近端/摄像头侧在底部）。
- 小地图对超过新鲜度阈值、落后于当前播放时间的点位不再作为"当前位置"展示，改为显示信号丢失/停滞状态，避免误导。
- 前端与小地图相关的测试、后端身份软接管相关测试同步更新。

## Capabilities

### New Capabilities

（无新增 capability，全部为既有能力的要求变更。）

### Modified Capabilities

- `video-overlay-hud`: 小地图需支持默认收起与展开交互、展开不遮挡播放控件；小地图球场方向须与视频拍摄方向一致（近端在底部）；对落后于当前播放时间的球员点显示停滞/丢失状态而非过期位置。
- `player-trajectory-identity`: 身份层在无 hint、无既有映射时，可对"合格且在场内、距某球员最近已知位置在阈值内"的 track 做位置连续性软接管，产出 `tentative` 低置信度身份样本；保留"不独立创建第 5 个身份"与"远距离 track 不误配"的约束。
- `player-identity-display`: 软接管产生的低置信度临时身份在检测框标签 SHALL 仍显示 canonical `P1-P4`（可带较低置信度），仅完全未关联的框显示中性文本 `person`。

## Impact

- 前端：`src/components/platform/CourtMinimap.tsx`、`src/components/platform/VideoAnalysisCard.tsx`、`src/services/videoOverlayHud.ts` 及其测试。
- 后端：`backend/app/services/analysis_pipeline.py`、`backend/app/vision/player_tracking_engine/player_identity.py`、`backend/app/schemas/tracking.py`（`PlayerTrackingStatus` 增加 `tentative`）及其测试。
- 不改变 lock manager 的硬锁状态机；不改变现有 artifact 的既有字段语义；已有旧任务产物无需迁移。
