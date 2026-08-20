# multiview-joint-observability Delta Specification

## ADDED Requirements

### Requirement: 分层可视化展示

联合运行状态页面 SHALL 在保持后端投影语义不变的前提下，以 L1 概览层、L2 图形层、L3 明细层组织展示。L1 SHALL 包含一句话结论、健康度与四阶段流水线状态灯；L2 SHALL 以图表形式呈现四大域事实；L3 SHALL 保留等价于现状的完整明细。页面 MUST NOT 因可视化升级而重算或改写后端已发布结论。

#### Scenario: 概览层呈现

- **WHEN** summary 可用且页面加载完成
- **THEN** 页面 SHALL 在首屏呈现一句话结论、健康度评分与 SYNC / FUSION / RECOVERY / REFINEMENT 流水线状态灯
- **AND** 概览层内容 SHALL 全部源自 summary 既有字段，不引入新算法结论

#### Scenario: 四大域图表化

- **WHEN** 页面加载完成
- **THEN** SYNC SHALL 以双视角对比可视化呈现 per-view authority 与参考机位
- **AND** FUSION SHALL 以环形图呈现 `effective_multiview_ratio`、以堆叠条呈现 `status_counts`
- **AND** RECOVERY SHALL 以六段漏斗图呈现 `funnel` 计数
- **AND** REFINEMENT SHALL 以门控流程呈现 execution / publication 决策与 `final_source`

#### Scenario: 明细层等价保留

- **WHEN** 用户展开 L3 明细层
- **THEN** 每个分域 SHALL 呈现与可视化改造前等价的指标明细与 reason 文本
- **AND** 缺失字段 SHALL 显示 "-"（沿用现有 `MetricRow` 语义），MUST NOT 伪造

### Requirement: 状态与可用性语义延续

各分域 `availability` 与状态灯展示 SHALL 延续现有独立状态域语义：某一分域 `not_applicable` MUST NOT 渲染为失败；`partial` MUST 附带缺失证据 reason；前端推导的健康度评分 MUST 标注为展示汇总。

#### Scenario: 不适用分域展示

- **WHEN** 任务为 `late_fusion_v1` 且 recovery / refinement 为 `not_applicable`
- **THEN** 对应流水线阶段与图表 SHALL 显示"不适用"灰色状态
- **AND** 其余分域 SHALL 独立正常展示，不受影响

#### Scenario: 评分标注汇总性质

- **WHEN** 页面显示健康度评分
- **THEN** 评分旁 SHALL 标注"前端基于后端事实汇总"
- **AND** 页脚 SHALL 保留"页面不重新计算算法结论"说明
