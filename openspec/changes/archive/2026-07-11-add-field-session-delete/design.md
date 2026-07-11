## Context

CaptureHomePage (`/capture`) 和 AnalysisTasksPage (`/tasks` 的「录制视频」Tab) 目前都有采集任务（Field Session）的展示入口，但都没有提供删除功能。用户如果想删一个空的采集任务，需要进入采集控制台（CameraHubPage）才能操作。

后端已经实现了 `DELETE /api/field-sessions/{id}`，并在 `field_session_service.py` 中做了完善的安全检查（禁止删除 `live` 状态、有录制关联、有时间线事件的任务），返回 `FieldSessionDeleteResult`。

前端的 `deleteFieldSession(id)` 也已经在 `analysisClient.ts` 中导出，可以直接使用。

## Goals / Non-Goals

**Goals:**
- CaptureHomePage 每张任务卡片上增加删除按钮
- FieldSessionGroupCard 头部增加删除当前采集任务按钮
- 删除前用 `window.confirm` 确认
- 删除后自动刷新列表
- 后端返回 `blocked` 时展示提示

**Non-Goals:**
- 不改后端 API 逻辑
- 不改删除确认弹窗的 UI 风格（保持 `window.confirm`，与现有 `RecordingTaskCard` 一致）
- 不添加批量删除功能

## Decisions

### 1. 删除按钮位置

| 页面 | 位置 | 理由 |
|------|------|------|
| CaptureHomePage | 卡片右侧区域，在 `capture_mode` 标签后面 | 与「状态标签」平级，视觉不突兀 |
| FieldSessionGroupCard | 卡片头部右侧，在录制数量统计旁边 | 与展开/折叠按钮同一行，不干扰录制列表 |

### 2. 阻止事件冒泡

CaptureHomePage 的卡片是 `<button>`，点击触发导航到控制台。删除按钮必须用 `e.stopPropagation()` 阻止冒泡，否则点击删除会同时跳转到采集控制台。

FieldSessionGroupCard 的删除按钮在头部 `<button>` 外部（头部按钮控制展开/折叠），不存在事件冲突问题。

### 3. 确认对话框文案

沿用现有模式（参考 `RecordingTaskCard.tsx:30` 和 `App.tsx:4387`）：

```
确定删除采集任务「{title}」吗？已有录制记录或时间线事件的任务会被后端保护。
```

包含任务标题方便用户识别，提示后端保护规则减少困惑。

### 4. blocked 状态提示

后端返回 `blocked` 时携带 `detail` 字段。前端在 `console.error` 输出并在刷新后不做特殊处理（保持静默失败，与 `RecordingTaskCard` 一致）。如果后续需要更好的反馈，可以加 toast 组件。

### 5. 按钮可见性

- `live` 状态的采集任务隐藏删除按钮（后端也会拒绝，但提前隐藏 UX 更好）
- 仅 `planned`、`completed`、`archived` 显示删除按钮

## Risks / Trade-offs

| 风险 | 缓解措施 |
|------|----------|
| 用户误删重要任务 | `window.confirm` 二次确认；后端有录制/事件保护不会真正删除 |
| 删除后列表不刷新 | `loadSessions()` / `onRefresh()` 保证删除后立即重新拉取 |
| 同时点击删除和导航 | `e.stopPropagation()` 阻止事件冒泡到卡片按钮 |
