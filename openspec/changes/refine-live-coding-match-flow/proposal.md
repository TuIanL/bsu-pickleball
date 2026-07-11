## Why

实时录制的当前“下一分”会在一个动作内结束当前分并立即开始下一分，和实际比赛中“得分结束后先进入赛间间歇、裁判或运动员准备后才开下一分”的流程不一致。独立的“结束当前分”和“非比赛”按钮也重复表达同一状态，换边不能结束当前分；与此同时，撤销没有恢复完整的事件和区间投影，导致盘、局、分色条在前端残留或重复。

MiniTimeline 以不断增长的总录制时长重新计算全部色条的百分比位置，录制时会出现整条时间线按秒跳动。现在需要把比赛语义、服务端投影和实时展示统一起来，避免错误标注持续污染后续分析。

## What Changes

- 将比赛实时编码改为显式的“进行中分 / 赛间间歇 / 战术暂停 / 换边间歇”流程；`开始下一分`只开始分，不再隐式结束上一分。
- 合并“结束当前分”和“非比赛”概念：结束当前分会关闭当前分并开启赛间间歇；移除面向用户的“非比赛”切换按钮。
- 增加战术暂停和换边的原子语义及可区分的间歇原因，使换边在进行中按下时自动结束当前分并进入换边间歇。
- 扩展间歇事件的结构化 payload，保留赛间、暂停、换边原因，并让时间线以不同遮罩呈现。
- 将 undo 改为服务端权威重放：撤销动作关联的事件、区间和实时状态都必须被恢复；API 返回完整有效投影，前端整体替换，杜绝残留及重复色条。
- 将 MiniTimeline 改为固定时宽的平滑滚动视口；时间推进不再重新缩放历史色条。
- 更新快捷键、按钮禁用状态、状态文案和前后端测试以匹配新流程。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `live-coding-console`: 修改比赛 action 的状态转换、undo 的权威投影返回、实时控制台状态和 MiniTimeline 滚动及间歇视觉要求。
- `session-timeline-events`: 为编码动作生成的间歇事件增加可查询、可重放的间歇原因元数据。

## Impact

- 前端：`src/pages/CaptureConsolePage.tsx`、`src/components/MiniTimeline.tsx`、`src/services/codingOutbox.ts`、`src/types/report.ts` 及其测试。
- 后端：coding action 状态机、LiveCodingState、CaptureCodingAction、CaptureSegment 投影、TimelineEvent 服务、Pydantic schema 和后端测试。
- API：`POST /api/capture-takes/{id}/coding-actions` 的 action 枚举、LiveCodingState 与成功响应将扩展；旧 `toggle_non_play` 不再由比赛控制台发起。
- 不引入新运行时依赖；旧时间线事件仍须可读取，并按默认赛间间歇语义兼容显示。
