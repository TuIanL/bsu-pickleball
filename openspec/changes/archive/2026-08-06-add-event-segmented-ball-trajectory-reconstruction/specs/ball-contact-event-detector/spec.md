## ADDED Requirements
### Requirement: 启发式击球候选检测
系统 SHALL 提供基于轨迹运动特征而非姿态关键点的启发式击球候选检测器，输出候选事件状态。

#### Scenario: 输出击球候选
- **WHEN** 检测器在突变前后均检测到连续有效观测，且速度方向变化达到阈值或速度幅值发生明显变化
- **THEN** 检测器 SHALL 输出 `hit_candidate` 事件
- **AND** 候选事件 SHALL 包含 frame_index、timestamp_sec、image_xy、confidence 与 diagnostics

#### Scenario: 候选缺少前后连续观测
- **WHEN** 突变前或突变后缺少足够连续的有效观测点
- **THEN** 检测器 SHALL 标记该候选为 `rejected_hit`
- **AND** 拒绝原因 SHALL 记录为结构化字符串（如 `insufficient_context_before` / `insufficient_context_after`）

#### Scenario: 长缺失后首次重新锁定不作为击球
- **WHEN** 当前帧是长时间缺失之后的首次重新锁定
- **THEN** 检测器 SHALL NOT 将该帧标记为击球候选
- **AND** 该帧仅作为轨迹恢复点处理

#### Scenario: 已确认弹地抑制窗口内的候选
- **WHEN** 击球候选落在已确认弹地事件的抑制窗口内
- **THEN** 检测器 SHALL 抑制该候选
- **AND** 抑制原因 SHALL 记录为 `within_bounce_suppression_window`

#### Scenario: 满足最小事件间隔
- **WHEN** 连续两个击球候选的时间间隔小于配置的最小事件间隔（refractory period）
- **THEN** 检测器 SHALL 保留置信度更高的候选
- **AND** 丢弃间隔内的另一个候选

### Requirement: 突变上下文与拟合残差校验
系统 SHALL 在突变前后分别校验轨迹拟合残差，确认突变不是孤立误检造成的假象。

#### Scenario: 突变前后拟合残差较低
- **WHEN** 突变前后两段轨迹的拟合残差分别低于阈值
- **THEN** 候选 SHALL 保留并继续进入仲裁
- **AND** 前后残差 SHALL 记录在 diagnostics 中

#### Scenario: 突变一侧拟合残差过高
- **WHEN** 突变前或突变后的拟合残差超过阈值
- **THEN** 候选 SHALL 被标记为 `rejected_hit`
- **AND** 拒绝原因 SHALL 记录为 `high_fit_residual`

### Requirement: 击球与弹地候选仲裁
系统 SHALL 通过事件仲裁层解决同一时间窗口内击球候选与弹地候选的冲突，不武断分类。

#### Scenario: 高可信弹地存在时抑制击球
- **WHEN** 同一时间窗口内已存在高可信 bounce 事件
- **THEN** 仲裁层 SHALL 抑制对应的 hit candidate
- **AND** 仅保留 bounce 事件作为该时刻的边界事件

#### Scenario: 靠近球员区域且弹地证据弱时接受击球
- **WHEN** 击球候选明显靠近球员区域且同窗口弹地证据较弱
- **THEN** 仲裁层 SHALL 接受 hit candidate
- **AND** 事件来源 SHALL 标记为 `heuristic`

#### Scenario: 两者证据都不充分
- **WHEN** 同窗口内击球候选与弹地候选的证据均不充分
- **THEN** 仲裁层 SHALL 输出 `event_type = ambiguous`
- **AND** 该事件 SHALL 仅用于切段或降低质量评分，不武断分类为击球或弹地

#### Scenario: 球员运动仅作弱证据
- **WHEN** `player_motion_pixels` 可用时
- **THEN** 仲裁层 SHALL 将其作为弱证据参与击球候选评估
- **AND** MUST NOT 仅凭 player_motion_pixels 将候选确定为击球

### Requirement: 击球事件来源标注
系统 SHALL 为每个被确认的击球事件记录事件来源类型，第一版仅使用 `heuristic`。

#### Scenario: 第一版使用启发式来源
- **WHEN** 击球事件由纯启发式规则确认
- **THEN** 事件 `event_source` SHALL 为 `heuristic`
- **AND** 后续版本接入手腕/球拍区域后 SHALL 支持 `pose_assisted` 与 `manual_corrected` 来源

### Requirement: 确定性输出
系统 SHALL 对相同输入产生确定性的候选事件序列。

#### Scenario: 相同输入产生相同事件
- **WHEN** 对同一份轨迹输入重复运行击球检测
- **THEN** 击球候选、仲裁结果与事件 ID 序列 SHALL 完全一致
