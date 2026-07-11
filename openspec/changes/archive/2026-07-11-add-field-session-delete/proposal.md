## Why

用户在当前页面无法删除大采集任务（Field Session），需要先进入采集控制台才能操作。`/capture` 首页和 `/tasks` 任务管理页缺少删除入口，导致工作流不顺畅。

## What Changes

- **CaptureHomePage** (`/capture`): 每张采集任务卡片上增加删除按钮
- **FieldSessionGroupCard** (`/tasks` 的「录制视频」Tab): 分组卡片头部增加删除当前采集任务的按钮
- 删除前弹出确认框，删除后自动刷新列表
- 后端已保护有录制/时间线事件的 session，返回 `blocked` 状态，前端需要展示提示

## Capabilities

### New Capabilities

- `field-session-delete`: 在前端两个页面提供大采集任务的删除功能，复用后端已有的 `DELETE /api/field-sessions/{id}` 接口

### Modified Capabilities

- 无

## Impact

- `src/pages/CaptureHomePage.tsx` — 增加删除按钮和处理器
- `src/components/platform/FieldSessionGroupCard.tsx` — 增加 `onDeleteFieldSession` prop 和删除按钮
- `src/App.tsx` — 为 `FieldSessionGroupCard` 传入删除回调
