## Why

当前录制控制台只支持简单的事件打点（局开始、比分更新等），但存在三个关键问题：

1. **缺少层级结构**：事件是扁平的时间点，无法表达"盘→局→分"的父子关系
2. **双摄无法打点**：事件面板只在单摄录制时显示，双摄同步录制时无法创建事件
3. **payload 数据丢失**：前端 QuickEventDef 定义了 note 和 payload，但实际提交时被丢弃

现场采集需要一个类似 Hudl Sportscode 的实时编码控制台，让用户在长时间录制中快速标记盘、局、分的开始，并自动维护层级关系。赛后片段管理（编辑、拆分、合并、按片段分析）将作为后续 Change 单独交付。

## What Changes

- **新增 CaptureTake 统一时间轴**：抽象单摄/双摄为统一的录制单元，所有事件绑定 capture_take_id
- **新增 CaptureCodingAction 持久化命令模型**：保存每条语义命令，支撑幂等性、undo、审计和状态重放
- **新增 coding-actions 语义命令 API**：后端事务内处理层级关闭规则，保证事件、片段与状态的一致性
- **新增 LiveCodingState 实时状态**：可重建快照，维护当前第几盘/局/分，支持前端乐观显示和后端权威校验
- **新增"下一分"一键推进**：每次点击自动关闭当前分并创建下一分，减少现场操作频率
- **新增只读多轨实时时间线**：在录制控制台底部显示盘/局/分区间轨道
- **新增局部深色主题**：在录制控制台启用专业分析模式 UI
- **修复 QuickEventDef payload 丢失**：事件创建时提交完整的 note 和 payload_json
- **双摄录制支持打点**：统一单摄/双摄的事件创建流程
- **引入 Alembic 数据库迁移体系**：替代 create_all() 的增量 DDL 方案

## Capabilities

### New Capabilities

- `capture-take-unified-timeline`: 统一单摄/双摄的录制时间轴，引入 CaptureTake 和 CaptureTrack 数据模型，支持双摄分段式时间偏移映射
- `live-coding-console`: 实时编码控制台，包含层级状态管理、一键推进、CaptureCodingAction 命令日志、FIFO Outbox、撤销、幂等性和只读多轨时间线

### Modified Capabilities

- `session-timeline-events`: 事件创建 API 增加 capture_take_id 字段，支持 coding-actions 语义命令，事件标记 undone 状态
- `recording-session-control`: 录制启动时创建 CaptureTake，录制停止时关闭未结束区间（补偿流程，非跨存储原子事务）
- `dual-camera-sync-recording`: 双摄录制流程适配 CaptureTake，支持事件打点

## Impact

- **后端新增**：CaptureTake/CaptureTrack/CaptureCodingAction ORM 模型、coding-actions API、LiveCodingState 服务、CaptureSegment 最小投影
- **后端修改**：timeline_event_service 重构内部 commit 为两层方法、recording-session-control 适配 CaptureTake 补偿流程
- **前端新增**：LiveCodingState 乐观 reducer、只读多轨时间线组件、局部深色主题、FIFO Outbox
- **前端修改**：CaptureConsolePage 重构、QuickEventDef payload 提交、双摄打点面板
- **数据库迁移**：新增 capture_takes、capture_tracks、capture_coding_actions、live_coding_states、capture_segments 表，timeline_events 表增加 capture_take_id 字段
- **基础设施**：引入 Alembic 作为 SQLite 增量迁移工具
- **API 变更**：新增 POST /api/capture-takes/{id}/coding-actions 端点
