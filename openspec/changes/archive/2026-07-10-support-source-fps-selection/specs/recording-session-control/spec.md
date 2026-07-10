## ADDED Requirements

### Requirement: 录制启动使用用户选择 FPS
系统 SHALL 在单摄和双摄实时录制启动时使用用户选择的 FPS，并将该 FPS 保存到录制 session。

#### Scenario: 单摄录制不使用硬编码 FPS
- **WHEN** 用户在单摄录制界面选择 60fps 并点击开始录制
- **THEN** 前端提交的 `POST /api/recordings/start` 请求 MUST 包含 `fps=60`
- **AND** 请求 MUST NOT 使用硬编码 90fps 覆盖用户选择

#### Scenario: 双摄录制不使用硬编码 FPS
- **WHEN** 用户在双摄录制界面选择 90fps 并点击开始同步录制
- **THEN** 前端提交的同步录制启动请求 MUST 包含 `fps=90`
- **AND** 请求 MUST NOT 使用硬编码 30fps 覆盖用户选择

#### Scenario: 录制 FPS 用于后续分析预填
- **WHEN** 录制 session 完成并注册为可分析视频
- **THEN** 系统 SHALL 在录制 session metadata 中保留启动时选择的 FPS
- **AND** 从该录制创建分析任务时 SHALL 使用该 FPS 作为默认源视频 FPS
