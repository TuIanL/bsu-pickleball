## Purpose

Define the local developer commands used to start and stop the RTMPose-enabled analysis runtime.
## Requirements
### Requirement: One-command local startup

系统 SHALL 提供单命令启动 API、独立 analysis-worker 和前端。默认基础模式 SHALL 不依赖模型文件；显式启用模型时 SHALL 在启动前验证依赖及权重。API 与 Worker SHALL 使用一致分析配置。

#### Scenario: Start command launches runtime
- **WHEN** 开发者运行本地启动命令且未显式启用模型
- **THEN** 系统 SHALL 启动 API（embedded Worker 关闭）、独立 Worker 和前端，并分别记录 PID/日志
- **AND** 缺少 YOLO、RTMPose、场线权重 SHALL 不阻止基础模式启动，模型相关能力 SHALL 明确不可用

#### Scenario: 显式模型模式
- **WHEN** 开发者显式启用 RTMPose 或其他模型
- **THEN** 系统 SHALL 预检对应运行依赖、配置与可信本地权重，失败时在启动进程前退出并解释原因
- **AND** RTMPose 成功配置 SHALL 保留可信 checkpoint 加载兼容，API 与 Worker SHALL 接收相同设置

#### Scenario: Start command detects occupied ports
- **WHEN** 后端或前端所需端口被占用
- **THEN** 命令 SHALL 在启动新进程前失败并报告冲突端口

#### Scenario: API reload does not restart Worker
- **WHEN** API 因源码变化 reload
- **THEN** 独立 Worker SHALL 保持运行，PID/日志 SHALL 继续可被停止命令识别

### Requirement: One-command local shutdown

The project SHALL provide a single local command that stops the local analysis-worker, backend API and frontend processes launched by the startup command.

#### Scenario: Stop command shuts down runtime

- **WHEN** a developer runs the local shutdown command after using the startup command
- **THEN** the command stops the recorded analysis-worker, backend and frontend processes
- **AND** clears their runtime PID files after successful shutdown

#### Scenario: Stop command handles stale state

- **WHEN** a recorded process is no longer running
- **THEN** the command removes the stale PID file without failing the shutdown workflow

#### Scenario: Worker shutdown is graceful when possible

- **WHEN** the shutdown command sends a normal termination signal to analysis-worker
- **THEN** Worker SHALL stop claiming new jobs and attempt to exit at a safe checkpoint
- **AND** a forced termination SHALL be recoverable by the next startup heartbeat reconciliation

### Requirement: Local runtime documentation

项目 SHALL 文档化基础与模型两种配置、API/Worker/前端角色、PID/日志、心跳超时及优雅停止和失联的区别。

#### Scenario: Developer reads runtime docs
- **WHEN** 开发者按文档从干净环境安装并运行
- **THEN** 基础命令 SHALL 不要求私有媒体或个人模型路径，模型配置 SHALL 列出独立安装、权重及校验步骤
- **AND** 文档 SHALL 给出停止流程和 Worker liveness 检查方法
