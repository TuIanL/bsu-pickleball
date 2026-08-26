# ball-trajectory-visualization Specification Delta

## MODIFIED Requirements

### Requirement: 轨迹筛选与视觉编码

系统 SHALL 允许用户在全部轨迹、较高可信度轨迹与球员球路之间筛选，并 SHALL 使用方向颜色、透明度、线宽和来源线型区分方向、低可信度、推算点和预测区间。可信度判定 SHALL 使用后端质量评分和段级展示资格，而非前端平均置信度。球员筛选选项 SHALL 来自产物 `player_roster`，不得硬编码。默认视图 MUST NOT 使用事件点型区分击球或弹地，也 MUST NOT 绘制 `display_eligible = false` 的 segment。

#### Scenario: 仅显示较高可信度轨迹

- **WHEN** 用户启用高可信度筛选
- **THEN** 场景仅显示后端质量评分达到规定阈值、推算比例未超过规定值且 `display_eligible = true` 的重建段

#### Scenario: 按球员筛选

- **WHEN** 用户选择某球员（如 P3）
- **THEN** 场景仅显示 `hitter_player_id == Player_3` 的 Shot 内所有 segment
- **AND** 可见球路的 `hitter_player_id` SHALL 均为 `Player_3`

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
