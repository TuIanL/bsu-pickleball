## 1. 数据契约与兼容层

- [x] 1.1 扩展后端 CodingAction action enum、请求 schema 和前端 `CodingActionType`，加入 `start_timeout` 并保留 `toggle_non_play` 的旧客户端兼容。
- [x] 1.2 为 LiveCodingState 持久化和 API schema 增加 `match_phase`、`intermission_kind`，并将 `non_play` 维护为兼容派生字段。
- [x] 1.3 为 CodingActionResponse 增加完整 `timeline_events` 和 `segments` 权威投影字段，更新 `analysisClient` 与前端类型。
- [x] 1.4 定义并实现 `payload_json.intermission_kind` 的读写适配；缺失原因的历史间歇默认解释为 `between_rallies`。
- [x] 1.5 为 CaptureCodingAction 保存 action 直接创建或修改的事件和 Segment 关联，支持审计与撤销定位。

## 2. 后端比赛状态机

- [x] 2.1 重构 coding action dispatcher，使 `start_next_rally` 只在 `idle` 或 `intermission` 开始分，并在进行中分时拒绝且不改变状态。
- [x] 2.2 实现 `end_rally`：关闭当前分、写入 `rally_end` 和 `between_rallies` 间歇起点，并更新 phase。
- [x] 2.3 实现 `start_timeout`：原子关闭当前分或当前间歇，开启带 `timeout` 原因的间歇。
- [x] 2.4 重构 `change_side`：写入换边点事件，原子关闭当前分或当前间歇，并开启带 `side_change` 原因的间歇。
- [x] 2.5 实现开始下一分、开始新局、开始新盘、结束局和结束盘时对开启间歇的正确关闭及原因继承。
- [x] 2.6 保留并覆盖 `toggle_non_play` 的历史兼容处理，确保新比赛控制台不再使用该 action。

## 3. 权威投影与撤销

- [x] 3.1 实现按有效 CaptureCodingAction 序列重放 LiveCodingState、TimelineEvent 和 CaptureSegment 的投影服务。
- [x] 3.2 实现 undo：设置 `reverses_action_id`、标记目标 action 与其直接事件为 undone，并使受影响 Segment 退出 active 投影。
- [x] 3.3 让每次成功 action 和幂等重复 action 返回当前 Take 的完整有效事件、区间和状态快照。
- [x] 3.4 确保 `listTimelineEvents`、`listSegments` 和 action response 对已撤销或已归档的投影使用一致的有效性筛选。
- [x] 3.5 为“开始第 N 分、撤销、再开始第 N 分”及盘、局、分层级组合增加后端回归测试。

## 4. 实时控制台交互

- [x] 4.1 将比赛控制按钮改为“开始下一分”“结束当前分”“战术暂停”“换边”，移除用户可见的“非比赛”切换按钮并更新文案、图标、颜色和快捷键。
- [x] 4.2 基于 `match_phase` 和 `intermission_kind` 显示当前状态，并在不合法状态禁用开始下一分和结束当前分等动作。
- [x] 4.3 修改 Outbox 和 `applyCodingResponse`：以 action response 的完整快照替换当前 Take 的事件、区间和状态。
- [x] 4.4 修改轮询加载逻辑：以当前 Take 的完整有效列表替换本地数组，丢弃过期 Take 的异步响应。
- [x] 4.5 移除 ordinal 的本地乐观增减，改为 pending 交互反馈和服务端确认后的权威更新。
- [x] 4.6 更新单摄和双摄的初始化、停止和队列恢复流程，确认新状态字段在两种路径中一致。

## 5. MiniTimeline 呈现

- [x] 5.1 重构 MiniTimeline 坐标计算为 90 秒固定时宽滚动窗口，避免随总录制时长重缩放历史色条。
- [x] 5.2 使用基于录制起点的 `requestAnimationFrame` 连续时钟更新游标、开放分段和未关闭间歇，不依赖秒级计时器作为布局来源。
- [x] 5.3 扩展间歇区间推导，读取 `intermission_kind` 并兼容历史事件的默认赛间原因。
- [x] 5.4 分别渲染赛间灰色、战术暂停深灰条纹和换边浅紫带边界遮罩，并保留换边竖线与菱形标记。
- [x] 5.5 覆盖窗口开始、超过 90 秒滚动、开放区间、关闭区间和不同间歇类型的组件测试。

## 6. 验证与回归

- [x] 6.1 为后端 action 状态转换、间歇 payload、完整投影、undo 重放和历史事件兼容增加单元及集成测试。
- [x] 6.2 为前端按钮状态、快捷键、Outbox 权威替换、轮询过期响应和撤销后同序号重建增加 Vitest 测试。
- [x] 6.3 运行后端测试、`npm run test` 和 `npm run build`，修复本变更引入的失败。
- [x] 6.4 在浏览器中手动验证单摄与双摄的“开始分 → 结束分 → 暂停或换边 → 开始下一分 → 撤销”流程，以及 90 秒后的时间线平滑滚动。
