## Why

当前 CaptureConsolePage 虽然完成了组件拆分和浅灰底色迁移，但存在三个层次的问题：首屏关键操作（事件按钮、时间线）需要滚动才能看到；单摄/双摄共用一套布局导致单摄右侧大面积空白；侧边栏时钟与主页面时钟不一致、无数据指标仍占位显示、系统状态为硬编码假数据。这些问题使页面无法满足比赛现场实时编码的操作要求。

## What Changes

### Step 0: 行为保护测试
- 为当前开始/停止/恢复/取消和事件标注行为建立基线测试
- 为时钟计算建立失败复现测试（无时区时间、非法字符串等）
- 为 unsupported 指标和硬编码健康状态建立断言

### Step 1: 数据可信度
- 统一时钟计算：主页面和侧边栏使用同一个 `computeCaptureElapsedMs(startedAt)` 纯函数，**不使用 serverNow 修正**，保证两边结果完全一致
- 后端时间戳：`ActiveCaptureTake` 和当前页面使用的录制接口的 `startedAt` 字段强制带时区；使用 `ensure_utc()` 安全转换，不直接 `replace(tzinfo=UTC)`
- 隐藏无数据指标：`MetricValue` 为 `unsupported` 时不渲染对应区块
- 删除系统状态硬编码：当前只保留 Outbox 同步状态，其余不渲染
- 事件中文映射：创建 `formatTimelineEventLabel(event, segments)` 纯函数，完整覆盖 `rally_start`、`timeout_start`、`score_update` 等所有实际事件类型

### Step 2: 布局重排
- **固定紧凑 Header**：标题 + 录制状态与时长 + 停止按钮 + 设备入口，停止按钮永远不移动（不随指标动态合并）
- **单摄模式**：直接渲染 `<CameraPreviewCard />`（不带 Grid 包装），右侧 300px 上下文栏（比分 + 设备信息）
- **双摄模式**：两路 16:9 预览（`max-height: 330px`），下方 56-72px `CompactScoreStrip`
- 单摄画面高度增加 `clamp(320px, 42vh, 430px)` 限制
- 摄像头 `<select>` 移出主布局，迁入设备抽屉

### Step 3: 紧凑时间线置首屏
- MiniTimeline 增加 `compact` prop（轨道高度 18px、间距 4px）
- 时间窗口状态与视觉密度状态分离：`TimelineWindowMode = "full" | "recent"` + `TimelineDensity = "compact" | "expanded"`
- 录制时间 ≤ 5 分钟默认全场，> 5 分钟默认最近 5 分钟
- LiveCodingPanel 置于摄像机区域正下方
- 同步状态合并到 LiveCodingPanel 标题栏

### Step 4: 非核心压缩
- BottomRow 只保留最近事件和快捷操作两栏
- QuickActions 使用 Lucide 图标替换 Emoji，删除重复和无功能占位按钮
- RecentEvents 使用中文标签 + segment ordinal，显示最近 5 条

## Capabilities

### New Capabilities
（无新能力——全部是已有行为的修正与增强）

### Modified Capabilities
- `capture-workspace-layout`: 单摄/双摄两套独立布局、上下文栏、CompactScoreStrip
- `live-coding-console`: 事件中文映射；紧凑时间线 prop；时间窗口与密度分离
- `frontend-capture-runtime`: 统一时钟纯函数；时间戳契约

## Impact

- **CaptureConsolePage.tsx**: return 区全部重排，单摄/双摄使用 `<SingleCameraWorkspace>` / `<DualCameraWorkspace>` 条件分支
- **RecordingControlPanel.tsx**: 拆入固定 Header，不再条件合并
- **ScoreBoard.tsx**: 新增 `CompactScoreStrip` 组件（双摄横条版）
- **CameraPreviewCard.tsx**: 新增 `CameraInfoCard` 组件；单摄模式直接使用，不经过 Grid
- **RecentEventsCard.tsx**: `formatTimelineEventLabel` 映射函数
- **MiniTimeline.tsx**: `compact` prop、`TimelineWindowMode`/`TimelineDensity`
- **useActiveCaptureTake.ts / useCaptureRuntime.ts**: 统一调用 `computeCaptureElapsedMs(startedAt)`
- **新建 `captureClock.ts`**: 纯函数 `computeCaptureElapsedMs`
- **后端**: 当前页面使用的录制接口的 `startedAt` 字段强制带时区
- **设备抽屉**: 迁入摄像头选择器
