## MODIFIED Requirements

### Requirement: 录制会话生命周期

录制会话 MUST 遵循严格的状态机。`field_session_id` 为必填参数。启动流程通过 `CaptureStartCoordinator` 在单事务中创建 Take + Tracks + Leases，并 SHALL 在启动 FFmpeg 前解析、校验并记录本次录制的会话存储目录。

#### Scenario: 开始录制
- **WHEN** 用户提交 `POST /api/recordings/start` 或 `POST /api/sync-recordings/start`，提供摄像头配置、`field_session_id` 和可选 `storage_root`
- **THEN** 系统 SHALL 校验并创建唯一会话目录
- **AND** SHALL 在事务或等价的启动元数据中记录实际会话目录
- **AND** 目录校验成功后才创建 CaptureTake、CaptureTrack、CameraLease 并启动 FFmpeg
- **AND** 目标目录不可用时不得启动 FFmpeg
- **AND** 返回的录制会话 SHALL 能查询实际会话目录引用

#### Scenario: 停止录制
- **WHEN** 用户请求停止单摄或双摄录制
- **THEN** 系统 SHALL 停止相关 FFmpeg/TrackRecorder
- **AND** SHALL 在实际会话目录写入最终 manifest 和事件/时间线快照
- **AND** 正常完成时 Session.status 更新为 `completed`
- **AND** 显式调用 `finalize_capture_take(capture_take_id, "completed")`
- **AND** 通过统一 Builder 返回 `CaptureStopResult`

#### Scenario: 存储故障停止录制
- **WHEN** 录制过程中会话目录所在介质不可写或消失
- **THEN** 系统 SHALL 立即停止所有相关轨道
- **AND** Session.status 与 CaptureTake.status SHALL 更新为 `failed`
- **AND** SHALL 记录存储错误并释放所有 CameraLease
- **AND** SHALL 不触发自动分析

### Requirement: RecordingSession 数据模型

系统 MUST 在 `RecordingSession` 中保存录制生命周期字段，并 MAY 保存其所属 Field Session。对于正式录制，系统 SHALL 额外保存本次录制的存储根目录引用、会话目录引用和存储状态；这些字段缺失时历史会话 SHALL 按 legacy 路径兼容读取。

#### Scenario: 新会话记录存储位置
- **WHEN** 单摄或双摄录制成功启动
- **THEN** RecordingSession 或对应同步会话 SHALL 保存规范化后的存储根目录引用
- **AND** SHALL 保存 `captures/<日期>/<capture_take_id>/` 会话目录引用

#### Scenario: 旧会话模型兼容
- **WHEN** 读取没有存储目录字段的历史会话
- **THEN** 系统 SHALL 使用已有 `video_path`、`output_dir` 或 artifact path
- **AND** 不得因为新增字段为空而判定历史会话损坏

### Requirement: 双摄录制停止与终态

系统 SHALL 支持停止、查询和恢复展示双摄同步录制的终态，并 SHALL 使用双摄会话记录的实际存储目录解析两路媒体、事件和分析文件。

#### Scenario: 停止双摄同步录制
- **WHEN** 用户停止当前双摄同步录制
- **THEN** 系统 SHALL 终止两路 FFmpeg 进程并等待线程退出
- **AND** SHALL 在同一 capture_take 会话目录完成两路文件收尾
- **AND** 系统 SHALL 展示双摄录制完成信息（含 analysis_available 判断）

#### Scenario: 双摄录制存储异常
- **WHEN** 双摄会话目录不可写
- **THEN** 系统 SHALL 同时停止两路录制
- **AND** SHALL 将同步会话和 CaptureTake 标记为 failed
- **AND** SHALL 释放两个摄像头的录制占用
