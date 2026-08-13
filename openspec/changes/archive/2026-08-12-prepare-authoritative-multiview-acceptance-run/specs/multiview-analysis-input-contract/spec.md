## ADDED Requirements

### Requirement: Historical registered video index repair

对于历史 CaptureTake，系统 SHALL 在创建 joint input 前核对 SQLite CaptureTrack、CaptureTake session metadata、manifest 和 VideoService registered video metadata。若 CaptureTrack `video_id` 缺失但 session metadata 明确提供与 camera/slot 一致的 registered video id，系统 SHALL 通过幂等 repair operation 补齐该索引及相关 timing provenance。

#### Scenario: manifest 与 track 一致
- **WHEN** session metadata 中 registered video id 对应的文件存在，且 camera identity、slot 和 take directory 一致
- **THEN** 系统 SHALL 将其绑定到对应 CaptureTrack
- **AND** 后续 `jointViewInputs.videoId` SHALL 使用该 registered video id

#### Scenario: manifest 与 track 冲突
- **WHEN** registered video 文件不存在、camera identity 不一致或多个候选无法唯一匹配
- **THEN** preflight SHALL 返回结构化 input error
- **AND** SHALL NOT 按 cam slot 猜测或创建半成品 joint Parent

### Requirement: Prepared input bundle completeness

允许创建 `joint_tracking_v2` 的 input bundle SHALL 同时包含两路可读 registered video、两路 calibration、明确 court orientation、两路 source timing provenance、camera identity matching 的 sync calibration 和 canonical frame reference。任何缺项 SHALL 在任务创建前报告。

#### Scenario: 历史 take 准备完成
- **WHEN** 两路 video id/index、sidecar、calibration、orientation、sync mapping 和 canonical frame 均通过校验
- **THEN** preflight SHALL 允许持久化完整 `jointViewInputs`
- **AND** Parent 重启后 SHALL 能仅凭持久化 input 重建 JointRun

#### Scenario: timing 或 sync 未准备完成
- **WHEN** 任一路 source timing 缺失或 sync calibration 不可用
- **THEN** preflight SHALL 返回 take_dir、期望 artifact 路径、缺失字段和修复建议
- **AND** SHALL NOT 静默创建 authoritative joint task
