# recording-session-control Specification

## Purpose
管理录制会话的完整生命周期，包括单摄分片录制、停止录制、录制异常处理、录制会话状态管理、RecordingSession 数据模型和双摄录制的停止与终态。

## Requirements
### Requirement: 单摄分片录制

系统 MUST 将单摄录制改为 TrackRecorder × 1 + SingleTrackRestartPolicy，stop 时通过 CaptureFinalizer 合并 TS 片段为 MP4。

#### Scenario: 单摄录制生成 TS 分片

- **WHEN** 单摄录制启动
- **THEN** TrackRecorder MUST 录制 TS 格式分片（非直接 MP4）
- **AND** 每次 FFmpeg 启动 MUST 创建新的 MediaFragment 记录

#### Scenario: 单摄 stop 同步合并 TS 片段

- **WHEN** 单摄 stop 被调用
- **THEN** Finalizer MUST 同步完成合并（不异步返回）
- **AND** 合并成功后 MUST 返回 completed + CaptureStopResult
- **AND** 合并超时（finalizer_timeout_seconds=60）MUST 返回 partial + warnings

### Requirement: 停止录制

**变更**：修复停止路由在媒体已成功停止后因响应组装错误返回 HTTP 500 的问题。

**修改前**：`POST /api/recordings/{session_id}/stop` 路由在调用 `session_service.stop_session()` 成功后，组装 `CaptureStopResult` 时调用未导入的 `get_session_factory()`，抛出 `NameError`，返回 HTTP 500。

**修改后**：系统 SHALL 在停止路由中正确导入 `get_session_factory`。
- 停止端点 SHALL 在 `session_service.stop_session()` 成功后返回 HTTP 200
- 停止端点 SHALL 返回完整的 `CaptureStopResult`，包含 `capture_take`、`tracks`（长度为 1）、`default_analysis_video_id`、`analysis_available`
- 停止端点 SHALL NOT 因响应组装阶段的 import 错误而抛出未处理异常

### Requirement: 录制异常处理

系统 MUST 在单摄迁移到 TrackRecorder × 1 + CaptureFinalizer 后，支持分片级异常恢复。FFmpeg 异常退出时 MUST 生成下一个 Fragment 而非整场 failed。

#### Scenario: 单摄 FFmpeg 异常退出后重启新 Fragment

- **WHEN** 单摄 TrackRecorder 中 FFmpeg 意外退出且重启预算未耗尽
- **THEN** 系统 MUST 记录 Fragment status=failed
- **AND** MUST 在退避后启动新的 Fragment（fragment_index+1）
- **AND** MUST NOT 标记 RecordingSession.status=failed

#### Scenario: 单摄 stop 后合并所有有效 Fragment

- **WHEN** 单摄录制正常停止
- **THEN** CaptureFinalizer MUST 合并所有 completed 和 interrupted 但可读的 Fragment
- **AND** MUST 生成一个完整 MP4
- **AND** 最终 MP4 时长 MUST 排除 fragment 间 gap

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
