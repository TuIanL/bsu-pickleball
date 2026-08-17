## ADDED Requirements

### Requirement: same-tick 恢复单独计数

same-tick 双向恢复形成的 target-view formal observation SHALL 作为独立 recovery 来源，**单独计数**（`same_tick_opportunity_count / same_tick_guidance_generated_count / same_tick_roi_invocation_count / same_tick_formal_observation_count / same_tick_recovery_success_count`），MUST NOT 混入 #2 的 `guided_recovery_success_count`（证明增益来源：next-tick fast path vs same-tick path）。recovery episode 建立与关闭逻辑 SHALL 与既有语义一致。

#### Scenario: same-tick 恢复计入独立计数

- **WHEN** 某 global 因 same-tick guidance 在缺失路 ROI 内重新获得 formal observation
- **THEN** 系统 SHALL 递增 `same_tick_formal_observation_count` 与 `same_tick_recovery_success_count`
- **AND** `guided_recovery_success_count`（#2 语义）SHALL NOT 因此递增

#### Scenario: same-tick 未恢复不虚报

- **WHEN** same-tick ROI 内未检测到或未接受真实 candidate
- **THEN** 系统 SHALL NOT 声明 recovery success
- **AND** SHALL NOT 将 same-tick guidance 计为恢复
