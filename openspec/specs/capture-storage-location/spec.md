# capture-storage-location Specification

## Purpose
管理每次单摄或双摄录制的临时存储位置、会话目录结构、目录复用和存储故障处理，并明确路径隔离、清理和恢复时的可验证边界。

## Requirements
### Requirement: 原生目录选择与本次录制作用域

系统 SHALL 通过本地应用提供的原生目录选择器让用户选择录制存储根目录。用户选择 SHALL 只对当前录制生效；用户未选择目录时 SHALL 使用当前标准默认目录，且每次新建录制都重新回到该默认目录。

#### Scenario: 使用默认录制位置
- **WHEN** 用户未选择自定义目录并开始单摄或双摄录制
- **THEN** 系统 SHALL 使用当前标准默认目录
- **AND** 不得读取或复用上一次录制的自定义目录

#### Scenario: 使用移动硬盘位置
- **WHEN** 用户通过原生目录选择器选择一个可写的移动硬盘目录并开始录制
- **THEN** 系统 SHALL 将该目录作为当前录制的存储根目录
- **AND** 不得要求用户修改代码或环境变量

### Requirement: 存储目录规范化与会话目录唯一性

系统 SHALL 将录制文件保存到 `captures/<日期>/<capture_take_id>/` 会话目录。若用户选择的目录已经是 `captures` 目录，系统 SHALL 直接复用该目录；不得创建 `captures/captures`。同一日期的每次新录制 SHALL 使用新的 `capture_take_id`。

#### Scenario: 重新选择已有存储根目录
- **WHEN** 用户在后续日期再次选择已有录制目录并开始录制
- **THEN** 系统 SHALL 识别已有 `captures` 目录
- **AND** SHALL 创建新的日期或新的 take 会话目录
- **AND** SHALL 保留历史录制且不得覆盖或复制历史目录

#### Scenario: 同一天多次录制
- **WHEN** 用户在同一日期连续创建多个录制
- **THEN** 每次录制 SHALL 位于独立的 `capture_take_id` 目录
- **AND** 任一录制不得覆盖另一录制的视频、事件或分析文件

### Requirement: 会话文件完整归档

系统 SHALL 在同一个会话目录中保存该次录制的视频、分片、录制元数据、事件、标记、时间线快照和分析文件。SQLite SHALL 继续保存应用索引、状态和关系，但不得替代会话目录中的文件归档。

#### Scenario: 单摄录制归档
- **WHEN** 单摄录制完成或失败
- **THEN** 会话目录 SHALL 至少包含单摄媒体、metadata、timeline 和 manifest
- **AND** 若触发分析，分析产物 SHALL 位于该会话目录的 analysis 子目录

#### Scenario: 双摄录制归档
- **WHEN** 双摄录制完成或失败
- **THEN** 会话目录 SHALL 保存 cam_1 和 cam_2 的分片及最终视频（若可用）
- **AND** 两路事件、标记和时间线 SHALL 归属于同一个 capture_take_id

#### Scenario: 实时事件归档
- **WHEN** 录制过程中用户创建或修改事件、标记或时间线
- **THEN** 系统 SHALL 将可恢复的事件状态同步写入当前会话目录
- **AND** SQLite 中 SHALL 保留对应索引记录

### Requirement: 目录可用性与空间校验

系统 SHALL 在启动录制前确认目标目录可访问、可写、可创建会话目录，并满足配置的最低剩余空间要求。校验失败时不得创建 FFmpeg 录制进程。

#### Scenario: 目标目录不可写
- **WHEN** 原生选择器返回不存在、无权限或不可创建文件的目录
- **THEN** 系统 SHALL 拒绝开始录制
- **AND** SHALL 返回可理解的目录错误
- **AND** 不得占用摄像头或启动 FFmpeg

#### Scenario: 目标空间不足
- **WHEN** 目标目录剩余空间低于单摄或双摄录制的最低要求
- **THEN** 系统 SHALL 拒绝开始录制
- **AND** SHALL 显示空间不足原因

### Requirement: 存储中断失败处理

系统 SHALL 将录制期间目标介质消失、目录不可写、I/O 错误或会话文件无法持续写入视为本次录制失败。系统 SHALL 立即停止所有相关录制轨道、保留已完成文件、标记 CaptureTake 和源会话为 failed、释放 CameraLease，并禁止自动分析。

#### Scenario: 移动硬盘被拔出
- **WHEN** 录制期间系统检测到会话目录所在移动硬盘不可访问
- **THEN** 系统 SHALL 立即停止单摄或双摄所有相关 FFmpeg/TrackRecorder
- **AND** CaptureTake SHALL 标记为 failed
- **AND** 源 RecordingSession 或 SyncRecordingSession SHALL 标记为 failed
- **AND** 系统 SHALL 释放所有摄像头占用

#### Scenario: 存储故障保留现场
- **WHEN** 存储故障发生且已有媒体片段或事件快照写入磁盘
- **THEN** 系统 SHALL 尽可能保留已写入内容和失败 manifest
- **AND** SHALL 记录包含存储路径的错误原因
- **AND** 不得自动切换到默认目录继续录制

### Requirement: 会话目录安全清理与兼容读取

系统 SHALL 根据 SQLite 索引和 manifest 定位新会话目录，删除或取消时不得删除会话目录之外的路径。没有新存储字段的历史会话 SHALL 继续使用其现有路径读取。

#### Scenario: 删除新会话
- **WHEN** 用户删除一个已终态的新存储会话
- **THEN** 系统 SHALL 只删除该 capture_take_id 对应的会话目录
- **AND** 不得删除同一日期的其他录制或 captures 根目录

#### Scenario: 读取历史会话
- **WHEN** 用户打开存储位置功能上线前创建的录制
- **THEN** 系统 SHALL 根据旧的 video_path、output_dir 或全局 artifact 路径读取
- **AND** 不得要求历史录制重新迁移

### Requirement: 运行时存储容量查询

系统 SHALL 在录制运行状态快照中返回当前 CaptureTake 实际存储根目录的总容量、已用容量、可用容量和可用性状态。

#### Scenario: 自定义存储位置

- **WHEN** 当前录制使用用户选择的自定义存储根目录
- **THEN** 运行状态 SHALL 读取该目录所在文件系统的容量
- **AND** 不得读取默认录制目录代替实际目录

#### Scenario: 默认存储位置

- **WHEN** 当前录制使用默认存储根目录
- **THEN** 运行状态 SHALL 读取默认目录所在文件系统的真实容量

### Requirement: 存储运行故障反馈

运行状态接口 SHALL 将存储目录不可访问、不可写或容量读取失败表达为明确的错误状态，并将错误信息传递给工作台。

#### Scenario: 录制中存储不可用

- **WHEN** 当前会话目录所在介质在录制中不可访问
- **THEN** 运行状态 SHALL 返回 storage status 为 `error`
- **AND** SHALL 包含不会泄露无关路径的可读错误描述
