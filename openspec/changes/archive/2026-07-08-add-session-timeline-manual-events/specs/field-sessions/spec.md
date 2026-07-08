## MODIFIED Requirements

### Requirement: 删除 Field Session

系统 MUST 允许用户删除没有录制关联、没有时间线事件且不在进行中的 Field Session。

#### Scenario: 删除空采集任务
- **WHEN** 用户请求删除一个不存在录制关联、不存在时间线事件且 `status` 不是 `live` 的 Field Session
- **THEN** 系统 SHALL 删除该 Field Session
- **AND** 后续读取该 Field Session SHALL 返回 404

#### Scenario: 拒绝删除进行中任务
- **WHEN** 用户请求删除 `status` 为 `live` 的 Field Session
- **THEN** 系统 SHALL 返回 409
- **AND** Field Session SHALL 保持存在

#### Scenario: 拒绝删除已有录制的任务
- **WHEN** 用户请求删除已经被 RecordingSession 引用的 Field Session
- **THEN** 系统 SHALL 返回 409
- **AND** Field Session SHALL 保持存在

#### Scenario: 拒绝删除已有时间线事件的任务
- **WHEN** 用户请求删除已经包含 Session Timeline Event 的 Field Session
- **THEN** 系统 SHALL 返回 409
- **AND** Field Session SHALL 保持存在

### Requirement: Field Session 采集控制台

系统 MUST 在前端提供 Field Session 采集控制台，用于在任务上下文中操作摄像头预览、录制和人工时间线事件。

#### Scenario: 创建后进入控制台
- **WHEN** 用户成功创建 Field Session
- **THEN** 前端 SHALL 提供进入该 Field Session 采集控制台的路径
- **AND** 控制台 SHALL 展示任务名称、状态、采集模式、比赛形式、摄像头方案和场地信息

#### Scenario: 在控制台复用摄像头能力
- **WHEN** 用户进入 Field Session 采集控制台
- **THEN** 前端 SHALL 保留摄像头列表、摄像头探测、实时预览和录制控制能力
- **AND** 开始录制时 SHALL 将当前 Field Session id 传给后端

#### Scenario: 在控制台操作时间线事件
- **WHEN** 用户选择 Field Session 进入采集控制台
- **THEN** 前端 SHALL 加载并展示该 Field Session 的 Session Timeline Event 列表
- **AND** 控制台 SHALL 提供创建人工时间线事件的入口

#### Scenario: 保留直接录制入口
- **WHEN** 用户未选择 Field Session 进入球场采集页
- **THEN** 前端 SHALL 仍允许用户使用既有摄像头预览和直接录制流程
- **AND** 前端 SHALL 不要求用户创建 Session Timeline Event

#### Scenario: 删除采集任务入口
- **WHEN** 用户选择一个 `status` 不是 `live` 的 Field Session
- **THEN** 前端 SHALL 提供删除该 Field Session 的操作
- **AND** 如果后端因为已有录制或时间线事件拒绝删除，前端 SHALL 展示失败原因
