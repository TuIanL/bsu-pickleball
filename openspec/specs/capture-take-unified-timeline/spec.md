# capture-take-unified-timeline Specification

## Purpose

定义 CaptureTake、CaptureTrack 与事件时间线的数据模型、生命周期、时间映射和旧数据适配规则。
## Requirements
### Requirement: CaptureTake 数据模型

系统 MUST 为单摄和双摄录制引入统一的 CaptureTake 抽象层。

#### Scenario: 创建 CaptureTake

- **WHEN** 用户启动单摄或双摄录制
- **THEN** 系统 SHALL 创建 CaptureTake 记录
- **AND** `capture_mode` SHALL 设置为 `single` 或 `dual`
- **AND** `source_session_type` SHALL 设置为 `recording` 或 `sync_recording`
- **AND** `source_session_id` SHALL 关联底层 RecordingSession 或 SyncRecordingSession
- **AND** `status` SHALL 设置为 `recording`
- **AND** `revision` SHALL 初始化为 0
- **AND** `source_session_type` + `source_session_id` 组合 SHALL 唯一

#### Scenario: duration_ms 非负约束

- **WHEN** 保存 CaptureTake
- **THEN** `duration_ms` SHALL 为 null 或 >= 0
- **AND** `revision` SHALL >= 0

#### Scenario: 录制前创建错误的 CaptureTake 可硬删除

- **WHEN** CaptureTake 状态为 `recording` 且无关联事件和轨道资产
- **THEN** 系统 SHALL 允许硬删除该 CaptureTake

#### Scenario: 已录制 CaptureTake 只能归档

- **WHEN** CaptureTake 有关联事件或已完成录制
- **THEN** 系统 SHALL 只通过 `archived_at` 字段标记归档
- **AND** 系统 SHALL 不执行硬删除

### Requirement: CaptureTrack 数据模型与约束

系统 MUST 为每个 CaptureTake 创建对应的 CaptureTrack。

#### Scenario: 创建 CaptureTrack

- **WHEN** 创建 CaptureTake 时
- **AND** 如果是单摄录制
- **THEN** 系统 SHALL 创建一个 CaptureTrack，`role` 为 `primary`
- **AND** `offset_ms` SHALL 为 0
- **AND** `offset_source` SHALL 为 `measured`
- **AND** `sync_quality` SHALL 为 `good`

#### Scenario: 双摄 CaptureTrack 使用 PTS 映射

系统 MUST 为双摄 CaptureTrack 保存基于真实时间轴校正的相对偏移和同步质量，而不是仅使用进程启动时间或假设值。

- **WHEN** 创建或完成双摄 CaptureTake 的时间轴校正
- **THEN** 系统 SHALL 为每个摄像头保存相对于参考机位的 `offset_ms`
- **AND** SHALL 保存可选的 `drift_ppm` 或等价速率参数
- **AND** `offset_source` SHALL 为 `measured` 或 `corrected`
- **AND** `sync_quality` SHALL 为 `good`、`degraded` 或 `unknown`

#### Scenario: 无法测量可靠的跨路时间偏移

- **WHEN** 源 PTS 缺失、不单调、跨路不可比较或拟合残差超过阈值
- **THEN** 系统 SHALL 将 `sync_quality` 标记为 `degraded` 或 `unknown`
- **AND** SHALL 保留诊断原因
- **AND** SHALL NOT 将 `offset_source` 标记为 `measured`

#### Scenario: 事件映射到 CaptureTrack

- **WHEN** 需要定位事件在某个摄像头视频中的位置
- **THEN** 系统 SHALL 保持事件 `timestamp_ms` 相对 CaptureTake 起点不变
- **AND** SHALL 使用 CaptureTrack 的 offset/drift 映射得到摄像头本地时间和帧号
- **AND** SHALL 将映射误差暴露给训练导出或诊断清单

#### Scenario: CaptureTrack 唯一约束

- **WHEN** 创建 CaptureTrack
- **THEN** `capture_take_id` + `role` 组合 SHALL 唯一

### Requirement: CaptureTake 生命周期

系统 MUST 管理 CaptureTake 的状态转换。

#### Scenario: 录制停止关闭 CaptureTake（补偿流程）

- **WHEN** 底层录制停止或失败或取消
- **THEN** 系统 SHALL 完成底层录制 JSON 更新后，更新 CaptureTake 的 `status`
- **AND** 系统 SHALL 记录 `ended_at` 和 `duration_ms`
- **AND** 如果 SQLite 更新失败，系统 SHALL 记录 reconciliation_pending
- **AND** 下次查询时 SHALL 执行修复

### Requirement: 旧数据兼容适配

系统 MUST 支持旧 RecordingSession 数据的渐进式适配。

