## 1. 后端：活跃录制查询接口

- [ ] 1.1 实现 `GET /api/capture-takes/active` 后端端点，返回当前活跃录制信息或 204
- [ ] 1.2 在 `analysisClient.ts` 中添加 `getActiveCaptureTake()` API 方法

## 2. 全局导航重构

- [ ] 2.1 改造 AppShell：接收 `routeName` prop，根据 routeName 决定是否渲染 Sidebar
- [ ] 2.2 实现 `AppSidebar` 组件（216px 固定左侧，导航项列表，品牌标识）
- [ ] 2.3 实现 `useActiveCaptureTake` hook（5 秒轮询，document.visibility 感知）
- [ ] 2.4 实现 Sidebar 底部录制状态块（活跃录制信息 + 实时时钟动画）
- [ ] 2.5 LandingPage 简化：只保留品牌展示 + "进入开始使用" CTA 按钮
- [ ] 2.6 更新路由系统：将 routeName 传递到 AppShell

## 3. CaptureConsolePage 骨架优先（方案 A 第一阶段）

- [ ] 3.1 创建 `CaptureWorkspaceLayout` 组件（定义新布局结构 + slot 插槽）
- [ ] 3.2 将 CaptureConsolePage 的顶级 div 替换为 CaptureWorkspaceLayout
- [ ] 3.3 将现有内联渲染函数分别移入对应 slot（标题栏、预览、控制栏、事件、时间线）
- [ ] 3.4 验证：所有录制功能正常（开始、停止、恢复、取消、事件标注）

## 4. 组件提取（方案 A 第二阶段）

- [ ] 4.1 提取 `CameraPreviewCard` + `CameraPreviewGrid` 组件
- [ ] 4.2 提取 `RecordingControlPanel` 组件
- [ ] 4.3 提取 `EventActionToolbar` 组件（带事件按钮分组）
- [ ] 4.4 提取 `CaptureWorkspaceHeader` 组件（标题 + 状态标签 + 存储空间 + 设置）
- [ ] 4.5 提取 `RecentEventsCard` / `CaptureHealthCard` / `QuickActionsCard` 组件
- [ ] 4.6 提取 `DeviceDrawer` 为独立组件
- [ ] 4.7 提取 `CompletionPanel` 为独立组件

## 5. MiniTimeline 改进

- [ ] 5.1 实现等距时间刻度算法和渲染（替换当前的三标签）
- [ ] 5.2 新增重点标记独立轨道行（第四根轨道）
- [ ] 5.3 更新 miniTimeline props 接口以支持新轨道

## 6. 视觉迁移（方案 A 第三阶段）

- [ ] 6.1 定义视觉 Token 常量（颜色、圆角、阴影），集成到 Tailwind 配置
- [ ] 6.2 页面底色从绿色渐变改为 `#F7F8FA`
- [ ] 6.3 逐个组件切换样式：白卡片 + 浅灰底 + 新阴影
- [ ] 6.4 事件按钮按三组重新样式化（层级/比赛状态/辅助）
- [ ] 6.5 摄像机预览卡添加状态覆盖标签（连接中/中断/重试）

## 7. 验收与回归

- [ ] 7.1 双摄录制时两路画面在第一屏完整可见
- [ ] 7.2 用户可在 1 秒内找到停止录制按钮
- [ ] 7.3 录制时长和录制状态清晰可读
- [ ] 7.4 盘/局/分在时间线上具有明显层级
- [ ] 7.5 单摄模式不显示空白第二机位
- [ ] 7.6 页面刷新后录制状态按现有恢复逻辑正常恢复
- [ ] 7.7 停止录制期间不能重复提交停止请求
- [ ] 7.8 1440px 宽度下不出现横向滚动条
- [ ] 7.9 现有测试通过（`CaptureConsolePage.test.tsx` 等）
