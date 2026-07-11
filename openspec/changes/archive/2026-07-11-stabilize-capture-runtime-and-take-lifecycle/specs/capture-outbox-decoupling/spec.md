## ADDED Requirements

### Requirement: 媒体停止优先于 Outbox 同步

系统 MUST 将媒体录制停止与 Outbox 事件同步分离为两个独立生命周期。停止操作 MUST 先 freeze 编码按钮、立即调用 stop API，同时 best-effort flushWithDeadline。

#### Scenario: 停止时 freeze + 立即停止媒体

- **WHEN** 用户点击停止按钮
- **THEN** 系统 MUST 立即 freeze()（禁止新 CodingAction 入 outbox）
- **AND** 系统 MUST 立即调用 stop API（停止 FFmpeg）
- **AND** 同时进行 best-effort flushWithDeadline(timeoutMs=3000)

#### Scenario: freeze 后 CodingAction 被拒绝入队

- **WHEN** Outbox 已 freeze
- **AND** 用户尝试打点
- **THEN** 系统 MUST 不将事件加入 outbox
- **AND** MAY 提示「录制已停止，请使用重新同步」

### Requirement: flushWithDeadline + localStorage 恢复

系统 MUST 在 codingOutbox.ts 中提供 freeze()、flushWithDeadline()、getPendingItems() 方法。

#### Scenario: flushWithDeadline 超时后未同步事件保留

- **WHEN** flushWithDeadline(3000) 在 deadline 内未完成
- **THEN** 未同步事件 MUST 保留在 localStorage
- **AND** outboxHealth MUST 设为 "pending"

#### Scenario: 页面重载后恢复 pending items

- **WHEN** 用户刷新页面且 localStorage 中仍有该 capture_take_id 的 pending items
- **THEN** getPendingItems(captureTakeId) MUST 返回所有未同步事件
- **AND** 系统 MAY 自动尝试重新同步

### Requirement: 迟到事件 reproject_coding_timeline

系统 MUST 在接收迟到 CodingAction 后调用 `reproject_coding_timeline(capture_take_id)` 重建派生 TimelineEvent 和 CaptureSegment。

#### Scenario: 迟到 action 写入后触发 reproject

- **WHEN** 迟到 CodingAction 成功写入（校验通过）
- **THEN** 系统 MUST 调用 `reproject_coding_timeline(capture_take_id)`
- **AND** 按 timestamp_ms + sequence_number 重放该 take 的全部 CodingAction
- **AND** 重建 TimelineEvent 和 CaptureSegment 派生投影
- **AND** 最后 MUST 将所有仍 open 的 CaptureSegment 的 end_ms 裁剪到 capture_take.duration_ms

#### Scenario: 迟到事件不会残留 open segment

- **WHEN** CaptureTake 已完成且所有 segment 已关闭
- **AND** 一条迟到 CodingAction 触发 reproject
- **THEN** reproject 完成后 MUST NOT 存在 open segment（end_ms 为 null）
- **AND** 已完成 take 的 duration_ms MUST 不做扩展

### Requirement: 迟到事件基础校验

系统 MUST 对迟到 CodingAction 执行 client_action_id 幂等性、timestamp 范围、grace period 三重校验。

#### Scenario: 三重校验通过则接受

- **WHEN** 迟到 CodingAction 到达
- **AND** client_action_id 未执行过
- **AND** 0 <= timestamp_ms <= capture_take.duration_ms
- **AND** now < capture_take.ended_at + grace_period
- **THEN** 系统 MUST 接受该事件

#### Scenario: 宽限期外拒绝

- **WHEN** 迟到 CodingAction 超过 grace_period
- **THEN** 系统 MUST 拒绝并返回宽限期已过错误
