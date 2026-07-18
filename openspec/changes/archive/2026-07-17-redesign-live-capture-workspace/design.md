## Context

CaptureConsolePage 743 行单体，内联 5 个主要渲染函数。MiniTimeline 时间刻度只显示 3 个标签。事件按钮为平铺彩色 pills，无视觉分组。页面使用绿色渐变背景，信息层级不清晰。

本 Change 依赖 Change A（`add-app-sidebar-and-active-capture-presence`）提供的 AppShell capture mode，确保 CaptureWorkspaceLayout 在无全局 header/footer 的环境中使用。

## Goals / Non-Goals

**Goals:**
- CaptureConsolePage 按方案 A 重构为 CaptureWorkspaceLayout + 子组件
- ViewModel 模式：页面层构造 ViewModel，子组件只消费自己的片段
- MiniTimeline 支持容器宽度感知的等距刻度算法
- MiniTimeline 新增重点标记轨道，使用归一化 TimelineMarker
- 事件按钮按三组视觉分组
- CSS Variables 定义完整视觉 Token
- 健康指标卡片使用真实数据或 skeleton/隐藏状态

**Non-Goals:**
- 不修改现有业务 hooks（useCaptureRuntime / useCameraSetup / useLiveCoding / useCapturePreflight）
- 不修改事件语义、后端 API 或数据模型
- 不做手机端适配（仅保证 1024px+ 可用）
- 不做复杂时间线缩放编辑器

## Decisions

### D1: 方案 A 实施策略

三阶段递进，每阶段可独立验证：

```
┌─────────────────────────────────────────────────────────┐
│ Phase 1: 骨架优先                                        │
│ 1. 创建 CaptureWorkspaceLayout（空骨架 + slot 定义）      │
│ 2. 把现有顶级 div 替换为骨架                              │
│ 3. 内联渲染函数原封不动移入对应 slot                       │
│ 4. 验证：所有功能正常                                      │
├─────────────────────────────────────────────────────────┤
│ Phase 2: 提取组件                                         │
│ 1. CameraPreviewCard + CameraPreviewGrid                  │
│ 2. RecordingControlPanel                                  │
│ 3. LiveCodingPanel (EventActionToolbar + CaptureTimeline) │
│ 4. RecentEventsCard / CaptureHealthCard / QuickActionsCard│
│ 5. DeviceDrawer / CompletionPanel                         │
│ 6. 每步验证功能无回归                                      │
├─────────────────────────────────────────────────────────┤
│ Phase 3: 视觉迁移                                         │
│ 1. 引入 CSS Variables 取代 hard-coded 颜色                 │
│ 2. 页面底色 → #F7F8FA                                     │
│ 3. 逐个组件切换白卡片 + 新阴影 + 新间距                    │
│ 4. 事件按钮三组样式统一                                    │
│ 5. 相机预览状态覆盖标签                                    │
└─────────────────────────────────────────────────────────┘
```

### D2: ViewModel 模式

CaptureWorkspaceLayout 是纯布局组件——只负责 CSS Grid、间距、区域容器。不接收整个 ViewModel。

页面层（CaptureConsolePage 缩减版）负责组合 hooks、构造 ViewModel、传递语义回调和子组件：

```tsx
function CaptureConsolePage({ sessionId, onNavigate }: Props) {
  // Hooks 保持原样
  const runtime = useCaptureRuntime({ ... });
  const cameraSetup = useCameraSetup({ ... });
  const liveCoding = useLiveCoding({ ... });

  // 构造 ViewModel 片段
  const headerVm = useMemo(() => toHeaderVM(/*...*/), [/*...*/]);
  const cameraVms = useMemo(() => cameraSetup.previewTracks.map(toCameraPreviewVM), [cameraSetup.previewTracks]);
  const recordingVm = useMemo(() => toRecordingVM(runtime), [runtime]);
  const codingVm = useMemo(() => toCodingVM(liveCoding), [liveCoding]);
  // ...

  return (
    <CaptureWorkspaceLayout>
      <CaptureWorkspaceHeader vm={headerVm} onStoragePick={handlePickStorage} />
      <CameraPreviewGrid cameras={cameraVms} />
      <RecordingControlPanel vm={recordingVm} onStop={handleStop} onPause={handlePause} />
      <LiveCodingPanel vm={codingVm} onAction={handleCodingAction} />
      <BottomRow>
        <RecentEventsCard events={recentEventVms} />
        <CaptureHealthCard metrics={healthMetrics} />
        <QuickActionsCard actions={quickActions} />
      </BottomRow>
    </CaptureWorkspaceLayout>
  );
}
```

CaptureWorkspaceLayout 只接收子组件（children），不接收 ViewModel 和回调。每个子组件只消费自己的 ViewModel 片段。

