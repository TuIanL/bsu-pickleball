## ADDED Requirements

### Requirement: 创建分析任务携带源 FPS
系统 SHALL 在上传视频和录制视频创建分析任务时携带用户确认的源视频 FPS。

#### Scenario: 上传视频分析任务包含 FPS
- **WHEN** 用户上传本地视频并提交真实分析任务
- **THEN** 创建分析任务请求 MUST 包含用户确认的源视频 FPS
- **AND** 后端 MUST 将该 FPS 保存到任务 metadata 或 pipeline options

#### Scenario: 已有 videoId 的录制视频可提交
- **WHEN** 用户从录制完成页进入创建分析任务页面且 URL 包含 `videoId`
- **THEN** 页面 SHALL 允许在没有本地 `selectedFile` 的情况下提交分析任务
- **AND** 任务 MUST 使用该 `videoId`、标定结果和用户确认 FPS 创建

#### Scenario: 任务页面展示 FPS 输入状态
- **WHEN** 创建分析任务页面已从视频 metadata 或录制 session 获得 FPS
- **THEN** 页面 SHALL 展示该 FPS 作为默认值
- **AND** 用户修改后提交的值 MUST 覆盖默认值
