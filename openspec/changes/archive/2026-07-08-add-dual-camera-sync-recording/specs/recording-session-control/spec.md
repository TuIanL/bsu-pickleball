## ADDED Requirements

### Requirement: 双摄同步录制控制入口
系统 SHALL 在录制控制层支持双摄同步录制入口，并保持单摄录制入口不变。

#### Scenario: 单摄采集任务继续使用单摄录制
- **WHEN** Field Session 的 `camera_setup` 为 `single` 或 `debug_single`
- **THEN** 系统继续调用现有单摄录制 API 开始和停止录制
- **AND** 系统返回现有 Recording Session 响应结构

#### Scenario: 双摄采集任务使用同步录制
- **WHEN** Field Session 的 `camera_setup` 为 `dual` 且用户点击开始同步录制
- **THEN** 系统调用双摄同步录制 API
- **AND** 系统将返回的双摄同步录制会话作为当前活跃录制
- **AND** 系统使用双摄会话 ID 停止该录制

### Requirement: 录制占用保护
系统 SHALL 防止同一摄像头同时参与单摄录制和双摄同步录制。

#### Scenario: 单摄录制占用双摄摄像头
- **WHEN** 用户尝试开始双摄同步录制且任一摄像头正在单摄录制
- **THEN** 系统拒绝开始双摄同步录制
- **AND** 系统返回状态冲突错误

#### Scenario: 双摄录制占用单摄摄像头
- **WHEN** 用户尝试开始单摄录制且该摄像头正在双摄同步录制中
- **THEN** 系统拒绝开始单摄录制
- **AND** 系统返回状态冲突错误

### Requirement: 双摄录制停止与终态
系统 SHALL 支持停止、查询和恢复展示双摄同步录制的终态。

#### Scenario: 停止双摄同步录制
- **WHEN** 用户停止当前双摄同步录制
- **THEN** 系统调用双摄停止 API
- **AND** 系统将前端状态切换到 stopped
- **AND** 系统展示双摄录制完成信息

#### Scenario: 双摄录制异常终止
- **WHEN** 双摄同步录制服务将会话标记为 failed
- **THEN** 前端查询状态时展示失败状态和错误信息
- **AND** 系统释放两个摄像头的录制占用
