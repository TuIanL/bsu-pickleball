## MODIFIED Requirements

### Requirement: Canonical Rally/Shot artifact envelope

系统 SHALL 为完成或明确降级的分析任务生成可选的 `shot_rally_events.json`，其 schema SHALL 为 `shot-rally-events.v1`，并包含 `job_id`、`video_id`、`status`、`detail`、`generated_at`、`time_unit`、`coordinate_system`、`rallies`、`shots` 和 `diagnostics`。`time_unit` SHALL 为 `ms`；court 坐标单位 SHALL 明确为 `ft`，image 坐标单位 SHALL 明确为 `px`。绑定成功的 canonical Rally SHALL 引用该 Job 冻结的 `AnalysisRallyContextSnapshot`；缺失 context SHALL 显式表达 unavailable，而不得从 `initial_side` 推断正式 Team A/B。

#### Scenario: 事件产物成功生成
- **WHEN** 一个真实 job 已完成，且存在可消费的 rally/shot 输入产物
- **THEN** 系统 SHALL 写入 `shot_rally_events.json`
- **AND** `status` SHALL 为 `available`
- **AND** payload SHALL 声明 `schema_version = "shot-rally-events.v1"`
- **AND** `rallies` 与 `shots` SHALL 即使为空也保持数组类型

#### Scenario: 事件源不足
- **WHEN** job 完成但没有足够输入构造可靠事件
- **THEN** 系统 SHALL 保留 artifact 状态为 `unavailable`、`skipped` 或 `failed`
- **AND** `detail` SHALL 说明缺少的输入或失败原因
- **AND** SHALL NOT 用 ball trajectory 或 mock 数据伪造 shot 事件

#### Scenario: Rally 有任务绑定上下文
- **WHEN** formal Rally 已使用定义优先级绑定有效 AnalysisRallyContextSnapshot
- **THEN** canonical Rally SHALL 引用冻结的发球队、A/B 端位与 roster identity facts
- **AND** 后续消费者 SHALL 不再根据 player `initial_side` 建立正式队伍语义
