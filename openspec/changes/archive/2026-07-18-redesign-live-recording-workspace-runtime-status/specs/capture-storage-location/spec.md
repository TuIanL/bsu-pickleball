## ADDED Requirements

### Requirement: 运行时存储容量查询

系统 SHALL 在录制运行状态快照中返回当前 CaptureTake 实际存储根目录的总容量、已用容量、可用容量和可用性状态。

#### Scenario: 自定义存储位置

- **WHEN** 当前录制使用用户选择的自定义存储根目录
- **THEN** 运行状态 SHALL 读取该目录所在文件系统的容量
- **AND** 不得读取默认录制目录代替实际目录

#### Scenario: 默认存储位置

- **WHEN** 当前录制使用默认存储根目录
- **THEN** 运行状态 SHALL 读取默认目录所在文件系统的真实容量

### Requirement: 存储运行故障反馈

运行状态接口 SHALL 将存储目录不可访问、不可写或容量读取失败表达为明确的错误状态，并将错误信息传递给工作台。

#### Scenario: 录制中存储不可用

- **WHEN** 当前会话目录所在介质在录制中不可访问
- **THEN** 运行状态 SHALL 返回 storage status 为 `error`
- **AND** SHALL 包含不会泄露无关路径的可读错误描述
