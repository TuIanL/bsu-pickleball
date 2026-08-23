## Context

片段管理页由 `SegmentManagerPage` 组合 `SegmentVideoPlayer` 和 `EditableSegmentTimeline`。当前页面有三套彼此独立的状态：播放器内部维护当前时间，页面没有接收 `onTimeUpdate`，时间线被固定传入 `currentTimeMs={0}`，右侧列表只在点击时调用 seek。片段边界拖拽直接在鼠标移动事件中调用 `onBoundaryChange`，页面因此会连续发送 PATCH 并在每次响应后重新加载片段列表。

后端的 `CaptureSegment` 已经提供 `corrected_start_ms`、`corrected_end_ms`、`edit_version` 和编辑操作记录；`SessionTimelineEvent` 是比赛关键事件的独立时间轴，不应被片段边界修正直接覆盖。设计需要保持现有 API 和数据模型的兼容性，同时让播放、列表、时间线和编辑操作围绕同一个页面状态运行。

## Goals / Non-Goals

**Goals:**

- 让片段列表点击、视频播放、时间线播放头和当前片段高亮保持双向同步。
- 支持点击片段后从有效起点播放，到有效终点自动暂停。
- 将时间线点击定义为 seek，将边界拖拽定义为对 `CaptureSegment` 的显式编辑。
- 在拖拽过程中提供本地预览，释放后单次提交，并用 `edit_version` 防止旧请求覆盖新修改。
- 在前后端阻止无效边界，并明确关键事件不会因片段编辑而改变。

**Non-Goals:**

- 不重新设计片段拆分、合并、归档和分析批次创建的业务流程。
- 不把 `CaptureSegment` 自动转换为或覆盖 `SessionTimelineEvent`。
- 不在本 change 中新增多视频同步播放算法；机位切换仍使用现有播放器能力。
- 不改变分析任务读取片段有效边界的既有语义。

## Decisions

### 1. 页面作为跨组件播放状态的唯一协调者

在 `SegmentManagerPage` 增加 `currentTimeMs`、`durationMs`、`activeSegmentId` 和播放模式状态。页面把当前时间传给时间线，并通过播放器的 `onTimeUpdate` 更新它；列表点击和时间线点击都由页面先确定目标时间，再调用播放器 handle。播放器继续拥有原生 `<video>` 引用和播放控制，但不直接决定列表或时间线的展示状态。

选择页面协调而不是让列表和时间线互相通信，是为了避免两个组件分别订阅播放器导致状态竞态；也保留 `SegmentVideoPlayer` 作为可独立测试的受控播放组件。

### 2. 明确区分 seek、普通播放和片段播放

播放器 handle 的 `seekToTakeTime` 只定位并暂停状态不变；普通 `play` 不设置片段终点；`playSegment(startMs, endMs)` 设置一次性 playback range，定位到起点并开始播放。播放器在 `timeupdate` 或 `ended` 中检测有效终点，先将时间钳制到终点，再暂停并通知页面清除片段播放模式。

列表单击调用 `playSegment`，因此用户点击某一分即可播放该分；时间线点击调用 seek，不会自动修改片段边界。标签编辑入口停止事件传播，编辑操作不会隐式启动片段播放。

### 3. 高亮以有效边界和当前播放时间为依据

页面维护显式 `activeSegmentId`。用户点击列表或时间线片段时立即设置它；播放器时间更新时，如果当前时间位于某个非 superseded 片段的有效区间内，则更新为该片段，否则保留用户刚选择的片段直到本次片段播放结束。列表行和时间线块使用同一 ID 高亮，播放结束后保持最后一个片段的可见选中状态，但清除“正在播放”状态。

有效边界始终使用 `corrected_start_ms ?? start_ms` 和 `corrected_end_ms ?? end_ms`，避免列表、播放器和时间线分别使用不同的时间来源。

### 4. 拖拽边界采用本地草稿 + 释放提交

`EditableSegmentTimeline` 在 pointer down 时记录原始边界，在 pointer move 时只更新该片段的本地预览值，并通过受控回调把临时边界交给页面；pointer up 时提交一次 `{ corrected_start_ms, corrected_end_ms, expected_version }`。拖拽期间不发网络请求，不触发整页 reload；成功后以 API 返回的片段替换本地项，失败则恢复拖拽前值并提示错误。

这样既避免鼠标移动产生大量 PATCH，也避免异步响应乱序造成边界回退。使用 pointer 事件并在释放时清理监听，保证拖拽离开时间线区域后仍能正确结束。

### 5. 后端边界校验与关键事件隔离

服务层在保存任一 corrected 边界前统一校验：非负、起点不晚于终点、片段时长不低于现有最小片段时长、终点不超过可用媒体/Take 时长；校验失败返回 400，`edit_version` 不递增。版本不匹配继续返回 409，前端重新加载最新片段并提示用户重试。

边界 PATCH 只更新 `CaptureSegment` 及其 `SegmentEditOperation`，不调用 timeline event 写入逻辑。测试通过编辑前后事件快照相等来固定“片段编辑不改变关键事件”的契约。

### 6. 兼容现有 API，增加显式版本参数

保留 `PATCH /api/capture-segments/{segment_id}` 路由和现有 query 参数，前端边界提交同时携带 `expected_version`。不新增数据库迁移；利用现有编辑版本和操作记录实现并发控制。若后端已有可用媒体时长字段，校验使用它；否则使用 Take/片段可用范围作为上限，并在无法确定上限时至少执行非负、顺序和最小时长校验。

## Risks / Trade-offs

- [风险] `timeupdate` 事件频率低于逐帧频率，播放头可能不是每一帧移动。→ [缓解] 播放头以浏览器事件为准，片段终点同时在 `timeupdate` 和 `ended` 检查；精确逐帧编辑仍使用现有帧步进控制。
- [风险] 双击标签时浏览器可能先触发一次 click。→ [缓解] 将编辑入口独立为可识别的交互区域并阻止传播；播放触发逻辑只绑定片段行的明确播放区域，增加双击回归测试。
- [风险] 拖拽期间本地边界与服务端数据短暂不一致。→ [缓解] 只在释放时提交，保存中锁定该片段的再次编辑，失败时恢复草稿并提示。
- [风险] 多标签页同时修改导致 409。→ [缓解] 强制携带 `expected_version`，保留服务端版本冲突响应，前端重新拉取而不是静默覆盖。
- [风险] 旧数据可能已经存在结束早于开始的异常片段。→ [缓解] 页面加载时展示错误状态并禁止继续拖拽保存；后续可通过独立修复脚本处理历史异常，不在本 change 中自动篡改历史数据。

## Migration Plan

1. 先部署后端边界校验和测试；现有合法片段与 API 调用保持兼容。
2. 再部署前端受控播放、时间线同步和拖拽草稿提交逻辑。
3. 对已有异常边界只阻止新的无效修改，保留原数据并在页面提示；确认历史数据后再单独执行修复。
4. 回滚时可恢复前端旧交互和后端旧校验逻辑，不需要数据库 migration；现有 corrected 字段和 edit version 数据保持可读。

## Open Questions

- 可用媒体总时长是否始终能从 `CaptureTake` 或视频元数据取得；如果不能，后端需要明确采用哪个上限字段。
- 用户点击已归档或 `superseded` 片段时，是仅允许查看原始时间，还是完全禁止播放；本设计默认列表过滤后不提供普通播放入口。
