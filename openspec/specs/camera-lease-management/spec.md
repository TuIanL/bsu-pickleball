# camera-lease-management Specification

## Purpose

定义摄像轨道 FFmpeg 进程登记、注入式 ProcessRegistry、退出记录和启动恢复清理的统一契约。

## Requirements

### Requirement: FFmpeg 进程登记与启动恢复

系统 MUST 将 ProcessRegistry 改为注入式公共服务，增加 fragment_id / return_code / exit_reason 字段。启动恢复 MUST 按 fragment 级清理孤儿进程。

#### Scenario: Fragment 启动时通过 ProcessRegistry 登记

- **WHEN** TrackRecorder.start_fragment() 启动 FFmpeg
- **THEN** ProcessRegistry.register_started() MUST 记录 capture_take_id、capture_track_id、fragment_id、pid、pgid、command_fingerprint、output_path

#### Scenario: Fragment 结束时更新 registry

- **WHEN** FFmpeg 进程退出
- **THEN** ProcessRegistry.register_ended() MUST 记录 return_code、exit_reason、ended_at

#### Scenario: 启动恢复按 fragment 级清理

- **WHEN** 应用启动且发现 ended_at IS NULL 的 registry 记录
- **THEN** MUST 查询对应 MediaFragment
- **AND** 如果 Fragment.status 仍在 recording → MUST 标记为 interrupted
- **AND** MUST 校验 PID/PGID/fingerprint 后清理孤儿进程
- **AND** MUST release 关联 CameraLease

### Requirement: ProcessRegistry 注入式接口

系统 MUST 提供 `ProcessRegistry` 注入式公共服务，TrackRecorder 通过构造函数注入，不再通过 Recorder 私有方法调用。

#### Scenario: registry 不依赖 Recorder 全局状态

- **WHEN** TrackRecorder 被实例化
- **THEN** ProcessRegistry MUST 通过构造函数注入
- **AND** MUST NOT 通过 `from app.camera.recorder import ...` 隐式依赖