ViewModel 中所有不确定的健康指标使用显式联合：

```ts
type MetricValue<T> =
  | { state: "ready"; value: T; label: string }
  | { state: "loading" }
  | { state: "unsupported" }
  | { state: "error"; message?: string };
```

例如：

```ts
interface RecordingControlViewModel {
  elapsedMs: number;
  fileSize: MetricValue<number>;
  fps: MetricValue<number>;
  bitrate: MetricValue<number>;
}

interface CaptureHealthViewModel {
  encoding: MetricValue<"ok" | "error">;
  storage: MetricValue<{ used: number; total: number }>;
  network: MetricValue<"connected" | "disconnected">;
  sync: MetricValue<"synced" | "pending" | "failed">;
}
```

QuickActionsCard 的每个操作必须映射到现有真实回调：

| 操作 | 真实回调 |
|------|----------|
| 重点标记 | `liveCoding.addTimelineEvent({ type: "add_note", payload: { highlight: true } })` |
| 打开设备抽屉 | setDrawerOpen(true) |
| 撤销上一步 | `liveCoding.addTimelineEvent({ type: "undo" })` |
| 查看全部事件 | `onNavigate` 跳转 |

禁止渲染无行为的占位按钮（如"截图保存"、"静音"）。

### D3: 组件树

```
CaptureWorkspaceLayout
├── CaptureWorkspaceHeader (title + status + storage)
├── CameraPreviewGrid
│   └── CameraPreviewCard[] (aspect-ratio 16/9, status overlay)
├── RecordingControlPanel (duration, fileSize, controls, fps, bitrate)
├── LiveCodingPanel
│   ├── EventActionToolbar (3 groups + undo)
│   ├── CaptureTimeline
│   │   ├── TimelineTrack (set/game/rally + highlight)
│   │   ├── TimelineRange (non-play overlays)
│   │   ├── TimelineMarker (normalized: highlight/side_change/timeout)
│   │   └── TimelinePlayhead
│   └── TimelineControls (zoom toggle: full/recent)
├── BottomRow
│   ├── RecentEventsCard
│   ├── CaptureHealthCard
│   └── QuickActionsCard
├── DeviceDrawer (slide-in, parsed as portal)
└── CompletionPanel (modal/inline)
```

### D4: MiniTimeline 等距刻度算法

刻度计算为纯函数，位于独立文件 `timelineScale.ts`：

```ts
interface TimelineTick {
  label: string;     // "0:00", "0:30", "1:00"
  positionPct: number;  // 0–100
}

const NICE_STEP_MS = [
  1_000, 2_000, 5_000,
  10_000, 15_000, 30_000,
  60_000, 120_000, 300_000,
  600_000, 900_000, 1_800_000,
  3_600_000, 7_200_000, 10_800_000,
  21_600_000, 43_200_000,
];

function computeTicks(
  windowStartMs: number,
  windowEndMs: number,
  containerWidthPx: number,
  minLabelSpacingPx = 72,
): TimelineTick[] {
  const duration = windowEndMs - windowStartMs;
  const targetCount = Math.max(2, Math.floor(containerWidthPx / minLabelSpacingPx));
  const stepMs = NICE_STEP_MS.find(s => duration / s <= targetCount) ?? NICE_STEP_MS.at(-1)!;
  const firstTick = Math.ceil(windowStartMs / stepMs) * stepMs;
  const ticks: TimelineTick[] = [];
  for (let t = firstTick; t <= windowEndMs; t += stepMs) {
    ticks.push({ label: formatDuration(t), positionPct: scale(t) });
  }
  return ticks;
}
```

关键行为：
- 覆盖窗口长度为 0、不足 1 秒、超过 1 小时的情况
- 在窗口起点 > 0 且首个刻度与起点太近（< 36px）时，不补非整洁刻度
- 使用 `ResizeObserver` 观察时间线容器自身宽度变化（而非 window resize），覆盖 sidebar 折叠、drawer 打开等非窗口级的宽度变化
- `containerWidthPx <= 0` 或 `windowEndMs <= windowStartMs` 或 `duration < 1000ms` 时返回空列表
- 组件卸载时 disconnect ResizeObserver

### D5: TimelineMarker 归一化

MiniTimeline 不再直接接收 `SessionTimelineEvent[]` 中的事件类型来判断标记。改为接收归一化后的 `TimelineMarker[]`：

```ts
interface TimelineMarker {
  id: string;
  timestampMs: number;
  track: "highlight" | "side_change" | "timeout";
  label?: string;
  pending?: boolean;
  failed?: boolean;
}
```

三种标记类型的映射规则：

| 原始事件 | TimelineMarker track |
|----------|---------------------|
| `event_type === "side_change"` | `"side_change"` |
| `event_type === "add_note" && highlight === true` | `"highlight"` |
| `event_type === "session_note" && highlight === true` | `"highlight"` |
| `event_type === "non_play_start" && intermission_kind === "timeout"` | `"timeout"` |

