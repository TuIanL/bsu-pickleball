## ADDED Requirements

### Requirement: 任务调度保留并传递源 FPS
系统 SHALL 在分析任务创建、持久化、签名和 worker 执行过程中保留用户确认的源 FPS。

#### Scenario: 创建任务保存 FPS
- **WHEN** API 收到包含源 FPS 的分析任务创建请求
- **THEN** JobStore MUST 将该 FPS 保存到任务摘要或任务输入中
- **AND** 后续查询任务时 SHALL 能读取该 FPS

#### Scenario: Worker 传递 FPS 给 Pipeline
- **WHEN** AnalysisWorker 执行包含源 FPS 的任务
- **THEN** worker MUST 将源 FPS 传递给 AnalysisPipeline
- **AND** Pipeline MUST 使用该值计算 `effective_fps`

#### Scenario: FPS 纳入签名
- **WHEN** `analysis_signature()` 计算任务签名
- **THEN** 签名输入 MUST 包含源 FPS 或其规范化等价值
- **AND** 不同源 FPS 的任务 MUST 产生不同签名
