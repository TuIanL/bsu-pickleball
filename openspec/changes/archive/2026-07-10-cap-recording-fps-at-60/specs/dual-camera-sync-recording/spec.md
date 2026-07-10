## ADDED Requirements

### Requirement: 双摄同步录制 FPS 上限
系统 SHALL 将双摄同步录制的默认 FPS 和最高允许 FPS 设为 60fps。

#### Scenario: 双摄同步录制默认 60fps
- **WHEN** 用户打开双摄同步录制控制台且未手动修改视频帧率
- **THEN** FPS 控件 MUST 默认显示 60fps
- **AND** 开始同步录制请求 MUST 使用 `fps=60`

#### Scenario: 双摄同步录制选项最高为 60fps
- **WHEN** 用户查看双摄同步录制 FPS 控件
- **THEN** 控件 MUST 提供 60fps 选项
- **AND** 控件 MUST NOT 提供 90fps 或 120fps 选项

#### Scenario: 双摄同步录制 API 拒绝超过 60fps
- **WHEN** 客户端提交 `POST /api/sync-recordings/start` 且 `fps > 60`
- **THEN** 系统 MUST 拒绝该请求
- **AND** 系统 MUST NOT 创建双摄同步录制会话
- **AND** 系统 MUST NOT 启动任何 FFmpeg 录制进程
