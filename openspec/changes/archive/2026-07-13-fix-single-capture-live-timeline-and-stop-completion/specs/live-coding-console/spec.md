## MODIFIED Requirements

### Requirement: 录制中实时时间线视图

**变更**：替换 `CaptureConsolePage` 中时间戳胶囊占位为真正的 `MiniTimeline` 组件。

**修改前**：`CaptureConsolePage` 在录制阶段将最近 20 条事件渲染为时间戳芯片，不显示区间增长、非比赛时段叠加或分层轨道。

**修改后**：CaptureConsolePage SHALL 在 `recording` 和 `stopping` 阶段渲染 `<MiniTimeline>` 组件。
- MiniTimeline SHALL 显示盘/局/分三层区间轨道
- MiniTimeline SHALL 显示非比赛时段（回合间、暂停、换边）叠加层
- MiniTimeline SHALL 显示换边和重点标记
- MiniTimeline SHALL 显示实时播放头
- MiniTimeline SHALL 使用 `segments`、`events`、`liveState` 和 `elapsedMs` 作为数据源

### Requirement: 事件写入唯一入口

**变更**：`addTimelineEvent` 不再直接调用 `createTimelineEvent` API，仅通过 Outbox 写入。

**修改前**：按钮点击 → 创建 Outbox item → enqueue → 直接调用 `createTimelineEvent` → Outbox sender flush。同一事件可能产生两条 DB 记录。

**修改后**：按钮点击 → 创建 Outbox item → enqueue → Outbox sender 通过 `coding-actions` 接口发送 → 响应更新 `events`/`segments`/`liveState`。SHALL 不再直接调用 `POST /api/field-sessions/{id}/timeline-events`。
