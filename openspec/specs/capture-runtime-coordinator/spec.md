# capture-runtime-coordinator Specification

## Purpose

定义录制轨道启动、停止、退出事件消费和故障恢复预算的统一编排规则，确保多轨运行状态可恢复且不会重复启动。

## Requirements

### Requirement: Coordinator 编排轨道运行与故障恢复

系统 MUST 提供 `CaptureRuntimeCoordinator` 用单一控制线程消费 TrackRuntimeEvent，不让多个 TrackRecorder 回调直接并发修改 CaptureTake。

#### Scenario: start 同时启动所有轨道

- **WHEN** 调用 `coordinator.start_tracks(tracks, policy)`
- **THEN** MUST 为每个 CaptureTrack 调用 TrackRecorder.start_fragment()
- **AND** MUST 记录每个 Fragment 的 fragment_index（per-track）+ rotation_index（全组）
- **AND** 所有轨道 MUST 在 start 时共享同一个 rotation_index

#### Scenario: FragmentExit 通过事件队列消费

- **WHEN** 某 TrackRecorder 的 on_exit 回调触发
- **THEN** Coordinator MUST 将事件入队
- **AND** 控制线程 MUST 按序消费事件
- **AND** MUST NOT 在 on_exit 回调中直接修改 CaptureTake

#### Scenario: stop 禁止新 fragment 并停止全部

- **WHEN** 调用 `coordinator.stop_tracks()`
- **THEN** MUST 禁止启动新 Fragment
- **AND** MUST 停止全部 TrackRecorder
- **AND** MUST 等待所有线程退出
- **AND** MUST 持久化所有 Fragment 终态
- **AND** MUST 返回 Fragment 列表供 Finalizer 处理

#### Scenario: 重启预算耗尽后标记不可恢复

- **WHEN** 某轨道 fragment 重启次数超过 max_restart_attempts
- **AND** 该轨道为主轨（analysis_role=default）
- **THEN** CaptureTake MUST 标记为 failed
- **WHEN** 失败轨为辅轨
- **THEN** CaptureTake MUST 标记为 partial
