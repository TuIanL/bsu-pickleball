## ADDED Requirements

### Requirement: 参考视角关联短时稳定

跨视角关联在参考视角出现短时漏检、`no_association_input`、`ambiguous` 或低于切换门限的候选时，SHALL 保持当前 incumbent binding，不得仅因单帧证据缺失或轻微代价优势改变 canonical player 绑定。只有连续满足几何可行、超过 `switch_margin` 且 challenger identity 不变的强证据，才 SHALL 完成 reassociation。

#### Scenario: 参考视角短时漏检保持 incumbent
- **WHEN** `cam_1` 在连续窗口内暂时没有可接受 association input，但 incumbent binding 仍有 donor/global continuity evidence
- **THEN** 系统 SHALL 保持原有 `(view_id, view_player_id) → global_player_id` binding
- **AND** SHALL 将该窗口记录为 continuity-preserved 或 pending，而不是创建新的 global identity

#### Scenario: 歧义候选不得单帧换人
- **WHEN** 当前候选与次优候选的代价差低于 `switch_margin`，或 pair 被标记为 `ambiguous`
- **THEN** 系统 SHALL 不得切换 incumbent
- **AND** diagnostics SHALL 记录 `ambiguous`/`switch_margin_not_met` 原因

#### Scenario: 强证据连续确认后才重关联
- **WHEN** 同一 challenger 连续达到配置的 reassociation 帧数，且每帧均满足几何门、代价 margin 和时间连续性
- **THEN** 系统 SHALL 才允许完成 reassociation
- **AND** SHALL 记录旧 binding、新 binding、确认窗口和切换原因

#### Scenario: 交叉跑位不造成 P2/P4 身份闪换
- **WHEN** P2 与 P4 在参考画面中接近、交叉或出现局部框重叠，但没有满足连续强 reassociation 证据
- **THEN** 系统 SHALL 保持各自 canonical identity
- **AND** overlay 不得因单帧空间距离更近而交换 P2/P4 标签
