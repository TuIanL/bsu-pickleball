## ADDED Requirements

### Requirement: joint 编排包含独立的双摄球分析阶段
joint 模式的阶段图 SHALL 在双摄融合完成后、指标与可视化发布前执行 `multiview-ball-analysis` 阶段。该阶段 SHALL 有明确的 queued/running/succeeded/degraded/failed 状态，并 SHALL 受 Parent 生命周期与取消逻辑管理。

#### Scenario: joint 正常推进
- **WHEN** 双摄输入检查与 player joint fusion 成功
- **THEN** 编排 SHALL 推进到 `multiview-ball-analysis`
- **AND** 球分析完成后 SHALL 才推进 metrics、visualization 与 report

#### Scenario: joint 球分析不可用
- **WHEN** 球分析因模型、标定、输入或质量原因不可用
- **THEN** 阶段 SHALL 进入可解释的 degraded/failed 状态
- **AND** 编排 SHALL 按降级策略继续生成球员报告，不得把阶段异常伪装为成功

### Requirement: Parent 完成状态晚于双摄球产物发布
Parent 的最终 `result.json` 与完成事件 SHALL 在球相关 artifact 的 path/url/status/detail 已写入并可查询之后发布。任何消费者读取完成任务时 SHALL 能看到一致的球员结果与球分析状态。

#### Scenario: 全部产物成功发布
- **WHEN** player、ball、metrics 和 visualization 阶段均完成
- **THEN** 系统 SHALL 先写入并校验 Parent artifacts
- **AND** 再写入最终 result 并发出 completed 事件

#### Scenario: 球分析失败后完成
- **WHEN** player 阶段成功而 ball 阶段失败或超时
- **THEN** 系统 SHALL 先写入球 artifact 的失败状态与 detail
- **AND** 再发布带降级状态的 Parent result

### Requirement: 阶段状态与现有进度状态机保持单一事实源
球分析阶段 SHALL 复用现有 orchestration/progress 状态持久化与恢复机制。前端不得自行推断一个独立的球分析生命周期；应用重启、取消、删除和重试 SHALL 能处理该阶段。

#### Scenario: 应用重启恢复球分析
- **WHEN** 应用在 `multiview-ball-analysis` running 状态时重启
- **THEN** reconciliation SHALL 根据持久化状态恢复、重试或标记该阶段终止
- **AND** 不得把 Parent 错误恢复为已完成且缺少球产物

#### Scenario: 取消 joint 任务
- **WHEN** 用户取消处于球分析阶段的 Parent
- **THEN** 系统 SHALL 终止或回收球分析资源
- **AND** SHALL 持久化取消状态并阻止后续 report 发布
