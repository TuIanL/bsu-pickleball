# Design: 删除双摄录制下的分析任务

## Context

当前任务管理页「双摄录制」Tab 对每条录制只提供「删除」（整条录制，经 `CaptureCleanupService.delete_take(delete_media=True)` 连录制资产一并清除），没有「仅删除该录制派生的分析任务」的入口。同时 `delete_analysis_job`（`backend/app/services/mock_analysis.py`）对 capture job 只按清单删除约 12 个已知 JSON 文件，遗留大量产物：

- `analysis_overlay.mp4`（子任务可达 1.3GB）、`ball_trajectory.json`、`cleaned_ball_trajectory.json`、`bounce_events.json`、`player_render_trajectory.json`、`players_trajectory.*`、`detections.jsonl`、`player_selection*.json`、`court_view_roi.json`、`calibration_diagnostics.json`；
- Parent 命名空间的 `fused_manifest.json` / `fused_diagnostics.json` / `fused_player_trajectory.json`；
- `take_dir/analysis/<job_id>/position_visualizations/` 整个目录。

既有的可复用能力：后端已有 `GET /api/analysis/jobs?recording_session_id=<sid>`（按录制过滤，`include_internal` 默认隐藏 child）、`POST /api/analysis/jobs/delete`（批量删）、`delete_analysis_job` 内对 multiview Parent 的 `delete_cascade`（级联删 child + fusion run 产物）。前端 `SyncRecordingTaskCard` 已通过 `recordingDerivedJobs` 拿到每条录制派生的 public 分析任务。

## Goals / Non-Goals

**Goals:**
- 提供「删除双摄录制下分析任务」的能力：一个入口清除该录制派生的所有分析任务（multiview Parent + internal child + 单摄任务）及其本地磁盘产物。
- 完整清理本地磁盘：删除每个 job 在 `take_dir/analysis/<job_id>/` 下的**整个产物目录**，而非部分文件。
- 严格保留录制本身：session JSON、双路视频、CaptureTake、`sync_calibration.json`、CaptureTrack 均不触碰。

**Non-Goals:**
- 不删除双摄录制本身（现有「删除」按钮行为不变）。
- 不引入新的单摄录制删除路径。
- 不改动检测/融合算法、不改动 `recording-analysis-bridge` 的归属契约。
- 不实现录制工作台（`RecordingWorkspacePage`）入口（本期仅任务管理页）。

## Decisions

### D1: 后端新增录制级删除端点

新增 `DELETE /api/sync-recordings/{session_id}/analysis`（置于 `routes_sync_recording.py`，与录制生命周期同一模块）。

- 内部逻辑：按 `session_id` 查找到所有归属该录制的分析任务 → 逐个 `delete_analysis_job`（multiview Parent 经既有 `delete_cascade` 级联删 child + fusion run）→ 返回 `AnalysisDeleteResult[]`。
- 任务匹配规则（与既有 `GET /jobs?recording_session_id=` 一致并补强）：
  - `metadata.recording_session_id == session_id` 或 `recordingSessionId == session_id`；
  - 或 `metadata.capture_take_id == session.capture_take_id`（补强：即使 session id 缺失也能按 take 命中）。
- 删除范围只含 `visibility=public` 的 Parent/单摄任务；internal child 由 cascade 处理，不直接删。

**为什么选专用端点**：前端已能算 `recordingDerivedJobs`，也可直接调批量删除；但专用端点把「按录制定位任务」下沉到后端，避免前端 job 列表过期导致漏删/重复，且级联语义集中在后端一处。

### D2: 修复 `delete_analysis_job` 磁盘清理

在 `delete_analysis_job` 内，`resolve_capture_job_root(job_id, capture_take_id)` 之后，对 `_job_artifact_root(job_id)` 做 `delete_path_tree` 整体删除。

- 对 capture job：`_job_artifact_root` = `take_dir/analysis/<job_id>`，只删该 job 自己的目录，`take_dir` 下的录制资产不受影响（录制视频、分段、`sync_calibration.json` 均在 `take_dir` 而非 `take_dir/analysis/<job_id>` 内）。
- 对非 capture job：`_job_artifact_root` = `outputs_dir/<job_id>`，与现有 `delete_path_tree(job_output_dir)` 等价，可保留原路径避免双删。
- 保留现有的「共享 video/calibration 仍被其他 job 引用则保留」逻辑（`_cleanup_shared_video_artifacts` / `_cleanup_shared_calibration_artifacts`），它们作用域在共享资源层，与产物目录删除不冲突。
- 删除前校验：仅当根路径确实等于 `take_dir/analysis/<job_id>` 或 `outputs_dir/<job_id>` 才删，防止误删录制目录。

### D3: 前端「删除分析任务」按钮

`SyncRecordingTaskCard` 在「删除」（整条录制）按钮旁新增「删除分析任务」按钮：

- 仅当该卡片存在分析任务（`analysisJobs.length > 0`，即 multiviewJob / cam1Job / cam2Job 任一存在）时显示。
- 点击 → `window.confirm`（说明会删除分析任务与本地产物、保留录制）→ 调 `deleteRecordingAnalysis(session_id)`（新 client 函数）。
- 完成后刷新任务列表与录制列表（录制保留），用现有 toast 反馈机制报告删除/阻断数量。

## Risks / Trade-offs

- **活跃任务不可删** → 端点对 `status` 处于 processing 的任务返回 `blocked`；前端 toast 报告「N 个分析中未删除」，由用户稍后重试。与现有批量删除语义一致。
- **路径误删风险** → [Risk] 整体删除 `take_dir/analysis/<job_id>` 若路径解析错误可能误伤录制目录 → Mitigation: 删除前校验根路径与目标格式完全匹配（`<take>/analysis/<job_id>` 或 `<outputs>/<job_id>`），且 `job_id` 必须以 `job-` 前缀开头并仅含 URL 安全字符（`^job-[A-Za-z0-9_-]+$`），避免匹配任意目录名。
- **任务归属边界** → [Risk] 匹配规则若过宽可能误删同 session 下不希望删的任务 → Mitigation: 匹配仅限 `recording_session_id` 字段 + `capture_take_id` 命中，且只删 public 任务；internal child 仅经 Parent cascade。
- **旧的单摄任务归属缺失** → [Risk] 历史单摄任务可能只有 `camera_slot` 而无 `recording_session_id` → Mitigation: 本期按 session/take 匹配；确实无法归属的历史任务不在删除范围，用户仍可在 upload tab 单删。

## Migration Plan

- 无数据迁移。发布顺序：后端端点 + 磁盘清理修复 → 前端 client 函数 → 前端按钮。
- 回滚：移除按钮 / 回退端点；磁盘清理修复单独可回退（保留原文件清单）。

## Open Questions

- 确认对话框文案（建议：「删除该录制的所有分析任务及本地产物？录制本身会保留。」）。
- 是否需要在 `RecordingWorkspacePage` 也提供同一入口（本期默认不加，可后续追加）。
