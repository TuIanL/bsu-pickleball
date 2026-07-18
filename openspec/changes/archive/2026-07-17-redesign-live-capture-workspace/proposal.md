## Why

CaptureConsolePage 是一个 743 行单体组件，将所有渲染逻辑内联在页面中。视觉上使用大面积浅绿渐变背景，信息层级不清晰，不符合比赛现场长时间使用的专业控制台要求。MiniTimeline 的时间刻度只显示 3 个窗口边界标签，事件按钮缺乏视觉分组。

## What Changes

- **CaptureWorkspaceLayout 新骨架**: 采用方案 A 策略，先搭新布局骨架，再逐块提取组件，最后迁移视觉样式
- **组件拆分**: CaptureConsolePage 拆分为 CameraPreviewGrid、RecordingControlPanel、LiveCodingPanel（含 EventActionToolbar + CaptureTimeline）、RecentEventsCard、CaptureHealthCard、QuickActionsCard、DeviceDrawer、CompletionPanel
- **ViewModel 模式**: 页面层构造 ViewModel，子组件只消费自己的视图模型片段
- **MiniTimeline 等距刻度**: 按容器宽度和目标刻度数计算整洁步长，而非硬编码三点标签
- **MiniTimeline 重点标记轨道**: 新增第四根轨道，使用归一化 TimelineMarker 数据
- **事件按钮分组**: 层级事件 / 比赛状态 / 辅助事件三组视觉区分
- **视觉 Token 系统**: CSS Variables 定义颜色、圆角、阴影、交互状态
- **页面底色从浅绿改为 #F7F8FA，绿色回归品牌强调色**
- **真实数据来源**: CaptureHealthCard 等指标从 API 获取，不支持时隐藏或显示 skeleton

## Capabilities

### New Capabilities
- `capture-workspace-layout`: CaptureConsolePage 新布局骨架、组件拆分方案、ViewModel 模式

### Modified Capabilities
- `live-coding-console`: MiniTimeline 刻度算法、重点标记轨道、事件按钮分组；MiniTimeline 接收归一化 TimelineMarker 而非原始事件类型

## Impact

- **CaptureConsolePage.tsx**: 743 行 → 骨架 + 10+ 子组件引用，内联渲染函数逐步删除
- **MiniTimeline.tsx**: 刻度算法重写（container-width-aware）+ 新增重点标记轨道 + TimelineMarker 归一化
- **新组件文件**: 10+ 个独立组件文件在 `src/components/capture/` 下
- **timelineQuickEvents.ts**: 事件按钮分组元数据调整
- **tailwind.config.ts** / CSS: 新增 CSS Variables 定义视觉 Token
