## MODIFIED Requirements

### Requirement: 执行模式字段与缺省规则

多视角创建请求 SHALL 在 `multiview.executionMode` 携带执行模式，取值为 `late_fusion_v1` 或 `joint_tracking_v2`；Parent 持久化字段 SHALL 为 `executionMode`。缺失或未知时 SHALL 缺省为 `late_fusion_v1`，以保持历史任务兼容。旧文档中的 `multiviewExecutionMode` SHALL 视为历史命名，不新增同名顶层字段。

#### Scenario: 历史任务缺省 late_fusion_v1

- **WHEN** 一个多视角 Parent 缺 `executionMode` 字段
- **THEN** 系统 SHALL 按 `late_fusion_v1` 处理
- **AND** 不触发任何数据或产物迁移

#### Scenario: 新建任务显式选择 joint

- **WHEN** 前端在 `multiview.executionMode` 发送 `joint_tracking_v2`
- **THEN** 系统 SHALL 将 Parent 标记为 `joint_tracking_v2`
- **AND** SHALL NOT 因字段命名差异回退为 late-fusion

#### Scenario: 未知模式安全缺省

- **WHEN** 请求携带未知 execution mode
- **THEN** 系统 SHALL 缺省为 `late_fusion_v1`
- **AND** SHALL 记录输入校验或兼容诊断

### Requirement: executionMode 进入输入签名

`executionMode` SHALL 进入 Parent 的 `inputSignature` / `configSignature`。同一 CaptureTake 的 `late_fusion_v1` 与 `joint_tracking_v2` 任务 SHALL 视为不同分析任务，SHALL NOT 被幂等或去重逻辑合并。

#### Scenario: A/B 不被去重

- **WHEN** 同一 CaptureTake 创建 `late_fusion_v1` 与 `joint_tracking_v2` 两个 Parent
- **THEN** 两者的 inputSignature SHALL 不同
- **AND** 系统 SHALL NOT 将二者判为重复任务而丢弃其一
