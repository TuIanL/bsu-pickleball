## MODIFIED Requirements

### Requirement: 关联迟滞

跨视角关联 SHALL 存在 association hysteresis：已建立 `A ↔ X` 关联后，即使下一帧出现略优的候选匹配，系统 SHALL NOT 立即换人；仅当连续多帧产生强证据时才 reassociate。系统 SHALL 通过 `PendingReassociation` 状态跟踪“候选换人”证据。一帧计为强证据 SHALL 同时满足：① challenger geometry 可行；② challenger cost 比 incumbent 好超过 `switch_margin`；③ challenger 指向的 global 连续一致；④ local slot 的 tracklet lineage、side/quadrant 和唯一槽位约束没有冲突。连续达到 `reassociation_frames` 帧强证据才正式切换，否则保持原绑定；challenger 每帧变化、local slot 被其他 global 竞争或证据中断则计数清零；切换 SHALL 在 diagnostics 中记录旧 binding、新 binding、确认窗口和原因。

#### Scenario: 保持既有关联

- **WHEN** 已有 `A ↔ X` 关联且下一帧出现略优候选
- **THEN** 系统 SHALL 保持 `A ↔ X`
- **AND** 系统 SHALL NOT 因单帧略优即切换

#### Scenario: 强证据 reassociate

- **WHEN** 连续多帧产生强证据表明另一匹配更可信，且 local slot lineage、side/quadrant 与唯一槽位均一致
- **THEN** 系统 SHALL 允许 reassociate
- **AND** 系统 SHALL 在 diagnostics 中记录旧 binding、新 binding、确认窗口和身份切换原因

#### Scenario: 微弱优势不累积换人

- **WHEN** challenger 每帧只比 incumbent 好 0.01（低于 `switch_margin`）
- **THEN** 该帧 SHALL NOT 计为强证据
- **AND** 计数 SHALL 不累积，绑定保持不变

#### Scenario: challenger 变化则清零

- **WHEN** 连续帧中 challenger 指向的 global 不一致（每帧不同 challenger）
- **THEN** 强证据计数 SHALL 清零
- **AND** 绑定 SHALL 保持不变

#### Scenario: 交叉跑位不单帧换色

- **WHEN** 网前两名球员交叉跑位，单帧另一 candidate 距离更近
- **THEN** 系统 SHALL NOT 单帧切换
- **AND** 仅当连续 `reassociation_frames` 帧该 candidate 持续为强证据且没有 slot 冲突时才切换

#### Scenario: local slot 标签抖动不触发跨人切换

- **WHEN** 同一 view 的 local `Player_N` 在 track fragment 或短时遮挡后与另一个 global 竞争，且无法建立连续 lineage
- **THEN** 系统 SHALL 保持 incumbent 或将观测标记为 `ambiguous`/`unresolved`
- **AND** SHALL NOT 仅凭当前帧 geometry 将 P2/P4 的 global binding 互换

### Requirement: Local slot 与 global 的全视图双射

`GlobalPlayerAssociator` SHALL 保证同一 tick 内每个 `(view_id, view_player_id, epoch)` 至多绑定一个 global，且每个 global 在同一 view 至多接受一个 local slot。该约束还 SHALL 通过绑定历史检查 local slot 在连续窗口内的 lineage；duplicate、cross-side、slot rebind 未达连续证据或 ambiguity margin 不足的 challenger SHALL NOT 覆盖 incumbent。发生冲突时观测可以进入 unresolved/diagnostics，但不得污染 canonical roster 或正式轨迹。

#### Scenario: P2 尺度投影候选落在 P1 bbox

- **WHEN** P2 projected candidate 的 target bbox memory owner 为 P1 或其 local slot 已绑定另一 global
- **THEN** association SHALL 拒绝该候选或保持为 unresolved display evidence
- **AND** SHALL NOT 将 P2 global 绑定到 P1 local slot

#### Scenario: 同一 local slot 跨 tick 竞争两个 global

- **WHEN** `cam_2 Player_2` 在连续窗口内先匹配 P2、后匹配 P4，但没有满足连续 reassociation、side/quadrant 与几何连续性条件
- **THEN** 系统 SHALL 保留已有 binding 或标记后续观测为 `ambiguous`
- **AND** SHALL 记录 incumbent、challenger、tracklet lineage 和冲突原因

#### Scenario: local slot 受控切换

- **WHEN** 同一 local slot 的 challenger 连续满足 reassociation 帧数、唯一槽位、运动/侧区和 ambiguity gate
- **THEN** 系统 SHALL 先记录并释放旧 binding，再建立新 binding
- **AND** 同一 tick 的其他 global SHALL NOT 获得重复 local slot
