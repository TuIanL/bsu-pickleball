## ADDED Requirements

### Requirement: Candidate recovery does not bypass roster identity confirmation

候选恢复 SHALL 只补充既有 roster global 的观测证据；候选 track SHALL NOT 直接成为 canonical `Player_N` display anchor，也 SHALL NOT 单独确认 `mapping_confirmed`。roster 的生命周期与 canonical display identity SHALL 分开管理；兜底 slot 映射必须继续标记为未确认，直到存在满足既有锚定条件的正式 reference-view identity binding。

#### Scenario: 候选恢复不伪造 Player 锚点
- **WHEN** 一个 candidate track 成功为既有 global 恢复位置观测，但尚无正式 reference-view `Player_N` binding
- **THEN** global SHALL 保留该 recovered evidence
- **AND** canonical `player_id` SHALL 保持未分配或明确 fallback 状态
- **AND** `mapping_confirmed` SHALL 为 false

#### Scenario: 恢复不创建第五个 global
- **WHEN** roster 已占满且有新候选持续出现
- **THEN** 系统 SHALL 仅尝试将其恢复到已有 roster global
- **AND** SHALL NOT 创建 `global_player_5` 或替换 roster occupant

#### Scenario: 正式 reference binding 到达
- **WHEN** 候选恢复后的 global 后续获得稳定正式 reference-view binding
- **THEN** canonical display mapping SHALL 依据该正式 binding 更新
- **AND** mapping confirmation SHALL 保留可审计来源
