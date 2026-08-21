## ADDED Requirements

### Requirement: 毫秒级迟滞参数真正参与状态转移

`OverlayDisplayStateMachine` 的 `hysteresis_grace_ms` / `projected_box_hold_ms` SHALL 真正参与 box → point → hidden 的渐进降级判定，MUST NOT 仅为构造参数而未进入 `step()`。迟滞判定 SHALL 以毫秒（`now_ms`）而非 tick 为单位驱动，跨 `frameStride` 保持稳定。`hysteresis_grace_ms` SHALL 仅在仍存在当前跨视角位置证据（`evidence_type = cross_view_projected`）的降级上生效：真实 bbox 丢失后 `display_state` SHALL 立即降级为 `PROJECTED_BOX`（复用最后可靠 presentation box geometry，MUST NOT 继续输出 `REAL_BOX`），以保持 BOX topology 不塌成 POINT。`hysteresis_grace_ms` MUST NOT 应用于无 projected 位置证据的降级（如 `observed → predicted_only`）。

#### Scenario: 短暂漏检保持框形态

- **WHEN** `REAL_BOX` 状态下的球员在当前 view 漏检，但当前有 donor / global projected evidence，且缺失时长 ≤ `hysteresis_grace_ms`
- **THEN** `display_state` SHALL 立即降级为 `PROJECTED_BOX`（MUST NOT 保持 `REAL_BOX`），复用最后可靠 presentation box geometry
- **AND** `evidence_type` SHALL 立即诚实降级为 `cross_view_projected`（MUST NOT 保持 `base_observed`）

#### Scenario: 无 projected 位置证据直接点

- **WHEN** 真实框状态下的球员下一 tick 无 projected 位置证据，仅剩 prediction（`evidence_type = predicted_only`）
- **THEN** `display_state` SHALL 直接进入 `PREDICTED_POINT`
- **AND** MUST NOT 用 `hysteresis_grace_ms` 或旧 bbox 继续画人体框

#### Scenario: 迟滞跨 frameStride 一致

- **WHEN** 同一球员在 `frameStride=1` 与 `frameStride=3` 下发生相同时长的短暂漏检
- **THEN** 迟滞保持窗口 SHALL 一致（ms 语义），MUST NOT 随 tick 间距漂移

### Requirement: projected_box_hold_ms 的模板瞬失宽限语义

`projected_box_hold_ms` SHALL 表示：在已存在可信 projected/display bbox 之后，bbox template 在短时间内瞬时不可用时的 geometry hold grace，而非 synthetic box 的无限生命周期。template 瞬失时长 ≤ `projected_box_hold_ms` 时 SHALL 短暂保持上一份 presentation box geometry；donor / global evidence 失效时 SHALL 由更高层 hard TTL 强制收敛，MUST NOT 让合成框长期赖在画面。

#### Scenario: template 瞬失保持框

- **WHEN** `PROJECTED_BOX` 状态的球员其 synthetic bbox template 瞬时不可用，但缺失时长 ≤ `projected_box_hold_ms`
- **THEN** renderer SHALL 短暂保持上一份 presentation box geometry（不塌成 POINT）
- **AND** SHALL NOT 发生 BOX → POINT → BOX 的逐 tick 抖动

#### Scenario: hold 用尽降级点

- **WHEN** synthetic bbox template 持续不可用超过 `projected_box_hold_ms`
- **THEN** `display_state` SHALL 降级为 `PROJECTED_POINT`

#### Scenario: hold 从最后有效演示几何计时

- **WHEN** `PROJECTED_BOX` 已持续 hold（如 100ms→300ms 均复用最后有效 presentation bbox），随后 300ms 才 template 瞬失
- **THEN** `projected_box_hold_ms` SHALL 从 `last_valid_box_geometry_ts`（=300ms，最后成功 presentation bbox）起算
- **AND** MUST NOT 从 `last_real_bbox_ts`（更早的真实观测）起算

#### Scenario: hard TTL 收敛不赖屏

- **WHEN** donor / global evidence 已失效（`prediction TTL` 超限或 `identity reset`）
- **THEN** hard stop SHALL 优先于任何 `hysteresis_grace_ms` / `projected_box_hold_ms` hold
- **AND** 人物 SHALL 进入 `HIDDEN`，合成框不得长期留在画面