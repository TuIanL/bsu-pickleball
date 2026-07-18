## MODIFIED Requirements

### Requirement: MiniTimeline 平滑滚动视口

系统 SHALL 使用容器宽度的等距整洁刻度替代三点标签。

**变更**：不改滚动窗口逻辑，但刻度渲染从三点标签改为等距整洁刻度。

**修改前**：时间刻度显示 3 个窗口边界标签（`windowStart`、中点、`windowEnd`），值可能为任意 ms 值（如 `0:12`、`0:57`、`1:42`）。

**修改后**：时间刻度 SHALL 使用容器宽度的等距整洁刻度。刻度值 SHALL 为整齐时间值（如 `0:00`、`0:30`、`1:00`）。

#### Scenario: 刻度计算

- **WHEN** MiniTimeline 渲染或容器宽度变化
- **THEN** 系统 SHALL 根据容器宽度和目标最小标签间距计算刻度数量
- **AND** 系统 SHALL 从整洁步长列表中选择最合适的步长
- **AND** 步长列表 SHALL 包含从 1s 到 12h 的覆盖（含 2h/3h/6h/12h 兜底）
- **AND** 系统 SHALL NOT 在窗口起点 > 0 时补非整洁刻度（除非首个刻度距离起点 > 36px）
- **AND** 刻度算法 SHALL 为纯函数，位于独立文件（如 `timelineScale.ts`）
- **AND** 系统 SHALL 使用 `ResizeObserver` 观察容器宽度（而非 window resize）
- **AND** 容器宽度 ≤ 0 或窗口长度 < 1000ms 时 SHALL 返回空列表
- **AND** 组件卸载时 SHALL disconnect ResizeObserver

#### Scenario: 刻度渲染

- **WHEN** 刻度列表生成
- **THEN** 每个刻度 SHALL 显示时间标签和对齐的浅灰色竖线
- **AND** 刻度 SHALL 不随播放头移动
- **AND** 刻度 SHALL 相对视口窗口固定

### Requirement: 重点标记轨道

系统 MUST 在 MiniTimeline 中新增重点标记独立轨道。

**变更**：新增第四根轨道显示重点标记。

**修改后**：MiniTimeline SHALL 在盘/局/分轨道下方显示重点标记轨道。

#### Scenario: 轨道渲染

- **WHEN** 存在 highlight 标记事件
- **THEN** MiniTimeline SHALL 显示"标记"轨道
- **AND** 轨道颜色 SHALL 为紫色（`var(--timeline-highlight)`）
- **AND** 每个标记 SHALL 显示为紫色菱形节点
- **WHEN** 没有 highlight 标记事件
- **THEN** "标记"轨道 SHALL 不渲染

### Requirement: TimelineMarker 归一化

系统 MUST 使用归一化 TimelineMarker 类型替代原始事件类型。

**变更**：MiniTimeline 不再直接解释业务事件类型。

**修改后**：MiniTimeline SHALL 接收归一化的 `TimelineMarker[]`，不直接处理 `SessionTimelineEvent` 类型。

#### Scenario: 标记归一化

- **WHEN** LiveCodingPanel 将事件数据传递给 MiniTimeline
- **THEN** 上层 SHALL 先将 `SessionTimelineEvent` 转换为 `TimelineMarker[]`
- **AND** `TimelineMarker` SHALL 包含 `id`、`timestampMs`、`track`、`label`、`pending`、`failed`
- **AND** `track` SHALL 为 `"highlight"` | `"side_change"` | `"timeout"` 联合类型
- **AND** MiniTimeline SHALL 只根据 `track` 值决定渲染样式，不关心原始事件类型
- **AND** 映射规则 SHALL 为：
  - `event_type === "side_change"` → `track: "side_change"`
  - `event_type === "add_note" && highlight === true` → `track: "highlight"`
  - `event_type === "session_note" && highlight === true` → `track: "highlight"`
  - `event_type === "non_play_start" && intermission_kind === "timeout"` → `track: "timeout"`

### Requirement: 事件按钮分组

系统 MUST 将事件按钮分为三组视觉分隔。

**变更**：事件按钮从平铺彩色 pills 改为三组视觉分隔。

#### Scenario: 按钮分组样式

- **WHEN** LiveCodingPanel 渲染事件按钮
- **THEN** 按钮 SHALL 分为三组：层级事件（盘/局/分）、比赛状态（换边/暂停/恢复）、辅助事件（重点标记/备注/撤销）
- **AND** 组间 SHALL 有明确间距分隔
- **AND** 每组 SHALL 有组标签标识
- **AND** 所有按钮 SHALL 统一高度（34—38px）和圆角（8px）
- **AND** 盘/局/分按钮分别使用橙色/蓝色/绿色系
- **AND** 撤销按钮 SHALL 使用红色系，与其他按钮保持额外间距
- **AND** 按钮样式 SHALL 使用浅背景 + 彩色边框 + 彩色文字，非实心高饱和色

## ADDED Requirements

### Requirement: 按钮 pending / 失败状态

系统 MUST 为事件按钮提供 pending 和失败状态的视觉反馈。

#### Scenario: pending 状态

- **WHEN** 事件正在通过 Outbox 同步
- **THEN** 按钮 SHALL 显示为 pending（降低透明度 + 禁用点击）
- **AND** 同步完成后 SHALL 移除 pending 状态

#### Scenario: 同步失败

- **WHEN** 事件同步失败
- **THEN** 按钮 SHALL 显示错误标记
- **AND** 系统 SHOULD 提供重试入口
