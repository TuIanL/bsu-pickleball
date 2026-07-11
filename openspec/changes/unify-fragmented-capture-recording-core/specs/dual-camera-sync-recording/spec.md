## MODIFIED Requirements

### Requirement: 同步分段与异常重启

系统 MUST 将 SyncRecorder 迁移为 TrackRecorder × 2 + CaptureRuntimeCoordinator + StrictSyncPolicy。

#### Scenario: 双摄任一路失败全组同步重启

- **WHEN** 任一 TrackRecorder Fragment 意外退出
- **AND** 策略为 StrictSyncPolicy
- **THEN** Coordinator MUST 停止全部 TrackRecorder
- **AND** MUST 使用新的 rotation_index 同步重启两路
- **AND** 两路的新 fragment_index MUST 各自递增
- **AND** rotation_index MUST 递增

#### Scenario: 双摄使用 PreservePrimaryPolicy

- **WHEN** 双摄配置为 PreservePrimaryPolicy
- **AND** 辅轨（cam_2）Fragment 意外退出
- **THEN** Coordinator MUST 仅重启辅轨
- **AND** 主轨（cam_1）MUST 继续录制
- **AND** 辅轨 fragment_index 递增，rotation_index 不变

#### Scenario: 双摄停止后合并两路 MP4

- **WHEN** 双摄正常停止
- **THEN** CaptureFinalizer MUST 为 cam_1 和 cam_2 分别合并有效 Fragment
- **AND** cam_1 合并后 MUST 登记为 default_analysis_video_id
