## MODIFIED Requirements

### Requirement: 概览选择、删除或取消单个历史分析任务

素材工作区概览 SHALL 列出该素材的历史分析任务（公开项，新→旧），允许选择 terminal 历史任务查看其结果或详情，并保留逐任务删除或取消能力，以管理多次分析而不删除原视频。

#### Scenario: 列出可识别的历史版本
- **WHEN** 素材存在一个或多个公开分析任务
- **THEN** 概览“分析状态”卡片 SHALL 显示“历史分析任务”列表
- **AND** 每项 SHALL 至少显示任务类型、状态和创建时间
- **AND** 对可用字段 SHALL 显示执行模式与分析窗口，不得为历史缺失字段伪造值

#### Scenario: 查看已完成历史结果
- **WHEN** 用户对 completed 历史任务点击“查看结果”
- **THEN** 系统 SHALL 导航到同一素材工作区的数据分析 view
- **AND** URL SHALL 显式携带该任务的 analysisJob

#### Scenario: 查看失败或取消任务详情
- **WHEN** 用户对 failed 或 canceled 历史任务点击“查看详情”
- **THEN** 系统 SHALL 在同一素材工作区显示该 Job 的状态与可用诊断
- **AND** URL SHALL 显式携带该任务的 analysisJob

#### Scenario: active 任务保持进度操作
- **WHEN** 历史列表中的任务处于 queued、uploaded 或 processing
- **THEN** 该行 SHALL 继续提供“查看进度”和“取消”
- **AND** SHALL NOT 将该 active Job 当作稳定结果版本加载

#### Scenario: 删除已完成任务
- **WHEN** 用户对已完成、失败或已取消的历史任务触发删除并确认
- **THEN** 系统 SHALL 调用任务删除接口并清理本地产物，保留原素材视频，删除后概览 SHALL 刷新最新状态

#### Scenario: 取消进行中任务
- **WHEN** 用户对排队中或分析中的历史任务触发取消
- **THEN** 系统 SHALL 请求取消该任务并在安全检查点停止，概览 SHALL 刷新最新状态
