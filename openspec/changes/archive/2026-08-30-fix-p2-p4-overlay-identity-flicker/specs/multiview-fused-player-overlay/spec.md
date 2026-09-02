## MODIFIED Requirements

### Requirement: 参考视角跨视角投影几何门控

`cross_view_projected` overlay SHALL 明确绑定当前任务的 `reference_view_id`。除 donor recency、canonical position 和 geometry valid 外，投影还 MUST 通过目标视角连续性、脚点运动、bbox 尺寸变化、bbox 与当前 projected footpoint 的一致性，以及与其他强/可信球员框的碰撞门控。仅因为投影点落在图像边界内，不得判定为可发布的 projected bbox。投影 geometry 的 bbox、footpoint 和 `target_player_slot` SHALL 属于同一个 canonical player，不能出现框停留在旧球员位置而脚点落在另一名球员框内的状态。

#### Scenario: 参考视角强观测优先

- **WHEN** reference view 当前 tick 存在 strong 或 accepted real bbox
- **THEN** overlay SHALL 使用该真实证据
- **AND** donor 投影不得覆盖、替换或改变该球员的真实 bbox

#### Scenario: 投影目标视角固定

- **WHEN** 当前任务的 `reference_view_id` 为 `cam_1` 且 reference view 缺少真实 bbox
- **THEN** 生成的 `cross_view_projected` geometry SHALL 使用 `cam_1` 的投影结果
- **AND** SHALL 携带 `donor_view` 说明证据来源，但不得把 donor image-space bbox 直接作为 cam_1 bbox

#### Scenario: 投影框与可信球员框冲突

- **WHEN** projected bbox 与另一名球员的 strong/accepted bbox 发生超过配置门限的空间重叠，或脚点/速度/尺寸跳变超过连续性门限
- **THEN** 系统 SHALL 禁止发布该 synthetic bbox
- **AND** SHALL 仅在上一份 presentation geometry 同时通过当前脚点一致性和可信框碰撞复核时复用它，否则降级为稳定的 `PROJECTED_POINT` 或 `HIDDEN`
- **AND** SHALL 记录 projection collision、continuity rejection 或 bbox-footpoint inconsistency reason

#### Scenario: 投影框与脚点一致

- **WHEN** `cross_view_projected` 仍需要显示 `PROJECTED_BOX`
- **THEN** bbox 的底边中心 SHALL 在配置的 image-space residual 内接近当前 projected footpoint
- **AND** bbox 不得与另一名可信球员框形成会误导身份的重叠

#### Scenario: synthetic geometry 不污染记忆

- **WHEN** projected bbox 通过 reanchor 或 view scale profile 生成
- **THEN** 该 bbox SHALL NOT 刷新 `TargetViewBBoxMemory` 或 scale profile
- **AND** 下一次投影 SHALL 只能使用合格真实 target-view bbox 建立的记忆

#### Scenario: 证据来源保持诚实

- **WHEN** renderer 为了保持几何稳定而复用上一份 presentation geometry
- **THEN** 当前 tick 的 `evidence_type` SHALL 仍反映当前真实来源
- **AND** SHALL NOT 将 `cross_view_projected` 改写为 `base_observed`

#### Scenario: P2/P4 碰撞窗口不互换标签

- **WHEN** P2 与 P4 的 projected/real geometry 在参考画面中重叠，且 association 未完成受控 reassociation
- **THEN** overlay SHALL 保持 P2/P4 的 canonical `player_id`
- **AND** 冲突 geometry SHALL 降级或隐藏，不得通过改变标签来消除重叠
