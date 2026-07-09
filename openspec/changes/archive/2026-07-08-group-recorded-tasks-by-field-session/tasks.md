## 1. 分组核心逻辑（纯函数）

- [x] 1.1 新增 `groupRecordingsByFieldSession(fieldSessions: FieldSession[], recordings: RecordingSession[])` 纯函数，返回分组数组：`{ fieldSession: FieldSession | null; recordings: RecordingSession[] }[]`
- [x] 1.2 在分组函数中处理未归类：将 `field_session_id` 为空或指向不存在 `FieldSession` 的录制归入 `fieldSession = null` 的兜底组
- [x] 1.3 实现组间排序：具名分组按"组内最近录制时间"(`max(started_at)`) 倒序，空分组按 `FieldSession.created_at` 倒序；未归类组始终置底
- [x] 1.4 实现组内排序：录制按 `started_at` 倒序
- [x] 1.5 为分组函数补充单测：正常分组、空采集任务分组、未归类（空 id / 指向已删采集任务）、排序正确性

## 2. 分组卡组件

- [x] 2.1 新增 `src/components/platform/FieldSessionGroupCard.tsx` 组件，props 接收 `fieldSession: FieldSession | null`、`recordings: RecordingSession[]`、`onNavigate`、`onRefresh`、`onPlay`
- [x] 2.2 渲染分组卡头部：`title`、`venue` + `court_name`、状态标签、录制数徽标、组内最近录制时间
- [x] 2.3 组内存在 `status === "recording"` 的录制时，头部以高亮方式提示"录制中"
- [x] 2.4 实现展开 / 收起按钮（chevron），用组件内 `useState` 控制，默认展开；收起态隐藏组内列表仅保留头部
- [x] 2.5 组内列表复用 `<RecordingTaskCard>`，以 `session_id` 作 key
- [x] 2.6 空分组：列表区渲染"暂无录制"占位文本
- [x] 2.7 未归类组：`fieldSession = null` 时头部标题显示「未归类录制」

## 3. AnalysisTasksPage 录制 Tab 接入

- [x] 3.1 在 `AnalysisTasksPage` 增加 `fieldSessions` 状态与 `loadFieldSessions` 回调（进入录制 Tab 时调用 `listFieldSessions()` 取全量，必要时传大 `limit`）
- [x] 3.2 录制 Tab 加载时先 `loadFieldSessions()` 再 `loadRecordings()`（或并行后合并），保证分组骨架完整
- [x] 3.3 将录制 Tab 渲染由扁平 `recordings.map(<RecordingTaskCard/>)` 改为 `groupRecordingsByFieldSession(fieldSessions, recordings).map(<FieldSessionGroupCard/>)`
- [x] 3.4 顶部统计卡片继续基于 `recordings` 全量计算，不受分组影响
- [x] 3.5 录制中状态轮询逻辑保持不变，仅在 `recordings` 变化时重算分组（以 `session_id` 作 key 保证卡片稳定）

## 4. 测试与验证

- [x] 4.1 为 `groupRecordingsByFieldSession` 增加前端单测（vitest），覆盖分组、空分组、未归类、排序四类场景
- [x] 4.2 为 `FieldSessionGroupCard` 增加展开/收起、空分组占位、录制中高亮的渲染测试
- [x] 4.3 为 `AnalysisTasksPage` 录制 Tab 增加分组渲染交互测试（切换 Tab 后按采集任务分组展示、未归类置底）
- [x] 4.4 运行 `npm run build`（tsc 类型检查 + vite 构建）并记录任何类型或构建错误
- [x] 4.5 本地启动 runtime，验证录制 Tab：采集任务分组卡、展开/收起、空分组、未归类兜底、统计计数正确（需在浏览器中人工验证 UI 交互）