#### Scenario: 读取旧事件时自动适配

- **WHEN** 查询 TimelineEvent 时 `capture_take_id` 为空但 `recording_session_id` 存在
- **THEN** 系统 SHALL 从 RecordingSession 自动创建适配的 CaptureTake
- **AND** `source_session_type` SHALL 设置为 `recording`
- **AND** `capture_mode` SHALL 设置为 `single`

#### Scenario: 不重复适配

- **WHEN** 同一 RecordingSession 已有适配的 CaptureTake
- **THEN** 系统 SHALL 直接返回已存在的 CaptureTake
- **AND** 系统 SHALL 不创建重复的 CaptureTake

### Requirement: CaptureTake 查询

系统 MUST 支持按条件查询 CaptureTake。

#### Scenario: 按 FieldSession 查询

- **WHEN** 用户请求 `GET /api/field-sessions/{id}/capture-takes`
- **THEN** 系统 SHALL 返回该 FieldSession 下的所有 CaptureTake
- **AND** 列表 SHALL 按 `started_at DESC` 排序

#### Scenario: 按状态筛选

- **WHEN** 用户查询时提供 `status` 参数
- **THEN** 系统 SHALL 只返回匹配状态的 CaptureTake

#### Scenario: 获取 CaptureTake 详情

- **WHEN** 用户请求 `GET /api/capture-takes/{id}`
- **THEN** 系统 SHALL 返回 CaptureTake 详情
- **AND** 响应 SHALL 包含关联的 CaptureTrack 列表

### Requirement: 事件时间戳相对 CaptureTake

系统 MUST 保证事件时间戳相对 CaptureTake 开始时间，不受 Track 偏移影响。

#### Scenario: 事件时间戳统一

- **WHEN** 在 CaptureTake 上创建 TimelineEvent
- **THEN** 事件的 `timestamp_ms` SHALL 相对 CaptureTake 开始时间
- **AND** 不受 CaptureTrack 偏移影响

#### Scenario: 计算 Track 相对时间

- **WHEN** 需要获取事件在特定 Track 上的相对时间
- **THEN** 系统 SHALL 计算 `track_relative_ms = timestamp_ms - track.offset_ms`
- **AND** 该值可用于定位 Track 对应的视频文件时间

#### Scenario: Track offset 不参与事件保存

- **WHEN** 创建事件时
- **THEN** 系统 SHALL 不将 Track offset 写入事件的 `timestamp_ms`
- **AND** offset 仅在读取时用于时间映射计算

### Requirement: CaptureTake 同步锚点时间线资产

系统 SHALL 将双摄同步锚点草稿、人工确认元数据和拟合 calibration 作为 CaptureTake 的版本化时间线资产持久化，并 SHALL 通过 CaptureTake 查询或专用 API 暴露当前状态摘要。AnalysisJob SHALL 引用该录制级权威结果，而不是复制一套任务级锚点。

#### Scenario: 保存录制级同步锚点
- **WHEN** 用户为双摄 CaptureTake 保存锚点草稿或确认结果
- **THEN** 资产 SHALL 写入该 CaptureTake 的时间线存储边界
- **AND** SHALL 记录 CaptureTake id、revision、camera identity、registered video identity 和 timing provenance

#### Scenario: 分析任务读取同步资产
- **WHEN** 系统为 CaptureTake 创建双摄 AnalysisJob
- **THEN** preflight SHALL 解析当前有效的录制级同步 calibration revision
- **AND** AnalysisJob SHALL NOT 创建独立且不可复用的锚点副本

#### Scenario: CaptureTake 详情暴露摘要
- **WHEN** 客户端查询双摄 CaptureTake 的同步锚点状态
- **THEN** API SHALL 返回状态、是否允许分析、来源、质量摘要、当前 revision 和失效原因
- **AND** 客户端 SHALL NOT 需要读取服务端文件系统路径推断状态

### Requirement: 同步锚点资产失效边界

系统 SHALL 基于素材 provenance 判断 CaptureTake 的人工同步确认是否仍然有效。会改变跨摄时间映射的素材或 timing 变化 SHALL 产生失效状态；AnalysisJob 生命周期和分析配置变化 SHALL 与录制级同步资产隔离。

#### Scenario: timing provenance 变化
- **WHEN** registered video 或 PTS sidecar 被重新生成且 identity 与确认版本不一致
- **THEN** 当前确认 SHALL 标记失效
- **AND** 旧 revision SHALL 保留用于审计

#### Scenario: 新建或删除 AnalysisJob
- **WHEN** 用户基于同一 CaptureTake 新建、重试或删除 AnalysisJob
- **THEN** CaptureTake 的同步锚点 revision SHALL NOT 因此改变
- **AND** 有效确认 SHALL 继续可复用

