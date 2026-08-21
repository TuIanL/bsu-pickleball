# Tasks — fix-segment-manager-video-stream

## 1. 后端：视频源与片段契约字段

- [x] 1.1 在 `backend/app/schemas/coding_actions.py` 的 `CaptureTakeSummary` 增加 `video_ids: list[str] = []`
- [x] 1.2 `get_capture_take_detail` 通过 `capture_track_service.get_tracks_for_take(db, take.id)` 汇总非空 `video_id`（按 slot cam_1→cam_2 排序）填充 `video_ids`
- [x] 1.3 `list_segments`（routes_coding_actions.py）复用 `routes_segment_editing._seg_dict` 输出完整契约字段，删除手工拼 dict
- [x] 1.4 补后端测试：`video_ids` 按机位顺序返回；`list_segments` 断言 `edit_status`/`edit_version`/`corrected_*`/`effective_*` 字段存在且 effective 遵循 corrected 优先

## 2. 前端：片段页视频播放

- [x] 2.1 `src/types/report.ts` 的 `CaptureTakeSummary` 增加 `video_ids?: string[]`
- [x] 2.2 `SegmentManagerPage` 移除 `source_session_id` 拼 URL 逻辑，改为从 `take.video_ids` 构造 `trackOptions`（多机位标注「机位N」）并接入 `SegmentVideoPlayer` 的 `trackOptions`/`onTrackChange`
- [x] 2.3 用 `activeVideoUrl` state 承接机位切换，默认选中第一个；`video_ids` 为空时渲染「暂无可用视频回放」稳定空态
- [x] 2.4 补前端测试：单摄流地址使用 `video_ids[0]`；双摄生成机位选项；不使用 `source_session_id`

## 3. 前端：数据加载独立兜底

- [x] 3.1 `loadData` 拆分为 take / segments / events 三个独立加载，各自 try/catch 独立兜底
- [x] 3.2 新增 `loadError` 状态：关键源（take 详情）失败时展示错误块 + 重试按钮，不再永久「加载中...」
- [x] 3.3 补前端测试：单一数据源失败不影响其余展示；take 详情失败展示错误态

## 4. 验证

- [x] 4.1 后端 `pytest` 全绿（1173 passed，无新增失败）
- [x] 4.2 前端 build 通过、片段页相关单测通过（Vitest 464 passed，64 files）
- [x] 4.3 手工验证：线上接口 `GET /api/capture-takes/ct_6896250c9695` 返回 `video_ids: ['rec-9e2d944d4d']`，`/api/videos/rec-9e2d944d4d/stream` 200，`list_segments` 包含 `edit_status/edit_version/corrected_*/effective_*` 完整契约字段
