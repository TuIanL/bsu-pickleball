## MODIFIED Requirements

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

## ADDED Requirements

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
