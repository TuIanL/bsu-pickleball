## MODIFIED Requirements

### Requirement: 前端从结构化数据渲染区域空间热力图

前端 SHALL 使用 `StructuredVisualizationData.zone_stats` 渲染区域空间热力图。视频分析页与真实 Player Report SHALL 消费同一份 job-scoped structured visualization artifact；报告组件 SHALL 通过 `PlayerReportEvidence` 获取当前 canonical player 的区域统计，不得使用位置网格或静态占位数据代替 `zone_stats`。

#### Scenario: 视频分析页正常渲染区域热力图

- **WHEN** 前端收到有效 `zone_stats` 数据
- **THEN** 渲染三段球场底图（Kitchen/Transition/Backcourt），顶部提供球员单选 chip，选中球员的三区占用率、NVZ 占用率、平均站位距离与反馈文案可见

#### Scenario: 真实报告页渲染区域热力图

- **WHEN** completed real job 的 `/visualization-data` 返回与 selected canonical player 匹配的 `zone_stats.players` 条目
- **THEN** Player Report 的“场地覆盖”卡 SHALL 使用该条目渲染区域空间热力图、三区占用条、NVZ 占用率、平均站位距厨房线和反馈
- **AND** 该卡 SHALL 标记或保留 structured visualization provenance，不得显示 demo 标记或静态演示区域

#### Scenario: 报告页缺少区域统计但仍有其他真实证据

- **WHEN** real job 报告存在有效运动证据，但 structured artifact 缺失、请求失败或没有 selected player 的 `zone_stats`
- **THEN** 报告整体 SHALL 继续渲染可用模块
- **AND** “场地覆盖”卡 SHALL 显示明确 unavailable 原因，不得渲染空白球场或从位置热力图猜测区域占用

#### Scenario: 有效帧不足时显示警示

- **WHEN** 选中球员的 `data_sufficiency` 为 `insufficient`
- **THEN** 卡片显示“有效帧不足”警示，不将占用百分比呈现为确定结论

#### Scenario: 无区域统计数据时降级

- **WHEN** `zone_stats` 缺失或 `players` 为空
- **THEN** 组件显示“暂无区域统计”或等价 unavailable 状态，不渲染空白球场
