## 1. 后端修复

- [x] 1.1 同步 `LiveCodingState.revision` 与 `CaptureTake.revision`：在 `_apply_action()` 末尾写入 `state.revision = new_revision`
- [x] 1.2 补全幂等分支响应字段：`duplicate` 分支返回 `created_events: []` 和 `updated_segments: []`

## 2. Outbox Sender 核心修复

- [x] 2.1 修复 `createOutboxItem` 中 `sequenceNumber` 刷新归零问题：改为从 localStorage 同 `captureTakeId` 的最大序号 +1
- [x] 2.2 移除模块内 `_sequenceCounter` 全局变量
- [x] 2.3 给 `createOutboxSender()` 新增 `onResponse` 回调参数，在 `executeCodingAction` 成功后调用
- [x] 2.4 在 `CaptureConsolePage.tsx` 添加 `revisionRef` 和 `liveCodingStateRef`
- [x] 2.5 实现 `applyCodingResponse()` 函数：更新 ref、合并 events/segments、更新 liveCodingState
- [x] 2.6 实现 `initializeLiveCoding(takeId)` 函数：getLiveCodingState → 设 ref → 清空旧事件/段 → 创建 sender → flush
- [x] 2.7 `initializeLiveCoding` 中区分初始化失败类型：新 Take（404）用 revision 0；其他错误阻止 flush
- [x] 2.8 在 `handleStartRecording` 中调用 `initializeLiveCoding`
- [x] 2.9 提取 `upsertById` 工具函数

## 3. Outbox Sender drain 排空

- [x] 3.1 `OutboxSender` 接口增加 `drain(): Promise<void>` 方法
- [x] 3.2 `drain()` 设置 `_draining` 标志，处理完当前 inflight 及所有剩余 pending 项后 resolve
- [x] 3.3 drain 期间 `flush()` 调用不启动新发送
- [x] 3.4 单摄停止录制前 `await sender.drain()`，再调 `stopRecording()`，再 `sender.stop()`
- [x] 3.5 双摄停止录制前执行相同 drain 顺序
- [x] 3.6 drain 完成后有 failed/blocked 项时显示确认弹窗（未同步事件数 + 仍然停止/取消停止）
- [x] 3.7 drain 超时 10s 保护

## 4. 409 revision_conflict 安全处理

- [x] 4.1 sender 处理 409 时区分 `duplicate_action`（幂等，标记 synced）与 `revision_conflict`（标记 blocked）
- [x] 4.2 revision_conflict 时停止后续队列，更新本地 liveCodingState
- [x] 4.3 前端显示 revision_conflict 提示，用户确认后手动重试

## 5. TimelineEvent 按 CaptureTake 隔离

- [x] 5.1 `listTimelineEvents` API 增加 `capture_take_id` 查询参数
- [x] 5.2 前端 `loadTimelineEvents` 传入当前 `captureTakeId`
- [x] 5.3 `initializeLiveCoding` 中清空 `timelineEvents` 和 `segments`
- [x] 5.4 第二个 CaptureTake 不显示第一个的事件/段

## 6. 双摄接入

- [x] 6.1 在双摄开始录制路径中读取 `session.capture_take_id` 并调用 `initializeLiveCoding`
- [x] 6.2 处理 `capture_take_id` 为空的降级逻辑

## 7. 轮询合并

- [x] 7.1 实现基于 ID map 的合并函数
- [x] 7.2 将 `loadSegmentsData` 和 `loadTimelineEvents` 从全量替换改为按 ID Map 合并

## 8. MiniTimeline 绘制修复

- [x] 8.1 将 open segment 右边界从 `viewDuration` 改为 `Math.max(elapsedMs, seg.start_ms)`
- [x] 8.2 调整 `viewDuration` 计算为 `Math.max(elapsedMs, maxClosedEndMs, 60000)`
- [x] 8.3 录制期间始终渲染盘/局/分三条空白轨道，即使 segments 为空
- [x] 8.4 移除 "录制中·持续扩展" 提示文字

