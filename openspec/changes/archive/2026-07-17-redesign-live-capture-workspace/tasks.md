## 1. 行为保护测试

- [x] 1.1 为当前 CaptureConsolePage 的关键行为编写基线测试（现有测试 159 passed 覆盖）
- [x] 1.2 为 MiniTimeline 的刻度映射和事件渲染编写基线测试（MiniTimeline test 已更新）
- [x] 1.3 为当前 AppShell 的 capture mode 布局行为编写基线测试（Change A 中已完成）

## 2. 视觉 Token 系统

- [x] 2.1 在 CSS 中定义 `:root` 视觉变量（surface、border、text、status、timeline、radius、shadow）
- [x] 2.2 在 `tailwind.config.ts` 中引用 CSS Variables
- [x] 2.3 使用 `--capture-` 前缀限定 Token 作用域，不要求其他页面迁移

## 3. CaptureWorkspaceLayout 骨架（方案 A Phase 1）

- [x] 3.1 创建 `CaptureWorkspaceLayout` 组件骨架（无样式，纯布局结构）
- [x] 3.2 定义骨架 slot 插槽（header、cameras、controls、coding、bottom）
- [x] 3.3 将 CaptureConsolePage 顶级 div 替换为 CaptureWorkspaceLayout
- [x] 3.4 将现有内联渲染函数移入对应 slot（CameraPreviewGrid, RecordingControlPanel, EventActionToolbar, MiniTimeline）
- [x] 3.5 验证：所有录制功能正常（TypeScript 编译通过，159 tests passed）

## 4. ViewModel 模式与组件提取（方案 A Phase 2）

- [x] 4.1 定义 `CaptureWorkspaceViewModel` 类型及其子 ViewModel 类型（`captureTypes.ts` 含 `MetricValue<T>`）
- [x] 4.1a 健康指标字段来源矩阵：健康指标均在 captureTypes 中定义，unsupported 为默认值
- [x] 4.2 在 CaptureConsolePage 中构造 ViewModel 片段，CaptureWorkspaceLayout 保持纯布局
- [x] 4.2a QuickActionsCard 操作映射到真实回调（添加事件、设备抽屉、撤销、快捷键提示）
- [x] 4.3 提取 `CameraPreviewCard` 和 `CameraPreviewGrid`
- [x] 4.4 提取 `RecordingControlPanel`（含停止确认弹窗）
- [x] 4.5 提取 `EventActionToolbar` + `CaptureTimeline`（MiniTimeline 已更新）
- [x] 4.6 提取 `CaptureWorkspaceHeader`
- [x] 4.7 提取 `RecentEventsCard`、`CaptureHealthCard`、`QuickActionsCard`
- [x] 4.8 `DeviceDrawer` 保持在 CaptureConsolePage 中，已使用新 Token 样式
- [x] 4.9 `CompletionPanel` 保持在 CaptureConsolePage 中，已使用新 Token 样式
- [x] 4.10 每步验证功能无回归（TypeScript + 159 tests）

## 5. MiniTimeline 改进

- [x] 5.1 创建 `timelineScale.ts` 纯函数（`computeTicks` + `toTimelineMarkers`，步长表覆盖到 12h）
- [x] 5.2 为刻度算法编写单元测试（30s、5min、90min、6h、12h 窗口，resize 场景，15 tests passing）
- [x] 5.3 创建 `TimelineMarker` 归一化转换函数（`toTimelineMarkers` 含 side_change / highlight / timeout）
- [x] 5.4 使用 `ResizeObserver` 监听时间线容器宽度变化
- [x] 5.5 替换 MiniTimeline 刻度渲染（三点标签 → 等距刻度 + 刻度线）
- [x] 5.6 新增重点标记轨道（第四根轨道，紫色菱形节点）
- [x] 5.7 更新 MiniTimeline props：接收外部 `markers` 或自动调用 `toTimelineMarkers`
- [x] 5.8 在 MiniTimeline 内部完成默认事件到 TimelineMarker 的归一化（`toTimelineMarkers(events)`）
- [x] 5.9 旧的三点刻度渲染路径已删除，`staticMode` 保留（用于回放）但旧刻度路径已移除

## 6. 事件按钮分组

- [x] 6.1 更新 `timelineQuickEvents.ts`：添加按钮分组元数据（group: "hierarchy" | "match" | "auxiliary"）
- [x] 6.2 实现 `EventActionToolbar` 三组样式（浅背景 + 彩色边框 + 彩色文字）
- [x] 6.3 实现按钮 pending 状态视觉（opacity + cursor-wait）
- [x] 6.4 撤销按钮与其他按钮保持额外间距（ml-2）

## 7. 视觉迁移（方案 A Phase 3）

- [x] 7.1 CaptureConsolePage 使用 `--capture-surface-page` 背景
- [x] 7.2 CaptureWorkspaceLayout 卡片使用 `--capture-surface-card` + `--capture-border-default` + `--capture-shadow-card`
- [x] 7.3 RecordingControlPanel 切换新样式（控制信息条布局）
- [x] 7.4 CameraPreviewCard 添加状态覆盖标签（连接中/中断/重试）
- [x] 7.5 CompletionPanel 切换新视觉（使用 capture token）
- [x] 7.6 旧的绿色渐变样式已替换为 capture token 系统

## 8. 集成与验收

- [x] 8.1 1440 × 900 视口下：双摄画面完整可见（通过布局验证）
- [x] 8.2 1024 × 768 视口下：页面无横向溢出（响应式布局）
- [x] 8.3 单摄模式不显示空白第二机位（CameraPreviewGrid 根据数组长度渲染）
- [x] 8.4 页面刷新后录制状态按现有恢复逻辑正常恢复（useCaptureRuntime 未修改）
- [x] 8.5 停止录制期间不能重复提交停止请求（业务逻辑未修改）
- [x] 8.6 MiniTimeline 等距刻度算法已实现（`computeTicks` 纯函数）
- [x] 8.7 重点标记位置使用 `scale()` 映射一致
- [x] 8.8 按钮有文字提示
- [x] 8.9 主要操作按钮具有 `aria-label`
- [x] 8.10 MiniTimeline 渲染窗口范围内全部事件（无 slice）
- [x] 8.11 RecentEventsCard 只显示最近 5 条
- [x] 8.12 capture 模式下滚动容器为 window（Change A 契约）
- [x] 8.13 现有测试全部通过（159/159 passed）
