## MODIFIED Requirements

### Requirement: 时间范围筛选联动

恢复卡片 SHALL 提供时间范围筛选控件，仅驱动 episodes 查询的 `from_ms`/`to_ms` 参数并过滤恢复时间线展示的数据集合。恢复漏斗 SHALL 始终展示后端已发布的完整 run 权威统计；前端 MUST NOT 基于窗口内 episodes 重算漏斗计数，因为 episode 数、guidance 数、candidate 数、expected-global-preserved 数与 opportunity 数为不同的 runtime 事实，不可互换。此要求强化「页面不重新计算算法结论」的不变量（见 `observability-viz-layer` 健康度评分推导 requirement）。

#### Scenario: 刷选联动

- **WHEN** 用户调整时间范围
- **THEN** episodes 请求 SHALL 携带 `from_ms`/`to_ms` 参数并过滤恢复时间线展示的数据集合
- **AND** 恢复漏斗 MUST NOT 随窗口变化被前端重算

#### Scenario: 漏斗统计来源不变

- **WHEN** 用户应用或重置时间范围
- **THEN** 恢复漏斗数字 SHALL 与未筛选时完全一致（后端权威统计）
- **AND** 前端 MUST NOT 用窗口内 episode 聚合替代后端漏斗

#### Scenario: 页面不重新计算声明自洽

- **WHEN** 用户使用时间范围筛选观察恢复区
- **THEN** 页面顶部「后端已发布事实分域展示，页面不重新计算算法结论」的声明 SHALL 对恢复漏斗保持成立
- **AND** 任何随窗口变化的展示 SHALL 仅限于 episodes 列表与时间线数据集合过滤
