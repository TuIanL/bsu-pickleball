# Proposal: 删除双摄录制下的分析任务

## Why

双摄录制完成分析后，任务管理页「双摄录制」Tab 只能整条删除录制，无法单独清除录制下的分析任务及其本地产物；同时 `delete_analysis_job` 对 capture job 的磁盘清理不完整（遗留 `analysis_overlay.mp4`、`position_visualizations/`、`fused_*.json` 等产物，最多可达 GB 级）。用户需要在保留录制本身的前提下，从前端、后端与本地磁盘一并清除录制派生的分析任务。

## What Changes

- **后端新增按录制会话删除分析任务的入口**：按 `recording_session_id` 查找该录制派生的所有分析任务（multiview Parent + 单摄任务），逐个删除；multiview Parent 自动级联删除 internal child 与 fusion run 产物。**不触碰录制本身**（session JSON、双路视频、CaptureTake、`sync_calibration.json`）。
- **修复 `delete_analysis_job` 对 capture job 的磁盘清理缺口**：删除该 job 在 `take_dir/analysis/<job_id>/` 下的**完整产物目录**，补齐当前删除清单遗漏的 `analysis_overlay.mp4`、`ball_trajectory.json`、`cleaned_ball_trajectory.json`、`bounce_events.json`、`player_render_trajectory.json`、`players_trajectory.*`、`position_visualizations/`、`fused_manifest.json`、`fused_diagnostics.json`、`fused_player_trajectory.json`、`detections.jsonl` 等。
- **前端「双摄录制」Tab 新增「删除分析任务」按钮**：在 `SyncRecordingTaskCard` 上对存在分析任务的录制提供该入口；确认后调用后端接口，仅刷新任务列表，录制卡片保留。

## Capabilities

### New Capabilities

- `recording-analysis-cleanup`: 删除双摄录制下分析任务的能力——按录制会话定位任务、级联清理 Parent/child/fusion run 产物、完整清除本地磁盘、不碰录制资产。

### Modified Capabilities

- `analysis-task-management`: 任务管理页「双摄录制」Tab 的分析任务操作能力（新增「删除分析任务」入口），以及分析任务删除时对 capture job 的磁盘清理完整性要求（删除整个 job 产物目录而非部分文件）。

## Impact

- `backend/app/api/routes_sync_recording.py`：新增 `DELETE /api/sync-recordings/{session_id}/analysis` 端点（或等价路由）。
- `backend/app/services/mock_analysis.py`：`delete_analysis_job` 磁盘清理逻辑（capture job 产物目录整体删除）。
- `backend/app/services/multiview_coordinator.py`：`delete_cascade` 行为校验（复用现有级联，确认产物与 fusion run 一并清除）。
- `backend/app/schemas/analysis.py`：如有需要新增删除结果 schema。
- `src/pages/AnalysisTasksPage.tsx`：`SyncRecordingTaskCard` 新增「删除分析任务」按钮与处理函数。
- `src/services/analysisClient.ts`：新增调用删除接口的 client 函数。
