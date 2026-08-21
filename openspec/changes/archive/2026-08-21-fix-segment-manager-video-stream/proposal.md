# fix-segment-manager-video-stream

## Why

比赛库素材的「片段」页（SegmentManagerPage）无法正常播放视频：视频流 URL 错误地使用了 `source_session_id`（采集会话 ID）而非 `video_id`，导致 `/api/videos/{id}/stream` 返回 404，片段列表加载成功但完全无法播放；此外，`list_segments` 返回字段与前端编辑器契约不一致，且 `loadData` 静默吞错会在任一接口失败时永久停在「加载中...」。

## What Changes

- 修正 SegmentManagerPage 的视频源解析：单摄使用该录制的 `video_id`；双摄提供多机位选择（`registered_video_ids` / `default_analysis_video_id`），不再使用 `source_session_id` 拼流地址。
- 对齐 `list_segments` 返回字段：后端返回 `edit_status`、`edit_version`、`corrected_start_ms`、`corrected_end_ms`、`effective_start_ms`、`effective_end_ms`，使前端拆分/合并过滤、乐观锁与边界修正真实生效。
- 拆解 `loadData` 的错误处理：三个数据源独立加载、独立兜底，任一失败显示明确错误态，不再永久「加载中...」。
- 视频源不可用时给出可见的不可播放反馈，而不是静默黑屏。

## Capabilities

### New Capabilities

- `segment-manager`: 覆盖片段管理页（SegmentManagerPage）的前端行为：单摄/双摄视频回放源解析、数据加载的错误反馈与空态/错误态展示。

### Modified Capabilities

- `segment-editing`: 片段列表接口（`GET /api/capture-takes/{id}/segments`）必须暴露编辑器所需的完整契约字段（`edit_status`、`edit_version`、`corrected_*`、`effective_*`），使前端过滤、乐观锁与边界修正生效。

## Impact

- 前端：`src/pages/SegmentManagerPage.tsx`、`src/components/SegmentVideoPlayer.tsx`、`src/types/report.ts`（CaptureSegmentSummary）、`src/services/libraryAdapter.ts`（为片段视图暴露视频源）。
- 后端：`backend/app/api/routes_coding_actions.py`（list_segments 返回字段）、`backend/app/services/segment_service.py`（补充 effective/corrected 计算）。
- 测试：SegmentManagerPage / 片段接口相关测试补充视频源解析与字段契约断言。
