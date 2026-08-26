## MODIFIED Requirements

### Requirement: 轨迹筛选与视觉编码

系统 SHALL 允许用户在全部轨迹、较高可信度轨迹与球员球路之间筛选，并 SHALL 使用方向颜色、透明度、线宽和来源线型区分方向、低可信度、推算点和预测区间。可信度判定 SHALL 使用后端质量评分和段级展示资格，而非前端平均置信度。球员筛选选项 SHALL 来自产物 `player_roster`，不得硬编码。默认视图 MUST NOT 使用事件点型区分击球或弹地，也 MUST NOT 绘制 `display_eligible = false` 的 segment。

#### Scenario: 仅显示较高可信度轨迹

- **WHEN** 用户启用高可信度筛选
- **THEN** 场景仅显示后端质量评分达到规定阈值、推算比例未超过规定值且 `display_eligible = true` 的重建段

#### Scenario: 按球员筛选

- **WHEN** 用户在报告页选择某个 canonical 球员（如 `Player_3`）
- **THEN** 场景 SHALL 仅显示 `hitter_player_id == Player_3` 且 `ownership_status == confirmed` 的 Shot
- **AND** 该 Shot 关联的全部 segment SHALL 保留并传入场景，即使一个 Shot 包含多个 segment
- **AND** 可见球路的原始 `hitter_player_id` SHALL 均为 `Player_3`，前端不得通过覆盖字段伪造归属

#### Scenario: 未归属球路不进入球员视图

- **WHEN** Shot 或 segment 的归属为 `ambiguous`、`unassigned`、缺少 `hitter_player_id`，或 `shot_id` 为空
- **THEN** 该球路 SHALL 不进入任何指定球员的个人筛选结果
- **AND** 该数据 SHALL 保留给全部轨迹或未归属视图使用，并 SHALL 不计入指定球员统计

#### Scenario: 报告页切换球员

- **WHEN** 用户从 `Player_1` 切换到 `Player_2`
- **THEN** `BallTrajectoryScene` SHALL 在下一次渲染中只接收 `Player_2` 的筛选结果
- **AND** SHALL NOT 保留上一名球员的可见轨迹或当前选中的不可见 Shot

#### Scenario: 单打双打自适应

- **WHEN** 产物 `player_roster` 只有两名球员
- **THEN** 球员筛选 SHALL 只显示两名球员选项
- **AND** SHALL NOT 显示硬编码的 P1—P4

#### Scenario: 旧任务无归属字段

- **WHEN** 产物为 v1 或无球员归属字段
- **THEN** 球员筛选 SHALL 隐藏或禁用
- **AND** 球路仍正常展示，不伪造归属

#### Scenario: 选择单条轨迹

- **WHEN** 用户从轨迹列表选择一条球路
- **THEN** 场景突出该球路并显示其时间范围、持续时间、点数和可信度摘要
- **AND** 选中状态 MAY 使用中性色加深或线宽变化，但 MUST NOT 恢复事件图标

#### Scenario: 低可信段仅调试显示

- **WHEN** 重建段质量评分低于默认展示阈值、`display_eligible = false` 或为 `image_only` 模式
- **THEN** 场景 SHALL NOT 在默认球场视图显示该段，除非用户开启调试/原始检测模式

#### Scenario: 断点和来源不被前端重新连接

- **WHEN** artifact 标记两个样本区间之间存在长缺口、lost/reset 边界或 `display_break = true`
- **THEN** 前端 SHALL 保持几何断开
- **AND** MUST NOT 为了视觉连续性自行插值、平滑或跨段连线

### Requirement: Shot 级列表与统计

系统 SHALL 按 Shot 聚合列表与统计，列表项展示击球者、飞行段数与时长，统计按 `shot_id` 去重。所有列表和统计 SHALL 基于当前球员、阶段、质量和数量限制后的可见结果计算，不得使用筛选前的整场轨迹数量。

#### Scenario: Shot 列表项

- **WHEN** 右侧列表渲染
- **THEN** 列表项 SHALL 按 Shot 展示（如“球路 7 · P2 · 2 个飞行段 · 3.8 秒”）
- **AND** MUST NOT 按 flight segment 逐条列示同一 Shot

#### Scenario: 统计按 Shot 去重

- **WHEN** 页面统计球路总数与球员击球数
- **THEN** 总数 SHALL 按 `shot_id` 去重计数（含 unassigned，不含 `shotId = null`）
- **AND** 球员击球数 SHALL 按 `hitter_player_id` 匹配且已确认的 Shot 去重计数
- **AND** 统计 SHALL 不包含未归属、击球者不明或另一球员的 Shot

#### Scenario: 筛选顺序

- **WHEN** 用户同时启用球员筛选、可信度筛选与数量限制
- **THEN** 筛选顺序 SHALL 为：球员归属筛选 → 可信度筛选 → 最近 N 条限制

#### Scenario: 无匹配球路

- **WHEN** 当前球员和其他筛选条件组合后没有可展示的 Shot
- **THEN** 页面 SHALL 显示明确的“当前筛选下没有可显示的球路”空态
- **AND** SHALL NOT 回退显示整场球路
