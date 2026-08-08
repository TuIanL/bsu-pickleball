# multiview-player-association Specification

## Purpose
TBD - created by archiving change add-multiview-player-trajectory-fusion. Update Purpose after archive.
## Requirements
### Requirement: View Identity 与 Global Identity 分离

系统 MUST 区分 View Identity（`(view_id, view_player_id)`）与 Global Identity（`global_player_id`）。`cam_1 / Player_1` 与 `cam_2 / Player_1` MUST NOT 被默认视为同一真人；两者 MUST 通过显式的跨视角关联建立映射关系。

#### Scenario: 标签不直接等价

- **WHEN** 两路分别产生 `cam_1 / Player_1` 与 `cam_2 / Player_1`
- **THEN** 系统 SHALL 不将二者视为同一 global player
- **AND** 系统 SHALL 仅在关联判定成立后才赋予同一 `global_player_id`

#### Scenario: 关联映射

- **WHEN** 跨视角关联判定两个 view 观测属于同一真实球员
- **THEN** 系统 SHALL 将二者映射到同一 `global_player_id`
- **AND** 该映射 SHALL 可被后续 Fusion 层消费

### Requirement: 跨视角关联不使用 side 字段

跨视角身份关联 MUST NOT 使用现有单视角 artifact 的 `side` 字段作为身份依据。关联 SHOULD 使用 canonical court distance、global prediction（来自 `GlobalTrackFilter.predict`）、temporal continuity、previous association 与 physical court constraints。

#### Scenario: 禁用 side

- **WHEN** `CrossViewPlayerAssociator` 计算关联代价
- **THEN** 关联代价 SHALL 不包含 `side` 字段输入
- **AND** 该约束 SHALL 由自动化测试断言

### Requirement: 关联迟滞

跨视角关联 SHALL 存在 association hysteresis：已建立 `A ↔ X` 关联后，即使下一帧出现略优的候选匹配，系统 SHALL NOT 立即换人；仅当连续多帧产生强证据时才 reassociate。

#### Scenario: 保持既有关联

- **WHEN** 已有 `A ↔ X` 关联且下一帧出现略优候选
- **THEN** 系统 SHALL 保持 `A ↔ X`
- **AND** 系统 SHALL NOT 因单帧略优即切换

#### Scenario: 强证据 reassociate

- **WHEN** 连续多帧产生强证据表明另一匹配更可信
- **THEN** 系统 SHALL 允许 reassociate
- **AND** 系统 SHALL 在 diagnostics 中记录该身份切换

### Requirement: 关联在 canonical 空间执行

跨视角关联 MUST 在 Canonical Physical Court Frame 空间执行，其代价基于 canonical 坐标距离与运动预测残差，而非 local 坐标。

关联代价 MUST 分离为两个层面：

- **几何可行性门**：`cross_view_distance <= max_feasibility_cost`。该门 MUST 仅使用 canonical 坐标距离，MUST NOT 包含预测项。
- **排序代价**：在几何可行的候选之间，使用 `cross_view_distance + prediction_bias * secondary_to_global_prediction_residual` 计算，MUST 先最大化可行匹配数量，再在相同数量下取排序代价最小。

prediction 项 MUST 为 **per-candidate**（使用 secondary observation 到该 global 预测位置的残差），MUST NOT 为同一 reference player 的常数，MUST NOT 影响几何可行性判定。

#### Scenario: canonical 距离代价

- **WHEN** 关联需要比较两路观测位置
- **THEN** 系统 SHALL 先归一化到 canonical 坐标
- **AND** 几何可行性门 SHALL 使用 canonical 坐标距离与 `max_feasibility_cost` 比较

#### Scenario: per-candidate prediction 排序

- **WHEN** 某 reference player 已关联到某 global player、该 global 存在预测位置，且存在多个 secondary candidate
- **THEN** 系统 SHALL 为每个 candidate 加入 `prediction_bias * distance(secondary_candidate, predicted_position)`（per-candidate）
- **AND** 该预测项 SHALL 影响候选之间的排序

#### Scenario: 几何可行性独立于预测

- **WHEN** 某 pair 的 `cross_view_distance <= max_feasibility_cost`，但预测残差较大
- **THEN** 该 pair SHALL 仍视为几何可行并可参与排序
- **AND** 系统 SHALL NOT 因预测项将几何合法的配对被整体剔除

### Requirement: 最大基数可行匹配（maximum-cardinality feasible matching）

跨视角二分图匹配 MUST 在可行匹配中优先最大化匹配数量（maximum-cardinality），再在相同数量下选择 ranking cost 最小的方案。匹配 MUST 支持 `reference_keys` 与 `secondary_keys` 数量不等的矩形输入（如 `2 ref / 1 sec`、`4 ref / 3 sec`、`1 ref / 2 sec`），MUST NOT 因索引方向错误抛出 `KeyError`。部分可行时 MUST 返回最大可行匹配（能配 1 对不返回 `[]`），未匹配元素 MUST 保持单视角。任一侧为空时 MUST 返回空列表。

#### Scenario: reference 多于 secondary

- **WHEN** 传入 `2 reference` 与 `1 secondary`（或 `4 ref / 3 sec`）
- **THEN** 系统 SHALL 正常运行，不抛出 `KeyError`
- **AND** 系统 SHALL 返回不超过 secondary 数量的匹配对
- **AND** 未匹配的 reference 元素 SHALL 保持单视角

#### Scenario: secondary 多于 reference

- **WHEN** 传入 `1 reference` 与 `2 secondary`
- **THEN** 系统 SHALL 正常运行，不抛出 `KeyError`
- **AND** 系统 SHALL 返回不超过 reference 数量的匹配对
- **AND** 未匹配的 secondary 元素 SHALL 保持单视角

#### Scenario: 部分可行（partial feasible）

- **WHEN** `2 reference` 与 `2 secondary` 中仅 `1` 对几何可行，其余对超过 `max_feasibility_cost`
- **THEN** 系统 SHALL 返回该 `1` 对可行匹配
- **AND** 系统 SHALL NOT 返回 `[]`（不得因其余对不可行而丢弃可行对）

#### Scenario: 空集合

- **WHEN** `reference_keys` 或 `secondary_keys` 为空
- **THEN** 系统 SHALL 返回空列表且不抛出异常
