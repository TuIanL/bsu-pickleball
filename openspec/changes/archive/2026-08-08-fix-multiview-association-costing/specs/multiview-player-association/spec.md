# multiview-player-association Delta

## ADDED Requirements

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

## MODIFIED Requirements

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
