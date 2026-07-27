## ADDED Requirements

### Requirement: Vidat 导入事件溯源
系统 MUST 为已确认 Vidat 导入生成的时间线事件记录来源标识、标注包版本和导入版本，以支持审计和训练数据追溯。

#### Scenario: 查询导入事件
- **WHEN** 用户查询一个 CaptureTake 的时间线事件
- **THEN** 每个由 Vidat 导入生成的事件 SHALL 包含 `vidat_import` 来源和关联的标注包版本标识
- **AND** 非 Vidat 历史事件 SHALL 保持其原有来源和内容
