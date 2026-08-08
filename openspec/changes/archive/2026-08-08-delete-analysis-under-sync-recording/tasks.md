# Tasks: 删除双摄录制下的分析任务

## 1. 后端：修复 `delete_analysis_job` 磁盘清理

- [x] 1.1 在 `backend/app/services/mock_analysis.py` 的 `delete_analysis_job` 中，`resolve_capture_job_root(job_id, capture_take_id)` 之后增加对 `_job_artifact_root(job_id)` 的整体 `delete_path_tree` 删除（对 capture job 即 `take_dir/analysis/<job_id>`，非 capture job 与现有 `outputs_dir/<job_id>` 删除等价）
- [x] 1.2 在整体删除前增加路径安全校验：目标路径必须匹配 `<take_dir>/analysis/<job_id>` 或 `<outputs_dir>/<job_id>`，且 `job_id` 匹配 `^job-[0-9a-f]{10}$`，否则跳过目录删除
- [x] 1.3 保留现有共享 video/calibration 引用保护逻辑（`_cleanup_shared_video_artifacts` / `_cleanup_shared_calibration_artifacts`），确认与目录删除不冲突
- [x] 1.4 新增/更新单测：删除 capture job 后 `take_dir/analysis/<job_id>/` 整个目录消失，`take_dir` 下录制视频与 `sync_calibration.json` 保留；非 capture job 行为不变

## 2. 后端：新增录制级删除分析任务端点

- [x] 2.1 在 `backend/app/services/mock_analysis.py`（或 `multiview_coordinator.py`）新增 `delete_analysis_by_recording_session(session_id, session_capture_take_id) -> list[AnalysisDeleteResult]`：遍历任务，命中 `metadata.recording_session_id == session_id` 或 `recordingSessionId == session_id` 或 `metadata.capture_take_id == session_capture_take_id` 的 public 任务，逐个 `delete_analysis_job`（multiview Parent 自动级联 child）
- [x] 2.2 在 `backend/app/api/routes_sync_recording.py` 新增 `DELETE /api/sync-recordings/{session_id}/analysis`，调用上述服务并返回 `AnalysisDeleteResult[]`；录制不存在返回 404
- [x] 2.3 新增/更新测试：multiview Parent 级联删除 child 与 fusion run 产物；活跃任务返回 `blocked` 且文件保留；录制 session/视频/take 不被动；单摄任务一并删除

## 3. 前端：client 函数与按钮

- [x] 3.1 在 `src/services/analysisClient.ts` 新增 `deleteRecordingAnalysis(sessionId: string): Promise<AnalysisDeleteResult[]>`，调用 `DELETE /api/sync-recordings/{sessionId}/analysis`
- [x] 3.2 在 `src/pages/AnalysisTasksPage.tsx` 的 `SyncRecordingTaskCard` 新增「删除分析任务」按钮：仅在 `analysisJobs.length > 0` 时显示，与「删除」（整条录制）按钮并列且文案/样式可区分
- [x] 3.3 新增处理函数：confirm 后调用 `deleteRecordingAnalysis`，完成后刷新任务列表与录制列表（录制保留），用现有 toast 反馈删除/阻断数量
- [x] 3.4 更新前端测试：有分析任务时按钮显示、无任务时不显示、确认后调用接口并保留录制卡片、blocked 结果如实报告

## 4. 收尾验证

- [x] 4.1 后端运行 `pytest`（含新增单测）通过
- [x] 4.2 前端 `npm test` 与 `npm run build` 通过
- [x] 4.3 手工冒烟：对一个已完成的双摄录制执行「删除分析任务」，确认分析任务消失、录制仍在、磁盘 `take_dir/analysis/<job_id>` 被清除且录制视频保留
