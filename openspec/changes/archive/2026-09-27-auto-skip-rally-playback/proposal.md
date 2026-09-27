## Why

片段页开启自动跳过后，目前仍要求用户先点击某个自动回合，普通播放按钮才会进入按回合续播的路径。从 0:00 或时间轴任意位置直接播放时会播放非比赛时间，与开关的预期不一致。片段列表路由还依赖另一个路由模块中的私有序列化函数，增加后端维护耦合。

## What Changes

- 自动跳过开启时，普通播放入口根据当前播放头从所在自动回合继续；若播放头处在回合之间或首回合之前，则跳到下一自动回合起点并连续播放。
- 播放头位于最后一个自动回合之后时不播放尾部非比赛时间；最后一个回合播完后停止。关闭自动跳过时保留现有播放行为。
- 将片段响应序列化逻辑移至共享后端模块，供片段列表与编辑路由共同调用，并保持 API 响应字段与现有语义不变。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `auto-skip-non-play-playback`：自动跳过开启后，普通播放入口也按播放头选择回合；非比赛区间中的播放头跳到后续回合，而非继续播放该区间。

## Impact

- 前端：`SegmentManagerPage`、`SegmentVideoPlayer` 及其现有自动跳过测试。
- 后端：`routes_segment_editing.py`、`routes_coding_actions.py` 与新增共享片段序列化模块。
- 不新增 API、依赖、数据库字段或响应字段；自动回合仍以当前已发布 run 的 active algorithm Rally 为唯一播放区间来源。
