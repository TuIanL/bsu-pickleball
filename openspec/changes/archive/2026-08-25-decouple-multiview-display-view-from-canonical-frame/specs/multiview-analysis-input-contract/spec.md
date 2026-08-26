# multiview-analysis-input-contract Delta

## ADDED Requirements

### Requirement: 展示机位不属于分析输入

多视角 Parent 的 `referenceViewId`、`canonicalFrameId`、`courtOrientation`、sync authority 和 `jointViewInputs` SHALL 作为一次分析的任务级输入保持不变。用户展示选择 `displayViewId` SHALL 只存在于结果展示状态或 URL，不得进入 AnalysisJob 创建请求、input signature、config signature 或 preflight 的 canonical frame 定义。

#### Scenario: 仅切换展示机位

- **WHEN** 用户在已完成任务中把 `displayViewId` 从 `cam_1` 改为 `cam_2`
- **THEN** 系统 SHALL 使用原 Parent 的 canonical frame 和 reference timeline
- **AND** SHALL NOT 触发新的 MultiView preflight 或 canonical frame 写入

#### Scenario: 同一任务重载展示状态

- **WHEN** 页面从 URL 恢复 `displayViewId`
- **THEN** 系统 SHALL 只校验该 view 是否属于已持久化的 `jointViewInputs`
- **AND** SHALL NOT 根据展示选择重新推断 orientation 或物理端点
