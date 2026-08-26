# rally-shot-stage-timeline Specification

## Purpose
TBD - created by archiving change add-rally-shot-stage-timeline. Update Purpose after archive.
## Requirements
### Requirement: 时序图必须消费 canonical 回合击球事件

系统 SHALL 使用当前分析任务的 `shot-rally-events.v1` 作为回合—击球阶段时序图的事件来源。图表 SHALL 保留 artifact 中的 `rally_id`、`shot_id`、`ordinal_in_rally`、`stage`、`hitter_player_id`、`ownership_status`、`quality` 和 `evidence_windows` 语义，不得从前端数组顺序重新推断这些字段。

#### Scenario: 读取可用回合击球事件

- **WHEN** 已完成真实任务返回 `shot-rally-events.v1` 且状态为 `available`
- **THEN** 时序图 SHALL 按 artifact 中的 Shot 和 Rally 数据渲染
- **AND** 每个可展示 Shot SHALL 按唯一 `shot_id` 计数

#### Scenario: 事件 artifact 不可用

- **WHEN** 任务没有生成事件 artifact，或 artifact 状态为 `unavailable`、`skipped` 或 `failed`
- **THEN** 时序图 SHALL 显示明确的不可用原因
- **AND** SHALL NOT 使用球员轨迹、demo 数据或数组下标伪造 Shot/Rally 事件

### Requirement: 时序图支持回合分行和无边界降级

系统 SHALL 在存在可靠回合边界时按 Rally 分行展示击球节点；当没有唯一 authoritative rally 边界但存在 Shot 时，系统 SHALL 降级为按事件时间排序的单行击球事件时间轴，并明确提示回合边界不可用。

#### Scenario: 可靠回合边界可用

- **WHEN** artifact 包含 `rallies`，且 Shot 能通过 `rally_id` 关联到 Rally
- **THEN** 页面 SHALL 为每个 Rally 渲染一行
- **AND** 行内 Shot SHALL 按 `ordinal_in_rally` 排序，横向位置 SHALL 依据 `contact_ms` 或有效事件时间展示

#### Scenario: 回合边界不可用但存在 Shot

- **WHEN** artifact 存在 Shot，但 `rallies` 为空或 diagnostics 表示 `rally_boundary_status=unavailable`
- **THEN** 页面 SHALL 显示单行击球事件时间轴
- **AND** 页面 SHALL 显示“未提供可靠回合边界”提示
- **AND** SHALL NOT 显示伪造的回合编号或拍序

#### Scenario: 没有可展示 Shot

- **WHEN** artifact 可读取但 `shots` 为空
- **THEN** 页面 SHALL 显示“暂无可展示击球事件”空态和 artifact detail
- **AND** SHALL NOT 渲染静态示例节点

### Requirement: 事件视觉编码必须保留阶段和归属不确定性

系统 SHALL 将 `stage` 显示为发球、接发、第三拍、后续击球或未分类；已确认的 `hitter_player_id` SHALL 使用 canonical 球员标识；`ambiguous`、`unassigned` 或缺失击球者的 Shot SHALL 使用中性样式并保留“击球者不明”语义。

#### Scenario: 显示击球阶段

- **WHEN** Shot 的 `stage` 为 `serve`、`return`、`third` 或 `rally_shot`
- **THEN** 节点 SHALL 显示对应阶段标签
- **AND** SHALL NOT 把未提供的 `shot_type` 或 `result` 映射成默认技术动作

#### Scenario: 击球者归属不确定

- **WHEN** Shot 的 `ownership_status` 为 `ambiguous` 或 `unassigned`
- **THEN** 节点 SHALL 使用中性归属样式
- **AND** SHALL NOT 将该 Shot 计入任意一个球员的归属击球统计
- **AND** 全局 Shot 统计仍可按唯一 `shot_id` 计数

#### Scenario: 质量字段可用

- **WHEN** Shot 提供 `quality.band`
- **THEN** 节点 SHALL 以可解释的透明度、徽标或样式表达 high、medium、low、none
- **AND** SHALL NOT 将质量等级直接转换为技能评分

### Requirement: 时序图摘要只能表达描述性统计

系统 SHALL 提供基于当前 artifact 的可审计摘要，包括可见 Shot 数、可见 Rally 数、平均每 Rally Shot 数、阶段分布和归属不明数量。摘要 SHALL 按唯一 `shot_id` 去重，并在分母不足或回合边界不可用时显示数据有限语义。

#### Scenario: 计算回合摘要

- **WHEN** artifact 包含多个有效 Rally 和 Shot
- **THEN** 页面 SHALL 显示去重后的 Shot 数、Rally 数、平均每回合 Shot 数和阶段分布
- **AND** 平均值 SHALL 只使用有可靠 Rally 关联的 Shot

#### Scenario: 数据不足

- **WHEN** Rally 数量、阶段样本或质量样本不足以形成稳定统计
- **THEN** 页面 SHALL 显示对应的样本数或“数据有限”状态
- **AND** SHALL NOT 用 0% 或技能等级替代缺失值

### Requirement: Shot 节点支持视频证据跳转

系统 SHALL 允许用户从具有有效 `evidence_windows` 的 Shot 节点跳转到对应视频时间，并继续使用 canonical 毫秒时间语义。没有有效证据窗的 Shot 可以查看详情，但不得跳转到任意默认时间。

#### Scenario: 点击带证据窗的 Shot

- **WHEN** 用户点击包含有效 `evidence_windows` 的 Shot 节点
- **THEN** 系统 SHALL 使用有效时间窗的 `start_ms` 触发现有视频 seek 机制
- **AND** 视频分析页 SHALL 保持当前任务和 canonical 时间上下文

#### Scenario: Shot 没有证据窗

- **WHEN** 用户点击没有有效 `evidence_windows` 的 Shot 节点
- **THEN** 系统 SHALL 展示事件详情和“暂无可跳转证据”提示
- **AND** SHALL NOT 将视频跳转到 0 秒或其他任意时间

### Requirement: 时序图加载失败不得影响其他分析内容

系统 SHALL 独立加载时序 artifact，并将 loading、available、unavailable、failed 状态限制在时序图卡片内。时序图不可用时，视频、状态栏、位置热力图、位置散点图和区域空间热力图 SHALL 继续保持既有行为。

#### Scenario: 时序 artifact 加载中

- **WHEN** 视频和任务结果已经可用但 `shot-rally-events.v1` 尚在请求或解析
- **THEN** 页面 SHALL 显示时序图 loading 状态
- **AND** 其他分析模块 SHALL 保持可交互

#### Scenario: 时序 artifact 请求失败

- **WHEN** artifact 请求返回 404 或网络/解析失败
- **THEN** 页面 SHALL 在时序图卡片中显示 unavailable 或 failed 及可读原因
- **AND** SHALL NOT 将整个视频分析页判定为失败
