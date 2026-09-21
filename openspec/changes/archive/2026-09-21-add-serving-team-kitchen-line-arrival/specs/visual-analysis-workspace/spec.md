## ADDED Requirements

### Requirement: 数据分析区域展示发球队网前到位率主卡
对于已完成的真实双打视频分析任务，视觉分析页的数据分析区域 SHALL 在现有位置热力图、位置散点图、区域空间热力图与回合—击球阶段时序图之外，独立加载并展示基于 `kitchen-arrival.v1` 的“发球队 · 网前到位率”场地控制主卡。该卡片 MUST NOT 阻塞视频优先工作区，也不得以 demo 或全场厨房占用数据填充。

#### Scenario: 真实任务存在可用到位率 artifact
- **WHEN** 用户打开已完成真实双打任务且 `kitchen-arrival.v1` 为 available
- **THEN** 数据分析区域 SHALL 渲染四名确认球员的场地控制主卡
- **AND** SHALL 展示每人的到位率、分子/分母和 Team A/B 对照
- **AND** SHALL 保留现有位置类图表与时序图

#### Scenario: 到位率 artifact 缺失或不可用
- **WHEN** 用户打开已完成任务但 artifact 缺失、unavailable、not_applicable、insufficient_evidence 或 failed
- **THEN** 页面 SHALL 保留主卡区域并显示相应可读状态
- **AND** SHALL 不显示模拟百分比、假定 Team A/B 或全场厨房区占用率
- **AND** 视频、状态栏和其他可视化 SHALL 继续可用

#### Scenario: artifact/card 使用独立停用开关
- **WHEN** `PICKLEBALL_KITCHEN_ARRIVAL_ENABLED=false`
- **THEN** 后端 SHALL 将厨房线产物标记为 `skipped`
- **AND** 前端 SHALL 不请求该 artifact 且不渲染厨房线卡片
- **WHEN** `PICKLEBALL_KITCHEN_ARRIVAL_CARD_ENABLED=false` 或
  `VITE_KITCHEN_ARRIVAL_CARD_ENABLED=false`
- **THEN** 前端 SHALL 不请求或渲染卡片
- **AND** 已生成的厨房线 artifact SHALL 不受影响
