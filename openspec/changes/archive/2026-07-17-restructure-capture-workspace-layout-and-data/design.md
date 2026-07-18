## Context

当前 CaptureConsolePage 在 1440×900 下首屏只能看到标题、控制条和摄像机画面，事件按钮和时间线需要滚动。单摄模式右侧空白约 400px。侧边栏时钟与主页面时钟偏差可达数小时。多个 UI 字段显示 `-` 或无真实数据。

## Goals / Non-Goals

**Goals:**
- 1440×900 首屏可见：摄像机 + 比分 + 事件按钮 + 紧凑时间线
- 单摄/双摄两套独立布局，消除单摄空列
- 侧边栏与主页面时钟完全一致（使用同一口径 `Date.now() - Date.parse(startedAt)`，不引入 serverNow 偏移）
- 隐藏所有无真实数据来源的指标
- 系统状态只显示 Outbox 同步，其余不渲染
- 事件名使用中文 + segment ordinal

**Non-Goals:**
- 不修改业务 hooks 的核心逻辑（useCaptureRuntime / useLiveCoding / useCameraSetup）
- 不修改后端录制/停止/恢复等业务流程
- 不做手机端适配
- 不做 MiniTimeline 的缩放编辑器

## Decisions

### D1: 统一时钟纯函数（修正）

```ts
// captureClock.ts — 与 timelineScale.ts 分离
export function computeCaptureElapsedMs(
  startedAt: string,
  clientNowMs = Date.now(),
): number {
  const startedMs = Date.parse(startedAt);
  if (!Number.isFinite(startedMs)) return 0;
  return Math.max(0, clientNowMs - startedMs);
}
```

**不使用 serverNow 参数**。两边完全相同的 `Date.now() - Date.parse(startedAt)` 口径。`serverNow` 仅用于后端诊断，不参与前端计时计算。

前提：后端 `startedAt` 输出明确带时区的 ISO 8601，前端 `Date.parse` 按 UTC 解析。

### D2: 后端时间戳契约（修正）

不直接使用 `dt.replace(tzinfo=utc)`。使用安全函数：

```python
from datetime import datetime, timezone

def ensure_utc(value: datetime) -> datetime:
    """确保 datetime 带 UTC 时区信息。"""
    if value.tzinfo is None:
        # 数据库约定：所有 naive datetime 均表示 UTC
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
```

修改范围收口为本页面使用的字段：
- `GET /api/capture-takes/active` 响应中的 `startedAt` 和 `serverNow`
- 录制启动响应中的 `started_at`
- 不上溯到 CaptureTake 模型全量输出

### D3: 固定紧凑 Header（修正——不再动态合并）

RecordingControlPanel 不根据指标有无动态合并。直接设计固定紧凑 Header：

```
┌──────────────────────────────────────────────────────┐
│ 记分比赛 · 单打        ● 录制中 00:35     [停止][设备]│
└──────────────────────────────────────────────────────┘
```

停止按钮永远在右上角固定位置。如果以后有真实帧率/码率/文件大小指标，再在 Header 下方增加可选指标行 `OptionalMetricsStrip`。

RecordingControlPanel 组件保留，但在本 Change 中直接内联进 Header（指标全部 unsupported 时不显示额外行）。

### D4: 单摄布局（修正——直接渲染 CameraPreviewCard）

```tsx
{isDualMode ? <DualCameraWorkspace /> : <SingleCameraWorkspace />}
```

`SingleCameraWorkspace`：

```tsx
<div className="grid min-w-0 gap-4 lg:grid-cols-[minmax(0,1fr)_300px]">
  <CameraPreviewCard vm={cameraVms[0]} />
  <aside className="flex flex-col gap-3 self-stretch">
    <ScoreBoard liveState={...} />
    <CameraInfoCard camera={cameraVms[0]} />
  </aside>
</div>
```

单摄画面高度限制：

```css
.single-camera-preview {
  width: 100%;
  height: clamp(320px, 42vh, 430px);
}
```

不经过 `CameraPreviewGrid`，避免旧 grid 布局残留。

`CameraInfoCard`：摄像机名称、分辨率/帧率、设备入口。摄像头 `<select>` 迁入设备抽屉。

### D5: 双摄布局

```tsx
<div className="grid grid-cols-2 gap-4">
  <CameraPreviewCard vm={cam1} />
  <CameraPreviewCard vm={cam2} />
</div>
<CompactScoreStrip liveState={...} />
```

`CompactScoreStrip`：56-72px，横向比分条，从左到右：盘局 | A比分:B比分 | 发球方 | 当前状态。

双摄预览 `max-height: 330px`。

### D6: 紧凑时间线与时间窗口分离（修正）

状态分离：

```ts
type TimelineWindowMode = "full" | "recent";
type TimelineDensity = "compact" | "expanded";
```

默认规则：录制时长 ≤ 5 分钟 → `full`，> 5 分钟 → `recent`（最近 5 分钟）。

UI：

```
[全场 | 最近 5 分钟]     [展开时间线 | 收起时间线]
```

MiniTimeline 新增 `compact` prop（轨道高度 18px、间距 4px）。

LiveCodingPanel 标题栏显示 Outbox 同步状态，不再独立成卡：

```
事件标注时间线                    ● 已同步
```

### D7: 事件中文映射（修正——完整覆盖）

纯函数 `formatTimelineEventLabel(event, segments)`：

```ts
const EVENT_LABELS: Record<string, string> = {
  set_start: "盘开始", set_end: "盘结束",
  game_start: "局开始", game_end: "局结束",
  rally_start: "分开始", rally_end: "分结束",
  non_play_start: "进入非比赛时间", non_play_end: "恢复比赛",
  side_change: "换边", add_note: "重点标记",
  timeout_start: "战术暂停", timeout_end: "暂停结束",
  score_update: "比分修正", undo: "撤销",
  session_note: "备注",
  rally_replay: "重打",
  rally_result_a: "A方得分", rally_result_b: "B方得分",
};
```

处理链：
1. `event.label` 存在且是用户自定义标签 → 使用
2. 有 `segment_id` → 查找 segment ordinal → `第 ${ordinal} 分开始`
3. 无 segment 关联 → 按 `timestamp_ms` 匹配对应区间的 segment → 获取 ordinal
4. 回退 → EVENT_LABELS 中查找中文
5. 最后回退 → 原始 `event_type`（仅调试用）

### D8: 第二屏精简

BottomRow 从 3 栏缩减为 2 栏：

```
最近事件 | 快捷操作
```

同步状态移入 LiveCodingPanel 标题栏。系统状态卡片删除。

QuickActions 使用 Lucide 图标，只保留真实操作：
- 重点标记（`Flag`）
- 打开设备（`Camera`）
- 快捷键（`Keyboard`）

### D9: CameraPreviewCard 状态标签增强

已有逻辑不变，补充：
- 分辨率/帧率覆盖标签（右上角，有数据才显示）
- 录制时间覆盖标签（左下角）
- 异常状态覆盖（连接中/中断/重试）

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| 后端时间戳修改影响范围超出预期 | 只修改当前页面使用的接口字段，不上溯模型层 |
| 单摄 `clamp` 高度在极端宽高比下裁切画面 | 使用 `object-fit: contain` 配合 `background: var(--capture-surface-video)` |
| 紧凑时间线在事件密集时可读性下降 | 提供「展开」切换到 `expanded` 密度 |
| 时钟统一后若 `startedAt` 解析失败 | `Number.isFinite` 防卫返回 0 |
