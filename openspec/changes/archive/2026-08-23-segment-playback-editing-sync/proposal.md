## Why

片段管理页目前把“选中片段”“播放片段”“编辑片段标签”和“调整片段边界”混在同一组交互中，导致点击片段不能稳定播放、播放结束不会自动暂停、列表高亮与时间线播放头不同步。时间线拖拽还会在鼠标移动过程中连续提交边界修改，并且服务端缺少完整的起止边界校验，已经出现结束时间早于开始时间的无效片段。

现在需要建立统一的片段回放与编辑同步契约，使右侧片段列表、视频播放器、时间线和关键事件展示围绕同一个播放状态工作，同时明确边界修正不会直接改写 `SessionTimelineEvent`。

## What Changes

- 点击片段时定位到片段起点并开始播放；播放到该片段有效结束边界后自动暂停，并清理播放状态。
- 统一片段列表的 active/highlight 状态：点击、时间线点击、播放过程和播放结束都更新当前片段；双击编辑标签不再误触发播放。
- 将播放器的当前时间和媒体时长同步到片段管理页与 `EditableSegmentTimeline`，让播放头、片段高亮和关键事件标记随时间变化。
- 时间线点击只负责 seek；拖拽边界只修改 `CaptureSegment.corrected_start_ms/corrected_end_ms`，不修改 `SessionTimelineEvent`，并在释放拖拽后合并提交，避免每次鼠标移动都发 PATCH。
- 为边界修正增加前端和后端约束，禁止负数、超出媒体时长、结束早于开始及低于最小时长的片段；处理并发编辑版本冲突，避免旧请求覆盖新边界。
- 为片段播放、列表/时间线同步、边界编辑和关键事件不变性增加前后端测试与回归验收。

## Capabilities

### New Capabilities

- `segment-playback-editing-sync`: 定义片段列表、视频播放器、时间线和边界编辑之间的统一状态、播放和持久化同步行为。

### Modified Capabilities

- `segment-manager`: 扩展片段管理页的播放入口、片段高亮、时间线 seek/播放头同步和编辑交互要求。

## Impact

- 前端：`src/pages/SegmentManagerPage.tsx`、`src/components/SegmentVideoPlayer.tsx`、`src/components/EditableSegmentTimeline.tsx` 及其测试。
- 后端：`backend/app/api/routes_segment_editing.py`、`backend/app/services/segment_edit_service.py`，必要时补充媒体时长/片段范围查询。
- 数据语义：片段边界修正继续落在 `CaptureSegment` 的 corrected 字段和编辑历史中，不覆盖 `SessionTimelineEvent`；分析批次继续使用片段的有效边界。
- API：保留现有片段 PATCH 接口，补充稳定的边界校验、版本冲突和错误响应语义。
