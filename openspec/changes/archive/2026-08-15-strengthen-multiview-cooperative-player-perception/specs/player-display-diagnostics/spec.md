## ADDED Requirements

### Requirement: 漏斗行展示 pre-association 与 same-tick guidance

`player-display-diagnostics.v1` 漏斗行 SHALL 增加 `pre_association_status`（`candidate_found / projection_failed / ambiguous / not_assessed`）与 `same_tick_guidance_status`（`generated / not_generated_no_cross_candidate / not_needed_observed / geometry_unavailable`），使"本 tick 为什么没被 same-tick 救"可观测。字段缺省兼容旧产物（前端按未评估显示）。

#### Scenario: same-tick 触发过程可观测

- **WHEN** 某 `(player, view)` 本 tick 因另一路有 strong base candidate 而生成 same-tick guidance
- **THEN** 漏斗行 SHALL 展示 `pre_association_status=candidate_found` 与 `same_tick_guidance_status=generated`
- **AND** 补检结果（formal observation 是否形成）SHALL 由既有分层断裂字段呈现

#### Scenario: 两路投影失败可观测

- **WHEN** 两路均有 raw box 但两路 projection 均失败（本 Change 不补检的场景）
- **THEN** 漏斗行 SHALL 展示 `pre_association_status=projection_failed`
- **AND** 该情况 SHALL 明确呈现为 projection repair 问题（非 same-tick 机制失败）

#### Scenario: 旧产物兼容

- **WHEN** 查询历史任务的显示诊断产物（无该两字段）
- **THEN** 前端 SHALL 按未评估显示
- **AND** 查询 API SHALL NOT 因字段缺失报错
