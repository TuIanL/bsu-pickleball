## MODIFIED Requirements

### Requirement: 录制启动使用用户选择 FPS
系统 SHALL 在单摄和双摄实时录制启动时使用用户选择的 FPS，并将该 FPS 保存到录制 session。录制入口 MUST 默认选择 60fps，且实时录制请求的 FPS MUST NOT 超过 60fps。

#### Scenario: 单摄录制默认使用 60fps
- **WHEN** 用户进入单摄录制界面且尚未手动修改视频帧率
- **THEN** 前端提交的 `POST /api/recordings/start` 请求 MUST 包含 `fps=60`
- **AND** 录制 session metadata SHALL 保存 `fps=60`

#### Scenario: 单摄录制不使用硬编码高 FPS
- **WHEN** 用户在单摄录制界面选择 60fps 并点击开始录制
- **THEN** 前端提交的 `POST /api/recordings/start` 请求 MUST 包含 `fps=60`
- **AND** 请求 MUST NOT 使用硬编码 90fps 覆盖用户选择

#### Scenario: 双摄录制默认使用 60fps
- **WHEN** 用户进入双摄同步录制界面且尚未手动修改视频帧率
- **THEN** 前端提交的 `POST /api/sync-recordings/start` 请求 MUST 包含 `fps=60`
- **AND** 双摄录制 session metadata SHALL 保存 `fps=60`

#### Scenario: 双摄录制不使用硬编码高 FPS
- **WHEN** 用户在双摄录制界面选择 60fps 并点击开始同步录制
- **THEN** 前端提交的同步录制启动请求 MUST 包含 `fps=60`
- **AND** 请求 MUST NOT 使用硬编码 90fps 或 30fps 覆盖用户选择

#### Scenario: 录制入口不提供超过 60fps 的选项
- **WHEN** 用户打开单摄或双摄实时录制的 FPS 选择控件
- **THEN** 控件 MUST 提供 60fps 选项
- **AND** 控件 MUST NOT 提供 90fps 或 120fps 录制选项

#### Scenario: 后端拒绝超过 60fps 的录制请求
- **WHEN** 客户端提交 `POST /api/recordings/start` 或 `POST /api/sync-recordings/start` 且 `fps > 60`
- **THEN** 系统 MUST 拒绝该请求
- **AND** 系统 MUST NOT 启动任何 FFmpeg 录制进程

#### Scenario: 录制 FPS 用于后续分析预填
- **WHEN** 录制 session 完成并注册为可分析视频
- **THEN** 系统 SHALL 在录制 session metadata 中保留启动时选择的 FPS
- **AND** 从该录制创建分析任务时 SHALL 使用该 FPS 作为默认源视频 FPS
