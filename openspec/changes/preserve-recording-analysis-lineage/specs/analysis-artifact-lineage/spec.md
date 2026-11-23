# Spec Delta

## ADDED Requirements

### Requirement: 新建任务的产物位置来自可信持久化关系

新建任务的产物读取 SHALL 使用服务端持久化且可核验的位置，按 CaptureTake、RecordingSession、任务级可信持久化位置的顺序解析。较高优先级位置缺失时才可尝试下一层；进程重启后仍 MUST 能从持久化关系恢复。客户端提供的 `metadata.session_dir` MUST NOT 成为产物位置或可信位置的回退值。

#### Scenario: Take 位置可用时优先使用

- **WHEN** CaptureTake 与 RecordingSession 都具有可用的可信产物位置
- **THEN** 系统 SHALL 使用 CaptureTake 关联的位置
- **AND** MUST NOT 使用请求 metadata 中的路径

#### Scenario: Take 位置缺失时使用 Session 位置

- **WHEN** CaptureTake 没有持久化位置而 RecordingSession 有可用位置
- **THEN** 系统 SHALL 使用 RecordingSession 的持久化位置

#### Scenario: Take 与 Session 位置缺失时使用任务级可信位置

- **WHEN** CaptureTake 与 RecordingSession 均没有位置，但任务存在独立于请求 metadata 的可信持久化位置
- **THEN** 系统 SHALL 使用该任务级位置
- **AND** Worker 重启后仍 SHALL 能解析到该位置

#### Scenario: Worker 重启后恢复位置

- **WHEN** 任务创建后 Worker 重启，进程内上下文不再存在
- **THEN** 系统 SHALL 仅凭可信持久化关系恢复产物位置

### Requirement: 客户端路径不得获得产物定位信任

系统 MUST NOT 使用请求提供的路径定位、创建或回退分析产物目录。客户端路径字段 MAY 为兼容而保留，但 MUST NOT 被复制为服务端可信持久化位置。

#### Scenario: HTTP metadata 提供伪造路径

- **WHEN** HTTP 请求在 `metadata.session_dir` 中提供其他目录
- **THEN** 来源判定与产物定位 MUST 不受该值影响
- **AND** 系统 MUST NOT 在该目录读取、写入或创建产物

### Requirement: 存储不可用与历史产物读取保持可区分

系统 SHALL 将可信存储位置离线报告为位置不可用，MUST NOT 静默切换到本地目录。已有历史任务的产物 SHALL 继续通过其既有受控读取路径访问。

#### Scenario: 已登记外接卷离线

- **WHEN** 被选中的可信产物位置指向未挂载或不可读的外接卷
- **THEN** 系统 SHALL 返回 `location_unavailable`
- **AND** MUST NOT 回退到 Session、任务的低优先级路径或本地目录

#### Scenario: 没有可信持久化位置

- **WHEN** CaptureTake、RecordingSession 和任务级可信持久化位置均不可用
- **THEN** 系统 SHALL 返回 `location_unavailable`
- **AND** MUST NOT 从客户端路径推测或创建替代目录

#### Scenario: 历史任务继续使用原有读取路径

- **WHEN** 用户读取迁移前已存在的任务产物
- **THEN** 系统 SHALL 保持原有 Job ID 与受控读取路径
- **AND** MUST NOT 将历史 `metadata.session_dir` 升格为可信产物位置
