## 1. 侧边栏导航修正

- [x] 1.1 修正 navItems：工作台→`/workspace`（空白页），视频管理→`/analysis/tasks`，分析任务→`/capture`
- [x] 1.1a 修正 routeMeta：captureHome→navSection `"analysis"`，analysis-tasks→navSection `"videos"`，新增 workspace route
- [x] 1.2 侧边栏品牌 Logo 增加 `onClick={() => onNavigate("/")}` 首页跳转
- [x] 1.3 侧边栏录制状态块整块可点击跳转到录制工作台，删除「结束录制」按钮

## 2. 顶部栏移除

- [x] 2.1 AppShell 中 standard 模式不再渲染 Topbar（条件改为 `isLanding`）
- [x] 2.2 landing 模式 Topbar 保留不变
- [x] 2.3 capture 模式不变（无 Topbar）

## 3. 时钟修正

- [x] 3.1 确保 `useActiveCaptureTake` 将 `serverNow` 传递给 `computeElapsedMs`
- [x] 3.2 增加防卫性检查：`serverClockOffset` 偏差超过 1 小时时兜底处理

## 4. CaptureConsolePage 布局修复

- [x] 4.1 删除重复的「录制保存位置」卡片
- [x] 4.2 将「设备」「新录制」按钮移入 RecordingControlPanel（通过 extraButtons prop）
- [x] 4.3 RecordingControlPanel 新增 `error` prop，`phase === "failed"` 时显示错误卡片

## 5. 验证

- [x] 5.1 导航项点击跳转到正确页面
- [x] 5.2 侧边栏 Logo 点击回到首页
- [x] 5.3 录制状态块点击跳转到录制工作台
- [x] 5.4 无顶部栏的 standard 页面布局正常（TypeScript compile + 174 tests）
- [x] 5.5 控制区不再拥挤（extraButtons 内联在 RecordingControlPanel 中）
- [x] 5.6 录制失败时显示错误信息（error prop + failed phase 红色卡片）
- [x] 5.7 活跃录制加入超时判断（3h 陈旧自动忽略），已清理 59 条陈旧记录
- [x] 5.8 TypeScript 编译无错误，测试全部通过（175 tests）
