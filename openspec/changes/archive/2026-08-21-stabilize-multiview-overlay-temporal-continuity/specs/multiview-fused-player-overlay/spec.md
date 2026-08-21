## ADDED Requirements

### Requirement: display_state 作为正式展示契约

fused overlay entity 的 `display_state` SHALL 作为 bundle 的正式展示契约（供 renderer 决定 geometry topology / 时间保持 / 渐进降级），而非仅被序列化但未消费的可选 metadata。`evidence_type` SHALL 继续保持当前 tick 的真实 evidence provenance（raw），MUST NOT 被 display hysteresis 修改或伪造。旧 artifact 缺失 `display_state` 时 SHALL 保持兼容 fallback，MUST NOT 因字段缺失报错。

#### Scenario: display_state 被 renderer 消费

- **WHEN** overlay entity 携带 `display_state`
- **THEN** renderer SHALL 以 `display_state` 作为人物几何形态（BOX / POINT / HIDDEN）的权威
- **AND** SHALL NOT 仅凭 `evidence_type` 决定形态

#### Scenario: evidence_type 不因迟滞修改

- **WHEN** 状态机通过 `hysteresis_grace_ms` / `projected_box_hold_ms` 保持几何形态
- **THEN** 该 tick 的 `evidence_type` SHALL 仍反映真实证据来源（MUST NOT 被保持为之前的 `base_observed` / `guided_observed`）
- **AND** SHALL 诚实降级为实际来源（如 `cross_view_projected` / `predicted_only`）

#### Scenario: 旧产物缺失 display_state 兼容

- **WHEN** 历史 fused overlay entity 缺失 `display_state`
- **THEN** 前端 SHALL 按既有逻辑渲染，不做形态保持或迟滞处理
- **AND** SHALL NOT 因字段缺失报错