注意 `session_note` 也可能携带 highlight 标记，纳入处理。如果当前后端没有稳定的 timeout 事件，track 中保留 `"timeout"` 类型但不产生映射（做好基础设施，后端支持后即生效）。

归一化由 LiveCodingPanel 或 CaptureTimeline 层完成：

```ts
function toTimelineMarkers(events: SessionTimelineEvent[]): TimelineMarker[] {
  return events
    .filter(e => e.event_type === "side_change"
      || (e.event_type === "add_note" && e.payload_json?.highlight === true)
      || (e.event_type === "session_note" && e.payload_json?.highlight === true)
      || (e.event_type === "non_play_start" && e.payload_json?.intermission_kind === "timeout"))
    .map(e => {
      let track: TimelineMarker["track"];
      if (e.event_type === "side_change") track = "side_change";
      else if (e.event_type === "non_play_start") track = "timeout";
      else track = "highlight";
      return { id: e.id, timestampMs: e.timestamp_ms, track, label: e.note ?? e.label };
    });
}
```

未来增加新标记类型只需扩展 `TimelineMarker.track` 联合类型。

### D6: CSS Variables 视觉系统

在 `:root` 中定义 Capture Workspace 范围的语义 Token，使用 `--capture-` 前缀限定作用域，避免与其他页面样式冲突：

```css
:root {
  --capture-surface-page: #f7f8fa;
  --capture-surface-card: #ffffff;
  --capture-surface-video: #101828;
  --capture-border-default: #e4e7ec;
  --capture-border-strong: #d0d5dd;
  --capture-text-primary: #182230;
  --capture-text-secondary: #475467;
  --capture-text-muted: #98a2b3;
  --capture-brand-primary: #3baa62;
  --capture-brand-soft: #eaf7ee;
  --capture-status-recording: #e5484d;
  --capture-status-success: #3baa62;
  --capture-status-warning: #f59e42;
  --capture-status-info: #4f7df3;
  --capture-timeline-set: #f08a3c;
  --capture-timeline-game: #4f7df3;
  --capture-timeline-rally: #3baa62;
  --capture-timeline-highlight: #8b5cf6;
  --capture-timeline-playhead: #e5484d;
  --capture-timeline-side-change: #ec6d9e;
  --capture-radius-sm: 8px;
  --capture-radius-md: 12px;
  --capture-radius-lg: 16px;
  --capture-shadow-card: 0 1px 2px rgba(16,24,40,0.04), 0 4px 12px rgba(16,24,40,0.03);
}
```

本 Change 只要求在 Capture Workspace 新组件中使用这些 Token，不要求其他页面迁移。未来生态成熟后可由单独的 Design System Change 推广到全站。

Tailwind 引用这些变量：

```ts
// tailwind.config.ts
colors: {
  capture: {
    surface: { page: "var(--capture-surface-page)", card: "var(--capture-surface-card)" },
    brand: { primary: "var(--capture-brand-primary)", soft: "var(--capture-brand-soft)" },
    // ...
  },
}
```

交互状态补充：`:hover`、`:active`、`:disabled`、`:focus-visible` 使用 `opacity` 或对应变量的暗色变体。

### D7: CaptureHealthCard 真实数据策略

有三种可能的数据状态：

| 状态 | 渲染 |
|------|------|
| 有可靠数据 | 显示数值 + 状态标签 |
| API 加载中 | skeleton（浅灰脉冲块） |
| 当前不支持 | 不渲染该项（非隐藏占位） |
| 错误 | 显示"暂不可用" |

禁止在正式页面中使用硬编码运行指标（如 `2.45 GB`、`8.2 Mbps`）。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| ViewModel 模式可能让页面层变厚 | ViewModel 的构造逻辑本身在 `useMemo` 中，不增加渲染成本。页面层仍然比 743 行少得多 |
| 方案 A Phase 1 中旧代码填入新骨架时布局错乱 | 先用 `max-w` 限制主区域，旧代码 CSS class 保持不动，骨架调试完成后再改样式 |
| MiniTimeline 刻度重写可能引入播放头定位回归 | 保留旧刻度路径通过 feature flag 切换，新刻度测试通过后再删除旧路径 |
| TimelineMarker 归一化增加一层数据转换 | 转换函数是纯的、可测试的，成本远低于在 MiniTimeline 中维护业务事件判断 |
| Change A 与 B 的滚动容器契约不一致导致双滚动条 | 双方约定：capture 模式下滚动容器为 window，非 shell-main 内部滚动。DeviceDrawer fixed 定位、sticky 工作台 Header、时间线宽度计算均基于此假设 |
