## 1. CaptureHomePage 删除功能

- [x] 1.1 在 `CaptureHomePage.tsx` 中导入 `deleteFieldSession`（来自 `../services/analysisClient`）和 `Trash2`（来自 `lucide-react`）
- [x] 1.2 在 `CaptureHomePage` 组件内添加 `handleDelete` 异步函数：`window.confirm` 确认后调用 `deleteFieldSession(id)`，成功后调用 `loadSessions()` 刷新列表，失败时静默处理
- [x] 1.3 在每张 session 卡片的右侧操作区（`capture_mode` 标签后方）添加删除按钮，用 `Trash2` 图标 + 「删除」文字，`e.stopPropagation()` 阻止事件冒泡
- [x] 1.4 删除按钮对所有状态显示（后端决定是否允许删除）；后端拒绝时 `alert` 展示错误信息

## 2. FieldSessionGroupCard 删除功能

- [x] 2.1 在 `FieldSessionGroupCard.tsx` 的 props 接口中添加 `onDeleteFieldSession?: (session: FieldSession) => void`
- [x] 2.2 在卡片头部渲染区域的右侧（录制数量统计旁边）添加删除按钮，仅 `fieldSession` 非 `null` 时显示（不按状态过滤）
- [x] 2.3 点击删除按钮调用 `onDeleteFieldSession(fieldSession)`（如果回调存在）
- [x] 2.4 在 `App.tsx` 的 `AnalysisTasksPage` 中创建删除处理器：调用 `deleteFieldSession(id)`，成功后调用 `loadFieldSessions()` + `loadRecordings()`
- [x] 2.5 将删除处理器通过 `onDeleteFieldSession` 传给 `FieldSessionGroupCard`

## 3. 后端修复：删除视频文件

- [x] 3.1 在 `session_service.py` 的 `delete_session()` 中增加删除 `session.video_path` 视频文件的逻辑

## 4. 错误提示优化

- [x] 4.1 CaptureHomePage 的 `catch` 改为 `alert` 显示后端错误信息
- [x] 4.2 App.tsx `handleDeleteFieldSession` 的 `catch` 改为 `alert` 显示后端错误信息
- [x] 4.3 两处确认对话框文案简化（不再预判后端行为）

## 5. 构建验证

- [x] 5.1 运行 Vite 构建确认无语法错误
