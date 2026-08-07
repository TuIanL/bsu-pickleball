# multiview-player-association Specification

## Purpose

定义跨视角身份关联（View Identity → Global Identity）的建立规则，确保两路单视角的 `Player_1` 等标签不会被误认为同一真人，并保证关联不使用摄像机相对且反转的 `side` 字段。

## ADDED Requirements

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

#### Scenario: canonical 距离代价

- **WHEN** 关联需要比较两路观测位置
- **THEN** 系统 SHALL 先归一化到 canonical 坐标
- **AND** 关联代价 SHALL 使用 canonical 坐标与 `GlobalTrackFilter.predict` 提供的 global prediction 残差计算
