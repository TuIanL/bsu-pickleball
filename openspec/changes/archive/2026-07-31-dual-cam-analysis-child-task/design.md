## Context

当前系统的双摄录制（`SyncRecordingSession`）在停止合并完成后，`registered_video_ids` 内同时保存了 cam_1 与 cam_2 两路视频 ID，但 `default_analysis_video_id` 仅指向 cam_1，UI 也仅暴露 cam_1 的「分析 A 机位」按钮。从录制发起分析仍需经过完整的 `NewAnalysisPage`（8 个字段表单 + 四角标定），录制端已填写的场地、帧率、角度等元数据被浪费。侧边栏的导航标签与目标路径颠倒——"分析任务"指向了 `/capture`（录制管理），"视频管理"指向了 `/analysis/tasks`（真实分析列表）。

## Goals / Non-Goals

**Goals:**
- 双摄录制合并完成后，cam_1 和 cam_2 均可独立发起分析。
- 录制→分析链路不再经过 `NewAnalysisPage`，改为迷你配置面板——仅做四角标定，元数据从录制继承且只读。
- 分析任务与录制 session 建立父子归属关系（`recording_session_id`），任务列表可过滤查询。
- 修复侧边栏导航标签与路径的对应关系。
- 清理死代码（`TasksPage.tsx`、`UploadModePage.tsx`），统一默认帧率为 60fps。

**Non-Goals:**
- 不改变纯文件上传分析路径（`/analysis/new` 仍走 `NewAnalysisPage`）。
- 不将 `AnalysisTasksPage` 的 3 tab 拆为独立路由。
- 不统一 11 个分析入口的文案。
- 不实现「单任务多视频」分析（两路合进一个 job）；此 change 仍保持「每路一个独立 job」。
- 不修改 `SyncRecordingSession` 的 `default_analysis_video_id` 字段（保持向后兼容）。

## Decisions

### D1: 录制→分析迷你面板作为独立页面

路由 `/capture/:sessionId/analyze?cam=cam_1`，新组件 `RecordingAnalyzePage`。

**替代方案**：a) 嵌入录制任务卡片内的 inline modal；b) 改造 `NewAnalysisPage`，当来源为 recording 时渲染简化模式。驳回理由：a) 标定需要大画布交互，modal 局促；b) 会使 NMAP 的条件分支更复杂。独立页面路由清晰，与 `CaptureConsolePage`（`/capture/:sid`）命名空间一致。

### D2: 儿子任务归属用 metadata 字段，不需新表

`AnalysisUploadMetadata.recording_session_id` 已存在。新增 `camera_slot: "cam_1" | "cam_2"` 字段；后台 `GET /api/analysis/jobs?recording_session_id=<sid>` 支持过滤。

**替代方案**：新建 `analysis_job_parent` 关联表。驳回理由：父子关系量级小、不跨实体 join，加字段的改动成本最低，且录制卡片只展示"本 session 派生的 jobs"，无需跨表查询。

### D3: 抽出共享的四角标定组件 `<CourtCornerCalibrator />`

从 `NewAnalysisPage`（~300 行内联标定逻辑）抽出，同时供 `RecordingAnalyzePage` 使用。

**Props 设计**：
- `videoSrc: string`（视频流 URL）
- `onComplete: (calibrationId: string, points: CalibrationPointDraft[]) => void`
- `onCancel: () => void`
- `initialPoints?: CalibrationPointDraft[]`（自动标定结果回填）
- `autoCalibrate?: (videoId: string) => Promise<AutomaticCalibrationResponse>`（自动标定回调，双页面共用同一 client 函数）

### D4: 元数据只读的交互载体

`RecordingAnalyzePage` 顶部 banner 展示录制信息卡（场地、日期、帧率、格式、角度、机位），纯展示无 input。`AnalysisUploadMetadata` 的 8 个字段表在迷你面板中不渲染。分析任务创建时从录制 session 数据直取快照，不依赖脆弱的 `getRecording()` 网络回退。

### D5: 分析创建调用链

`RecordingAnalyzePage` 内 `onComplete` → `POST /api/analysis/jobs { videoId, calibrationId, metadata: { ...录制服照 }, recording_session_id, camera_slot }` → 跳转 `/analysis/<jobId>`。

不需要额外 API：calibrationId 来自面板内标定流程的产物，videoId 来自路由 `cam` 参数对应的 `registered_video_ids[role]`。

### D6: 默认 fps 修正

`NewAnalysisPage.sourceFps` 默认值从 30 改为 60（录制端默认也是 60）。

## Risks / Trade-offs

- **[风险] 双摄未合并完成时 A/B 按钮误触**：合并未完成时 `registered_video_ids` 可能为空或只有部分。→ 按钮在 `merge_status !== "success"` 时 disabled，tooltip 提示"请先合并片段"。
- **[风险] cam_2 分析所需的 video 流已注册但调用方不知道**：`GET /api/sync-recordings/:id` 返回的 `registered_video_ids` 已包含两路 ID，前端可从中取 cam_2 的 ID 直接用。→ 确认接口返回值完整性。
- **[风险] `<CourtCornerCalibrator />` 组件抽出引入回归**：`NewAnalysisPage` 的标定逻辑集成了自动标定 + 手动点选 + 空白帧跳过等边缘逻辑。→ 抽出时保留所有现有分支，`NewAnalysisPage` 改用组件后验证"纯文件上传→分析"全链路。
