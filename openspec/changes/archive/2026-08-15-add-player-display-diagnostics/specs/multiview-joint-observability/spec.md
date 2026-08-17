## ADDED Requirements

### Requirement: 双摄协同分析页 per-player 显示诊断入口

双摄协同分析页 SHALL 提供 per-player 显示诊断展开面板（默认折叠），用户可对单个球员在单个时间点查询显示漏斗证据链；页面 MUST 通过显示诊断 API 获取数据，MUST NOT 直接加载 raw trace。MVP SHALL 仅支持单球员单时刻窗口查询，不提供整场拉取、GT A/B 或交互式时间线。

#### Scenario: 查看单球员显示诊断

- **WHEN** 用户在双摄协同分析页展开某球员的显示诊断
- **THEN** 页面 SHALL 显示该球员在参考视角与辅助视角的逐 stage 漏斗（候选 / 投影 / formal observation / association / guidance / overlay）
- **AND** 面板默认折叠，展开后按时间窗口请求

#### Scenario: 诊断不可用时页面语义

- **WHEN** 该 job 无显示漏斗产物或 `debugTraceEnabled=false`
- **THEN** 页面 SHALL 显示结构化不可用原因
- **AND** 其他区域（Sync / Fusion / Recovery / Refinement）SHALL 不受影响
