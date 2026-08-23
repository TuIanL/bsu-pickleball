# vidat-service-control Specification (delta)

## ADDED Requirements

### Requirement: 本地 Vidat 服务状态
系统 SHALL 提供当前本地 Vidat 静态服务的可区分状态，包括未运行、由本系统运行、由其他进程占用和状态未知。

#### Scenario: 查询受控运行服务
- **WHEN** 用户查询服务状态且服务状态文件、进程归属和 Vidat URL 均有效
- **THEN** 系统 SHALL 返回运行中、URL、PID 是否受本系统控制和启动时间

#### Scenario: 端口被未受控进程占用
- **WHEN** Vidat URL 可访问但进程不属于本系统记录的服务
- **THEN** 系统 SHALL 返回未受控占用状态
- **AND** SHALL 不允许停止接口终止该进程

### Requirement: 启动本地 Vidat 服务
系统 SHALL 允许用户启动受本系统控制的本地 Vidat 静态服务，并避免重复启动。

#### Scenario: 启动服务
- **WHEN** 用户请求启动且没有受控服务运行或端口冲突
- **THEN** 系统 SHALL 启动配置的 Nginx 服务
- **AND** SHALL 记录服务标识、master PID、配置路径、URL 和启动时间
- **AND** SHALL 等待 URL 就绪后返回启动结果

#### Scenario: 重复启动
- **WHEN** 用户请求启动且受控服务已运行
- **THEN** 系统 SHALL 返回已运行状态
- **AND** SHALL 不启动第二个 Nginx master

### Requirement: 停止本地 Vidat 服务
系统 SHALL 允许用户显式停止当前由本系统控制的本地 Vidat 静态服务。

#### Scenario: 服务运行中停止
- **WHEN** 用户在服务运行时请求停止
- **THEN** 系统 SHALL 仅终止状态文件确认归属本系统的 Nginx master
- **AND** SHALL 等待服务地址不可用
- **AND** SHALL 返回停止结果（含地址和最终状态）

#### Scenario: 服务未运行
- **WHEN** 用户请求停止一个未运行的服务
- **THEN** 系统 SHALL 返回“服务未运行”状态
- **AND** SHALL 不产生副作用（不误杀其他进程）

#### Scenario: 停止失败
- **WHEN** 系统无法定位或终止 Nginx 进程
- **THEN** 系统 SHALL 返回明确的停止错误
- **AND** SHALL 保留清晰的失败原因供排查

#### Scenario: PID 已失联但端口仍可访问
- **WHEN** 状态文件记录的 PID 已失效而服务地址仍可访问
- **THEN** 系统 SHALL 返回状态异常
- **AND** SHALL 不执行无归属的端口级 kill
