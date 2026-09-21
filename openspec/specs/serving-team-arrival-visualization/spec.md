# serving-team-arrival-visualization Specification

## Purpose
TBD - created by archiving change add-serving-team-kitchen-line-arrival. Update Purpose after archive.
## Requirements
### Requirement: 发球队网前到位率场地控制主卡
已完成的真实视频分析工作区 SHALL 在数据分析区域提供“发球队 · 网前到位率”场地控制主卡。卡片 SHALL 使用当前 Job 的 `kitchen-arrival.v1`，按 P1–P4 展示显示名、队伍归属、到位率及 arrived/eligible 分子分母；横向球场和四条比例泳道只表示统计对照，不表示实时站位。

#### Scenario: 可用的四人汇总数据
- **WHEN** 已完成真实双打任务的 kitchen-arrival artifact 状态为 available
- **THEN** 卡片 SHALL 将四名球员按冻结 Team A/B 分组展示
- **AND** 每条泳道 SHALL 以一致的球员颜色展示到位比例、有效未到位余量和可读的分子/分母
- **AND** SHALL 不将全场厨房区占用率替代为到位率

### Requirement: 主卡独立加载与诚实降级
主卡 SHALL 独立于视频、同步小地图、位置图和时序图加载；loading、insufficient_evidence、not_applicable、unavailable 与 failed 状态必须局部展示，并明确原因。真实任务不得用 demo 百分比或伪造球员数据填充该卡。

#### Scenario: 样本不足
- **WHEN** artifact 为 `insufficient_evidence` 且存在已知 arrived/eligible 计数
- **THEN** 卡片 SHALL 显示例如“1/2 · 样本不足”及原因
- **AND** MUST NOT 将该计数渲染为 50% 或比例泳道

#### Scenario: 指标不可用
- **WHEN** artifact 缺失、状态为 unavailable 或无法解析
- **THEN** 卡片 SHALL 显示 roster、context、binding、identity audit 或轨迹覆盖等可读缺失原因
- **AND** 视频播放和其他可用可视化 SHALL 继续工作

#### Scenario: 暂不提供证据回跳
- **WHEN** 用户查看 V1 到位率主卡
- **THEN** 卡片 SHALL 展示汇总和数据状态
- **AND** MUST NOT 暗示可点击百分比跳转视频或存在逐回合证据列表

