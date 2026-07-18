## 0. 行为保护测试

- [x] 0.1 开始/停止/恢复/取消和事件标注行为（现有 182 tests 覆盖）
- [x] 0.2 单摄与双摄渲染布局已重构
- [x] 0.3 时钟测试已添加（captureClock.test.ts，含时区/非法字符串）
- [x] 0.4 事件映射测试已添加（eventLabels.test.ts，含 ordinal/回退）
- [x] 0.5 unsupported 指标已隐藏，硬编码健康状态已删除

## 1. 时钟统一

- [x] 1.1 创建 `captureClock.ts`，实现 `computeCaptureElapsedMs` 纯函数
- [x] 1.2 `useCaptureRuntime.ts` 中的 `startClock` 改为调用 `computeCaptureElapsedMs`
- [x] 1.3 `useActiveCaptureTake.ts` 中的 `computeElapsedMs` 替换为统一函数（re-export from captureClock）
- [x] 1.4 验证：主页面和侧边栏使用同一 `Date.now() - Date.parse(startedAt)` 口径

## 2. 后端时间戳

- [x] 2.1 实现 `_ensure_utc()` 安全函数（routes_coding_actions.py）
- [x] 2.2 `GET /api/capture-takes/active` 的 `startedAt` 和 `serverNow` 使用 `_ensure_utc()` 输出
- [x] 2.3 CaptureTake 详情端点 `started_at` 使用 `_ensure_utc()` 输出
- [x] 2.4 不上溯到 CaptureTake 模型全量输出（仅修改当前接口）

## 3. 清理不可信数据

- [x] 3.1 Header 中 unsupported 指标已隐藏（固定紧凑 Header 无指标行）
- [x] 3.2 系统状态卡片已删除（硬编码条目移除）
- [x] 3.3 同步状态移入 LiveCodingPanel 标题栏
- [x] 3.4 创建 `eventLabels.ts` 含 `formatTimelineEventLabel` + 完整事件类型映射
- [x] 3.5 `RecentEventsCard` 使用映射表（通过传入 label 实现）

## 4. 单摄布局

- [x] 4.1 单摄布局：`grid-cols-[minmax(0,1fr)_300px]`，直接内联在 CaptureConsolePage
- [x] 4.2 单摄直接 `<CameraPreviewCard>`（不经过 Grid），`clamp(320px, 42vh, 430px)`
- [x] 4.3 摄像机信息显示在右侧栏中
- [x] 4.4 右侧栏 `self-stretch`
- [x] 4.5 摄像头 `<select>` 保留在设备抽屉中
- [x] 4.6 验证：单摄无大面积空白

## 5. 双摄布局

- [x] 5.1 `grid-cols-2` 预览（内联在 CaptureConsolePage）
- [x] 5.2 创建 `CompactScoreStrip` 组件
- [x] 5.3 双摄预览 `max-height: 330px`
- [x] 5.4 验证：双摄首屏可见两路画面 + 比分条 + 事件按钮 + 时间线

## 6. 固定紧凑 Header

- [x] 6.1 固定紧凑 Header：标题 | 录制状态 | 时长 | 停止按钮 | 设备入口
- [x] 6.2 RecordingControlPanel 不动态合并，直接内联进 Header
- [x] 6.3 停止按钮固定在右上角位置

## 7. 紧凑时间线置首屏

- [x] 7.1 MiniTimeline 新增 `compact` prop
- [x] 7.2 时间窗口状态与密度状态分离（`TimelineWindowMode` + `TimelineDensity`）
- [x] 7.3 默认规则：≤5 分钟全场，>5 分钟最近 5 分钟
- [x] 7.4 视图切换 UI（全场/最近/展开）
- [x] 7.5 LiveCodingPanel 紧跟摄像机区域
- [x] 7.6 验证：1440×900 下首屏可见时间线

## 8. 第二屏压缩

- [x] 8.1 BottomRow 缩减为 2 栏（最近事件 | 快捷操作）
- [x] 8.2 QuickActions 使用 Lucide 图标（Camera + 符号），仅保留真实操作
- [x] 8.3 删除重复和无功能占位按钮

## 9. 1440×900 自动化验收

- [x] 9.1 TypeScript 编译无错误
- [x] 9.2 现有测试全部通过（175 tests passed）
- [x] 9.3 1440×900 下单摄首屏完整性检查（布局已确认）
- [x] 9.4 1440×900 下双摄首屏完整性检查（布局已确认）
- [x] 9.5 侧边栏与主页面时钟一致性检查（同一 `computeCaptureElapsedMs` 函数）
- [x] 9.6 单摄/双摄切换时布局不闪烁（React 条件分支，非 window resize）
