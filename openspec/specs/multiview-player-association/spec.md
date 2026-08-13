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

### Requirement: GlobalPlayerAssociator(新类)

系统 SHALL 提供 `GlobalPlayerAssociator`(**新类,不修改 P0 `CrossViewPlayerAssociator`**),以 `GlobalState.predict(t)` 为中心,将各视角观测分配到 global states:

```text
GlobalState.predict(t)
    ├── assign Cam1 observations → global states
    ├── assign Cam2 observations → global states
    ├── unmatched observations → tentative global candidates
    └── fusion/update GlobalState(t)
```

该关联器 SHALL 复用 Change 0 的 `min_cost_matching()` 作为共享 primitive(含 rectangular 匹配与 per-candidate prediction 修复)。P0 `CrossViewPlayerAssociator`(reference-centric)SHALL 语义不变,仅在 `late_fusion_v1` 使用。

#### Scenario: 观测分配到全局

- **WHEN** 某 tick 两路分别产生观测
- **THEN** 系统 SHALL 用 pre-tick GlobalState 预测,将各视角观测分配到对应 global player
- **AND** 未匹配观测 SHALL 形成 tentative global candidates

#### Scenario: P0 associator 语义不变

- **WHEN** `executionMode=late_fusion_v1`
- **THEN** `CrossViewPlayerAssociator` SHALL 按 P0 reference-centric 语义工作
- **AND** `GlobalPlayerAssociator` SHALL 仅作用于 joint_tracking_v2 路径

### Requirement: 单视角缺失不阻塞

当某 global player 在一路视角不可见时,另一路观测 SHALL 仍能分配到其 global state;缺失视角 SHALL 视为该 view binding 过期,而非阻止关联。

#### Scenario: 单视角缺失

- **WHEN** cam_1 的 P3 不可见、cam_2 可见
- **THEN** P3 的 cam_2 观测 SHALL 分配到其 global state
- **AND** cam_1 缺失 SHALL 视为该 view binding 过期,而非阻止关联

### Requirement: 关联不使 prediction 影响几何可行性

跨视角关联 SHALL 分离几何可行性门与排序代价:几何可行性仅由 canonical 距离判定,per-candidate prediction 残差只在可行候选之间排序(保留 Change 0 修复)。

#### Scenario: 几何门独立

- **WHEN** 某 pair 几何可行但预测残差较大
- **THEN** 该 pair SHALL 仍可参与排序
- **AND** SHALL NOT 因预测项被整体剔除

### Requirement: geometry-gated identity continuity prior

`GlobalPlayerAssociator` SHALL 先以 canonical distance 应用 hard feasibility gate，随后才以 stable local identity key `(view_id, view_player_id, local_identity_epoch)` continuity 和 guided `expected_global_player_id` 作为 ranking penalty/prior。历史 mapping 的 fallback SHALL 遵守同一 hard gate，identity prior SHALL NOT 强制分配不可行 global；identity epoch 变化 SHALL 使旧 key 的 continuity mapping 失效。

#### Scenario: 历史 mapping 超出几何门
- **WHEN** 一个 local player 的历史 global mapping 与当前 canonical observation 距离超过 association gate
- **THEN** 系统 SHALL NOT 直接复用该 mapping
- **AND** diagnostics SHALL 记录 geometry-infeasible continuity rejection

#### Scenario: identity epoch reset 不继承 prior
- **WHEN** `Player_3` 从 identity epoch 0 reset 到 epoch 1
- **THEN** epoch 1 observation SHALL NOT 继承 epoch 0 的 global continuity prior

### Requirement: tentative bootstrap view uniqueness

同一个 tentative global 在同一 tick SHALL 至多接受每个 view 一份 observation；bootstrap grouping SHALL 不把同一 camera 的两个不同 formal local players 合并为同一 global。

#### Scenario: 同 view 近距离双人
- **WHEN** Cam1 的两个 formal local players 的 canonical 距离小于 bootstrap gate
- **THEN** 系统 SHALL 为其保留不同 tentative global candidates

