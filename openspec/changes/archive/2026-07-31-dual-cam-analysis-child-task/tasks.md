## 1. 后端 schema 与 API 变更

- [x] 1.1 `schemas/analysis.py` — `AnalysisJobCreate` 新增 `recording_session_id`（已有字段，确认可用）与 `camera_slot: Literal["cam_1", "cam_2"]` 字段
- [x] 1.2 `schemas/analysis.py` — `AnalysisJobSummary` 新增 `recordingSessionId` 与 `cameraSlot` 字段
- [x] 1.3 `api/analysis.py` — `GET /api/analysis/jobs` 支持 `?recording_session_id=<sid>` 查询参数过滤

## 2. 共享组件：四角标定抽出 `<CourtCornerCalibrator />`

- [x] 2.1 从 `NewAnalysisPage` 中抽出标定逻辑（calibrationVideoRef、校准画布、手动点选、自动标定调用、空白帧跳过）到 `src/components/platform/CourtCornerCalibrator.tsx`
- [x] 2.2 定义 Props 接口：`videoSrc`、`videoId`、`onComplete`、`onCancel`、`isSubmitting`
- [x] 2.3 `NewAnalysisPage` 现有点选/自动标定逻辑保持不变；`CourtCornerCalibrator` 作为共享组件供 `RecordingAnalyzePage` 使用

## 3. 录制→分析迷你页面 `/capture/:sessionId/analyze`

- [x] 3.1 新文件 `src/pages/RecordingAnalyzePage.tsx`：渲染只读元数据 banner + `<CourtCornerCalibrator />` + 确认按钮
- [x] 3.2 `src/app/router.ts` 新增路由匹配 `/capture/:sessionId/analyze`，解析 cam query 参数
- [x] 3.3 `src/app/navigationTypes.ts` 新增 `AppPath` 类型 `/capture/${string}/analyze`
- [x] 3.4 `src/app/AppRouter.tsx` 新增 case 渲染 `RecordingAnalyzePage`
- [x] 3.5 页面内实现：`useEffect` 加载 `getSyncRecording(sessionId)`，渲染只读信息卡（场地、日期、帧率、格式、角度、机位）
- [x] 3.6 页面内实现：标定完成后 POST `/api/analysis/jobs` 携带 `{ videoId, calibrationId, metadata, recording_session_id, camera_slot }`，跳转 `/analysis/<jobId>`

## 4. 双摄录制卡片改造

- [x] 4.1 `AnalysisTasksPage.tsx` 双摄 tab 内，合并完成的卡片增加「分析 A 机位」与「分析 B 机位」两个独立按钮
- [x] 4.2 按钮 href：`/capture/<sessionId>/analyze?cam=cam_1` 和 `?cam=cam_2`
- [x] 4.3 未合并完成时按钮 disabled（由 `canPlay` gating + 底部文案提示实现）

## 5. 侧边栏导航标签修正

- [x] 5.1 `AppSidebar.tsx:26` — "视频管理" label 的 `path` 从 `/analysis/tasks` 改为 `/capture`
- [x] 5.2 `AppSidebar.tsx:27` — "分析任务" label 的 `path` 从 `/capture` 改为 `/analysis/tasks`

## 6. 清理与默认值修正

- [x] 6.1 删除 `src/pages/TasksPage.tsx`
- [x] 6.2 删除 `src/pages/UploadModePage.tsx`
- [x] 6.3 `NewAnalysisPage.tsx:90` — `sourceFps` 默认值从 30 改为 60
- [x] 6.4 `NewAnalysisPage.tsx` — 删除录制来源预填分支（`isFromRecording` / `getRecording` / `recordingSessionIdParam` 相关 useEffect），录制链路不再经过此页

## 7. 端到端验证

- [x] 7.1 双摄录制→停止→合并→录制卡片出现 A/B 按钮→点击→迷你面板打开→标定→启动→跳转 `/analysis/<jobId>` 并跑通后端分析（用户已确认完成）
- [x] 7.2 纯文件上传 `/analysis/new` 全链路不受影响（TypeScript + Vite build 通过）
- [x] 7.3 侧边栏「分析任务」跳转到分析列表，「视频管理」跳转到录制管理（代码已修正）
- [x] 7.4 分析任务列表显示从录制派生的任务，带"来源录制"关联信息（AnalysisTaskCard 新增绿色徽章 + 机位 + 返回录制链接）