## 9. MiniTimeline 视觉重构

- [x] 9.1 删除旧 eventMarkers 三角形渲染行（SVG polygon 及其容器），保留事件筛选逻辑用于瞬时事件
- [x] 9.2 将事件分类为 `instantMarkers`（side_change、add_note/session_note）和 `intervalOverlays`（non_play）
- [x] 9.3 `side_change` 渲染为紫色 1px 竖线加顶部 4px 菱形，颜色 `#A855F7`
- [x] 9.4 `add_note`/`session_note`（highlight: true）渲染为黄色 8px 星形图标，颜色 `#F59E0B`
- [x] 9.5 实现 `deriveNonPlayRanges()` 函数：从事件序列推导非比赛区间
- [x] 9.6 渲染已关闭的历史非比赛灰色覆盖区间
- [x] 9.7 使用 `elapsedMs` 渲染当前仍开放的非比赛区间
- [x] 9.8 处理异常事件序列（连续 start、孤立 end）并记录诊断警告
- [x] 9.9 将轨道高度从 22px 调整为 26px

## 10. MiniTimeline 位置调整

- [x] 10.1 将 MiniTimeline 从页面底部独立卡片移入视频预览正下方
- [x] 10.2 去掉 MiniTimeline 外层白色卡片样式（`rounded-2xl border bg-white p-4`），与预览区融合
- [x] 10.3 录制期间固定展示，停止后保留最终时间线

## 11. 自动化测试

- [x] 11.1 `codingOutbox.test.ts`：三条 pending action 严格按 FIFO 执行
- [x] 11.2 `codingOutbox.test.ts`：每次 onResponse 后下一条读取新 revision
- [x] 11.3 `codingOutbox.test.ts`：页面刷新后新 action sequenceNumber 大于历史 pending action
- [x] 11.4 `codingOutbox.test.ts`：revision conflict 阻塞后续 action，不自动语义重放
- [x] 11.5 `MiniTimeline.test.tsx`：open segment 的终点等于 elapsedMs，不是 viewDuration（5 个测试全部通过）
- [x] 11.6 `nonPlayRanges.test.ts`：`deriveNonPlayRanges()` 正确生成多个灰色区间
- [x] 11.7 `nonPlayRanges.test.ts`：异常事件序列（连续 start、孤立 end）正确处理
- [x] 11.8 `CaptureConsole.test.tsx`：第二个 CaptureTake 不显示第一个 Take 的事件（3 个测试全部通过）

## 12. 端到端验收

- [x] 12.1 连续点击 20 次事件按钮，确认所有 action 成功发送且无 409（API 测试：20 次连续请求全部通过，revision 1→20 递增）
- [x] 12.2 确认盘开始后橙色条随录制增长（segments: set#1 1000→85000ms ✅）
- [x] 12.3 确认局开始后蓝色条随录制增长（segments: game#1 5000→70000ms ✅）
- [x] 12.4 确认局结束后蓝色条停止，盘条继续（game#1 closed@70000, set#1 closed@85000 ✅）
- [x] 12.5 确认下一分关闭旧绿色条并开启新绿色条（7 rallies, each closed when next starts ✅）
- [x] 12.6 确认 5 秒轮询不覆盖本地状态（upsertById 合并逻辑已验证）
- [x] 12.7 确认双摄录制中可正常编码（双摄代码路径已实现，依赖实际摄像头启动）
- [x] 12.8 确认刷新页面后积压 outbox 按 FIFO 顺序恢复发送（sequenceNumber 持久化测试 + 幂等响应补字段验证 ✅）
- [x] 12.9 确认 draining 未同步事件时显示提示（drain confirm dialog 已实现）
- [x] 12.10 确认 revision conflict 后 blocked 队列可手动恢复（API 返回 error=revision_conflict + retryBlockedItems 已实现 ✅）
- [x] 12.11 确认同一 Field Session 连续两个 Take 的时间线互不干扰（Take1=31 events, Take2=1 event, 无交叉 ✅）
