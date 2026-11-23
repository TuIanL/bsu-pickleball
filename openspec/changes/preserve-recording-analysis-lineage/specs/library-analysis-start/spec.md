## ADDED Requirements

### Requirement: 分析创建请求的来源契约

系统 SHALL 在分析创建请求中接受可选的录制来源声明，并在服务端核验后才写入任务。

单摄请求 MUST 允许省略 `camera_slot`。省略时系统 MUST NOT 拒绝请求，也 MUST NOT 把任何默认视图标识写入来源快照。系统 MUST NOT 为统一契约而把原本可选的单摄字段改为必填。

`camera_slot` 在系统中是**视图标识**，不是来源身份。系统 MUST NOT 仅凭 `camera_slot` 匹配就认定来源已核实；来源核实 MUST 至少同时覆盖 Session 与 Video。当请求显式声明了 `camera_slot` 且该机位在 Take 登记中对应的视频与请求视频不一致时，系统 MUST 判定为来源归属冲突。

未声明任何录制来源的普通上传请求 SHALL 保持既有合法路径。双摄请求 SHALL 继续遵循既有的多视角绑定契约，本要求 MUST NOT 改变其判定逻辑。

#### Scenario: 单摄省略机位

- **WHEN** 单摄分析请求不包含 `camera_slot`
- **THEN** 系统 SHALL 正常创建任务（与变更前一致）
- **AND** 来源快照中的机位字段 SHALL 为空

#### Scenario: 单摄显式机位与登记一致

- **WHEN** 单摄请求显式声明 `camera_slot`，且该机位在 Take 登记中对应的视频与请求视频相同
- **THEN** 系统 SHALL 通过来源核验并记录该机位

#### Scenario: 单摄显式机位与登记不一致

- **WHEN** 单摄请求显式声明 `camera_slot`，但该机位登记的视频与请求视频不同
- **THEN** 系统 MUST 返回来源归属冲突（HTTP 409）

#### Scenario: 仅有槽位时按无来源处理

- **WHEN** 请求只提供 `camera_slot` 与 `videoId`，不提供可核实的 Session 或 Take
- **THEN** 系统 MUST NOT 认定来源已核实
- **AND** SHALL 按无来源（普通上传）路径创建任务，且该 `camera_slot` MUST NOT 写入来源快照
- **AND** MUST NOT 因此返回 400——槽位不是来源申报信号

#### Scenario: 普通上传不受影响

- **WHEN** 请求不声明任何录制来源
- **THEN** 系统 SHALL 按既有上传分析路径创建任务
- **AND** MUST NOT 要求补充来源字段

### Requirement: 重复来源声明与显式 Take 边界

顶层字段与 metadata 对同一来源属性重复声明时 MUST 一致；只从一个允许入口声明时 SHALL 由服务端归一化。显式提供但不存在的 Take ID MUST 返回 404，且 MUST NOT 降级为 session-only。

#### Scenario: 重复来源字段冲突

- **WHEN** 顶层与 metadata 同时声明 Session 或机位，但对应值不同
- **THEN** 系统 MUST 返回 HTTP 409 `source_ownership_mismatch`
- **AND** MUST NOT 选择任一值创建任务

#### Scenario: 单入口来源声明归一化

- **WHEN** 一个契约允许的来源入口提供了完整可核验信息，另一个入口未重复声明
- **THEN** 服务端 SHALL 核验并归一化来源
- **AND** MUST NOT 因缺少重复字段而拒绝请求

#### Scenario: 显式 Take 不存在不降级

- **WHEN** 请求显式提供 `capture_take_id` 且该 Take 不存在
- **THEN** 系统 MUST 返回 HTTP 404 `recording_source_not_found`
- **AND** MUST NOT 将请求降级为 session-only
