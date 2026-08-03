# track-recorder Specification

## Purpose

定义单轨 FFmpeg Fragment 的启动、优雅停止、强制取消、异常退出通知和重复停止幂等行为。

## Requirements

### Requirement: TrackRecorder 管理单轨 FFmpeg 进程

系统 MUST 提供独立 `TrackRecorder` 组件，管理一个 CaptureTrack 的当前一个 FFmpeg 进程，完成一个 MediaFragment 生命周期。TrackRecorder 通过注入 `ProcessFactory`、`ProcessRegistry`、`Clock` 实现可单测。

#### Scenario: start_fragment 启动并登记

- **WHEN** 调用 `start_fragment(FragmentStartSpec, on_exit)`
- **THEN** MUST 构建 FFmpeg 命令（TS 格式输出）
- **AND** MUST 通过 ProcessFactory 启动子进程（start_new_session=True）
- **AND** MUST 通过 ProcessRegistry.register_started() 登记 pid/pgid/fingerprint
- **AND** MUST 启动监控线程等待进程退出
- **AND** MUST 返回 FragmentHandle

#### Scenario: stop_fragment 优雅停止

- **WHEN** 调用 `stop_fragment(reason=USER_STOPPED, timeout=10)`
- **THEN** MUST 向 FFmpeg 写入 'q' 等待优雅退出
- **AND** 超时后 MUST force kill
- **AND** MUST 通过 ProcessRegistry.register_ended() 更新退出信息
- **AND** MUST 调用 on_exit 回调
- **AND** MUST 返回 FragmentResult(status=completed, return_code, file_size)

#### Scenario: cancel_fragment 强制停止

- **WHEN** 调用 `cancel_fragment()`
- **THEN** MUST 立即 kill 进程
- **AND** MUST 通过 ProcessRegistry.register_ended()
- **AND** MUST 返回 FragmentResult(status=discarded)

#### Scenario: 意外退出通过 on_exit 通知

- **WHEN** FFmpeg 进程在无 stop/cancel 情况下退出
- **THEN** MUST 通过 on_exit 回调通知 FragmentExit(return_code, unexpected=True)
- **AND** MUST 通过 ProcessRegistry.register_ended()

#### Scenario: 重复停止幂等

- **WHEN** 对已停止的 Fragment 再次调用 stop_fragment
- **THEN** MUST 不报错，返回已有 FragmentResult
