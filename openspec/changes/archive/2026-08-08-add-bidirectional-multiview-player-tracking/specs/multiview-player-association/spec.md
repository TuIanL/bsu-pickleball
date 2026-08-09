# multiview-player-association Delta

## ADDED Requirements

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
